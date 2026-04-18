<?php
require __DIR__ . '/common.php';
ensure_data_paths();
json_response(try_recover_loop_state_if_needed());
