<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$model = normalize_model_id((string)post_value('model', default_model_id()), default_model_id());
$summarizerModel = normalize_model_id((string)post_value('summarizerModel', $model), $model);

$state = recover_loop_state_if_needed();
if (empty($state['activeTask']) || !is_array($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing runtime settings.'], 409);
}

$activeTask = $state['activeTask'];
$runtime = is_array($activeTask['runtime'] ?? null) ? $activeTask['runtime'] : [];
$currentBudget = normalize_budget_config(is_array($runtime['budget'] ?? null) ? $runtime['budget'] : []);
$currentLoop = normalize_loop_preferences(is_array($activeTask['preferredLoop'] ?? null) ? $activeTask['preferredLoop'] : []);
$currentReasoningEffort = trim((string)($runtime['reasoningEffort'] ?? 'low'));
if (!in_array($currentReasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $currentReasoningEffort = 'low';
}

$reasoningEffort = trim((string)post_value('reasoningEffort', $currentReasoningEffort));
if (!in_array($reasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $reasoningEffort = $currentReasoningEffort;
}

$budget = normalize_budget_config([
    'maxTotalTokens' => post_int_value('maxTotalTokens', $currentBudget['maxTotalTokens']),
    'maxCostUsd' => post_float_value('maxCostUsd', $currentBudget['maxCostUsd']),
    'maxOutputTokens' => post_int_value('maxOutputTokens', $currentBudget['maxOutputTokens']),
]);
$preferredLoop = normalize_loop_preferences([
    'rounds' => post_int_value('loopRounds', $currentLoop['rounds']),
    'delayMs' => post_int_value('loopDelayMs', $currentLoop['delayMs']),
]);

$updatedState = mutate_state(function (array $state) use ($model, $summarizerModel, $reasoningEffort, $budget, $preferredLoop): array {
    if (!is_array($state['activeTask'] ?? null)) {
        throw new RuntimeException('No active task.');
    }

    $task = $state['activeTask'];
    $workers = task_workers($task);
    foreach ($workers as &$worker) {
        $worker['model'] = $model;
    }
    unset($worker);

    $task['workers'] = $workers;
    $task['runtime'] = is_array($task['runtime'] ?? null) ? $task['runtime'] : [];
    $task['runtime']['model'] = $model;
    $task['runtime']['reasoningEffort'] = $reasoningEffort;
    $task['runtime']['budget'] = $budget;
    $task['preferredLoop'] = $preferredLoop;

    $summary = summarizer_config($task);
    $summary['model'] = $summarizerModel;
    $task['summarizer'] = $summary;

    $state['activeTask'] = $task;
    $state['draft'] = build_draft_from_task($task);
    return $state;
});

write_task_snapshot($updatedState['activeTask']);
append_step('model', 'Applied settings runtime and loop selection to the active task.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel,
    'reasoningEffort' => $reasoningEffort,
    'budget' => $budget,
    'preferredLoop' => $preferredLoop,
    'workerCount' => count(task_workers($updatedState['activeTask']))
]);

json_response([
    'message' => 'Applied runtime settings to the active task.',
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel,
    'reasoningEffort' => $reasoningEffort,
    'budget' => $budget,
    'preferredLoop' => $preferredLoop
]);
