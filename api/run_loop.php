<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();
allow_long_running_request();

$rounds = clamp_loop_rounds(post_value('rounds', 3));
$delayMs = clamp_loop_delay_ms(post_value('delayMs', 1000));

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
recover_dispatch_jobs_if_needed();
if (with_lock(function () use ($state): int {
    return active_target_job_count_unlocked((string)($state['activeTask']['taskId'] ?? ''), true);
}) > 0) {
    json_response(['message' => 'Target dispatch jobs are still running. Wait for them to finish before running the full loop.'], 409);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is already active.'], 409);
}

try {
    $result = execute_loop_process([
        'taskId' => $state['activeTask']['taskId'],
        'mode' => 'sync',
        'rounds' => $rounds,
        'delayMs' => $delayMs
    ]);
    json_response($result);
} catch (Throwable $ex) {
    json_response(['message' => $ex->getMessage()], 500);
}
