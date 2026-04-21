<?php

require_once __DIR__ . '/common.php';

function dispatch_job_runner_path(): string {
    return ROOT_PATH . DIRECTORY_SEPARATOR . 'scripts' . DIRECTORY_SEPARATOR . 'dispatch_runner.php';
}

function target_job_status_can_retry(?string $status): bool {
    return in_array((string)$status, ['interrupted', 'error', 'budget_exhausted', 'cancelled', 'completed'], true);
}

function active_target_jobs_unlocked(?string $taskId = null, bool $includePartial = true): array {
    $jobs = [];
    foreach (read_jobs_unlocked() as $job) {
        if ((string)($job['jobType'] ?? 'loop') !== 'target') {
            continue;
        }
        if (!job_status_is_active($job['status'] ?? null)) {
            continue;
        }
        if ($taskId !== null && (string)($job['taskId'] ?? '') !== $taskId) {
            continue;
        }
        if (!$includePartial && !empty($job['partialSummary'])) {
            continue;
        }
        $jobs[] = default_job($job);
    }
    usort($jobs, static function (array $a, array $b): int {
        $runningA = (string)($a['status'] ?? '') === 'running' ? 0 : 1;
        $runningB = (string)($b['status'] ?? '') === 'running' ? 0 : 1;
        if ($runningA !== $runningB) {
            return $runningA <=> $runningB;
        }
        $timeA = parse_job_ts($a['queuedAt'] ?? null) ?? 0;
        $timeB = parse_job_ts($b['queuedAt'] ?? null) ?? 0;
        return $timeA <=> $timeB;
    });
    return $jobs;
}

function active_target_job_count_unlocked(?string $taskId = null, bool $includePartial = true): int {
    return count(active_target_jobs_unlocked($taskId, $includePartial));
}

function dispatch_target_label(array $job): string {
    $target = strtolower((string)($job['target'] ?? 'target'));
    if ($target === 'answer_now') {
        return 'Answer now';
    }
    if ($target === 'commander') {
        return 'Commander';
    }
    if ($target === 'commander_review') {
        return 'Commander review';
    }
    if ($target === 'summarizer') {
        return !empty($job['partialSummary']) ? 'Summarizer (partial)' : 'Summarizer';
    }
    return 'Worker ' . strtoupper($target);
}

function dispatch_dependency_ids(array $job): array {
    return array_values(array_filter(array_map(static function ($value): string {
        return trim((string)$value);
    }, is_array($job['dependencyJobIds'] ?? null) ? $job['dependencyJobIds'] : [])));
}

function dispatch_dependency_jobs_unlocked(array $job): array {
    $dependencies = [];
    foreach (dispatch_dependency_ids($job) as $jobId) {
        $dependency = read_job_unlocked($jobId);
        if (is_array($dependency)) {
            $dependencies[$jobId] = default_job($dependency);
        }
    }
    return $dependencies;
}

function dispatch_dependency_failure_message_unlocked(array $job): ?string {
    foreach (dispatch_dependency_ids($job) as $dependencyId) {
        $dependency = read_job_unlocked($dependencyId);
        if (!is_array($dependency)) {
            return 'Dependency ' . $dependencyId . ' is missing.';
        }
        $status = (string)($dependency['status'] ?? 'queued');
        if (job_status_is_terminal($status) && $status !== 'completed') {
            return dispatch_target_label($dependency) . ' finished with status ' . $status . '.';
        }
    }
    return null;
}

function dispatch_dependencies_completed_unlocked(array $job): bool {
    foreach (dispatch_dependency_ids($job) as $dependencyId) {
        $dependency = read_job_unlocked($dependencyId);
        if (!is_array($dependency)) {
            return false;
        }
        if ((string)($dependency['status'] ?? 'queued') !== 'completed') {
            return false;
        }
    }
    return true;
}

