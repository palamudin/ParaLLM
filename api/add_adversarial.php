<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing the worker roster.'], 409);
}

$requestedType = trim((string)post_value('type', ''));
$activeTask = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
$draft = normalize_draft_state(isset($state['draft']) && is_array($state['draft']) ? $state['draft'] : []);
$worker = next_adversarial_worker_definition($activeTask ?: $draft, $requestedType !== '' ? $requestedType : null);
if ($worker === null) {
    json_response(['message' => 'All available adversarial worker slots are already in use.'], 409);
}

$updatedState = mutate_state(function (array $state) use ($worker): array {
    $draft = normalize_draft_state(isset($state['draft']) && is_array($state['draft']) ? $state['draft'] : []);
    $draftWorkers = task_workers([
        'runtime' => ['model' => $draft['model']],
        'workers' => $draft['workers'],
    ]);
    $draftWorkers[] = $worker;
    $draft['workers'] = task_workers([
        'runtime' => ['model' => $draft['model']],
        'workers' => $draftWorkers,
    ]);
    $state['draft'] = $draft;
    return $state;
});
append_step('worker_roster', 'Added a new adversarial worker slot.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'workerId' => $worker['id'],
    'label' => $worker['label'],
    'type' => $worker['type'] ?? null,
    'temperature' => $worker['temperature'] ?? null,
    'model' => $worker['model']
]);

json_response([
    'message' => 'Adversarial worker added.',
    'worker' => $worker
]);
