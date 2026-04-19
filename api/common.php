<?php
header('Access-Control-Allow-Origin: *');

define('ROOT_PATH', dirname(__DIR__));
define('DATA_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'data');
define('TASKS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'tasks');
define('CHECKPOINTS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'checkpoints');
define('OUTPUTS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'outputs');
define('SESSIONS_PATH', DATA_PATH . DIRECTORY_SEPARATOR . 'sessions');
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

function default_model_catalog(): array {
    return [
        'gpt-5.4' => ['label' => 'GPT-5.4', 'inputPer1M' => 2.50, 'cachedInputPer1M' => 0.25, 'outputPer1M' => 15.00],
        'gpt-5.4-mini' => ['label' => 'GPT-5.4 mini', 'inputPer1M' => 0.75, 'cachedInputPer1M' => 0.075, 'outputPer1M' => 4.50],
        'gpt-5.4-nano' => ['label' => 'GPT-5.4 nano', 'inputPer1M' => 0.20, 'cachedInputPer1M' => 0.02, 'outputPer1M' => 1.25],
        'gpt-5.2' => ['label' => 'GPT-5.2', 'inputPer1M' => 1.75, 'cachedInputPer1M' => 0.175, 'outputPer1M' => 14.00],
        'gpt-5.1' => ['label' => 'GPT-5.1', 'inputPer1M' => 1.25, 'cachedInputPer1M' => 0.125, 'outputPer1M' => 10.00],
        'gpt-5' => ['label' => 'GPT-5', 'inputPer1M' => 1.25, 'cachedInputPer1M' => 0.125, 'outputPer1M' => 10.00],
        'gpt-5-mini' => ['label' => 'GPT-5 mini', 'inputPer1M' => 0.25, 'cachedInputPer1M' => 0.025, 'outputPer1M' => 2.00],
        'gpt-5-nano' => ['label' => 'GPT-5 nano', 'inputPer1M' => 0.05, 'cachedInputPer1M' => 0.005, 'outputPer1M' => 0.40],
        'gpt-4.1' => ['label' => 'GPT-4.1', 'inputPer1M' => 2.00, 'cachedInputPer1M' => 0.50, 'outputPer1M' => 8.00],
        'gpt-4.1-mini' => ['label' => 'GPT-4.1 mini', 'inputPer1M' => 0.40, 'cachedInputPer1M' => 0.10, 'outputPer1M' => 1.60],
        'gpt-4.1-nano' => ['label' => 'GPT-4.1 nano', 'inputPer1M' => 0.10, 'cachedInputPer1M' => 0.025, 'outputPer1M' => 0.40],
        'gpt-4o' => ['label' => 'GPT-4o', 'inputPer1M' => 2.50, 'cachedInputPer1M' => 1.25, 'outputPer1M' => 10.00],
        'gpt-4o-mini' => ['label' => 'GPT-4o mini', 'inputPer1M' => 0.15, 'cachedInputPer1M' => 0.075, 'outputPer1M' => 0.60],
    ];
}

function default_model_id(): string {
    return 'gpt-5-mini';
}

function default_draft_state(): array {
    $budget = default_budget_config();
    $model = default_model_id();
    return [
        'objective' => '',
        'constraints' => [],
        'sessionContext' => '',
        'executionMode' => 'live',
        'model' => $model,
        'summarizerModel' => $model,
        'reasoningEffort' => 'low',
        'maxTotalTokens' => $budget['maxTotalTokens'],
        'maxCostUsd' => $budget['maxCostUsd'],
        'maxOutputTokens' => $budget['maxOutputTokens'],
        'researchEnabled' => false,
        'researchExternalWebAccess' => true,
        'researchDomains' => [],
        'vettingEnabled' => true,
        'updatedAt' => gmdate('c')
    ];
}

function default_budget_config(): array {
    return [
        'maxTotalTokens' => 250000,
        'maxCostUsd' => 5.00,
        'maxOutputTokens' => 1200,
    ];
}

function coerce_bool($value, bool $default = false): bool {
    if (is_bool($value)) {
        return $value;
    }
    if (is_int($value) || is_float($value)) {
        return ((int)$value) !== 0;
    }
    if (is_string($value)) {
        $normalized = strtolower(trim($value));
        if ($normalized === '') {
            return $default;
        }
        if (in_array($normalized, ['1', 'true', 'yes', 'on'], true)) {
            return true;
        }
        if (in_array($normalized, ['0', 'false', 'no', 'off'], true)) {
            return false;
        }
    }
    return $default;
}

function normalize_string_list($value): array {
    $items = [];
    if (is_array($value)) {
        foreach ($value as $entry) {
            foreach (normalize_string_list($entry) as $normalized) {
                $items[] = $normalized;
            }
        }
    } elseif (is_string($value)) {
        foreach (preg_split('/[\r\n,]+/', $value) ?: [] as $entry) {
            $entry = trim($entry);
            if ($entry !== '') {
                $items[] = $entry;
            }
        }
    }

    $deduped = [];
    foreach ($items as $item) {
        $deduped[$item] = true;
    }
    return array_keys($deduped);
}

function normalize_allowed_domains($value): array {
    $domains = [];
    foreach (normalize_string_list($value) as $entry) {
        $entry = preg_replace('#^https?://#i', '', trim($entry));
        $entry = preg_replace('#/.*$#', '', (string)$entry);
        $entry = strtolower(trim((string)$entry, " \t\n\r\0\x0B./"));
        if ($entry === '') {
            continue;
        }
        $domains[$entry] = true;
    }
    return array_slice(array_keys($domains), 0, 100);
}

function normalize_budget_config(array $config = []): array {
    $default = default_budget_config();
    return [
        'maxTotalTokens' => max(0, (int)($config['maxTotalTokens'] ?? $default['maxTotalTokens'])),
        'maxCostUsd' => max(0.0, round((float)($config['maxCostUsd'] ?? $default['maxCostUsd']), 6)),
        'maxOutputTokens' => max(0, (int)($config['maxOutputTokens'] ?? $default['maxOutputTokens'])),
    ];
}

function normalize_draft_state(?array $draft): array {
    $default = default_draft_state();
    $reasoningEffort = trim((string)($draft['reasoningEffort'] ?? $default['reasoningEffort']));
    if (!in_array($reasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
        $reasoningEffort = $default['reasoningEffort'];
    }

    $executionMode = trim((string)($draft['executionMode'] ?? $default['executionMode']));
    if (!in_array($executionMode, ['live', 'mock'], true)) {
        $executionMode = $default['executionMode'];
    }

    return [
        'objective' => trim((string)($draft['objective'] ?? $default['objective'])),
        'constraints' => array_values(normalize_string_list($draft['constraints'] ?? $default['constraints'])),
        'sessionContext' => trim((string)($draft['sessionContext'] ?? $default['sessionContext'])),
        'executionMode' => $executionMode,
        'model' => normalize_model_id((string)($draft['model'] ?? $default['model']), $default['model']),
        'summarizerModel' => normalize_model_id((string)($draft['summarizerModel'] ?? $default['summarizerModel']), (string)($draft['model'] ?? $default['model'])),
        'reasoningEffort' => $reasoningEffort,
        'maxTotalTokens' => max(0, (int)($draft['maxTotalTokens'] ?? $default['maxTotalTokens'])),
        'maxCostUsd' => max(0.0, round((float)($draft['maxCostUsd'] ?? $default['maxCostUsd']), 6)),
        'maxOutputTokens' => max(0, (int)($draft['maxOutputTokens'] ?? $default['maxOutputTokens'])),
        'researchEnabled' => coerce_bool($draft['researchEnabled'] ?? $default['researchEnabled'], $default['researchEnabled']),
        'researchExternalWebAccess' => coerce_bool($draft['researchExternalWebAccess'] ?? $default['researchExternalWebAccess'], $default['researchExternalWebAccess']),
        'researchDomains' => normalize_allowed_domains($draft['researchDomains'] ?? $default['researchDomains']),
        'vettingEnabled' => coerce_bool($draft['vettingEnabled'] ?? $default['vettingEnabled'], $default['vettingEnabled']),
        'updatedAt' => trim((string)($draft['updatedAt'] ?? '')) ?: gmdate('c')
    ];
}

function build_draft_from_task(?array $task, array $overrides = [], bool $resetBudget = false): array {
    $default = default_draft_state();
    if ($task === null) {
        return normalize_draft_state(array_merge($default, $overrides));
    }

    $runtime = is_array($task['runtime'] ?? null) ? $task['runtime'] : [];
    $budget = $resetBudget
        ? default_budget_config()
        : normalize_budget_config(is_array($runtime['budget'] ?? null) ? $runtime['budget'] : []);
    $research = normalize_research_config(is_array($runtime['research'] ?? null) ? $runtime['research'] : []);
    $vetting = normalize_vetting_config(is_array($runtime['vetting'] ?? null) ? $runtime['vetting'] : []);
    $model = normalize_model_id((string)($runtime['model'] ?? $default['model']), $default['model']);
    $summarizer = is_array($task['summarizer'] ?? null) ? $task['summarizer'] : [];

    $draft = [
        'objective' => trim((string)($task['objective'] ?? $default['objective'])),
        'constraints' => array_values(normalize_string_list($task['constraints'] ?? $default['constraints'])),
        'sessionContext' => trim((string)($task['sessionContext'] ?? $default['sessionContext'])),
        'executionMode' => trim((string)($runtime['executionMode'] ?? $default['executionMode'])),
        'model' => $model,
        'summarizerModel' => normalize_model_id((string)($summarizer['model'] ?? $model), $model),
        'reasoningEffort' => trim((string)($runtime['reasoningEffort'] ?? $default['reasoningEffort'])),
        'maxTotalTokens' => $budget['maxTotalTokens'],
        'maxCostUsd' => $budget['maxCostUsd'],
        'maxOutputTokens' => $budget['maxOutputTokens'],
        'researchEnabled' => $research['enabled'],
        'researchExternalWebAccess' => $research['externalWebAccess'],
        'researchDomains' => $research['domains'],
        'vettingEnabled' => $vetting['enabled'],
        'updatedAt' => gmdate('c')
    ];

    return normalize_draft_state(array_merge($draft, $overrides));
}

function truncate_plain_text($value, int $maxLength = 220): string {
    $text = preg_replace('/\s+/', ' ', trim((string)$value));
    if ($text === '') {
        return '';
    }
    if (function_exists('mb_strlen') && function_exists('mb_substr')) {
        if (mb_strlen($text) <= $maxLength) {
            return $text;
        }
        return rtrim(mb_substr($text, 0, max(0, $maxLength - 3))) . '...';
    }
    if (strlen($text) <= $maxLength) {
        return $text;
    }
    return rtrim(substr($text, 0, max(0, $maxLength - 3))) . '...';
}

function build_session_context_summary(array $state): string {
    $task = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
    $summary = is_array($state['summary'] ?? null) ? $state['summary'] : null;
    $usage = normalize_usage_state(is_array($state['usage'] ?? null) ? $state['usage'] : []);
    $workers = is_array($state['workers'] ?? null) ? $state['workers'] : [];
    $lines = [];

    if ($task) {
        $objective = truncate_plain_text($task['objective'] ?? '', 240);
        if ($objective !== '') {
            $lines[] = 'Prior objective: ' . $objective;
        }
    }

    if ($summary) {
        $stable = [];
        foreach (array_slice((array)($summary['stableFindings'] ?? []), 0, 3) as $finding) {
            $trimmed = truncate_plain_text($finding, 150);
            if ($trimmed !== '') {
                $stable[] = $trimmed;
            }
        }
        if ($stable) {
            $lines[] = 'Stable findings: ' . implode('; ', $stable);
        }

        $recommended = truncate_plain_text($summary['recommendedNextAction'] ?? '', 180);
        if ($recommended !== '') {
            $lines[] = 'Recommended next action: ' . $recommended;
        }

        $conflicts = [];
        foreach (array_slice((array)($summary['conflicts'] ?? []), 0, 3) as $conflict) {
            if (!is_array($conflict)) {
                continue;
            }
            $topic = truncate_plain_text($conflict['topic'] ?? '', 120);
            if ($topic !== '') {
                $conflicts[] = $topic;
            }
        }
        if ($conflicts) {
            $lines[] = 'Open conflicts: ' . implode('; ', $conflicts);
        }
    }

    if (!$summary && $workers) {
        $observations = [];
        foreach ($workers as $workerId => $checkpoint) {
            if (!is_array($checkpoint)) {
                continue;
            }
            $observation = truncate_plain_text($checkpoint['observation'] ?? '', 120);
            if ($observation !== '') {
                $observations[] = $workerId . ': ' . $observation;
            }
            if (count($observations) >= 3) {
                break;
            }
        }
        if ($observations) {
            $lines[] = 'Latest lane signals: ' . implode(' | ', $observations);
        }
    }

    if (($usage['totalTokens'] ?? 0) > 0 || ($usage['estimatedCostUsd'] ?? 0.0) > 0.0) {
        $lines[] = sprintf(
            'Prior usage: %d tokens, approx $%.4f spend.',
            (int)$usage['totalTokens'],
            (float)$usage['estimatedCostUsd']
        );
    }

    if (!$lines) {
        $lines[] = 'No prior session context was available.';
    }

    return implode("\n", array_slice($lines, 0, 5));
}

function default_research_config(): array {
    return [
        'enabled' => false,
        'externalWebAccess' => true,
        'domains' => [],
    ];
}

function normalize_research_config(array $config = []): array {
    $default = default_research_config();
    return [
        'enabled' => coerce_bool($config['enabled'] ?? $default['enabled'], $default['enabled']),
        'externalWebAccess' => coerce_bool($config['externalWebAccess'] ?? $default['externalWebAccess'], $default['externalWebAccess']),
        'domains' => normalize_allowed_domains($config['domains'] ?? $default['domains']),
    ];
}

function default_vetting_config(): array {
    return [
        'enabled' => false,
    ];
}

function normalize_vetting_config(array $config = []): array {
    $default = default_vetting_config();
    return [
        'enabled' => coerce_bool($config['enabled'] ?? $default['enabled'], $default['enabled']),
    ];
}

function normalize_model_id(?string $model, ?string $fallback = null): string {
    $catalog = default_model_catalog();
    $candidate = trim((string)$model);
    if ($candidate !== '' && isset($catalog[$candidate])) {
        return $candidate;
    }
    $fallback = $fallback !== null ? trim($fallback) : default_model_id();
    return isset($catalog[$fallback]) ? $fallback : default_model_id();
}

function default_usage_bucket(): array {
    return [
        'calls' => 0,
        'webSearchCalls' => 0,
        'inputTokens' => 0,
        'cachedInputTokens' => 0,
        'billableInputTokens' => 0,
        'outputTokens' => 0,
        'reasoningTokens' => 0,
        'totalTokens' => 0,
        'modelCostUsd' => 0.0,
        'toolCostUsd' => 0.0,
        'estimatedCostUsd' => 0.0,
        'lastModel' => null,
        'lastResponseId' => null,
        'lastUpdated' => null,
    ];
}

function normalize_usage_bucket(?array $bucket): array {
    $default = default_usage_bucket();
    return [
        'calls' => max(0, (int)($bucket['calls'] ?? $default['calls'])),
        'webSearchCalls' => max(0, (int)($bucket['webSearchCalls'] ?? $default['webSearchCalls'])),
        'inputTokens' => max(0, (int)($bucket['inputTokens'] ?? $default['inputTokens'])),
        'cachedInputTokens' => max(0, (int)($bucket['cachedInputTokens'] ?? $default['cachedInputTokens'])),
        'billableInputTokens' => max(0, (int)($bucket['billableInputTokens'] ?? $default['billableInputTokens'])),
        'outputTokens' => max(0, (int)($bucket['outputTokens'] ?? $default['outputTokens'])),
        'reasoningTokens' => max(0, (int)($bucket['reasoningTokens'] ?? $default['reasoningTokens'])),
        'totalTokens' => max(0, (int)($bucket['totalTokens'] ?? $default['totalTokens'])),
        'modelCostUsd' => round((float)($bucket['modelCostUsd'] ?? $default['modelCostUsd']), 6),
        'toolCostUsd' => round((float)($bucket['toolCostUsd'] ?? $default['toolCostUsd']), 6),
        'estimatedCostUsd' => round((float)($bucket['estimatedCostUsd'] ?? $default['estimatedCostUsd']), 6),
        'lastModel' => $bucket['lastModel'] ?? null,
        'lastResponseId' => $bucket['lastResponseId'] ?? null,
        'lastUpdated' => $bucket['lastUpdated'] ?? null,
    ];
}

function default_usage_state(): array {
    return array_merge(default_usage_bucket(), [
        'byTarget' => [],
        'byModel' => [],
    ]);
}

function normalize_usage_state(?array $usage): array {
    $normalized = normalize_usage_bucket($usage ?? []);
    $normalized['byTarget'] = [];
    $normalized['byModel'] = [];

    if (is_array($usage['byTarget'] ?? null)) {
        foreach ($usage['byTarget'] as $target => $bucket) {
            if (!is_string($target) || trim($target) === '') {
                continue;
            }
            $normalized['byTarget'][$target] = normalize_usage_bucket(is_array($bucket) ? $bucket : []);
        }
    }

    if (is_array($usage['byModel'] ?? null)) {
        foreach ($usage['byModel'] as $model => $bucket) {
            if (!is_string($model) || trim($model) === '') {
                continue;
            }
            $normalized['byModel'][$model] = normalize_usage_bucket(is_array($bucket) ? $bucket : []);
        }
    }

    return $normalized;
}

function worker_catalog(): array {
    return [
        ['id' => 'A', 'label' => 'Worker A', 'role' => 'utility', 'focus' => 'benefits, feasibility, leverage, momentum'],
        ['id' => 'B', 'label' => 'Worker B', 'role' => 'adversarial', 'focus' => 'systemic failure, coupling, downside, hidden risk'],
        ['id' => 'C', 'label' => 'Worker C', 'role' => 'adversarial', 'focus' => 'cost ceilings, burn rate, economic drag'],
        ['id' => 'D', 'label' => 'Worker D', 'role' => 'adversarial', 'focus' => 'security abuse, privilege escalation, hostile actors'],
        ['id' => 'E', 'label' => 'Worker E', 'role' => 'adversarial', 'focus' => 'reliability collapse, uptime loss, brittle dependencies'],
        ['id' => 'F', 'label' => 'Worker F', 'role' => 'adversarial', 'focus' => 'concurrency races, lock contention, timing faults'],
        ['id' => 'G', 'label' => 'Worker G', 'role' => 'adversarial', 'focus' => 'data integrity, corruption, replay hazards'],
        ['id' => 'H', 'label' => 'Worker H', 'role' => 'adversarial', 'focus' => 'compliance, policy drift, governance gaps'],
        ['id' => 'I', 'label' => 'Worker I', 'role' => 'adversarial', 'focus' => 'user confusion, adoption friction, trust loss'],
        ['id' => 'J', 'label' => 'Worker J', 'role' => 'adversarial', 'focus' => 'performance cliffs, hot paths, slow feedback'],
        ['id' => 'K', 'label' => 'Worker K', 'role' => 'adversarial', 'focus' => 'observability blind spots, missing traces, opaque failures'],
        ['id' => 'L', 'label' => 'Worker L', 'role' => 'adversarial', 'focus' => 'scalability failure, fan-out load, resource exhaustion'],
        ['id' => 'M', 'label' => 'Worker M', 'role' => 'adversarial', 'focus' => 'recovery posture, rollback gaps, broken resumes'],
        ['id' => 'N', 'label' => 'Worker N', 'role' => 'adversarial', 'focus' => 'integration mismatch, boundary contracts, interoperability'],
        ['id' => 'O', 'label' => 'Worker O', 'role' => 'adversarial', 'focus' => 'abuse cases, spam, malicious automation'],
        ['id' => 'P', 'label' => 'Worker P', 'role' => 'adversarial', 'focus' => 'latency budgets, throughput realism, field conditions'],
        ['id' => 'Q', 'label' => 'Worker Q', 'role' => 'adversarial', 'focus' => 'incentive mismatch, local maxima, misuse of metrics'],
        ['id' => 'R', 'label' => 'Worker R', 'role' => 'adversarial', 'focus' => 'scope creep, hidden complexity, disguised expansions'],
        ['id' => 'S', 'label' => 'Worker S', 'role' => 'adversarial', 'focus' => 'maintainability drag, operator toil, handoff risk'],
        ['id' => 'T', 'label' => 'Worker T', 'role' => 'adversarial', 'focus' => 'edge cases, chaos inputs, pathological sequences'],
        ['id' => 'U', 'label' => 'Worker U', 'role' => 'adversarial', 'focus' => 'human factors, fatigue, procedural mistakes'],
        ['id' => 'V', 'label' => 'Worker V', 'role' => 'adversarial', 'focus' => 'vendor lock-in, portability loss, external dependence'],
        ['id' => 'W', 'label' => 'Worker W', 'role' => 'adversarial', 'focus' => 'privacy leakage, retention risk, oversharing'],
        ['id' => 'X', 'label' => 'Worker X', 'role' => 'adversarial', 'focus' => 'product mismatch, weak demand signal, false confidence'],
        ['id' => 'Y', 'label' => 'Worker Y', 'role' => 'adversarial', 'focus' => 'decision paralysis, review bottlenecks, process drag'],
        ['id' => 'Z', 'label' => 'Worker Z', 'role' => 'adversarial', 'focus' => 'wildcard attack surfaces, overlooked weirdness, novel failure'],
    ];
}

function normalize_worker_definition(array $worker, ?string $defaultModel = null): array {
    $workerId = strtoupper(trim((string)($worker['id'] ?? '')));
    if (!preg_match('/^[A-Z]$/', $workerId)) {
        throw new InvalidArgumentException('Worker ids must be single uppercase letters.');
    }

    $catalogMap = [];
    foreach (worker_catalog() as $entry) {
        $catalogMap[$entry['id']] = $entry;
    }
    $catalogWorker = $catalogMap[$workerId] ?? ['id' => $workerId, 'label' => 'Worker ' . $workerId, 'role' => 'adversarial', 'focus' => 'general adversarial review'];
    $fallbackModel = $defaultModel !== null ? $defaultModel : default_model_id();

    return [
        'id' => $workerId,
        'label' => trim((string)($worker['label'] ?? $catalogWorker['label'])) ?: $catalogWorker['label'],
        'role' => trim((string)($worker['role'] ?? $catalogWorker['role'])) ?: $catalogWorker['role'],
        'focus' => trim((string)($worker['focus'] ?? $catalogWorker['focus'])) ?: $catalogWorker['focus'],
        'model' => normalize_model_id($worker['model'] ?? null, $fallbackModel),
    ];
}

function task_workers(array $task): array {
    $defaultModel = normalize_model_id($task['runtime']['model'] ?? null, default_model_id());
    $workers = [];
    if (isset($task['workers']) && is_array($task['workers'])) {
        foreach ($task['workers'] as $worker) {
            if (!is_array($worker)) {
                continue;
            }
            $normalized = normalize_worker_definition($worker, $defaultModel);
            $workers[$normalized['id']] = $normalized;
        }
    }

    if (!$workers) {
        foreach (array_slice(worker_catalog(), 0, 2) as $worker) {
            $normalized = normalize_worker_definition($worker, $defaultModel);
            $workers[$normalized['id']] = $normalized;
        }
    }

    ksort($workers);
    return array_values($workers);
}

function empty_worker_state_map(array $workers): array {
    $map = [];
    foreach ($workers as $worker) {
        if (!is_array($worker) || empty($worker['id'])) {
            continue;
        }
        $map[(string)$worker['id']] = null;
    }
    return $map;
}

function find_task_worker(array $task, string $workerId): ?array {
    $workerId = strtoupper(trim($workerId));
    foreach (task_workers($task) as $worker) {
        if (($worker['id'] ?? null) === $workerId) {
            return $worker;
        }
    }
    return null;
}

function next_adversarial_worker_definition(array $task): ?array {
    $defaultModel = normalize_model_id($task['runtime']['model'] ?? null, default_model_id());
    $existing = [];
    foreach (task_workers($task) as $worker) {
        $existing[(string)$worker['id']] = true;
    }
    foreach (worker_catalog() as $worker) {
        if ($worker['id'] === 'A' || isset($existing[$worker['id']])) {
            continue;
        }
        return normalize_worker_definition($worker, $defaultModel);
    }
    return null;
}

function summarizer_config(array $task): array {
    $defaultModel = normalize_model_id($task['runtime']['model'] ?? null, default_model_id());
    $summary = isset($task['summarizer']) && is_array($task['summarizer']) ? $task['summarizer'] : [];
    return [
        'id' => 'summarizer',
        'label' => trim((string)($summary['label'] ?? 'Summarizer')) ?: 'Summarizer',
        'model' => normalize_model_id($summary['model'] ?? null, $defaultModel),
    ];
}

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
        'draft' => default_draft_state(),
        'workers' => [],
        'summary' => null,
        'memoryVersion' => 0,
        'usage' => default_usage_state(),
        'loop' => default_loop_state(),
        'lastUpdated' => gmdate('c')
    ];
}

function normalize_state(array $state): array {
    $normalized = default_state();
    $normalized['activeTask'] = $state['activeTask'] ?? null;
    $normalized['draft'] = normalize_draft_state(isset($state['draft']) && is_array($state['draft']) ? $state['draft'] : []);
    $normalized['summary'] = $state['summary'] ?? null;
    $normalized['memoryVersion'] = isset($state['memoryVersion']) ? (int)$state['memoryVersion'] : 0;
    $normalized['usage'] = normalize_usage_state(isset($state['usage']) && is_array($state['usage']) ? $state['usage'] : []);
    $normalized['lastUpdated'] = $state['lastUpdated'] ?? gmdate('c');

    if (isset($state['workers']) && is_array($state['workers'])) {
        $workers = [];
        foreach ($state['workers'] as $workerId => $checkpoint) {
            if (!is_string($workerId) || trim($workerId) === '') {
                continue;
            }
            $workers[$workerId] = $checkpoint;
        }
        ksort($workers);
        $normalized['workers'] = $workers;
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
        OUTPUTS_PATH,
        SESSIONS_PATH,
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

function session_archive_file_path(string $archiveId): string {
    return SESSIONS_PATH . DIRECTORY_SEPARATOR . $archiveId . '.json';
}

function write_task_snapshot(array $task): void {
    if (empty($task['taskId'])) {
        return;
    }
    file_put_contents(
        task_file_path((string)$task['taskId']),
        json_encode($task, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
    );
}

function write_session_archive_unlocked(array $archive): string {
    $taskId = trim((string)($archive['taskId'] ?? 'session'));
    if ($taskId === '') {
        $taskId = 'session';
    }
    $archiveId = 'session-' . gmdate('Ymd-His') . '-' . preg_replace('/[^A-Za-z0-9_-]+/', '-', $taskId);
    file_put_contents(
        session_archive_file_path($archiveId),
        json_encode($archive, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
    );
    return $archiveId . '.json';
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

function post_float_value(string $key, float $default): float {
    $value = post_value($key, $default);
    return is_numeric($value) ? (float)$value : $default;
}

function post_int_value(string $key, int $default): int {
    $value = post_value($key, $default);
    return is_numeric($value) ? (int)$value : $default;
}

function available_targets(?array $task): array {
    if (!$task) {
        return ['summarizer'];
    }
    $targets = array_map(static function (array $worker): string {
        return (string)$worker['id'];
    }, task_workers($task));
    $targets[] = 'summarizer';
    return $targets;
}

function is_valid_target(string $target, ?array $task): bool {
    return in_array($target, available_targets($task), true);
}

function resolve_target_spec(string $target, ?array $task): array {
    if ($target === 'summarizer') {
        return [
            'script' => 'summarizer.ps1',
            'args' => []
        ];
    }

    if (!$task || !find_task_worker($task, $target)) {
        throw new RuntimeException('Invalid target.');
    }

    return [
        'script' => 'worker.ps1',
        'args' => ['-WorkerId', $target]
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

function default_job(array $config): array {
    return [
        'jobId' => $config['jobId'],
        'taskId' => $config['taskId'],
        'mode' => $config['mode'] ?? 'background',
        'status' => $config['status'] ?? 'queued',
        'rounds' => (int)$config['rounds'],
        'delayMs' => (int)$config['delayMs'],
        'workerCount' => max(0, (int)($config['workerCount'] ?? 0)),
        'cancelRequested' => (bool)($config['cancelRequested'] ?? false),
        'queuedAt' => $config['queuedAt'] ?? gmdate('c'),
        'startedAt' => $config['startedAt'] ?? null,
        'finishedAt' => $config['finishedAt'] ?? null,
        'lastHeartbeatAt' => $config['lastHeartbeatAt'] ?? null,
        'completedRounds' => (int)($config['completedRounds'] ?? 0),
        'currentRound' => (int)($config['currentRound'] ?? 0),
        'lastMessage' => $config['lastMessage'] ?? 'Queued.',
        'usage' => normalize_usage_state(isset($config['usage']) && is_array($config['usage']) ? $config['usage'] : []),
        'results' => $config['results'] ?? [],
        'error' => $config['error'] ?? null
    ];
}

function write_job_unlocked(array $job): array {
    $normalized = default_job($job);
    file_put_contents(
        job_file_path($normalized['jobId']),
        json_encode($normalized, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
    );
    return $normalized;
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

        if (in_array($jobStatus, ['completed', 'cancelled', 'error', 'budget_exhausted'], true) || $status !== $jobStatus) {
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

function ps_command(string $scriptName, array $extraArgs = []): string {
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
    foreach ($extraArgs as $arg) {
        $parts[] = (string)$arg;
    }
    $escaped = array_map('escapeshellarg', $parts);
    return implode(' ', $escaped) . ' 2>&1';
}

function run_powershell_target(string $target, ?array $task = null): array {
    $stateTask = $task;
    if ($stateTask === null) {
        $state = read_state();
        $stateTask = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
    }

    $spec = resolve_target_spec($target, $stateTask);
    $cmd = ps_command($spec['script'], $spec['args']);
    $lines = [];
    $exitCode = 0;
    exec($cmd, $lines, $exitCode);
    $output = trim(implode(PHP_EOL, $lines));

    append_event('powershell_run', [
        'target' => $target,
        'script' => $spec['script'],
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
