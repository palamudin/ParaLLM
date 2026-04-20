<?php

declare(strict_types=1);

set_time_limit(0);

require __DIR__ . '/../api/common.php';
require __DIR__ . '/../api/dispatch_runtime.php';

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

if ((string)($job['jobType'] ?? 'loop') !== 'target') {
    fwrite(STDERR, "Job is not a target dispatch: {$jobId}\n");
    exit(1);
}

if (($job['status'] ?? 'queued') === 'cancelled') {
    append_step('dispatch', 'Background dispatch runner exited because the job was already cancelled.', [
        'taskId' => $job['taskId'] ?? null,
        'jobId' => $jobId,
        'target' => $job['target'] ?? null,
    ]);
    exit(0);
}

try {
    execute_target_job_process([
        'jobId' => $jobId,
        'taskId' => $job['taskId'] ?? null,
        'target' => $job['target'] ?? null,
        'timeoutSeconds' => $job['timeoutSeconds'] ?? 1800,
        'options' => [
            'partialSummary' => !empty($job['partialSummary']),
        ],
    ]);
    exit(0);
} catch (Throwable $ex) {
    fwrite(STDERR, $ex->getMessage() . PHP_EOL);
    exit(1);
}
