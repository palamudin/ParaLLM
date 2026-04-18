<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$objective = trim((string)post_value('objective', ''));
if ($objective === '') {
    json_response(['message' => 'Objective is required.'], 400);
}

$constraintsRaw = post_value('constraints', '[]');
$constraints = json_decode((string)$constraintsRaw, true);
if (!is_array($constraints)) $constraints = [];

$executionMode = trim((string)post_value('executionMode', 'live'));
if (!in_array($executionMode, ['live', 'mock'], true)) {
    $executionMode = 'live';
}

$model = trim((string)post_value('model', 'gpt-5-mini'));
if ($model === '') {
    $model = 'gpt-5-mini';
}

$reasoningEffort = trim((string)post_value('reasoningEffort', 'low'));
if (!in_array($reasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $reasoningEffort = 'low';
}

$taskId = 't-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
$task = [
    'taskId' => $taskId,
    'objective' => $objective,
    'constraints' => array_values($constraints),
    'createdAt' => gmdate('c'),
    'runtime' => [
        'executionMode' => $executionMode,
        'model' => $model,
        'reasoningEffort' => $reasoningEffort
    ],
    'syncPolicy' => [
        'mode' => 'checkpoint',
        'shareOnBlocker' => true,
        'shareEverySteps' => 3
    ],
    'workers' => [
        ['id' => 'A', 'role' => 'utility'],
        ['id' => 'B', 'role' => 'risk']
    ]
];

$state = read_state();
$state['activeTask'] = $task;
$state['workers'] = ['A' => null, 'B' => null];
$state['summary'] = null;
$state['memoryVersion'] = ($state['memoryVersion'] ?? 0) + 1;
write_state($state);

$taskFile = DATA_PATH . DIRECTORY_SEPARATOR . 'tasks' . DIRECTORY_SEPARATOR . $taskId . '.json';
file_put_contents($taskFile, json_encode($task, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
append_event('task_started', ['taskId' => $taskId, 'objective' => $objective]);
append_step('task', 'Created a new task and reset worker memory.', [
    'taskId' => $taskId,
    'constraintCount' => count($constraints),
    'runtime' => $task['runtime'],
    'syncPolicy' => $task['syncPolicy']
]);

json_response(['message' => 'Task created.', 'taskId' => $taskId]);
