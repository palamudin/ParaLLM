<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'An autonomous loop is active. Cancel it before starting a new task.'], 409);
}

$objective = trim((string)post_value('objective', ''));
if ($objective === '') {
    json_response(['message' => 'Objective is required.'], 400);
}

$sessionContext = trim((string)post_value('sessionContext', ''));

$constraintsRaw = post_value('constraints', '[]');
$constraints = json_decode((string)$constraintsRaw, true);
if (!is_array($constraints)) $constraints = [];

$workersRaw = post_value('workers', '[]');
$workersInput = json_decode((string)$workersRaw, true);
if (!is_array($workersInput)) $workersInput = [];

$summarizerHarnessRaw = post_value('summarizerHarness', '{}');
$summarizerHarnessInput = json_decode((string)$summarizerHarnessRaw, true);
if (!is_array($summarizerHarnessInput)) $summarizerHarnessInput = [];

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

$budgetTargetsRaw = post_value('budgetTargets', '{}');
$budgetTargetsInput = json_decode((string)$budgetTargetsRaw, true);
if (!is_array($budgetTargetsInput)) {
    $budgetTargetsInput = [];
}

$budget = normalize_budget_config([
    'maxTotalTokens' => post_int_value('maxTotalTokens', default_budget_config()['maxTotalTokens']),
    'maxCostUsd' => post_float_value('maxCostUsd', default_budget_config()['maxCostUsd']),
    'maxOutputTokens' => post_int_value('maxOutputTokens', default_budget_config()['maxOutputTokens']),
    'targets' => $budgetTargetsInput,
]);

$research = normalize_research_config([
    'enabled' => post_value('researchEnabled', default_research_config()['enabled']),
    'externalWebAccess' => post_value('researchExternalWebAccess', default_research_config()['externalWebAccess']),
    'domains' => post_value('researchDomains', default_research_config()['domains']),
]);

$vetting = normalize_vetting_config([
    'enabled' => post_value('vettingEnabled', default_vetting_config()['enabled']),
]);

$preferredLoop = normalize_loop_preferences([
    'rounds' => post_int_value('loopRounds', default_loop_preferences()['rounds']),
    'delayMs' => post_int_value('loopDelayMs', default_loop_preferences()['delayMs']),
]);

$workers = task_workers([
    'runtime' => ['model' => $model],
    'workers' => $workersInput,
]);

$taskId = 't-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
$task = [
    'taskId' => $taskId,
    'objective' => $objective,
    'constraints' => array_values($constraints),
    'sessionContext' => $sessionContext,
    'createdAt' => gmdate('c'),
    'runtime' => [
        'executionMode' => $executionMode,
        'model' => $model,
        'reasoningEffort' => $reasoningEffort,
        'budget' => $budget,
        'research' => $research,
        'vetting' => $vetting,
        'pricingSource' => 'https://openai.com/api/pricing',
        'pricingCheckedAt' => '2026-04-19',
        'pricingSources' => [
            'https://openai.com/api/pricing/',
            'https://developers.openai.com/api/docs/pricing'
        ],
        'pricingAccuracy' => 'assume_chargeable',
        'pricingNote' => 'This workspace uses a conservative chargeable-search assumption: web-search-related model tokens are treated as billable and tool calls stay separately priced.'
    ],
    'summarizer' => [
        'id' => 'summarizer',
        'label' => 'Summarizer',
        'model' => $summarizerModel,
        'harness' => normalize_harness_config($summarizerHarnessInput, default_summarizer_harness()['concision'])
    ],
    'syncPolicy' => [
        'mode' => 'checkpoint',
        'shareOnBlocker' => true,
        'shareEverySteps' => 3
    ],
    'preferredLoop' => $preferredLoop,
    'workers' => $workers
];

$state = mutate_state(function (array $state) use ($task): array {
    $state['activeTask'] = $task;
    $state['draft'] = build_draft_from_task($task);
    $state['commander'] = null;
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
    'hasSessionContext' => $sessionContext !== '',
    'runtime' => $task['runtime'],
    'preferredLoop' => $preferredLoop,
    'syncPolicy' => $task['syncPolicy'],
    'workerCount' => count($workers),
    'summarizerModel' => $summarizerModel
]);

json_response(['message' => 'Task created.', 'taskId' => $taskId]);
