<?php

function clamp_loop_rounds($rounds): int {
    $rounds = (int)$rounds;
    if ($rounds < 1) {
        return 1;
    }
    if ($rounds > 12) {
        return 12;
    }
    return $rounds;
}

function clamp_loop_delay_ms($delayMs): int {
    $delayMs = (int)$delayMs;
    if ($delayMs < 0) {
        return 0;
    }
    if ($delayMs > 10000) {
        return 10000;
    }
    return $delayMs;
}

function launch_loop_job_runner(array $job, bool $claimLoopState = true): array {
    $runnerPath = ROOT_PATH . DIRECTORY_SEPARATOR . 'scripts' . DIRECTORY_SEPARATOR . 'loop_runner.php';
    if ($claimLoopState) {
        mutate_state(function (array $state) use ($job): array {
            return set_loop_state($state, [
                'status' => 'queued',
                'jobId' => $job['jobId'],
                'mode' => $job['mode'] ?? 'background',
                'totalRounds' => (int)($job['rounds'] ?? 0),
                'completedRounds' => (int)($job['completedRounds'] ?? 0),
                'currentRound' => 0,
                'delayMs' => (int)($job['delayMs'] ?? 0),
                'cancelRequested' => false,
                'queuedAt' => $job['queuedAt'] ?? gmdate('c'),
                'startedAt' => null,
                'finishedAt' => null,
                'lastHeartbeatAt' => null,
                'lastMessage' => $job['lastMessage'] ?? 'Queued background loop.'
            ]);
        });
    }

    launch_background_php($runnerPath, ['--job-id=' . $job['jobId']]);
    append_step('autoloop', 'Background loop process launched.', [
        'taskId' => $job['taskId'] ?? null,
        'jobId' => $job['jobId'],
        'rounds' => $job['rounds'] ?? 0,
        'delayMs' => $job['delayMs'] ?? 0,
        'queuePosition' => $job['queuePosition'] ?? 0
    ]);
    return $job;
}

function create_loop_job(array $task, int $rounds, int $delayMs, string $mode = 'background', array $overrides = []): array {
    $jobId = 'job-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
    $queuedAt = gmdate('c');
    $queuePosition = max(0, (int)($overrides['queuePosition'] ?? 0));
    $updateLoopState = array_key_exists('updateLoopState', $overrides) ? (bool)$overrides['updateLoopState'] : true;
    $queuedMessage = (string)($overrides['lastMessage'] ?? ($queuePosition > 0 ? 'Queued behind another background loop.' : 'Queued background loop.'));
    $job = default_job([
        'jobId' => $jobId,
        'taskId' => $task['taskId'],
        'mode' => $mode,
        'status' => 'queued',
        'queuePosition' => $queuePosition,
        'attempt' => max(1, (int)($overrides['attempt'] ?? 1)),
        'resumeOfJobId' => $overrides['resumeOfJobId'] ?? null,
        'retryOfJobId' => $overrides['retryOfJobId'] ?? null,
        'resumeFromRound' => max(1, (int)($overrides['resumeFromRound'] ?? 1)),
        'rounds' => $rounds,
        'delayMs' => $delayMs,
        'workerCount' => count(task_workers($task)),
        'usage' => isset($overrides['usage']) && is_array($overrides['usage']) ? $overrides['usage'] : default_usage_state(),
        'queuedAt' => $queuedAt,
        'lastMessage' => $queuedMessage,
        'results' => isset($overrides['results']) && is_array($overrides['results']) ? $overrides['results'] : [],
        'completedRounds' => (int)($overrides['completedRounds'] ?? 0),
        'error' => $overrides['error'] ?? null,
    ]);
    write_job($job);

    if ($updateLoopState) {
        mutate_state(function (array $state) use ($jobId, $rounds, $delayMs, $queuedAt, $mode, $queuedMessage, $overrides): array {
            return set_loop_state($state, [
                'status' => 'queued',
                'jobId' => $jobId,
                'mode' => $mode,
                'totalRounds' => $rounds,
                'completedRounds' => (int)($overrides['completedRounds'] ?? 0),
                'currentRound' => 0,
                'delayMs' => $delayMs,
                'cancelRequested' => false,
                'queuedAt' => $queuedAt,
                'startedAt' => null,
                'finishedAt' => null,
                'lastHeartbeatAt' => null,
                'lastMessage' => $queuedMessage
            ]);
        });
    }

    append_step('autoloop', $queuePosition > 0 ? 'Background loop queued behind another job.' : 'Background loop queued.', [
        'taskId' => $task['taskId'],
        'jobId' => $jobId,
        'rounds' => $rounds,
        'delayMs' => $delayMs,
        'queuePosition' => $queuePosition,
        'resumeOfJobId' => $job['resumeOfJobId'],
        'retryOfJobId' => $job['retryOfJobId'],
        'resumeFromRound' => $job['resumeFromRound']
    ]);

    return $job;
}

