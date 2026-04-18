<?php
require __DIR__ . '/common.php';
require __DIR__ . '/loop_runtime.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
if (empty($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is already active.'], 409);
}

try {
    $result = execute_loop_process([
        'taskId' => $state['activeTask']['taskId'],
        'mode' => 'manual',
        'rounds' => 1,
        'delayMs' => 0
    ]);
    $result['message'] = 'Round executed.';
    json_response($result);
} catch (Throwable $ex) {
    $isBudgetStop = stripos($ex->getMessage(), 'Budget limit reached:') === 0;
    append_step($isBudgetStop ? 'budget' : 'error', $isBudgetStop ? 'Round execution stopped at the configured budget limit.' : 'Round execution failed.', ['error' => $ex->getMessage()]);
    json_response(['message' => $ex->getMessage()], $isBudgetStop ? 409 : 500);
}
