<?php
require __DIR__ . '/common.php';
require __DIR__ . '/dispatch_runtime.php';
ensure_data_paths();
recover_dispatch_jobs_if_needed();
$state = try_recover_loop_state_if_needed();
$state['dispatch'] = current_dispatch_state($state);
json_response($state);
