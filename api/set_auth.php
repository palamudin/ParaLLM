<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$authPath = auth_file_path();
$clear = trim((string)post_value('clear', '')) === '1';
$appendKey = trim((string)post_value('appendKey', ''));
$apiKey = trim((string)post_value('apiKey', ''));
$replaceIndex = post_value('replaceIndex', null);
$removeIndex = post_value('removeIndex', null);
$apiKeys = normalize_auth_key_pool(post_value('apiKeys', post_value('apiKey', '')));

if ($clear) {
    write_auth_key_pool([], $authPath);
    append_step('auth', 'Cleared the local API key pool file.', []);
    json_response(array_merge([
        'ok' => true,
        'message' => 'Stored API key pool cleared.',
    ], auth_pool_status($authPath)));
}

if ($appendKey !== '') {
    $pool = read_auth_key_pool($authPath);
    $pool[] = $appendKey;
    write_auth_key_pool($pool, $authPath);
    append_step('auth', 'Appended one API key into the local key pool.', ['keyCount' => count($pool)]);
    json_response(array_merge([
        'ok' => true,
        'message' => 'Stored ' . count($pool) . ' API keys.',
    ], auth_pool_status($authPath)));
}

if ($replaceIndex !== null && $apiKey !== '') {
    $index = is_numeric($replaceIndex) ? (int)$replaceIndex : -1;
    $pool = read_auth_key_pool($authPath);
    if ($index < 0 || $index >= count($pool)) {
        json_response(['error' => 'Key slot is out of range.'], 400);
    }
    $pool[$index] = $apiKey;
    write_auth_key_pool($pool, $authPath);
    append_step('auth', 'Replaced one API key in the local key pool.', ['slot' => $index + 1, 'keyCount' => count($pool)]);
    json_response(array_merge([
        'ok' => true,
        'message' => 'Updated key slot ' . ($index + 1) . '.',
    ], auth_pool_status($authPath)));
}

if ($removeIndex !== null) {
    $index = is_numeric($removeIndex) ? (int)$removeIndex : -1;
    $pool = read_auth_key_pool($authPath);
    if ($index < 0 || $index >= count($pool)) {
        json_response(['error' => 'Key slot is out of range.'], 400);
    }
    array_splice($pool, $index, 1);
    write_auth_key_pool($pool, $authPath);
    append_step('auth', 'Removed one API key from the local key pool.', ['slot' => $index + 1, 'keyCount' => count($pool)]);
    json_response(array_merge([
        'ok' => true,
        'message' => $pool ? 'Stored ' . count($pool) . ' API keys.' : 'Stored API key pool cleared.',
    ], auth_pool_status($authPath)));
}

if (!$apiKeys) {
    json_response([
        'error' => 'At least one API key is required.'
    ], 400);
}

write_auth_key_pool($apiKeys, $authPath);

append_step('auth', 'Updated the local API key pool file.', ['keyCount' => count($apiKeys)]);
json_response(array_merge([
    'ok' => true,
    'message' => count($apiKeys) === 1 ? 'Stored 1 API key.' : 'Stored ' . count($apiKeys) . ' API keys.',
], auth_pool_status($authPath)));
