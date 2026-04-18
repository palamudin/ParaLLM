<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$authPath = ROOT_PATH . DIRECTORY_SEPARATOR . 'Auth.txt';
$key = '';
if (file_exists($authPath)) {
    $key = trim((string)file_get_contents($authPath));
}

$last4 = strlen($key) >= 4 ? substr($key, -4) : $key;
$masked = $key !== '' ? str_repeat('*', max(4, strlen($key) - strlen($last4))) . $last4 : null;

json_response([
    'hasKey' => $key !== '',
    'last4' => $last4,
    'masked' => $masked
]);
