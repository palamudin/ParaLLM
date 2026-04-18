<?php
require __DIR__ . '/common.php';
ensure_data_paths();
$state = try_recover_loop_state_if_needed();
$recoveryWarning = null;
if (strpos((string)($state['loop']['lastMessage'] ?? ''), 'Recovery check deferred:') !== false) {
    $recoveryWarning = $state['loop']['lastMessage'];
}

$maxJobs = 10;
$maxArtifacts = 20;

$readJsonFile = static function (string $path): ?array {
    if (!file_exists($path)) {
        return null;
    }
    $raw = @file_get_contents($path);
    if ($raw === false || trim($raw) === '') {
        return null;
    }
    if (strncmp($raw, "\xEF\xBB\xBF", 3) === 0) {
        $raw = substr($raw, 3);
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
};

$jobFiles = glob(JOBS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: [];
usort($jobFiles, static function (string $a, string $b): int {
    return filemtime($b) <=> filemtime($a);
});

$jobs = [];
foreach (array_slice($jobFiles, 0, $maxJobs) as $jobFile) {
    $job = $readJsonFile($jobFile);
    if (!$job) {
        continue;
    }
    $task = null;
    if (!empty($job['taskId'])) {
        $task = $readJsonFile(task_file_path((string)$job['taskId']));
    }
    $jobs[] = [
        'jobId' => $job['jobId'] ?? null,
        'taskId' => $job['taskId'] ?? null,
        'objective' => $task['objective'] ?? null,
        'status' => $job['status'] ?? null,
        'mode' => $job['mode'] ?? null,
        'rounds' => isset($job['rounds']) ? (int)$job['rounds'] : 0,
        'completedRounds' => isset($job['completedRounds']) ? (int)$job['completedRounds'] : 0,
        'queuedAt' => $job['queuedAt'] ?? null,
        'startedAt' => $job['startedAt'] ?? null,
        'finishedAt' => $job['finishedAt'] ?? null,
        'lastHeartbeatAt' => $job['lastHeartbeatAt'] ?? null,
        'lastMessage' => $job['lastMessage'] ?? null,
        'error' => $job['error'] ?? null,
    ];
}

$artifactFiles = glob(CHECKPOINTS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: [];
usort($artifactFiles, static function (string $a, string $b): int {
    return filemtime($b) <=> filemtime($a);
});

$artifacts = [];
foreach ($artifactFiles as $artifactFile) {
    $name = basename($artifactFile);
    if (strpos($name, '_step') === false && strpos($name, '_round') === false) {
        continue;
    }

    $entry = [
        'name' => $name,
        'modifiedAt' => gmdate('c', filemtime($artifactFile)),
        'size' => filesize($artifactFile),
        'kind' => 'artifact',
        'taskId' => null,
        'worker' => null,
        'roundOrStep' => null,
    ];

    if (preg_match('/^(t-\d{8}-\d{6}-[a-f0-9]+)_([AB])_step(\d+)\.json$/i', $name, $matches)) {
        $entry['taskId'] = $matches[1];
        $entry['worker'] = $matches[2];
        $entry['kind'] = 'worker_step';
        $entry['roundOrStep'] = (int)$matches[3];
    } elseif (preg_match('/^(t-\d{8}-\d{6}-[a-f0-9]+)_summary_round(\d+)\.json$/i', $name, $matches)) {
        $entry['taskId'] = $matches[1];
        $entry['worker'] = 'summary';
        $entry['kind'] = 'summary_round';
        $entry['roundOrStep'] = (int)$matches[2];
    }

    $artifacts[] = $entry;
    if (count($artifacts) >= $maxArtifacts) {
        break;
    }
}

json_response([
    'jobs' => $jobs,
    'artifacts' => $artifacts,
    'recoveryWarning' => $recoveryWarning
]);