function dispatch_wait_message_unlocked(array $job): string {
    $dependencyIds = dispatch_dependency_ids($job);
    if (!$dependencyIds) {
        return 'Queued target dispatch.';
    }
    $labels = [];
    foreach ($dependencyIds as $dependencyId) {
        $dependency = read_job_unlocked($dependencyId);
        $labels[] = is_array($dependency) ? dispatch_target_label($dependency) : $dependencyId;
    }
    return 'Waiting for ' . implode(', ', $labels) . '.';
}

function dispatch_job_is_launchable_unlocked(array $job): bool {
    if ((string)($job['jobType'] ?? 'loop') !== 'target') {
        return false;
    }
    if ((string)($job['status'] ?? 'queued') !== 'queued') {
        return false;
    }
    if (!empty($job['cancelRequested'])) {
        return false;
    }
    return dispatch_dependencies_completed_unlocked($job);
}

function interrupt_unrunnable_dispatch_jobs_unlocked(?string $taskId = null, ?string $batchId = null): int {
    $changed = 0;
    do {
        $passChanged = 0;
        foreach (read_jobs_unlocked() as $job) {
            $job = default_job($job);
            if ((string)($job['jobType'] ?? 'loop') !== 'target') {
                continue;
            }
            if ((string)($job['status'] ?? '') !== 'queued') {
                continue;
            }
            if ($taskId !== null && (string)($job['taskId'] ?? '') !== $taskId) {
                continue;
            }
            if ($batchId !== null && (string)($job['batchId'] ?? '') !== $batchId) {
                continue;
            }
            $failure = dispatch_dependency_failure_message_unlocked($job);
            if ($failure === null) {
                continue;
            }
            write_job_unlocked(array_merge($job, [
                'status' => 'interrupted',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Dispatch stopped because a dependency failed.',
                'error' => $failure,
            ]));
            $passChanged++;
        }
        $changed += $passChanged;
    } while ($passChanged > 0);
    return $changed;
}

function recover_dispatch_jobs_if_needed(): void {
    with_lock(function (): void {
        $now = time();
        foreach (read_jobs_unlocked() as $job) {
            $job = default_job($job);
            if ((string)($job['jobType'] ?? 'loop') !== 'target') {
                continue;
            }
            $status = (string)($job['status'] ?? 'queued');
            if (!in_array($status, ['queued', 'running'], true)) {
                continue;
            }
            $queueTs = parse_job_ts($job['queuedAt'] ?? null);
            $heartbeatTs = parse_job_ts($job['lastHeartbeatAt'] ?? null)
                ?? parse_job_ts($job['startedAt'] ?? null)
                ?? $queueTs;
            $dependencyIds = dispatch_dependency_ids($job);
            $hasDependencies = !empty($dependencyIds);
            $waitingOnDependencies = $status === 'queued'
                && $hasDependencies
                && dispatch_dependency_failure_message_unlocked($job) === null
                && !dispatch_dependencies_completed_unlocked($job);
            $queueStale = $status === 'queued'
                && !$hasDependencies
                && !$waitingOnDependencies
                && $queueTs !== null
                && ($now - $queueTs) > JOB_QUEUE_STALE_SECONDS;
            $runStale = $status === 'running' && $heartbeatTs !== null && ($now - $heartbeatTs) > JOB_RUNNING_STALE_SECONDS;
            if (!$queueStale && !$runStale) {
                continue;
            }
            $message = $queueStale
                ? 'Recovered a stale queued dispatch job. It can be retried.'
                : 'Recovered a stale running dispatch job. It can be retried.';
            write_job_unlocked(array_merge($job, [
                'status' => 'interrupted',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => $message,
                'error' => $message,
            ]));
        }
        interrupt_unrunnable_dispatch_jobs_unlocked();
    });
    promote_ready_dispatch_jobs();
}