function promote_next_queued_loop_job(?string $taskId, ?string $finishedJobId = null): ?array {
    $nextJob = with_lock(function () use ($taskId, $finishedJobId): ?array {
        $state = read_state_unlocked();
        $activeTaskId = $state['activeTask']['taskId'] ?? null;
        if ($taskId === null || !$activeTaskId || $activeTaskId !== $taskId) {
            return null;
        }

        $nextJob = find_next_queued_background_job_unlocked($taskId, $finishedJobId);
        if ($nextJob === null) {
            return null;
        }

        $nextJob = write_job_unlocked(array_merge($nextJob, [
            'status' => 'queued',
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Queued background loop.'
        ]));

        $state = set_loop_state($state, [
            'status' => 'queued',
            'jobId' => $nextJob['jobId'],
            'mode' => $nextJob['mode'] ?? 'background',
            'totalRounds' => (int)($nextJob['rounds'] ?? 0),
            'completedRounds' => (int)($nextJob['completedRounds'] ?? 0),
            'currentRound' => 0,
            'delayMs' => (int)($nextJob['delayMs'] ?? 0),
            'cancelRequested' => false,
            'queuedAt' => $nextJob['queuedAt'] ?? gmdate('c'),
            'startedAt' => null,
            'finishedAt' => null,
            'lastHeartbeatAt' => null,
            'lastMessage' => 'Queued background loop.'
        ]);
        write_state_unlocked($state);
        return $nextJob;
    });

    if ($nextJob === null) {
        return null;
    }

    try {
        return launch_loop_job_runner($nextJob, false);
    } catch (Throwable $ex) {
        mutate_job($nextJob['jobId'], function (?array $job) use ($ex): array {
            return default_job(array_merge($job ?? [], [
                'status' => 'error',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Queued background launch failed.',
                'error' => $ex->getMessage()
            ]));
        });
        mutate_state(function (array $state) use ($nextJob, $ex): array {
            $loop = current_loop_state($state);
            if (($loop['jobId'] ?? null) === $nextJob['jobId']) {
                return set_loop_state($state, [
                    'status' => 'error',
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => 'Queued background launch failed: ' . $ex->getMessage()
                ]);
            }
            return $state;
        });
        append_step('error', 'Failed to launch the next queued background loop.', [
            'taskId' => $nextJob['taskId'] ?? null,
            'jobId' => $nextJob['jobId'],
            'error' => $ex->getMessage()
        ]);
        return null;
    }
}

