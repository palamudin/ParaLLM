<?php
header('Access-Control-Allow-Origin: *');

define('ROOT_PATH', dirname(__DIR__));
define('DATA_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'data');
define('PS_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'ps');
define('STATE_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'state.json');
define('EVENTS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'events.jsonl');
define('STEPS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'steps.jsonl');

function ensure_data_paths(): void {
    $paths = [
        DATA_PATH,
        DATA_PATH . DIRECTORY_SEPARATOR . 'tasks',
        DATA_PATH . DIRECTORY_SEPARATOR . 'checkpoints',
    ];
    foreach ($paths as $path) {
        if (!is_dir($path)) {
            mkdir($path, 0777, true);
        }
    }
    if (!file_exists(STATE_FILE)) {
        write_state(default_state());
    }
    if (!file_exists(EVENTS_FILE)) {
        file_put_contents(EVENTS_FILE, '');
    }
    if (!file_exists(STEPS_FILE)) {
        file_put_contents(STEPS_FILE, '');
    }
}

function default_state(): array {
    return [
        'activeTask' => null,
        'workers' => ['A' => null, 'B' => null],
        'summary' => null,
        'memoryVersion' => 0,
        'lastUpdated' => gmdate('c')
    ];
}

function read_state(): array {
    ensure_data_paths();
    $raw = @file_get_contents(STATE_FILE);
    if ($raw === false || trim($raw) === '') return default_state();
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : default_state();
}

function write_state(array $state): void {
    $state['lastUpdated'] = gmdate('c');
    file_put_contents(STATE_FILE, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
}

function append_event(string $type, array $payload = []): void {
    ensure_data_paths();
    $line = json_encode([
        'ts' => gmdate('c'),
        'type' => $type,
        'payload' => $payload
    ], JSON_UNESCAPED_SLASHES);
    file_put_contents(EVENTS_FILE, $line . PHP_EOL, FILE_APPEND);
}

function append_step(string $stage, string $message, array $context = []): void {
    ensure_data_paths();
    $line = json_encode([
        'ts' => gmdate('c'),
        'stage' => $stage,
        'message' => $message,
        'context' => $context
    ], JSON_UNESCAPED_SLASHES);
    file_put_contents(STEPS_FILE, $line . PHP_EOL, FILE_APPEND);
}

function json_response($data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

function post_value(string $key, $default = null) {
    return $_POST[$key] ?? $default;
}

function ps_command(string $scriptName): string {
    $scriptPath = PS_PATH . DIRECTORY_SEPARATOR . $scriptName;
    if (!file_exists($scriptPath)) {
        throw new RuntimeException('Script not found: ' . $scriptName);
    }
    $parts = [
        'powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $scriptPath,
        '-RootPath', ROOT_PATH
    ];
    $escaped = array_map('escapeshellarg', $parts);
    return implode(' ', $escaped) . ' 2>&1';
}
