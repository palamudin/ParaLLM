<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = read_state();
if (loop_is_running($state)) {
    json_response(['message' => 'An autonomous loop is running. Cancel it before resetting state.'], 409);
}

write_state(default_state());
append_event('state_reset', []);
append_step('reset', 'State reset to defaults.', []);
json_response(['message' => 'State reset.']);
