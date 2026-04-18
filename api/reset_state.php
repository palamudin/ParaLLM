<?php
require __DIR__ . '/common.php';
ensure_data_paths();
write_state(default_state());
append_event('state_reset', []);
append_step('reset', 'State reset to defaults.', []);
json_response(['message' => 'State reset.']);
