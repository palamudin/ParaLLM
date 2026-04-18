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

function create_loop_job(array $task, int $rounds, int $delayMs, string $mode = 'background'): array {
    $jobId = 'job-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);
    $queuedAt = gmdate('c');
    $job = default_job([
        'jobId' => $jobId,
        'taskId' => $task['taskId'],
        'mode' => $mode,
        'status' => 'queued',
        'rounds' => $rounds,
        'delayMs' => $delayMs,
        'workerCount' => count(task_workers($task)),
        'usage' => default_usage_state(),
        'queuedAt' => $queuedAt,
        'lastMessage' => 'Queued background loop.'
    ]);
    write_job($job);

    mutate_state(function (array $state) use ($jobId, $rounds, $delayMs, $queuedAt, $mode): array {
        return set_loop_state($state, [
            'status' => 'queued',
            'jobId' => $jobId,
            'mode' => $mode,
            'totalRounds' => $rounds,
            'completedRounds' => 0,
            'currentRound' => 0,
            'delayMs' => $delayMs,
            'cancelRequested' => false,
            'queuedAt' => $queuedAt,
            'startedAt' => null,
            'finishedAt' => null,
            'lastHeartbeatAt' => null,
            'lastMessage' => 'Queued background loop.'
        ]);
    });

    append_step('autoloop', 'Background loop queued.', [
        'taskId' => $task['taskId'],
        'jobId' => $jobId,
        'rounds' => $rounds,
        'delayMs' => $delayMs
    ]);

    return $job;
}

function execute_loop_process(array $config): array {
    $rounds = clamp_loop_rounds($config['rounds'] ?? 1);
    $delayMs = clamp_loop_delay_ms($config['delayMs'] ?? 0);
    $jobId = $config['jobId'] ?? null;
    $mode = $config['mode'] ?? 'sync';
    $taskId = $config['taskId'] ?? null;
    $results = [];
    $completedRounds = 0;
    $cancelled = false;

    $startPatch = mutate_state(function (array $state) use ($taskId, $jobId, $mode, $rounds, $delayMs): array {
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
            'delayMs' => $delayMs,
            'startedAt' => $loop['startedAt'] ?: gmdate('c'),
            'finishedAt' => null,
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Preparing round 1.'
        ]);
    });

    if ($jobId !== null) {
        mutate_job($jobId, function (?array $job) use ($rounds, $delayMs, $startPatch): array {
            return default_job(array_merge($job ?? [], [
                'status' => 'running',
                'rounds' => $rounds,
                'delayMs' => $delayMs,
                'startedAt' => current_loop_state($startPatch)['startedAt'],
                'finishedAt' => null,
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Preparing round 1.'
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
        for ($round = 1; $round <= $rounds; $round++) {
            $snapshot = read_state();
            $currentTaskId = $snapshot['activeTask']['taskId'] ?? null;
            if (!$currentTaskId || $currentTaskId !== $taskId) {
                throw new RuntimeException('No active task.');
            }
            $task = $snapshot['activeTask'];
            $workerSequence = array_map(static function (array $worker): string {
                return (string)$worker['id'];
            }, task_workers($task));
            $sequence = array_merge($workerSequence, ['summarizer']);
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
                $targetResult = run_powershell_target($target, $task);
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

        throw $ex;
    }
}
