<?php
require __DIR__ . '/common.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();

recover_dispatch_jobs_if_needed();
$state = try_recover_loop_state_if_needed();
$recoveryWarning = null;
if (strpos((string)($state['loop']['lastMessage'] ?? ''), 'Recovery check deferred:') !== false) {
    $recoveryWarning = $state['loop']['lastMessage'];
}

$maxJobs = 12;
$maxArtifacts = 30;
$maxRounds = 12;
$maxSessions = 10;

$taskCache = [];
$loadTask = static function (?string $taskId) use (&$taskCache): ?array {
    if (!is_string($taskId) || trim($taskId) === '') {
        return null;
    }
    if (!array_key_exists($taskId, $taskCache)) {
        $taskCache[$taskId] = read_task_snapshot($taskId);
    }
    return $taskCache[$taskId];
};

$jobFiles = list_job_files_unlocked();
usort($jobFiles, static function (string $a, string $b): int {
    return (filemtime($b) ?: 0) <=> (filemtime($a) ?: 0);
});

$jobs = [];
foreach (array_slice($jobFiles, 0, $maxJobs) as $jobFile) {
    $job = read_json_file_safe($jobFile);
    if (!is_array($job)) {
        continue;
    }
    $job = default_job($job);
    $task = $loadTask((string)($job['taskId'] ?? ''));
    $isTargetJob = (string)($job['jobType'] ?? 'loop') === 'target';
    $jobs[] = [
        'jobId' => $job['jobId'] ?? null,
        'taskId' => $job['taskId'] ?? null,
        'jobType' => $job['jobType'] ?? 'loop',
        'target' => $job['target'] ?? null,
        'batchId' => $job['batchId'] ?? null,
        'partialSummary' => !empty($job['partialSummary']),
        'objective' => $task['objective'] ?? null,
        'status' => $job['status'] ?? null,
        'mode' => $job['mode'] ?? null,
        'workerCount' => isset($job['workerCount']) ? (int)$job['workerCount'] : 0,
        'rounds' => isset($job['rounds']) ? (int)$job['rounds'] : 0,
        'completedRounds' => isset($job['completedRounds']) ? (int)$job['completedRounds'] : 0,
        'resumeFromRound' => isset($job['resumeFromRound']) ? (int)$job['resumeFromRound'] : 1,
        'queuePosition' => isset($job['queuePosition']) ? (int)$job['queuePosition'] : 0,
        'attempt' => isset($job['attempt']) ? (int)$job['attempt'] : 1,
        'resumeOfJobId' => $job['resumeOfJobId'] ?? null,
        'retryOfJobId' => $job['retryOfJobId'] ?? null,
        'queuedAt' => $job['queuedAt'] ?? null,
        'startedAt' => $job['startedAt'] ?? null,
        'finishedAt' => $job['finishedAt'] ?? null,
        'lastHeartbeatAt' => $job['lastHeartbeatAt'] ?? null,
        'lastMessage' => $job['lastMessage'] ?? null,
        'totalTokens' => isset($job['usage']['totalTokens']) ? (int)$job['usage']['totalTokens'] : 0,
        'estimatedCostUsd' => isset($job['usage']['estimatedCostUsd']) ? (float)$job['usage']['estimatedCostUsd'] : 0.0,
        'error' => $job['error'] ?? null,
        'canResume' => !$isTargetJob && job_status_can_resume($job['status'] ?? null),
        'canRetry' => !$isTargetJob && job_status_can_retry($job['status'] ?? null),
        'canCancel' => !$isTargetJob && in_array((string)($job['status'] ?? ''), ['queued', 'interrupted'], true),
    ];
}

$artifactFiles = array_merge(
    glob(CHECKPOINTS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: [],
    glob(OUTPUTS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: []
);
usort($artifactFiles, static function (string $a, string $b): int {
    return (filemtime($b) ?: 0) <=> (filemtime($a) ?: 0);
});

$artifacts = [];
$roundGroups = [];
foreach ($artifactFiles as $artifactFile) {
    $entry = build_artifact_history_entry($artifactFile);
    if ($entry === null) {
        continue;
    }

    $artifactOut = $entry;
    unset($artifactOut['path']);
    $artifacts[] = $artifactOut;

    if (
        isset($entry['taskId'], $entry['roundOrStep'])
        && in_array((string)$entry['kind'], ['worker_output', 'commander_output', 'commander_review_output', 'summary_output', 'summary_partial_output'], true)
    ) {
        $roundKey = (string)$entry['taskId'] . ':' . (int)$entry['roundOrStep'];
        if (!isset($roundGroups[$roundKey])) {
            $task = $loadTask((string)$entry['taskId']);
            $roundGroups[$roundKey] = [
                'taskId' => $entry['taskId'],
                'objective' => $task['objective'] ?? null,
                'round' => (int)$entry['roundOrStep'],
                'capturedAt' => $entry['modifiedAt'],
                'commanderArtifact' => null,
                'commanderReviewArtifact' => null,
                'summaryArtifact' => null,
                'workerArtifacts' => [],
            ];
        }
        if (($entry['kind'] ?? null) === 'commander_output') {
            $roundGroups[$roundKey]['commanderArtifact'] = $artifactOut;
        } elseif (($entry['kind'] ?? null) === 'commander_review_output') {
            $roundGroups[$roundKey]['commanderReviewArtifact'] = $artifactOut;
        } elseif (in_array((string)($entry['kind'] ?? null), ['summary_output', 'summary_partial_output'], true)) {
            $roundGroups[$roundKey]['summaryArtifact'] = $artifactOut;
        } else {
            $roundGroups[$roundKey]['workerArtifacts'][] = $artifactOut;
        }
        if (strtotime((string)$entry['modifiedAt']) > strtotime((string)$roundGroups[$roundKey]['capturedAt'])) {
            $roundGroups[$roundKey]['capturedAt'] = $entry['modifiedAt'];
        }
    }

    if (count($artifacts) >= $maxArtifacts) {
        break;
    }
}

$rounds = array_values($roundGroups);
usort($rounds, static function (array $a, array $b): int {
    $timeCompare = strtotime((string)($b['capturedAt'] ?? '')) <=> strtotime((string)($a['capturedAt'] ?? ''));
    if ($timeCompare !== 0) {
        return $timeCompare;
    }
    return ((int)($b['round'] ?? 0)) <=> ((int)($a['round'] ?? 0));
});
$rounds = array_slice($rounds, 0, $maxRounds);

foreach ($rounds as &$roundEntry) {
    usort($roundEntry['workerArtifacts'], static function (array $a, array $b): int {
        return strcmp((string)($a['worker'] ?? ''), (string)($b['worker'] ?? ''));
    });
}
unset($roundEntry);

json_response([
    'jobs' => $jobs,
    'dispatch' => current_dispatch_state($state),
    'artifacts' => $artifacts,
    'rounds' => $rounds,
    'sessions' => list_session_archives($maxSessions),
    'artifactPolicy' => artifact_visibility_policy(),
    'queueLimit' => LOOP_QUEUE_LIMIT,
    'recoveryWarning' => $recoveryWarning,
]);
