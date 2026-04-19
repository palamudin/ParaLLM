<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$archiveFile = basename(trim((string)($_GET['archiveFile'] ?? $_POST['archiveFile'] ?? '')));
$source = $archiveFile !== '' ? 'archive' : 'current';

$bundle = [
    'exportedAt' => gmdate('c'),
    'source' => $source,
    'artifactPolicy' => artifact_visibility_policy(),
];

if ($archiveFile !== '') {
    $path = SESSIONS_PATH . DIRECTORY_SEPARATOR . $archiveFile;
    $archive = read_json_file_safe($path);
    if (!is_array($archive)) {
        json_response(['message' => 'Archive not found.'], 404);
    }
    $bundle['archiveFile'] = $archiveFile;
    $bundle['archive'] = $archive;
    $taskId = is_string($archive['taskId'] ?? null) ? $archive['taskId'] : null;
} else {
    $state = try_recover_loop_state_if_needed();
    $bundle['state'] = normalize_state($state);
    $taskId = is_string($state['activeTask']['taskId'] ?? null) ? $state['activeTask']['taskId'] : null;
}

$jobs = [];
foreach (list_job_files_unlocked() as $jobFile) {
    $job = read_json_file_safe($jobFile);
    if (!is_array($job)) {
        continue;
    }
    if ($taskId !== null && (string)($job['taskId'] ?? '') !== $taskId) {
        continue;
    }
    $jobs[] = default_job($job);
}
$bundle['jobs'] = $jobs;

$artifacts = [];
foreach (array_merge(
    glob(CHECKPOINTS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: [],
    glob(OUTPUTS_PATH . DIRECTORY_SEPARATOR . '*.json') ?: []
) as $artifactFile) {
    $entry = build_artifact_history_entry($artifactFile);
    if ($entry === null) {
        continue;
    }
    if ($taskId !== null && (string)($entry['taskId'] ?? '') !== $taskId) {
        continue;
    }
    $content = read_json_file_safe($artifactFile);
    if (!is_array($content)) {
        continue;
    }
    $artifacts[] = [
        'meta' => array_diff_key($entry, ['path' => true]),
        'content' => $content,
    ];
}
$bundle['artifacts'] = $artifacts;

json_response($bundle);
