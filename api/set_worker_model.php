<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$positionId = trim((string)post_value('positionId', ''));
$model = normalize_model_id((string)post_value('model', default_model_id()), default_model_id());

if ($positionId === '') {
    json_response(['message' => 'positionId is required.'], 400);
}

$state = recover_loop_state_if_needed();
if (empty($state['activeTask']) || !is_array($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing models.'], 409);
}

$updatedState = mutate_state(function (array $state) use ($positionId, $model): array {
    if (!is_array($state['activeTask'] ?? null)) {
        throw new RuntimeException('No active task.');
    }
    $task = $state['activeTask'];

    if ($positionId === 'summarizer') {
        $summary = summarizer_config($task);
        $summary['model'] = $model;
        $task['summarizer'] = $summary;
        $state['activeTask'] = $task;
        return $state;
    }

    $workers = task_workers($task);
    $found = false;
    foreach ($workers as &$worker) {
        if (($worker['id'] ?? null) === strtoupper($positionId)) {
            $worker['model'] = $model;
            $found = true;
            break;
        }
    }
    unset($worker);

    if (!$found) {
        throw new RuntimeException('Unknown worker position.');
    }

    $task['workers'] = $workers;
    $state['activeTask'] = $task;
    return $state;
});

write_task_snapshot($updatedState['activeTask']);
append_step('model', 'Updated the model selection for a task position.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'positionId' => $positionId,
    'model' => $model
]);

json_response([
    'message' => 'Model updated.',
    'positionId' => $positionId,
    'model' => $model
]);
