<?php
header('Access-Control-Allow-Origin: *');

define('ROOT_PATH', dirname(__DIR__));
define('DATA_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'data');
define('TASKS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'tasks');
define('CHECKPOINTS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'checkpoints');
define('JOBS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'jobs');
define('LOCKS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'locks');
define('PS_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'ps');
define('STATE_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'state.json');
define('EVENTS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'events.jsonl');
define('STEPS_FILE', DATA_PATH . DIRECTORY_SEPARATOR . 'steps.jsonl');
define('LOCK_TIMEOUT_MS', 15000);
define('LOCK_STALE_SECONDS', 45);
define('JOB_QUEUE_STALE_SECONDS', 60);
define('JOB_RUNNING_STALE_SECONDS', 180);

function default_loop_state(): array {
    return [
        'status' => 'idle',
        'jobId' => null,
        'mode' => 'manual',
        'totalRounds' => 0,
        'completedRounds' => 0,
        'currentRound' => 0,
        'delayMs' => 0,
        'cancelRequested' => false,
        'queuedAt' => null,
        'startedAt' => null,
        'finishedAt' => null,
        'lastHeartbeatAt' => null,
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
        JOBS_PATH,
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

function loop_status(array $state): string {
    return (string)(current_loop_state($state)['status'] ?? 'idle');
}

function loop_is_running(array $state): bool {
    return loop_status($state) === 'running';
}

function loop_is_active(array $state): bool {
    return in_array(loop_status($state), ['queued', 'running'], true);
}

function task_file_path(string $taskId): string {
    return TASKS_PATH . DIRECTORY_SEPARATOR . $taskId . '.json';
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

function job_file_path(string $jobId): string {
    return JOBS_PATH . DIRECTORY_SEPARATOR . $jobId . '.json';
}

function read_job_unlocked(string $jobId): ?array {
    $path = job_file_path($jobId);
    if (!file_exists($path)) {
        return null;
    }
    $raw = @file_get_contents($path);
    if ($raw === false || trim($raw) === '') {
        return null;
    }
    if (strncmp($raw, "\xEF\xBB\xBF", 3) === 0) {
        $raw = substr($raw, 3);
    }
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
}

function write_job_unlocked(array $job): array {
    $normalized = default_job($job);
    file_put_contents(
        job_file_path($normalized['jobId']),
        json_encode($normalized, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
    );
    return $normalized;
}

function default_job(array $config): array {
    return [
        'jobId' => $config['jobId'],
        'taskId' => $config['taskId'],
        'mode' => $config['mode'] ?? 'background',
        'status' => $config['status'] ?? 'queued',
        'rounds' => (int)$config['rounds'],
        'delayMs' => (int)$config['delayMs'],
        'cancelRequested' => (bool)($config['cancelRequested'] ?? false),
        'queuedAt' => $config['queuedAt'] ?? gmdate('c'),
        'startedAt' => $config['startedAt'] ?? null,
        'finishedAt' => $config['finishedAt'] ?? null,
        'lastHeartbeatAt' => $config['lastHeartbeatAt'] ?? null,
        'completedRounds' => (int)($config['completedRounds'] ?? 0),
        'currentRound' => (int)($config['currentRound'] ?? 0),
        'lastMessage' => $config['lastMessage'] ?? 'Queued.',
        'results' => $config['results'] ?? [],
        'error' => $config['error'] ?? null
    ];
}

function read_job(string $jobId): ?array {
    return with_lock(function () use ($jobId): ?array {
        return read_job_unlocked($jobId);
    });
}

function write_job(array $job): array {
    $normalized = default_job($job);
    with_lock(function () use ($normalized): void {
        write_job_unlocked($normalized);
    });
    return $normalized;
}

function mutate_job(string $jobId, callable $callback): ?array {
    return with_lock(function () use ($jobId, $callback): ?array {
        $existing = read_job_unlocked($jobId);
        $next = $callback($existing);
        if ($next === null) {
            return $existing;
        }
        return write_job_unlocked($next);
    });
}

function parse_job_ts(?string $value): ?int {
    if (!is_string($value) || trim($value) === '') {
        return null;
    }
    $ts = strtotime($value);
    return $ts === false ? null : $ts;
}

function recover_loop_state_if_needed(): array {
    return with_lock(function (): array {
        $state = read_state_unlocked();
        $loop = current_loop_state($state);
        $status = $loop['status'] ?? 'idle';

        if (!in_array($status, ['queued', 'running'], true)) {
            return $state;
        }

        $jobId = $loop['jobId'] ?? null;
        if (!is_string($jobId) || $jobId === '') {
            $state = set_loop_state($state, [
                'status' => 'error',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Loop recovery failed: missing background job metadata.'
            ]);
            write_state_unlocked($state);
            return $state;
        }

        $job = read_job_unlocked($jobId);
        if ($job === null) {
            $state = set_loop_state($state, [
                'status' => 'error',
                'jobId' => $jobId,
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => 'Loop recovery failed: background job record is missing.'
            ]);
            write_state_unlocked($state);
            return $state;
        }

        $jobStatus = $job['status'] ?? 'queued';
        $now = time();
        $queueTs = parse_job_ts($job['queuedAt'] ?? null);
        $heartbeatTs = parse_job_ts($job['lastHeartbeatAt'] ?? null)
            ?? parse_job_ts($job['startedAt'] ?? null)
            ?? $queueTs;
        $queueStale = $jobStatus === 'queued' && $queueTs !== null && ($now - $queueTs) > JOB_QUEUE_STALE_SECONDS;
        $runStale = $jobStatus === 'running' && $heartbeatTs !== null && ($now - $heartbeatTs) > JOB_RUNNING_STALE_SECONDS;

        if ($queueStale || $runStale) {
            $message = $queueStale
                ? 'Recovered a stale queued background loop.'
                : 'Recovered a stale running background loop.';

            $job = write_job_unlocked(array_merge($job, [
                'status' => 'error',
                'finishedAt' => gmdate('c'),
                'lastHeartbeatAt' => gmdate('c'),
                'lastMessage' => $message,
                'error' => $message
            ]));

            $state = set_loop_state($state, [
                'status' => 'error',
                'jobId' => $jobId,
                'mode' => $job['mode'] ?? ($loop['mode'] ?? 'background'),
                'totalRounds' => (int)($job['rounds'] ?? ($loop['totalRounds'] ?? 0)),
                'completedRounds' => (int)($job['completedRounds'] ?? ($loop['completedRounds'] ?? 0)),
                'currentRound' => 0,
                'delayMs' => (int)($job['delayMs'] ?? ($loop['delayMs'] ?? 0)),
                'cancelRequested' => (bool)($job['cancelRequested'] ?? false),
                'queuedAt' => $job['queuedAt'] ?? null,
                'startedAt' => $job['startedAt'] ?? null,
                'finishedAt' => $job['finishedAt'] ?? gmdate('c'),
                'lastHeartbeatAt' => $job['lastHeartbeatAt'] ?? gmdate('c'),
                'lastMessage' => $message
            ]);
            write_state_unlocked($state);

            $line = json_encode([
                'ts' => gmdate('c'),
                'stage' => 'recovery',
                'message' => $message,
                'context' => [
                    'jobId' => $jobId,
                    'taskId' => $job['taskId'] ?? null,
                    'previousStatus' => $jobStatus
                ]
            ], JSON_UNESCAPED_SLASHES);
            file_put_contents(STEPS_FILE, $line . PHP_EOL, FILE_APPEND);

            return $state;
        }

        if (in_array($jobStatus, ['completed', 'cancelled', 'error'], true) || $status !== $jobStatus) {
            $state = set_loop_state($state, [
                'status' => $jobStatus,
                'jobId' => $jobId,
                'mode' => $job['mode'] ?? ($loop['mode'] ?? 'background'),
                'totalRounds' => (int)($job['rounds'] ?? ($loop['totalRounds'] ?? 0)),
                'completedRounds' => (int)($job['completedRounds'] ?? ($loop['completedRounds'] ?? 0)),
                'currentRound' => (int)($job['currentRound'] ?? 0),
                'delayMs' => (int)($job['delayMs'] ?? ($loop['delayMs'] ?? 0)),
                'cancelRequested' => (bool)($job['cancelRequested'] ?? false),
                'queuedAt' => $job['queuedAt'] ?? ($loop['queuedAt'] ?? null),
                'startedAt' => $job['startedAt'] ?? ($loop['startedAt'] ?? null),
                'finishedAt' => $job['finishedAt'] ?? ($loop['finishedAt'] ?? null),
                'lastHeartbeatAt' => $job['lastHeartbeatAt'] ?? ($loop['lastHeartbeatAt'] ?? null),
                'lastMessage' => $job['lastMessage'] ?? ($loop['lastMessage'] ?? 'Ready.')
            ]);
            write_state_unlocked($state);
        }

        return $state;
    });
}

function try_recover_loop_state_if_needed(): array {
    try {
        return recover_loop_state_if_needed();
    } catch (Throwable $ex) {
        $state = read_state_unlocked();
        $loop = current_loop_state($state);
        $loop['lastMessage'] = ($loop['lastMessage'] ?? 'Ready.') . ' Recovery check deferred: ' . $ex->getMessage();
        $state['loop'] = $loop;
        return $state;
    }
}

function php_cli_path(): string {
    $candidates = [
        dirname(dirname(ROOT_PATH)) . DIRECTORY_SEPARATOR . 'php' . DIRECTORY_SEPARATOR . 'php.exe',
        PHP_BINARY,
    ];

    foreach ($candidates as $candidate) {
        if (is_string($candidate) && $candidate !== '' && file_exists($candidate)) {
            return $candidate;
        }
    }

    throw new RuntimeException('Unable to locate PHP CLI executable.');
}

function launch_background_php(string $scriptPath, array $args = []): void {
    $phpPath = php_cli_path();
    $argumentList = array_merge([$scriptPath], $args);
    $psArgs = implode(', ', array_map(static function (string $value): string {
        return "'" . str_replace("'", "''", $value) . "'";
    }, $argumentList));

    $psScript = '$php=' . "'" . str_replace("'", "''", $phpPath) . "';" .
        '$args=@(' . $psArgs . ');' .
        'Start-Process -WindowStyle Hidden -FilePath $php -ArgumentList $args';

    $cmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ' . escapeshellarg($psScript) . ' 2>&1';
    $output = shell_exec($cmd);
    if ($output !== null && stripos($output, 'Start-Process') !== false && stripos($output, 'error') !== false) {
        throw new RuntimeException(trim($output));
    }
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
