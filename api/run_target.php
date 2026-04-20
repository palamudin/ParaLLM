<?php
require __DIR__ . '/common.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();
allow_long_running_request();

$target = trim((string)post_value('target', ''));
$state = recover_loop_state_if_needed();
recover_dispatch_jobs_if_needed();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is running. Cancel it before manual dispatch.'], 409);
}
if (with_lock(function () use ($state): int {
    return active_target_job_count_unlocked((string)($state['activeTask']['taskId'] ?? ''), true);
}) > 0) {
    json_response(['message' => 'A background target dispatch is already running. Wait for it to finish or use the queued answer path.'], 409);
}
if (!is_valid_target($target, $state['activeTask'])) {
    json_response(['message' => 'Invalid target.'], 400);
}

$preflight = target_dispatch_preflight($target, $state);
if ($preflight !== null) {
    append_step('dispatch', 'Manual runtime target blocked by preflight check.', [
        'target' => $target,
        'message' => $preflight['message'],
        'missingWorkers' => $preflight['missingWorkers'] ?? []
    ]);
    json_response([
        'message' => $preflight['message'],
        'missingWorkers' => $preflight['missingWorkers'] ?? []
    ], (int)($preflight['code'] ?? 409));
}

try {
    append_step('dispatch', 'Dispatching runtime target.', ['target' => $target]);
    $result = run_dispatch_target($target, $state['activeTask']);
    append_step('dispatch', 'Runtime target completed.', [
        'target' => $target,
        'outputPreview' => $result['output'],
        'exitCode' => $result['exitCode'],
        'backend' => $result['backend'] ?? 'python'
    ]);
    json_response([
        'message' => 'Executed ' . $target,
        'target' => $target,
        'output' => $result['output'],
        'backend' => $result['backend'] ?? 'python'
    ]);
} catch (Throwable $ex) {
    append_step('error', 'Runtime target failed.', [
        'target' => $target,
        'error' => $ex->getMessage()
    ]);
    $code = ($ex->getCode() >= 400 && $ex->getCode() < 600)
        ? (int)$ex->getCode()
        : (stripos($ex->getMessage(), 'Budget limit reached:') === 0 ? 409 : 500);
    json_response(['message' => $ex->getMessage()], $code);
}