function execute_loop_process(array $config): array {
    $rounds = clamp_loop_rounds($config['rounds'] ?? 1);
    $delayMs = clamp_loop_delay_ms($config['delayMs'] ?? 0);
    $jobId = $config['jobId'] ?? null;
    $mode = $config['mode'] ?? 'sync';
    $taskId = $config['taskId'] ?? null;
    $startRound = max(1, min($rounds, (int)($config['startRound'] ?? 1)));
    $results = isset($config['results']) && is_array($config['results']) ? array_values($config['results']) : [];
    $completedRounds = max(0, (int)($config['completedRounds'] ?? 0));
    $cancelled = false;

    $startPatch = mutate_state(function (array $state) use ($taskId, $jobId, $mode, $rounds, $delayMs, $completedRounds, $startRound): array {
        $activeTaskId = $state['activeTask']['taskId'] ?? null;
        if (!$activeTaskId || $activeTaskId !== $taskId) {
            throw new RuntimeException('No active task.');
        }

        $loop = current_loop_state($state);
        return set_loop_state($state, [
            'status' => 'running',
            'jobId' => $jobId,
            'mode' => $mode,
            'totalRounds' => $rounds,
            'completedRounds' => $completedRounds,
            'delayMs' => $delayMs,
            'startedAt' => $loop['startedAt'] ?: gmdate('c'),
            'finishedAt' => null,
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Preparing round ' . $startRound . '.'
        ]);
    });

    if ($jobId !== null) {
        mutate_job($jobId, function (?array $job) use ($rounds, $delayMs, $startPatch, $startRound, $completedRounds): array {
            return default_job(array_merge($job ?? [], [
                'status' => 'running',
                'rounds' => $rounds,
                'delayMs' => $delayMs,
                'completedRounds' => $completedRounds,
                'startedAt' => current_loop_state($startPatch)['startedAt'],
                'finishedAt' => null,
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Preparing round ' . $startRound . '.'
            ]));
        });
    }

    append_step('autoloop', $jobId !== null ? 'Background loop runner claimed job.' : 'Autonomous loop started.', [
        'taskId' => $taskId,
        'jobId' => $jobId,
        'mode' => $mode,
        'rounds' => $rounds,
        'delayMs' => $delayMs
    ]);

    try {
        for ($round = $startRound; $round <= $rounds; $round++) {
            $snapshot = read_state();
            $currentTaskId = $snapshot['activeTask']['taskId'] ?? null;
            if (!$currentTaskId || $currentTaskId !== $taskId) {
                throw new RuntimeException('No active task.');
            }
            $task = $snapshot['activeTask'];
            $workerSequence = array_map(static function (array $worker): string {
                return (string)$worker['id'];
            }, task_workers($task, $round));
            $sequence = array_merge(['commander'], $workerSequence, ['commander_review', 'summarizer']);
            if (current_loop_state($snapshot)['cancelRequested']) {
                $cancelled = true;
                break;
            }

            mutate_state(function (array $state) use ($taskId, $round, $rounds): array {
                $activeTaskId = $state['activeTask']['taskId'] ?? null;
                if (!$activeTaskId || $activeTaskId !== $taskId) {
                    throw new RuntimeException('No active task.');
                }
                return set_loop_state($state, [
                    'status' => 'running',
                    'currentRound' => $round,
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => 'Running round ' . $round . ' of ' . $rounds . '.'
                ]);
            });

            if ($jobId !== null) {
                mutate_job($jobId, function (?array $job) use ($round): array {
                    return default_job(array_merge($job ?? [], [
                        'status' => 'running',
                        'currentRound' => $round,
                        'lastHeartbeatAt' => gmdate('c'),
                        'lastMessage' => 'Running round ' . $round . '.'
                    ]));
                });
            }

            append_step('autoloop', 'Starting autonomous round.', [
                'taskId' => $taskId,
                'jobId' => $jobId,
                'round' => $round,
                'totalRounds' => $rounds
            ]);

            $roundResult = [
                'round' => $round,
                'targets' => []
            ];

            foreach ($sequence as $target) {
                $targetResult = run_dispatch_target($target, $task);
                $roundResult['targets'][] = $targetResult;
                $usageSnapshot = read_state()['usage'] ?? default_usage_state();

                mutate_state(function (array $state) use ($taskId): array {
                    $activeTaskId = $state['activeTask']['taskId'] ?? null;
                    if (!$activeTaskId || $activeTaskId !== $taskId) {
                        throw new RuntimeException('No active task.');
                    }
                    return set_loop_state($state, [
                        'lastHeartbeatAt' => gmdate('c')
                    ]);
                });

                append_step('autoloop', 'Autonomous target completed.', [
                    'taskId' => $taskId,
                    'jobId' => $jobId,
                    'round' => $round,
                    'target' => $target,
                    'exitCode' => $targetResult['exitCode'],
                    'outputPreview' => $targetResult['output']
                ]);

                if ($jobId !== null) {
                    mutate_job($jobId, function (?array $job) use ($round, $usageSnapshot): array {
                        $currentStatus = is_array($job) && isset($job['status']) ? $job['status'] : 'running';
                        return default_job(array_merge($job ?? [], [
                            'status' => $currentStatus,
                            'currentRound' => $round,
                            'lastHeartbeatAt' => gmdate('c'),
                            'usage' => $usageSnapshot
                        ]));
                    });
                }
            }

            $results[] = $roundResult;
            $completedRounds = $round;

            mutate_state(function (array $state) use ($taskId, $round, $rounds): array {
                $activeTaskId = $state['activeTask']['taskId'] ?? null;
                if (!$activeTaskId || $activeTaskId !== $taskId) {
                    throw new RuntimeException('No active task.');
                }
                return set_loop_state($state, [
                    'status' => 'running',
                    'completedRounds' => $round,
                    'currentRound' => 0,
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => 'Completed round ' . $round . ' of ' . $rounds . '.'
                ]);
            });

            if ($jobId !== null) {
                $usageSnapshot = read_state()['usage'] ?? default_usage_state();
                mutate_job($jobId, function (?array $job) use ($round, $roundResult, $usageSnapshot): array {
                    $resultsList = $job['results'] ?? [];
                    $resultsList[] = $roundResult;
                    return default_job(array_merge($job ?? [], [
                        'status' => 'running',
                        'completedRounds' => $round,
                        'currentRound' => 0,
                        'lastHeartbeatAt' => gmdate('c'),
                        'lastMessage' => 'Completed round ' . $round . '.',
                        'results' => $resultsList,
                        'usage' => $usageSnapshot
                    ]));
                });
            }

            append_step('autoloop', 'Autonomous round completed.', [
                'taskId' => $taskId,
                'jobId' => $jobId,
                'round' => $round,
                'totalRounds' => $rounds
            ]);

            if ($round >= $rounds || $delayMs <= 0) {
                continue;
            }

            $remainingMs = $delayMs;
            while ($remainingMs > 0) {
                usleep(min(250, $remainingMs) * 1000);
                $remainingMs -= 250;
                $snapshot = read_state();
                $currentTaskId = $snapshot['activeTask']['taskId'] ?? null;
                if (!$currentTaskId || $currentTaskId !== $taskId) {
                    throw new RuntimeException('No active task.');
                }
                if (current_loop_state($snapshot)['cancelRequested']) {
                    $cancelled = true;
                    break 2;
                }
            }
        }

        $finalStatus = $cancelled ? 'cancelled' : 'completed';
        $finalMessage = $cancelled
            ? ('Cancelled after ' . $completedRounds . ' completed round(s).')
            : ('Completed ' . $completedRounds . ' round(s).');

        mutate_state(function (array $state) use ($taskId, $jobId, $mode, $rounds, $delayMs, $completedRounds, $finalStatus, $finalMessage): array {
            $activeTaskId = $state['activeTask']['taskId'] ?? null;
            if (!$activeTaskId || $activeTaskId !== $taskId) {
                throw new RuntimeException('No active task.');
            }
            return set_loop_state($state, [
                'status' => $finalStatus,
                'jobId' => $jobId,
                'mode' => $mode,
                'totalRounds' => $rounds,
                'completedRounds' => $completedRounds,
                'currentRound' => 0,
                'delayMs' => $delayMs,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => $finalMessage
            ]);
        });

        if ($jobId !== null) {
            $usageSnapshot = read_state()['usage'] ?? default_usage_state();
            mutate_job($jobId, function (?array $job) use ($finalStatus, $completedRounds, $finalMessage, $results, $usageSnapshot): array {
                return default_job(array_merge($job ?? [], [
                    'status' => $finalStatus,
                    'completedRounds' => $completedRounds,
                    'currentRound' => 0,
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => $finalMessage,
                    'results' => $results,
                    'usage' => $usageSnapshot
                ]));
            });
        }

        append_step('autoloop', $cancelled ? 'Autonomous loop cancelled.' : 'Autonomous loop completed.', [
            'taskId' => $taskId,
            'jobId' => $jobId,
            'completedRounds' => $completedRounds,
            'requestedRounds' => $rounds
        ]);

        if ($jobId !== null && $mode === 'background') {
            promote_next_queued_loop_job($taskId, $jobId);
        }

        return [
            'message' => $cancelled ? 'Loop cancelled.' : 'Loop completed.',
            'completedRounds' => $completedRounds,
            'requestedRounds' => $rounds,
            'cancelled' => $cancelled,
            'results' => $results
        ];
    } catch (Throwable $ex) {
        $isBudgetStop = stripos($ex->getMessage(), 'Budget limit reached:') === 0;
        $finalStatus = $isBudgetStop ? 'budget_exhausted' : 'error';
        $finalMessage = $isBudgetStop ? $ex->getMessage() : ('Loop error: ' . $ex->getMessage());

        mutate_state(function (array $state) use ($taskId, $jobId, $mode, $rounds, $delayMs, $completedRounds, $finalStatus, $finalMessage): array {
            $loopTaskId = $state['activeTask']['taskId'] ?? null;
            if ($loopTaskId && $loopTaskId === $taskId) {
                return set_loop_state($state, [
                    'status' => $finalStatus,
                    'jobId' => $jobId,
                    'mode' => $mode,
                    'totalRounds' => $rounds,
                    'completedRounds' => $completedRounds,
                    'currentRound' => 0,
                    'delayMs' => $delayMs,
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => $finalMessage
                ]);
            }
            return $state;
        });

        if ($jobId !== null) {
            $usageSnapshot = read_state()['usage'] ?? default_usage_state();
            mutate_job($jobId, function (?array $job) use ($completedRounds, $finalStatus, $finalMessage, $ex, $results, $usageSnapshot): array {
                return default_job(array_merge($job ?? [], [
                    'status' => $finalStatus,
                    'completedRounds' => $completedRounds,
                    'currentRound' => 0,
                    'finishedAt' => gmdate('c'),
                    'lastHeartbeatAt' => gmdate('c'),
                    'lastMessage' => $finalMessage,
                    'results' => $results,
                    'usage' => $usageSnapshot,
                    'error' => $ex->getMessage()
                ]));
            });
        }

        append_step($isBudgetStop ? 'budget' : 'error', $isBudgetStop ? 'Autonomous loop stopped at the configured budget limit.' : 'Autonomous loop failed.', [
            'taskId' => $taskId,
            'jobId' => $jobId,
            'completedRounds' => $completedRounds,
            'status' => $finalStatus,
            'error' => $ex->getMessage()
        ]);

        if ($jobId !== null && $mode === 'background') {
            promote_next_queued_loop_job($taskId, $jobId);
        }

        throw $ex;
    }
}