function current_dispatch_state(?array $state = null): array {
    return with_lock(function () use ($state): array {
        $snapshot = is_array($state) ? $state : read_state_unlocked();
        $taskId = (string)($snapshot['activeTask']['taskId'] ?? '');
        if ($taskId === '') {
            return [
                'status' => 'idle',
                'activeJobs' => [],
                'runningCount' => 0,
                'queuedCount' => 0,
                'partialCount' => 0,
                'lastMessage' => 'Ready.',
            ];
        }
        $jobs = active_target_jobs_unlocked($taskId, true);
        if (!$jobs) {
            return [
                'status' => 'idle',
                'activeJobs' => [],
                'runningCount' => 0,
                'queuedCount' => 0,
                'partialCount' => 0,
                'lastMessage' => 'Ready.',
            ];
        }
        $runningCount = 0;
        $queuedCount = 0;
        $partialCount = 0;
        $activeJobs = [];
        foreach ($jobs as $job) {
            if (($job['status'] ?? '') === 'running') {
                $runningCount++;
            } else {
                $queuedCount++;
            }
            if (!empty($job['partialSummary'])) {
                $partialCount++;
            }
            $activeJobs[] = [
                'jobId' => $job['jobId'] ?? null,
                'target' => $job['target'] ?? null,
                'targetLabel' => dispatch_target_label($job),
                'status' => $job['status'] ?? null,
                'batchId' => $job['batchId'] ?? null,
                'partialSummary' => !empty($job['partialSummary']),
                'queuedAt' => $job['queuedAt'] ?? null,
                'startedAt' => $job['startedAt'] ?? null,
                'lastHeartbeatAt' => $job['lastHeartbeatAt'] ?? null,
                'lastMessage' => $job['lastMessage'] ?? null,
            ];
        }
        return [
            'status' => $runningCount > 0 ? 'running' : 'queued',
            'activeJobs' => $activeJobs,
            'runningCount' => $runningCount,
            'queuedCount' => $queuedCount,
            'partialCount' => $partialCount,
            'lastMessage' => $activeJobs[0]['lastMessage'] ?? 'Dispatch in progress.',
        ];
    });
}

function launch_dispatch_job_runner(array $job): array {
    $runnerPath = dispatch_job_runner_path();
    launch_background_php($runnerPath, ['--job-id=' . $job['jobId']]);
    append_step('dispatch', 'Background target dispatch launched.', [
        'taskId' => $job['taskId'] ?? null,
        'jobId' => $job['jobId'] ?? null,
        'target' => $job['target'] ?? null,
        'partialSummary' => !empty($job['partialSummary']),
        'batchId' => $job['batchId'] ?? null,
    ]);
    return $job;
}

function create_target_job(array $task, string $target, array $overrides = []): array {
    $jobId = 'dispatch-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
    $queuedAt = gmdate('c');
    $dependencyIds = array_values(array_filter(array_map(static function ($value): string {
        return trim((string)$value);
    }, is_array($overrides['dependencyJobIds'] ?? null) ? $overrides['dependencyJobIds'] : [])));
    $job = default_job([
        'jobId' => $jobId,
        'taskId' => $task['taskId'],
        'jobType' => 'target',
        'mode' => 'background',
        'status' => 'queued',
        'target' => $target,
        'batchId' => $overrides['batchId'] ?? null,
        'queuePosition' => 0,
        'attempt' => max(1, (int)($overrides['attempt'] ?? 1)),
        'rounds' => 0,
        'delayMs' => 0,
        'workerCount' => max(0, (int)($overrides['workerCount'] ?? count(task_workers($task)))),
        'dependencyJobIds' => $dependencyIds,
        'partialSummary' => (bool)($overrides['partialSummary'] ?? false),
        'timeoutSeconds' => max(30, (int)($overrides['timeoutSeconds'] ?? 1800)),
        'queuedAt' => $queuedAt,
        'lastMessage' => $dependencyIds ? ($overrides['lastMessage'] ?? 'Waiting for dependencies.') : ($overrides['lastMessage'] ?? 'Queued target dispatch.'),
        'metadata' => isset($overrides['metadata']) && is_array($overrides['metadata']) ? $overrides['metadata'] : [],
    ]);
    write_job($job);
    append_step('dispatch', 'Queued background target dispatch.', [
        'taskId' => $task['taskId'],
        'jobId' => $jobId,
        'target' => $target,
        'partialSummary' => !empty($job['partialSummary']),
        'dependencyJobIds' => $dependencyIds,
        'batchId' => $job['batchId'],
    ]);
    return $job;
}

