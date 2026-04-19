<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$workerId = strtoupper(trim((string)post_value('workerId', '')));
$type = post_value('type', null);
$temperature = post_value('temperature', null);
$model = post_value('model', null);

if (!preg_match('/^[A-Z]$/', $workerId)) {
    json_response(['message' => 'A valid workerId is required.'], 400);
}

if ($type === null && $temperature === null && $model === null) {
    json_response(['message' => 'Provide at least one worker property to update.'], 400);
}

$state = recover_loop_state_if_needed();
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing worker settings.'], 409);
}

$updatedState = mutate_state(function (array $state) use ($workerId, $type, $temperature, $model): array {
    $draft = normalize_draft_state(isset($state['draft']) && is_array($state['draft']) ? $state['draft'] : []);
    $draftWorkers = task_workers([
        'runtime' => ['model' => $draft['model']],
        'workers' => $draft['workers'],
    ]);

    $apply = function (array $workers, string $defaultModel) use ($workerId, $type, $temperature, $model): array {
        $updated = [];
        $found = false;
        foreach ($workers as $worker) {
            if (!is_array($worker) || ($worker['id'] ?? '') !== $workerId) {
                $updated[] = $worker;
                continue;
            }
            $patch = array_filter([
                'type' => $type,
                'temperature' => $temperature,
                'model' => $model,
            ], static function ($value) {
                return $value !== null;
            });
            if ($type !== null) {
                $patch['label'] = '';
                $patch['role'] = '';
                $patch['focus'] = '';
            }
            $updated[] = normalize_worker_definition(array_merge($worker, $patch), $defaultModel);
            $found = true;
        }
        if (!$found) {
            throw new RuntimeException('Unknown worker position.');
        }
        return task_workers([
            'runtime' => ['model' => $defaultModel],
            'workers' => $updated,
        ]);
    };

    $draft['workers'] = $apply($draftWorkers, $draft['model']);
    $state['draft'] = $draft;

    if (is_array($state['activeTask'] ?? null)) {
        $task = $state['activeTask'];
        $defaultModel = normalize_model_id($task['runtime']['model'] ?? $draft['model'], $draft['model']);
        $task['workers'] = $apply(task_workers($task), $defaultModel);
        $state['activeTask'] = $task;
    }

    return $state;
});

$task = is_array($updatedState['activeTask'] ?? null) ? $updatedState['activeTask'] : null;
if ($task) {
    write_task_snapshot($task);
}

$worker = null;
$sourceWorkers = $task ? task_workers($task) : ($updatedState['draft']['workers'] ?? []);
foreach ($sourceWorkers as $candidate) {
    if (($candidate['id'] ?? null) === $workerId) {
        $worker = $candidate;
        break;
    }
}

append_step('worker_roster', 'Updated worker configuration.', [
    'taskId' => $task['taskId'] ?? null,
    'workerId' => $workerId,
    'type' => $worker['type'] ?? null,
    'temperature' => $worker['temperature'] ?? null,
    'model' => $worker['model'] ?? null
]);

json_response([
    'message' => 'Worker updated.',
    'worker' => $worker,
    'draft' => $updatedState['draft']
]);
