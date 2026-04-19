<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$archiveFile = basename(trim((string)post_value('archiveFile', '')));
if ($archiveFile === '') {
    json_response(['message' => 'An archive file is required.'], 400);
}

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'Cancel the active loop before replaying an archived session.'], 409);
}

$archivePath = SESSIONS_PATH . DIRECTORY_SEPARATOR . $archiveFile;
$archive = read_json_file_safe($archivePath);
if (!is_array($archive)) {
    json_response(['message' => 'Archive not found.'], 404);
}

$archivedState = normalize_state(is_array($archive['state'] ?? null) ? $archive['state'] : []);
$restoredState = mutate_state(function (array $state) use ($archivedState): array {
    $next = normalize_state($archivedState);
    $next['loop'] = default_loop_state();
    $next['loop']['lastMessage'] = 'Replayed archived session into the workspace.';
    $next['lastUpdated'] = gmdate('c');
    return $next;
});

if (is_array($restoredState['activeTask'] ?? null)) {
    write_task_snapshot($restoredState['activeTask']);
}

append_event('session_replayed', [
    'archiveFile' => $archiveFile,
    'taskId' => $restoredState['activeTask']['taskId'] ?? null,
]);
append_step('session', 'Replayed an archived session into the workspace.', [
    'archiveFile' => $archiveFile,
    'taskId' => $restoredState['activeTask']['taskId'] ?? null,
]);

json_response([
    'message' => 'Archived session replayed.',
    'archiveFile' => $archiveFile,
    'state' => $restoredState,
]);
