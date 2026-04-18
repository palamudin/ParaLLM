<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$rounds = clamp_loop_rounds(post_value('rounds', 3));
$delayMs = clamp_loop_delay_ms(post_value('delayMs', 1000));

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is already active.'], 409);
}

$task = $state['activeTask'];
$job = create_loop_job($task, $rounds, $delayMs, 'background');
$runnerPath = ROOT_PATH . DIRECTORY_SEPARATOR . 'scripts' . DIRECTORY_SEPARATOR . 'loop_runner.php';

try {
    launch_background_php($runnerPath, ['--job-id=' . $job['jobId']]);
    append_step('autoloop', 'Background loop process launched.', [
        'taskId' => $task['taskId'],
        'jobId' => $job['jobId'],
        'rounds' => $rounds,
        'delayMs' => $delayMs
    ]);
    json_response([
        'message' => 'Background loop started.',
        'jobId' => $job['jobId'],
        'rounds' => $rounds,
        'delayMs' => $delayMs
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
