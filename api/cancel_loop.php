<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = read_state();
if (!loop_is_running($state)) {
    json_response(['message' => 'No autonomous loop is currently running.'], 400);
}

$taskId = $state['activeTask']['taskId'] ?? null;
$state = mutate_state(function (array $state): array {
    return set_loop_state($state, [
        'cancelRequested' => true,
        'lastMessage' => 'Cancellation requested. The loop will stop after the current round.'
    ]);
});

append_step('autoloop', 'Cancellation requested for the autonomous loop.', [
    'taskId' => $taskId,
    'completedRounds' => current_loop_state($state)['completedRounds']
]);

json_response(['message' => 'Cancellation requested.']);
