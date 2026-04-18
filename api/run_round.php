<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_running($state)) {
    json_response(['message' => 'The autonomous loop is already running.'], 409);
}

$sequence = ['A', 'B', 'summarizer'];
$results = [];

try {
    append_step('round', 'Starting full round execution.', [
        'taskId' => $state['activeTask']['taskId'] ?? null
    ]);

    foreach ($sequence as $target) {
        $result = run_powershell_target($target);
        $results[] = $result;
        append_step('round', 'Round target completed.', [
            'target' => $target,
            'outputPreview' => $result['output'],
            'exitCode' => $result['exitCode']
        ]);
    }

    append_step('round', 'Full round execution finished.', [
        'targets' => $sequence
    ]);

    json_response([
        'message' => 'Round executed.',
        'results' => $results
    ]);
} catch (Throwable $ex) {
    append_step('error', 'Round execution failed.', ['error' => $ex->getMessage()]);
    json_response(['message' => $ex->getMessage()], 500);
}
