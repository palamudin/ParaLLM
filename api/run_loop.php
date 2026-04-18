<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$rounds = (int)post_value('rounds', 3);
if ($rounds < 1) {
    $rounds = 1;
}
if ($rounds > 12) {
    $rounds = 12;
}

$delayMs = (int)post_value('delayMs', 1000);
if ($delayMs < 0) {
    $delayMs = 0;
}
if ($delayMs > 10000) {
    $delayMs = 10000;
}

$state = read_state();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_running($state)) {
    json_response(['message' => 'The autonomous loop is already running.'], 409);
}

$taskId = $state['activeTask']['taskId'] ?? null;
$sequence = ['A', 'B', 'summarizer'];
$results = [];
$completedRounds = 0;
$cancelled = false;

mutate_state(function (array $state) use ($rounds, $delayMs): array {
    $state['loop'] = array_merge(default_loop_state(), [
        'status' => 'running',
        'totalRounds' => $rounds,
        'completedRounds' => 0,
        'currentRound' => 0,
        'delayMs' => $delayMs,
        'cancelRequested' => false,
        'startedAt' => gmdate('c'),
        'finishedAt' => null,
        'lastMessage' => 'Preparing round 1.'
    ]);
    return $state;
});

append_step('autoloop', 'Autonomous loop started.', [
    'taskId' => $taskId,
    'rounds' => $rounds,
    'delayMs' => $delayMs
]);

try {
    for ($round = 1; $round <= $rounds; $round++) {
        $snapshot = read_state();
        if (current_loop_state($snapshot)['cancelRequested']) {
            $cancelled = true;
            break;
        }

        mutate_state(function (array $state) use ($round, $rounds): array {
            return set_loop_state($state, [
                'status' => 'running',
                'currentRound' => $round,
                'lastMessage' => 'Running round ' . $round . ' of ' . $rounds . '.'
            ]);
        });

        append_step('autoloop', 'Starting autonomous round.', [
            'taskId' => $taskId,
            'round' => $round,
            'totalRounds' => $rounds
        ]);

        $roundResult = [
            'round' => $round,
            'targets' => []
        ];

        foreach ($sequence as $target) {
            $targetResult = run_powershell_target($target);
            $roundResult['targets'][] = $targetResult;
            append_step('autoloop', 'Autonomous target completed.', [
                'taskId' => $taskId,
                'round' => $round,
                'target' => $target,
                'exitCode' => $targetResult['exitCode'],
                'outputPreview' => $targetResult['output']
            ]);
        }

        $results[] = $roundResult;
        $completedRounds = $round;

        mutate_state(function (array $state) use ($round, $rounds): array {
            return set_loop_state($state, [
                'status' => 'running',
                'completedRounds' => $round,
                'currentRound' => 0,
                'lastMessage' => 'Completed round ' . $round . ' of ' . $rounds . '.'
            ]);
        });

        append_step('autoloop', 'Autonomous round completed.', [
            'taskId' => $taskId,
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

    mutate_state(function (array $state) use ($rounds, $delayMs, $completedRounds, $finalStatus, $finalMessage): array {
        return set_loop_state($state, [
            'status' => $finalStatus,
            'totalRounds' => $rounds,
            'completedRounds' => $completedRounds,
            'currentRound' => 0,
            'delayMs' => $delayMs,
            'finishedAt' => gmdate('c'),
            'lastMessage' => $finalMessage
        ]);
    });

    append_step('autoloop', $cancelled ? 'Autonomous loop cancelled.' : 'Autonomous loop completed.', [
        'taskId' => $taskId,
        'completedRounds' => $completedRounds,
        'requestedRounds' => $rounds
    ]);

    json_response([
        'message' => $cancelled ? 'Loop cancelled.' : 'Loop completed.',
        'completedRounds' => $completedRounds,
        'requestedRounds' => $rounds,
        'cancelled' => $cancelled,
        'results' => $results
    ]);
} catch (Throwable $ex) {
    mutate_state(function (array $state) use ($rounds, $delayMs, $completedRounds, $ex): array {
        return set_loop_state($state, [
            'status' => 'error',
            'totalRounds' => $rounds,
            'completedRounds' => $completedRounds,
            'currentRound' => 0,
            'delayMs' => $delayMs,
            'finishedAt' => gmdate('c'),
            'lastMessage' => 'Loop error: ' . $ex->getMessage()
        ]);
    });

    append_step('error', 'Autonomous loop failed.', [
        'taskId' => $taskId,
        'completedRounds' => $completedRounds,
        'error' => $ex->getMessage()
    ]);

    json_response(['message' => $ex->getMessage()], 500);
}
