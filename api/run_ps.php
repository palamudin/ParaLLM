<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$target = trim((string)post_value('target', ''));
$map = [
    'A' => 'workerA.ps1',
    'B' => 'workerB.ps1',
    'summarizer' => 'summarizer.ps1'
];

if (!isset($map[$target])) {
    json_response(['message' => 'Invalid target.'], 400);
}

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}

try {
    $cmd = ps_command($map[$target]);
    append_step('dispatch', 'Dispatching PowerShell target.', ['target' => $target]);
    $output = shell_exec($cmd);
    append_event('powershell_run', ['target' => $target, 'output' => trim((string)$output)]);
    append_step('dispatch', 'PowerShell target completed.', [
        'target' => $target,
        'outputPreview' => trim((string)$output)
    ]);
    json_response([
        'message' => 'Executed ' . $target,
        'target' => $target,
        'output' => trim((string)$output)
    ]);
} catch (Throwable $ex) {
    append_step('error', 'PowerShell target failed.', [
        'target' => $target,
        'error' => $ex->getMessage()
    ]);
    json_response(['message' => $ex->getMessage()], 500);
}
