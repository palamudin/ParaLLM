<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$rounds = clamp_loop_rounds(post_value('rounds', 3));
$delayMs = clamp_loop_delay_ms(post_value('delayMs', 1000));

$state = recover_loop_state_if_needed();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}

$task = $state['activeTask'];
$taskId = (string)($task['taskId'] ?? '');
$activeBackgroundJobs = with_lock(function () use ($taskId): int {
    return active_background_job_count_unlocked($taskId);
});
if ($activeBackgroundJobs >= LOOP_QUEUE_LIMIT) {
    json_response(['message' => 'Background loop queue is full. Cancel or finish an existing queued job first.'], 409);
}

$queuePosition = with_lock(function () use ($taskId): int {
    return loop_is_active(read_state_unlocked()) ? next_background_queue_position_unlocked($taskId) : 0;
});
$job = create_loop_job($task, $rounds, $delayMs, 'background', [
    'queuePosition' => $queuePosition,
    'updateLoopState' => !loop_is_active($state),
    'lastMessage' => $queuePosition > 0 ? 'Queued behind another background loop.' : 'Queued background loop.',
]);

try {
    if ($queuePosition === 0 && !loop_is_active($state)) {
        launch_loop_job_runner($job, false);
    }
    json_response([
        'message' => $queuePosition > 0 ? 'Background loop queued.' : 'Background loop started.',
        'jobId' => $job['jobId'],
        'rounds' => $rounds,
        'delayMs' => $delayMs,
        'queuePosition' => $queuePosition
    ]);
} catch (Throwable $ex) {
    mutate_state(function (array $state): array {
        $state['loop'] = default_loop_state();
        $state['loop']['lastMessage'] = 'Background launch failed.';
        return $state;
    });

    mutate_job($job['jobId'], function (?array $existing) use ($ex): array {
        return default_job(array_merge($existing ?? [], [
            'status' => 'error',
            'finishedAt' => gmdate('c'),
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Background launch failed.',
            'error' => $ex->getMessage()
        ]));
    });

    append_step('error', 'Failed to launch background loop.', [
        'taskId' => $task['taskId'],
        'jobId' => $job['jobId'],
        'error' => $ex->getMessage()
    ]);

    json_response(['message' => $ex->getMessage()], 500);
}
