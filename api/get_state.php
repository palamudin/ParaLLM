<?php
require __DIR__ . '/common.php';
ensure_data_paths();
json_response(read_state());
