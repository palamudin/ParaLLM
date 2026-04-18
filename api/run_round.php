<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}

$sequence = [
    'A' => 'workerA.ps1',
    'B' => 'workerB.ps1',
    'summarizer' => 'summarizer.ps1'
];
$results = [];

try {
    append_step('round', 'Starting full round execution.', [
        'taskId' => $state['activeTask']['taskId'] ?? null
    ]);

    foreach ($sequence as $target => $script) {
        $output = shell_exec(ps_command($script));
        $trimmed = trim((string)$output);
        $results[] = [
            'target' => $target,
            'output' => $trimmed
        ];
        append_event('powershell_run', ['target' => $target, 'output' => $trimmed]);
        append_step('round', 'Round target completed.', [
            'target' => $target,
            'outputPreview' => $trimmed
        ]);
    }

    append_step('round', 'Full round execution finished.', [
        'targets' => array_keys($sequence)
    ]);

    json_response([
        'message' => 'Round executed.',
        'results' => $results
    ]);
} catch (Throwable $ex) {
    append_step('error', 'Round execution failed.', ['error' => $ex->getMessage()]);
    json_response(['message' => $ex->getMessage()], 500);
}
