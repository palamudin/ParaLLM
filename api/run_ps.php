<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$target = trim((string)post_value('target', ''));
$state = recover_loop_state_if_needed();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is running. Cancel it before manual dispatch.'], 409);
}
if (!is_valid_target($target, $state['activeTask'])) {
    json_response(['message' => 'Invalid target.'], 400);
}

$preflight = target_dispatch_preflight($target, $state);
if ($preflight !== null) {
    append_step('dispatch', 'PowerShell target blocked by preflight check.', [
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
    append_step('dispatch', 'Dispatching PowerShell target.', ['target' => $target]);
    $result = run_powershell_target($target, $state['activeTask']);
    append_step('dispatch', 'PowerShell target completed.', [
        'target' => $target,
        'outputPreview' => $result['output'],
        'exitCode' => $result['exitCode']
    ]);
    json_response([
        'message' => 'Executed ' . $target,
        'target' => $target,
        'output' => $result['output']
    ]);
} catch (Throwable $ex) {
    append_step('error', 'PowerShell target failed.', [
        'target' => $target,
        'error' => $ex->getMessage()
    ]);
    $code = stripos($ex->getMessage(), 'Budget limit reached:') === 0 ? 409 : 500;
    json_response(['message' => $ex->getMessage()], $code);
}
