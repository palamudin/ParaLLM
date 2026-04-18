<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (!loop_is_active($state)) {
    json_response(['message' => 'No autonomous loop is currently running.'], 400);
}

$loop = current_loop_state($state);
$taskId = $state['activeTask']['taskId'] ?? null;
$jobId = $loop['jobId'] ?? null;

if (($loop['status'] ?? 'idle') === 'queued') {
    $state = mutate_state(function (array $state): array {
        return set_loop_state($state, [
            'status' => 'cancelled',
            'cancelRequested' => true,
            'finishedAt' => gmdate('c'),
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Cancelled before the background loop started.'
        ]);
    });
    if ($jobId !== null) {
        mutate_job($jobId, function (?array $job): array {
            return default_job(array_merge($job ?? [], [
                'status' => 'cancelled',
                'cancelRequested' => true,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Cancelled before start.'
            ]));
        });
    }

    append_step('autoloop', 'Queued background loop cancelled before start.', [
        'taskId' => $taskId,
        'jobId' => $jobId
    ]);

    json_response(['message' => 'Queued loop cancelled before start.']);
}

$state = mutate_state(function (array $state): array {
    return set_loop_state($state, [
        'cancelRequested' => true,
        'lastHeartbeatAt' => gmdate('c'),
        'lastMessage' => 'Cancellation requested. The loop will stop after the current round.'
    ]);
});

if ($jobId !== null) {
    mutate_job($jobId, function (?array $job): array {
        return default_job(array_merge($job ?? [], [
            'cancelRequested' => true,
            'lastHeartbeatAt' => gmdate('c'),
            'lastMessage' => 'Cancellation requested.'
        ]));
    });
}

append_step('autoloop', 'Cancellation requested for the autonomous loop.', [
    'taskId' => $taskId,
    'jobId' => $jobId,
    'completedRounds' => current_loop_state($state)['completedRounds']
]);

json_response(['message' => 'Cancellation requested.']);
