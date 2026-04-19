<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'An autonomous loop is running. Cancel it before resetting the session.'], 409);
}

$previousTask = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
$previousTaskId = $previousTask['taskId'] ?? null;
$archiveFile = null;
$carryContext = '';
$hadSession = $previousTask !== null || !empty($state['summary']) || !empty($state['workers']);

$state = mutate_state(function (array $state) use (&$archiveFile, &$carryContext, $previousTask, $hadSession): array {
    $carryContext = $hadSession ? build_session_context_summary($state) : '';

    if ($hadSession) {
        $archive = [
            'archivedAt' => gmdate('c'),
            'reason' => 'reset_session',
            'taskId' => is_array($previousTask) ? ($previousTask['taskId'] ?? null) : null,
            'carryContext' => $carryContext,
            'state' => normalize_state($state)
        ];
        $archiveFile = write_session_archive_unlocked($archive);
    }

    $next = default_state();
    $next['draft'] = $previousTask
        ? build_draft_from_task($previousTask, [
            'objective' => '',
            'constraints' => [],
            'sessionContext' => $carryContext,
            'updatedAt' => gmdate('c')
        ], true)
        : build_draft_from_task(null, [
            'sessionContext' => $carryContext,
            'updatedAt' => gmdate('c')
        ]);

    return $next;
});

append_event('session_reset', [
    'fromTaskId' => $previousTaskId,
    'archiveFile' => $archiveFile,
    'hasCarryContext' => $carryContext !== ''
]);

append_step('session', $hadSession ? 'Archived the current session and loaded a carry-forward draft.' : 'Loaded a fresh draft with no prior session to archive.', [
    'fromTaskId' => $previousTaskId,
    'archiveFile' => $archiveFile,
    'hasCarryContext' => $carryContext !== ''
]);

json_response([
    'message' => $hadSession ? 'Session reset and carry-forward draft loaded.' : 'Fresh draft loaded.',
    'archiveFile' => $archiveFile,
    'carryContext' => $carryContext,
    'draft' => $state['draft']
]);