function create_round_dispatch_jobs(array $task, array $overrides = []): array {
    $roundNumber = max(1, (int)($overrides['roundNumber'] ?? 1));
    $roundWorkers = task_workers($task, $roundNumber);
    $batchId = 'batch-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
    $commanderJob = create_target_job($task, 'commander', [
        'batchId' => $batchId,
        'timeoutSeconds' => $overrides['timeoutSeconds'] ?? 1800,
        'workerCount' => count($roundWorkers),
        'lastMessage' => 'Queued commander dispatch.',
        'metadata' => ['trigger' => 'round'],
    ]);
    $workerJobs = [];
    foreach ($roundWorkers as $worker) {
        $workerJobs[] = create_target_job($task, (string)$worker['id'], [
            'batchId' => $batchId,
            'dependencyJobIds' => [$commanderJob['jobId']],
            'timeoutSeconds' => $overrides['timeoutSeconds'] ?? 1800,
            'workerCount' => count($roundWorkers),
            'lastMessage' => 'Waiting for commander.',
            'metadata' => ['trigger' => 'round'],
        ]);
    }
    $summaryDependencies = array_map(static function (array $job): string {
        return (string)$job['jobId'];
    }, $workerJobs);
    $commanderReviewJob = create_target_job($task, 'commander_review', [
        'batchId' => $batchId,
        'dependencyJobIds' => $summaryDependencies,
        'timeoutSeconds' => $overrides['timeoutSeconds'] ?? 1800,
        'workerCount' => count($roundWorkers),
        'lastMessage' => $summaryDependencies ? 'Waiting for workers.' : 'Waiting for commander.',
        'metadata' => ['trigger' => 'round'],
    ]);
    $summaryJob = create_target_job($task, 'summarizer', [
        'batchId' => $batchId,
        'dependencyJobIds' => [$commanderReviewJob['jobId']],
        'timeoutSeconds' => $overrides['timeoutSeconds'] ?? 1800,
        'workerCount' => count($roundWorkers),
        'lastMessage' => 'Waiting for commander review.',
        'metadata' => ['trigger' => 'round'],
    ]);
    return [
        'batchId' => $batchId,
        'commander' => $commanderJob,
        'workers' => $workerJobs,
        'commanderReview' => $commanderReviewJob,
        'summarizer' => $summaryJob,
    ];
}

function promote_ready_dispatch_jobs(?string $taskId = null, ?string $batchId = null): array {
    $launchable = with_lock(function () use ($taskId, $batchId): array {
        interrupt_unrunnable_dispatch_jobs_unlocked($taskId, $batchId);
        $jobs = [];
        foreach (read_jobs_unlocked() as $job) {
            $job = default_job($job);
            if ((string)($job['jobType'] ?? 'loop') !== 'target') {
                continue;
            }
            if ($taskId !== null && (string)($job['taskId'] ?? '') !== $taskId) {
                continue;
            }
            if ($batchId !== null && (string)($job['batchId'] ?? '') !== $batchId) {
                continue;
            }
            if (!dispatch_job_is_launchable_unlocked($job)) {
                continue;
            }
            $jobs[] = write_job_unlocked(array_merge($job, [
                'status' => 'running',
                'startedAt' => $job['startedAt'] ?? gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Launching target dispatch.',
            ]));
        }
        return $jobs;
    });

    $launched = [];
    foreach ($launchable as $job) {
        try {
            launch_dispatch_job_runner($job);
            $launched[] = $job;
        } catch (Throwable $ex) {
            mutate_job((string)$job['jobId'], function (?array $existing) use ($ex): array {
                return default_job(array_merge($existing ?? [], [
                    'status' => 'error',
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => 'Dispatch launch failed.',
                    'error' => $ex->getMessage(),
                ]));
            });
            append_step('error', 'Failed to launch a background target dispatch.', [
                'taskId' => $job['taskId'] ?? null,
                'jobId' => $job['jobId'] ?? null,
                'target' => $job['target'] ?? null,
                'error' => $ex->getMessage(),
            ]);
        }
    }
    return $launched;
}

