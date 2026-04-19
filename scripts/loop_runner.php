<?php

declare(strict_types=1);

set_time_limit(0);

require __DIR__ . '/../api/common.php';
require __DIR__ . '/../api/loop_runtime.php';

$opts = getopt('', ['job-id:']);
$jobId = $opts['job-id'] ?? null;

if (!is_string($jobId) || $jobId === '') {
    fwrite(STDERR, "Missing --job-id\n");
    exit(1);
}

$job = read_job($jobId);
if ($job === null) {
    fwrite(STDERR, "Job not found: {$jobId}\n");
    exit(1);
}

if (($job['status'] ?? 'queued') === 'cancelled') {
    append_step('autoloop', 'Background runner exited because the job was already cancelled.', [
        'taskId' => $job['taskId'] ?? null,
        'jobId' => $jobId
    ]);
    exit(0);
}

try {
    execute_loop_process([
        'jobId' => $jobId,
        'taskId' => $job['taskId'],
        'mode' => 'background',
        'rounds' => $job['rounds'],
        'delayMs' => $job['delayMs'],
        'startRound' => $job['resumeFromRound'] ?? 1,
        'results' => $job['results'] ?? [],
        'completedRounds' => $job['completedRounds'] ?? 0
    ]);
    exit(0);
} catch (Throwable $ex) {
    fwrite(STDERR, $ex->getMessage() . PHP_EOL);
    exit(1);
}
