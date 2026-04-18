<?php
require __DIR__ . '/common.php';
ensure_data_paths();
header('Content-Type: text/plain; charset=utf-8');
if (!file_exists(EVENTS_FILE)) {
    echo 'No events.';
    exit;
}
$lines = file(EVENTS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
if (!$lines) {
    echo 'No events.';
    exit;
}
$lines = array_reverse(array_slice($lines, -100));
echo implode(PHP_EOL, $lines);
