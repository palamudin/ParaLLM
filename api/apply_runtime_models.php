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
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing models.'], 409);
}

$updatedState = mutate_state(function (array $state) use ($model, $summarizerModel): array {
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

    $summary = summarizer_config($task);
    $summary['model'] = $summarizerModel;
    $task['summarizer'] = $summary;

    $state['activeTask'] = $task;
    $state['draft'] = build_draft_from_task($task);
    return $state;
});

write_task_snapshot($updatedState['activeTask']);
append_step('model', 'Applied settings model selection to the active task.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel,
    'workerCount' => count(task_workers($updatedState['activeTask']))
]);

json_response([
    'message' => 'Applied model selection to the active task.',
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel
]);