function execute_target_job_process(array $config): array {
    $jobId = (string)($config['jobId'] ?? '');
    $target = trim((string)($config['target'] ?? ''));
    $taskId = trim((string)($config['taskId'] ?? ''));
    $timeoutSeconds = max(30, (int)($config['timeoutSeconds'] ?? 1800));
    $options = isset($config['options']) && is_array($config['options']) ? $config['options'] : [];
    $dispatchTargetLabel = dispatch_target_label([
        'target' => $target,
        'partialSummary' => !empty($options['partialSummary']),
    ]);
    $options['dispatchJobId'] = $jobId;
    $options['dispatchHeartbeatMessage'] = 'Waiting on ' . $dispatchTargetLabel . ' response...';
    if ($jobId === '' || $target === '' || $taskId === '') {
        throw new RuntimeException('Target job metadata is incomplete.');
    }

    mutate_job($jobId, function (?array $job) use ($target): array {
        return default_job(array_merge($job ?? [], [
            'status' => 'running',
            'startedAt' => gmdate('c'),
            'finishedAt' => null,
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Running ' . dispatch_target_label(array_merge($job ?? [], ['target' => $target])) . '.',
            'error' => null,
        ]));
    });

    append_step('dispatch', 'Background target runner claimed job.', [
        'taskId' => $taskId,
        'jobId' => $jobId,
        'target' => $target,
        'options' => $options,
    ]);

    try {
        $task = read_task_snapshot($taskId);
        if (!is_array($task)) {
            throw new RuntimeException('Task snapshot is missing.');
        }
        $result = run_dispatch_target($target, $task, $options, $timeoutSeconds);
        $usageSnapshot = normalize_usage_state(read_state()['usage'] ?? []);
        $job = mutate_job($jobId, function (?array $job) use ($result, $usageSnapshot): array {
            return default_job(array_merge($job ?? [], [
                'status' => 'completed',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Completed ' . dispatch_target_label($job ?? []) . '.',
                'usage' => $usageSnapshot,
                'results' => [$result],
                'error' => null,
            ]));
        });
        append_step('dispatch', 'Background target dispatch completed.', [
            'taskId' => $taskId,
            'jobId' => $jobId,
            'target' => $target,
            'outputPreview' => $result['output'] ?? '',
            'exitCode' => $result['exitCode'] ?? 0,
        ]);
        promote_ready_dispatch_jobs($taskId, (string)($job['batchId'] ?? ''));
        return $result;
    } catch (Throwable $ex) {
        $finalStatus = stripos($ex->getMessage(), 'Budget limit reached:') === 0 ? 'budget_exhausted' : 'error';
        $job = mutate_job($jobId, function (?array $job) use ($finalStatus, $ex): array {
            return default_job(array_merge($job ?? [], [
                'status' => $finalStatus,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Dispatch failed.',
                'error' => $ex->getMessage(),
            ]));
        });
        append_step($finalStatus === 'budget_exhausted' ? 'budget' : 'error', 'Background target dispatch failed.', [
            'taskId' => $taskId,
            'jobId' => $jobId,
            'target' => $target,
            'error' => $ex->getMessage(),
        ]);
        with_lock(function () use ($taskId, $job): void {
            interrupt_unrunnable_dispatch_jobs_unlocked($taskId, (string)($job['batchId'] ?? ''));
        });
        promote_ready_dispatch_jobs($taskId, (string)($job['batchId'] ?? ''));
        throw $ex;
    }
}
