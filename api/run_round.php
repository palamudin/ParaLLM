<?php
require __DIR__ . '/common.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
recover_dispatch_jobs_if_needed();
$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is already active.'], 409);
}
$batch = null;
if (with_lock(function () use ($state): int {
    return active_target_job_count_unlocked((string)($state['activeTask']['taskId'] ?? ''), false);
}) > 0) {
    json_response(['message' => 'A background target dispatch is already running. Wait for it to finish or use Answer Now from current checkpoints.'], 409);
}

try {
    $nextRound = max(1, summary_round_from_state($state) + 1);
    $batch = create_round_dispatch_jobs($state['activeTask'], [
        'timeoutSeconds' => 1800,
        'roundNumber' => $nextRound,
    ]);
    launch_dispatch_job_runner($batch['commander']);
        json_response([
        'message' => 'Round dispatch queued.',
        'batchId' => $batch['batchId'],
        'jobIds' => array_merge(
            [$batch['commander']['jobId']],
            array_map(static function (array $job): string { return (string)$job['jobId']; }, $batch['workers']),
            [$batch['commanderReview']['jobId']],
            [$batch['summarizer']['jobId']]
        ),
    ]);
} catch (Throwable $ex) {
    if (is_array($batch)) {
        foreach (array_merge([$batch['commander']], $batch['workers'], [$batch['commanderReview']], [$batch['summarizer']]) as $job) {
            mutate_job((string)($job['jobId'] ?? ''), function (?array $existing) use ($ex): ?array {
                if (!is_array($existing)) {
                    return $existing;
                }
                return default_job(array_merge($existing, [
                    'status' => 'error',
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => 'Round dispatch launch failed.',
                    'error' => $ex->getMessage(),
                ]));
            });
        }
    }
    append_step('error', 'Round dispatch failed to queue.', ['error' => $ex->getMessage()]);
    json_response(['message' => $ex->getMessage()], 500);
}
