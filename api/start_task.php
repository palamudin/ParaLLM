<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'An autonomous loop is active. Cancel it before starting a new task.'], 409);
}

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

$model = normalize_model_id((string)post_value('model', default_model_id()), default_model_id());
$summarizerModel = normalize_model_id((string)post_value('summarizerModel', $model), $model);

$reasoningEffort = trim((string)post_value('reasoningEffort', 'low'));
if (!in_array($reasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $reasoningEffort = 'low';
}

$budget = normalize_budget_config([
    'maxTotalTokens' => post_int_value('maxTotalTokens', default_budget_config()['maxTotalTokens']),
    'maxCostUsd' => post_float_value('maxCostUsd', default_budget_config()['maxCostUsd']),
    'maxOutputTokens' => post_int_value('maxOutputTokens', default_budget_config()['maxOutputTokens']),
]);

$workers = task_workers([
    'runtime' => ['model' => $model]
]);

$taskId = 't-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
$task = [
    'taskId' => $taskId,
    'objective' => $objective,
    'constraints' => array_values($constraints),
    'createdAt' => gmdate('c'),
    'runtime' => [
        'executionMode' => $executionMode,
        'model' => $model,
        'reasoningEffort' => $reasoningEffort,
        'budget' => $budget,
        'pricingSource' => 'https://openai.com/api/pricing',
        'pricingCheckedAt' => '2026-04-18'
    ],
    'summarizer' => [
        'id' => 'summarizer',
        'label' => 'Summarizer',
        'model' => $summarizerModel
    ],
    'syncPolicy' => [
        'mode' => 'checkpoint',
        'shareOnBlocker' => true,
        'shareEverySteps' => 3
    ],
    'workers' => $workers
];

$state = mutate_state(function (array $state) use ($task): array {
    $state['activeTask'] = $task;
    $state['workers'] = empty_worker_state_map(task_workers($task));
    $state['summary'] = null;
    $state['memoryVersion'] = ($state['memoryVersion'] ?? 0) + 1;
    $state['usage'] = default_usage_state();
    $state['loop'] = default_loop_state();
    return $state;
});

write_task_snapshot($task);
append_event('task_started', ['taskId' => $taskId, 'objective' => $objective]);
append_step('task', 'Created a new task and reset worker memory.', [
    'taskId' => $taskId,
    'constraintCount' => count($constraints),
    'runtime' => $task['runtime'],
    'syncPolicy' => $task['syncPolicy'],
    'workerCount' => count($workers),
    'summarizerModel' => $summarizerModel
]);

json_response(['message' => 'Task created.', 'taskId' => $taskId]);
