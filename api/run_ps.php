<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$target = trim((string)post_value('target', ''));
$map = target_map();

if (!isset($map[$target])) {
    json_response(['message' => 'Invalid target.'], 400);
}

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is running. Cancel it before manual dispatch.'], 409);
}

try {
    append_step('dispatch', 'Dispatching PowerShell target.', ['target' => $target]);
    $result = run_powershell_target($target);
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
    json_response(['message' => $ex->getMessage()], 500);
}
