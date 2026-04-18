<?php
require __DIR__ . '/common.php';
ensure_data_paths();
header('Content-Type: text/plain; charset=utf-8');
if (!file_exists(STEPS_FILE)) {
    echo 'No steps.';
    exit;
}
$lines = file(STEPS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
if (!$lines) {
    echo 'No steps.';
    exit;
}
$lines = array_reverse(array_slice($lines, -150));
echo implode(PHP_EOL, $lines);
