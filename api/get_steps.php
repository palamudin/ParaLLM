<?php
require __DIR__ . '/common.php';
ensure_data_paths();
header('Content-Type: text/plain; charset=utf-8');
$lines = with_lock(function (): array {
    if (!file_exists(STEPS_FILE)) {
        return [];
    }
    $read = file(STEPS_FILE, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    return is_array($read) ? $read : [];
});
if (!$lines) {
    echo 'No steps.';
    exit;
}
$lines = array_reverse(array_slice($lines, -150));
echo implode(PHP_EOL, $lines);
