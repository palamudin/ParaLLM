<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$authPath = ROOT_PATH . DIRECTORY_SEPARATOR . 'Auth.txt';
$clear = trim((string)post_value('clear', '')) === '1';
$apiKey = trim((string)post_value('apiKey', ''));

if ($clear) {
    file_put_contents($authPath, '', LOCK_EX);
    append_step('auth', 'Cleared the local API key file.', []);
    json_response([
        'ok' => true,
        'message' => 'Stored API key cleared.',
        'hasKey' => false,
        'last4' => '',
        'masked' => null
    ]);
}

if ($apiKey === '') {
    json_response([
        'error' => 'API key is required.'
    ], 400);
}

file_put_contents($authPath, $apiKey . PHP_EOL, LOCK_EX);
$last4 = strlen($apiKey) >= 4 ? substr($apiKey, -4) : $apiKey;
$masked = str_repeat('*', max(4, strlen($apiKey) - strlen($last4))) . $last4;

append_step('auth', 'Updated the local API key file.', []);
json_response([
    'ok' => true,
    'message' => 'Stored API key updated.',
    'hasKey' => true,
    'last4' => $last4,
    'masked' => $masked
]);
