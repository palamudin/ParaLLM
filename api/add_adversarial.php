<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (empty($state['activeTask']) || !is_array($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing the worker roster.'], 409);
}

$task = $state['activeTask'];
$worker = next_adversarial_worker_definition($task);
if ($worker === null) {
    json_response(['message' => 'All available adversarial worker slots are already in use.'], 409);
}

$updatedState = mutate_state(function (array $state) use ($worker): array {
    if (!is_array($state['activeTask'] ?? null)) {
        throw new RuntimeException('No active task.');
    }
    $task = $state['activeTask'];
    $workers = task_workers($task);
    $workers[] = $worker;
    $task['workers'] = $workers;
    $state['activeTask'] = $task;

    $workerMap = is_array($state['workers'] ?? null) ? $state['workers'] : [];
    $workerMap[$worker['id']] = null;
    ksort($workerMap);
    $state['workers'] = $workerMap;
    return $state;
});

write_task_snapshot($updatedState['activeTask']);
append_step('worker_roster', 'Added a new adversarial worker slot.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'workerId' => $worker['id'],
    'label' => $worker['label'],
    'model' => $worker['model']
]);

json_response([
    'message' => 'Adversarial worker added.',
    'worker' => $worker
]);
