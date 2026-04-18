<?php
header('Access-Control-Allow-Origin: *');

define('ROOT_PATH', dirname(__DIR__));
define('DATA_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'data');
define('TASKS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'tasks');
define('CHECKPOINTS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'checkpoints');
define('LOCKS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'locks');
define('PS_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'ps');
define('STATE_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'state.json');
define('EVENTS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'events.jsonl');
define('STEPS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'steps.jsonl');
define('LOCK_TIMEOUT_MS', 15000);
define('LOCK_STALE_SECONDS', 900);

function default_loop_state(): array {
    return [
        'status' => 'idle',
        'totalRounds' => 0,
        'completedRounds' => 0,
        'currentRound' => 0,
        'delayMs' => 0,
        'cancelRequested' => false,
        'startedAt' => null,
        'finishedAt' => null,
        'lastMessage' => 'Ready.'
    ];
}

function default_state(): array {
    return [
        'activeTask' => null,
        'workers' => ['A' => null, 'B' => null],
        'summary' => null,
        'memoryVersion' => 0,
        'loop' => default_loop_state(),
        'lastUpdated' => gmdate('c')
    ];
}

function normalize_state(array $state): array {
    $normalized = default_state();
    $normalized['activeTask'] = $state['activeTask'] ?? null;
    $normalized['summary'] = $state['summary'] ?? null;
    $normalized['memoryVersion'] = isset($state['memoryVersion']) ? (int)$state['memoryVersion'] : 0;
    $normalized['lastUpdated'] = $state['lastUpdated'] ?? gmdate('c');

    if (isset($state['workers']) && is_array($state['workers'])) {
        $normalized['workers'] = array_merge(['A' => null, 'B' => null], $state['workers']);
    }

    if (isset($state['loop']) && is_array($state['loop'])) {
        $normalized['loop'] = array_merge(default_loop_state(), $state['loop']);
    }

    return $normalized;
}

function ensure_data_paths(): void {
    $paths = [
        DATA_PATH,
        TASKS_PATH,
        CHECKPOINTS_PATH,
        LOCKS_PATH,
    ];

    foreach ($paths as $path) {
        if (!is_dir($path)) {
            mkdir($path, 0777, true);
        }
    }

    if (!file_exists(STATE_FILE)) {
        file_put_contents(STATE_FILE, json_encode(default_state(), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    }
    if (!file_exists(EVENTS_FILE)) {
        file_put_contents(EVENTS_FILE, '');
    }
    if (!file_exists(STEPS_FILE)) {
        file_put_contents(STEPS_FILE, '');
    }
}

function lock_path(string $lockName = 'loop'): string {
    return LOCKS_PATH . DIRECTORY_SEPARATOR . $lockName . '.lock';
}

function remove_tree(string $path): void {
    if (!file_exists($path)) {
        return;
    }
    if (is_file($path) || is_link($path)) {
        @unlink($path);
        return;
    }
    $items = scandir($path);
    if (is_array($items)) {
        foreach ($items as $item) {
            if ($item === '.' || $item === '..') {
                continue;
            }
            remove_tree($path . DIRECTORY_SEPARATOR . $item);
        }
    }
    @rmdir($path);
}

function lock_is_stale(string $lockPath, int $staleSeconds = LOCK_STALE_SECONDS): bool {
    if (!is_dir($lockPath)) {
        return false;
    }
    $mtime = @filemtime($lockPath);
    if ($mtime === false) {
        return false;
    }
    return (time() - $mtime) > $staleSeconds;
}

function with_lock(callable $callback, int $timeoutMs = LOCK_TIMEOUT_MS, string $lockName = 'loop') {
    ensure_data_paths();
    $lockPath = lock_path($lockName);
    $deadline = microtime(true) + ($timeoutMs / 1000);

    do {
        if (@mkdir($lockPath, 0777)) {
            $meta = [
                'pid' => getmypid(),
                'ts' => gmdate('c')
            ];
            @file_put_contents($lockPath . DIRECTORY_SEPARATOR . 'owner.json', json_encode($meta, JSON_UNESCAPED_SLASHES));
            try {
                return $callback();
            } finally {
                remove_tree($lockPath);
            }
        }

        if (lock_is_stale($lockPath)) {
            remove_tree($lockPath);
            continue;
        }

        usleep(100000);
    } while (microtime(true) < $deadline);

    throw new RuntimeException('Timed out acquiring loop lock.');
}

function read_state_unlocked(): array {
    ensure_data_paths();
    $raw = @file_get_contents(STATE_FILE);
    if ($raw === false || trim($raw) === '') {
        return default_state();
    }
    if (strncmp($raw, "\xEF\xBB\xBF", 3) === 0) {
        $raw = substr($raw, 3);
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? normalize_state($decoded) : default_state();
}

function read_state(): array {
    return with_lock(function (): array {
        return read_state_unlocked();
    });
}

function write_state_unlocked(array $state): void {
    $state = normalize_state($state);
    $state['lastUpdated'] = gmdate('c');
    file_put_contents(STATE_FILE, json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
}

function write_state(array $state): void {
    with_lock(function () use ($state): void {
        write_state_unlocked($state);
    });
}

function mutate_state(callable $callback): array {
    return with_lock(function () use ($callback): array {
        $state = read_state_unlocked();
        $next = $callback($state);
        if (!is_array($next)) {
            $next = $state;
        }
        write_state_unlocked($next);
        return normalize_state($next);
    });
}

function append_event(string $type, array $payload = []): void {
    ensure_data_paths();
    $line = json_encode([
        'ts' => gmdate('c'),
        'type' => $type,
        'payload' => $payload
    ], JSON_UNESCAPED_SLASHES);

    with_lock(function () use ($line): void {
        file_put_contents(EVENTS_FILE, $line . PHP_EOL, FILE_APPEND);
    });
}

function append_step(string $stage, string $message, array $context = []): void {
    ensure_data_paths();
    $line = json_encode([
        'ts' => gmdate('c'),
        'stage' => $stage,
        'message' => $message,
        'context' => $context
    ], JSON_UNESCAPED_SLASHES);

    with_lock(function () use ($line): void {
        file_put_contents(STEPS_FILE, $line . PHP_EOL, FILE_APPEND);
    });
}

function current_loop_state(array $state): array {
    return array_merge(default_loop_state(), is_array($state['loop'] ?? null) ? $state['loop'] : []);
}

function set_loop_state(array $state, array $patch): array {
    $state = normalize_state($state);
    $state['loop'] = array_merge(current_loop_state($state), $patch);
    return $state;
}

function loop_is_running(array $state): bool {
    return (current_loop_state($state)['status'] ?? 'idle') === 'running';
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

function target_map(): array {
    return [
        'A' => 'workerA.ps1',
        'B' => 'workerB.ps1',
        'summarizer' => 'summarizer.ps1'
    ];
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

function run_powershell_target(string $target): array {
    $map = target_map();
    if (!isset($map[$target])) {
        throw new RuntimeException('Invalid target.');
    }

    $cmd = ps_command($map[$target]);
    $lines = [];
    $exitCode = 0;
    exec($cmd, $lines, $exitCode);
    $output = trim(implode(PHP_EOL, $lines));

    append_event('powershell_run', [
        'target' => $target,
        'exitCode' => $exitCode,
        'output' => $output
    ]);

    if ($exitCode !== 0) {
        throw new RuntimeException($output !== '' ? $output : ('Target ' . $target . ' failed.'));
    }

    return [
        'target' => $target,
        'output' => $output,
        'exitCode' => $exitCode
    ];
}
