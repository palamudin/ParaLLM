<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$jobId = trim((string)post_value('jobId', ''));
$action = strtolower(trim((string)post_value('action', '')));

if ($jobId === '') {
    json_response(['message' => 'A jobId is required.'], 400);
}
if (!in_array($action, ['resume', 'retry', 'cancel'], true)) {
    json_response(['message' => 'A valid action is required.'], 400);
}

$state = recover_loop_state_if_needed();
$job = read_job($jobId);
if ($job === null) {
    json_response(['message' => 'Job not found.'], 404);
}

$taskId = (string)($job['taskId'] ?? '');
if ($taskId === '') {
    json_response(['message' => 'Job is missing task metadata.'], 409);
}

if ($action === 'cancel') {
    if (($job['status'] ?? null) === 'queued' && ($state['loop']['jobId'] ?? null) === $jobId) {
        $cancelledQueuedJobs = cancel_queued_background_jobs($taskId, $jobId, 'Cancelled before the queued loop could start.');
        mutate_state(function (array $state): array {
            return set_loop_state($state, [
                'status' => 'cancelled',
                'cancelRequested' => true,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Cancelled before the background loop started.'
            ]);
        });
        mutate_job($jobId, function (?array $existing): array {
            return default_job(array_merge($existing ?? [], [
                'status' => 'cancelled',
                'cancelRequested' => true,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Cancelled before start.'
            ]));
        });
        append_step('autoloop', 'Queued background loop cancelled from Review before start.', [
            'taskId' => $taskId,
            'jobId' => $jobId,
            'queuedJobsCancelled' => $cancelledQueuedJobs,
        ]);
        json_response([
            'message' => 'Queued loop cancelled before start.',
            'queuedJobsCancelled' => $cancelledQueuedJobs,
        ]);
    }
    if (!in_array((string)($job['status'] ?? ''), ['queued', 'interrupted'], true)) {
        json_response(['message' => 'Only queued or interrupted jobs can be cancelled here.'], 409);
    }

    $updatedJob = mutate_job($jobId, function (?array $existing): array {
        return default_job(array_merge($existing ?? [], [
            'status' => 'cancelled',
            'cancelRequested' => true,
            'finishedAt' => gmdate('c'),
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Cancelled from Review.',
        ]));
    });

    append_step('autoloop', 'Cancelled a queued or interrupted background job from Review.', [
        'taskId' => $taskId,
        'jobId' => $jobId,
        'previousStatus' => $job['status'] ?? null,
    ]);

    json_response([
        'message' => 'Job cancelled.',
        'job' => $updatedJob,
    ]);
}

if (loop_is_active($state)) {
    json_response(['message' => 'Cancel or finish the active loop before resuming or retrying another job.'], 409);
}

if ($action === 'resume' && !job_status_can_resume($job['status'] ?? null)) {
    json_response(['message' => 'Only interrupted jobs can be resumed.'], 409);
}
if ($action === 'retry' && !job_status_can_retry($job['status'] ?? null)) {
    json_response(['message' => 'This job cannot be retried.'], 409);
}

$resumeFromRound = 1;
$seedResults = [];
$seedCompletedRounds = 0;
$resumeSourceJobId = null;
$retrySourceJobId = null;

if ($action === 'resume') {
    $resumeFromRound = job_resume_round($job);
    if ($resumeFromRound > (int)($job['rounds'] ?? 0)) {
        json_response(['message' => 'This interrupted job has no remaining rounds to resume. Retry it instead.'], 409);
    }

    $seedCompletedRounds = max(0, (int)($job['completedRounds'] ?? 0));
    $seedResults = is_array($job['results'] ?? null) ? $job['results'] : [];
    $resumeSourceJobId = $jobId;

    if ($seedCompletedRounds > 0 && (($state['activeTask']['taskId'] ?? null) !== $taskId)) {
        json_response(['message' => 'Resume needs the interrupted task still loaded in state. Replay that session first or use Retry to restart from round 1.'], 409);
    }
}

$taskSnapshot = read_task_snapshot($taskId);
if ($taskSnapshot === null) {
    json_response(['message' => 'Task snapshot is missing, so this job cannot be restored.'], 404);
}

$activeTaskId = $state['activeTask']['taskId'] ?? null;
$shouldRestoreSnapshot = $action === 'retry' || $seedCompletedRounds === 0 || $activeTaskId !== $taskId;
if ($shouldRestoreSnapshot) {
    mutate_state(function (array $state) use ($taskSnapshot): array {
        $state['activeTask'] = $taskSnapshot;
        $state['draft'] = build_draft_from_task($taskSnapshot);
        $state['commander'] = null;
        $state['workers'] = empty_worker_state_map(task_workers($taskSnapshot));
        $state['summary'] = null;
        $state['memoryVersion'] = (int)($state['memoryVersion'] ?? 0) + 1;
        $state['usage'] = default_usage_state();
        $state['loop'] = default_loop_state();
        return $state;
    });
    $seedCompletedRounds = 0;
    $seedResults = [];
    $resumeFromRound = 1;
    if ($action === 'resume') {
        $retrySourceJobId = $jobId;
        $resumeSourceJobId = null;
    } else {
        $retrySourceJobId = $jobId;
    }
} else {
    mutate_state(function (array $state): array {
        $state['loop'] = default_loop_state();
        return $state;
    });
}

$newJob = create_loop_job($taskSnapshot, clamp_loop_rounds($job['rounds'] ?? 1), clamp_loop_delay_ms($job['delayMs'] ?? 0), 'background', [
    'attempt' => max(1, (int)($job['attempt'] ?? 1)) + 1,
    'resumeOfJobId' => $resumeSourceJobId,
    'retryOfJobId' => $retrySourceJobId,
    'resumeFromRound' => $resumeFromRound,
    'results' => $seedResults,
    'completedRounds' => $seedCompletedRounds,
    'lastMessage' => $action === 'resume' ? 'Queued resumed background loop.' : 'Queued retried background loop.',
]);

try {
    launch_loop_job_runner($newJob, false);
} catch (Throwable $ex) {
    mutate_state(function (array $state): array {
        $state['loop'] = default_loop_state();
        $state['loop']['lastMessage'] = 'Background launch failed.';
        return $state;
    });

    mutate_job($newJob['jobId'], function (?array $existing) use ($ex): array {
        return default_job(array_merge($existing ?? [], [
            'status' => 'error',
            'finishedAt' => gmdate('c'),
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Background launch failed.',
            'error' => $ex->getMessage(),
        ]));
    });

    json_response(['message' => $ex->getMessage()], 500);
}

append_step('autoloop', $action === 'resume' ? 'Queued a resumed background loop.' : 'Queued a retried background loop.', [
    'taskId' => $taskId,
    'sourceJobId' => $jobId,
    'jobId' => $newJob['jobId'],
    'resumeFromRound' => $resumeFromRound,
]);

json_response([
    'message' => $action === 'resume' ? 'Interrupted loop resumed.' : 'Loop queued for retry.',
    'jobId' => $newJob['jobId'],
    'resumeFromRound' => $resumeFromRound,
]);
