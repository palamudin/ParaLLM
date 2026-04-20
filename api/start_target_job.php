<?php
require __DIR__ . '/common.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();

$target = trim((string)post_value('target', ''));
$state = recover_loop_state_if_needed();
recover_dispatch_jobs_if_needed();
$state = read_state();

if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is running. Cancel it before background target dispatch.'], 409);
}
if (!in_array($target, available_targets($state['activeTask']), true)) {
    json_response(['message' => 'Invalid target.'], 400);
}

$task = $state['activeTask'];
$taskId = (string)($task['taskId'] ?? '');
$dispatchActive = with_lock(function () use ($taskId): int {
    return active_target_job_count_unlocked($taskId, false);
});

if ($target !== 'answer_now' && $dispatchActive > 0) {
    json_response(['message' => 'Another background target dispatch is already active. Wait for it to finish or use Answer Now from current checkpoints.'], 409);
}

if ($target !== 'answer_now') {
    $preflight = target_dispatch_preflight($target, $state);
    if ($preflight !== null) {
        append_step('dispatch', 'Background target blocked by preflight check.', [
            'target' => $target,
            'message' => $preflight['message'],
            'missingWorkers' => $preflight['missingWorkers'] ?? []
        ]);
        json_response([
            'message' => $preflight['message'],
            'missingWorkers' => $preflight['missingWorkers'] ?? []
        ], (int)($preflight['code'] ?? 409));
    }
}

if ($target === 'answer_now' && commander_round_from_state($state) <= 0) {
    json_response(['message' => 'Answer Now needs a commander draft first.'], 409);
}

$job = create_target_job($task, $target, [
    'partialSummary' => $target === 'answer_now',
    'timeoutSeconds' => 1800,
    'lastMessage' => $target === 'answer_now' ? 'Queued partial summary from current checkpoints.' : 'Queued target dispatch.',
    'metadata' => ['trigger' => $target === 'answer_now' ? 'answer-now' : 'manual'],
]);

try {
    launch_dispatch_job_runner($job);
    json_response([
        'message' => $target === 'answer_now' ? 'Partial answer queued.' : ('Background dispatch queued for ' . $target . '.'),
        'jobId' => $job['jobId'],
        'target' => $target,
        'partialSummary' => $target === 'answer_now',
    ]);
} catch (Throwable $ex) {
    mutate_job($job['jobId'], function (?array $existing) use ($ex): array {
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
