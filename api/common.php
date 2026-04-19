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
define('RUNTIME_PATH', ROOT_PATH . DIRECTORY_SEPARATOR . 'runtime');
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

function default_loop_preferences(): array {
    return [
        'rounds' => 3,
        'delayMs' => 1000,
    ];
}

function normalize_loop_preferences(array $config = []): array {
    $default = default_loop_preferences();
    $rounds = (int)($config['rounds'] ?? $default['rounds']);
    $delayMs = (int)($config['delayMs'] ?? $default['delayMs']);
    return [
        'rounds' => max(1, min(12, $rounds)),
        'delayMs' => max(0, min(10000, $delayMs)),
    ];
}

function worker_temperature_catalog(): array {
    return [
        'cool' => ['label' => 'Cool', 'instruction' => 'deliberate, restrained, careful under pressure'],
        'balanced' => ['label' => 'Balanced', 'instruction' => 'practical, even-tempered, evidence-first'],
        'hot' => ['label' => 'Hot', 'instruction' => 'provocative, forceful, aggressively pressure-testing'],
    ];
}

function normalize_worker_temperature($value, string $fallback = 'balanced'): string {
    $catalog = worker_temperature_catalog();
    $candidate = strtolower(trim((string)$value));
    if (isset($catalog[$candidate])) {
        return $candidate;
    }
    return isset($catalog[$fallback]) ? $fallback : 'balanced';
}

function worker_type_catalog(): array {
    return [
        'proponent' => ['label' => 'Proponent', 'role' => 'utility', 'focus' => 'benefits, feasibility, leverage, momentum, practical execution', 'temperature' => 'balanced'],
        'sceptic' => ['label' => 'Sceptic', 'role' => 'adversarial', 'focus' => 'failure modes, downside, hidden coupling, consequences, externalities', 'temperature' => 'cool'],
        'economist' => ['label' => 'Economist', 'role' => 'adversarial', 'focus' => 'cost ceilings, burn rate, return on effort, economic drag', 'temperature' => 'cool'],
        'security' => ['label' => 'Security', 'role' => 'adversarial', 'focus' => 'security abuse, privilege escalation, hostile actors', 'temperature' => 'hot'],
        'reliability' => ['label' => 'Reliability', 'role' => 'adversarial', 'focus' => 'reliability collapse, uptime loss, brittle dependencies', 'temperature' => 'cool'],
        'concurrency' => ['label' => 'Concurrency', 'role' => 'adversarial', 'focus' => 'concurrency races, lock contention, timing faults', 'temperature' => 'hot'],
        'data' => ['label' => 'Data Integrity', 'role' => 'adversarial', 'focus' => 'data integrity, corruption, replay hazards', 'temperature' => 'cool'],
        'compliance' => ['label' => 'Compliance', 'role' => 'adversarial', 'focus' => 'compliance, policy drift, governance gaps', 'temperature' => 'balanced'],
        'user' => ['label' => 'User Advocate', 'role' => 'adversarial', 'focus' => 'user confusion, adoption friction, trust loss', 'temperature' => 'balanced'],
        'performance' => ['label' => 'Performance', 'role' => 'adversarial', 'focus' => 'performance cliffs, hot paths, slow feedback', 'temperature' => 'hot'],
        'observability' => ['label' => 'Observability', 'role' => 'adversarial', 'focus' => 'observability blind spots, missing traces, opaque failures', 'temperature' => 'cool'],
        'scalability' => ['label' => 'Scalability', 'role' => 'adversarial', 'focus' => 'scalability failure, fan-out load, resource exhaustion', 'temperature' => 'hot'],
        'recovery' => ['label' => 'Recovery', 'role' => 'adversarial', 'focus' => 'recovery posture, rollback gaps, broken resumes', 'temperature' => 'cool'],
        'integration' => ['label' => 'Integrations', 'role' => 'adversarial', 'focus' => 'integration mismatch, boundary contracts, interoperability', 'temperature' => 'balanced'],
        'abuse' => ['label' => 'Abuse Cases', 'role' => 'adversarial', 'focus' => 'abuse cases, spam, malicious automation', 'temperature' => 'hot'],
        'latency' => ['label' => 'Latency', 'role' => 'adversarial', 'focus' => 'latency budgets, throughput realism, field conditions', 'temperature' => 'balanced'],
        'incentives' => ['label' => 'Incentives', 'role' => 'adversarial', 'focus' => 'incentive mismatch, local maxima, misuse of metrics', 'temperature' => 'balanced'],
        'scope' => ['label' => 'Scope Control', 'role' => 'adversarial', 'focus' => 'scope creep, hidden complexity, disguised expansions', 'temperature' => 'cool'],
        'maintainability' => ['label' => 'Maintainability', 'role' => 'adversarial', 'focus' => 'maintainability drag, operator toil, handoff risk', 'temperature' => 'cool'],
        'edge' => ['label' => 'Edge Cases', 'role' => 'adversarial', 'focus' => 'edge cases, chaos inputs, pathological sequences', 'temperature' => 'hot'],
        'human' => ['label' => 'Human Factors', 'role' => 'adversarial', 'focus' => 'human factors, fatigue, procedural mistakes', 'temperature' => 'balanced'],
        'portability' => ['label' => 'Portability', 'role' => 'adversarial', 'focus' => 'vendor lock-in, portability loss, external dependence', 'temperature' => 'cool'],
        'privacy' => ['label' => 'Privacy', 'role' => 'adversarial', 'focus' => 'privacy leakage, retention risk, oversharing', 'temperature' => 'cool'],
        'product' => ['label' => 'Product Strategy', 'role' => 'adversarial', 'focus' => 'product mismatch, weak demand signal, false confidence', 'temperature' => 'balanced'],
        'governance' => ['label' => 'Governance', 'role' => 'adversarial', 'focus' => 'decision paralysis, review bottlenecks, process drag', 'temperature' => 'cool'],
        'wildcard' => ['label' => 'Wildcard', 'role' => 'adversarial', 'focus' => 'wildcard attack surfaces, overlooked weirdness, novel failure', 'temperature' => 'hot'],
    ];
}

function default_worker_type_sequence(): array {
    return [
        'proponent',
        'sceptic',
        'economist',
        'security',
        'reliability',
        'concurrency',
        'data',
        'compliance',
        'user',
        'performance',
        'observability',
        'scalability',
        'recovery',
        'integration',
        'abuse',
        'latency',
        'incentives',
        'scope',
        'maintainability',
        'edge',
        'human',
        'portability',
        'privacy',
        'product',
        'governance',
        'wildcard',
    ];
}

function worker_slot_ids(): array {
    return range('A', 'Z');
}

function default_worker_type_for_slot(string $workerId): string {
    $workerId = strtoupper(trim($workerId));
    $slots = worker_slot_ids();
    $index = array_search($workerId, $slots, true);
    $sequence = default_worker_type_sequence();
    if ($index === false || !isset($sequence[$index])) {
        return 'wildcard';
    }
    return $sequence[$index];
}

function default_draft_state(): array {
    $budget = default_budget_config();
    $model = default_model_id();
    $loop = default_loop_preferences();
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
        'loopRounds' => $loop['rounds'],
        'loopDelayMs' => $loop['delayMs'],
        'workers' => array_slice(worker_catalog($model), 0, 2),
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
    if (is_string($value)) {
        $trimmed = trim($value);
        if ($trimmed !== '' && str_starts_with($trimmed, '[')) {
            $decoded = json_decode($trimmed, true);
            if (is_array($decoded)) {
                $value = $decoded;
            }
        }
    }

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
    $loop = normalize_loop_preferences([
        'rounds' => $draft['loopRounds'] ?? $default['loopRounds'],
        'delayMs' => $draft['loopDelayMs'] ?? $default['loopDelayMs'],
    ]);
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
        'loopRounds' => $loop['rounds'],
        'loopDelayMs' => $loop['delayMs'],
        'workers' => task_workers([
            'runtime' => ['model' => normalize_model_id((string)($draft['model'] ?? $default['model']), $default['model'])],
            'workers' => $draft['workers'] ?? $default['workers'],
        ]),
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
    $loopPrefs = normalize_loop_preferences(is_array($task['preferredLoop'] ?? null) ? $task['preferredLoop'] : []);

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
        'loopRounds' => $loopPrefs['rounds'],
        'loopDelayMs' => $loopPrefs['delayMs'],
        'workers' => task_workers($task),
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

function worker_catalog(?string $defaultModel = null): array {
    $workers = [];
    foreach (worker_slot_ids() as $workerId) {
        $workers[] = normalize_worker_definition(['id' => $workerId], $defaultModel);
    }
    return $workers;
}

function normalize_worker_definition(array $worker, ?string $defaultModel = null): array {
    $workerId = strtoupper(trim((string)($worker['id'] ?? '')));
    if (!preg_match('/^[A-Z]$/', $workerId)) {
        throw new InvalidArgumentException('Worker ids must be single uppercase letters.');
    }

    $typeCatalog = worker_type_catalog();
    $defaultType = default_worker_type_for_slot($workerId);
    $type = strtolower(trim((string)($worker['type'] ?? $defaultType)));
    if (!isset($typeCatalog[$type])) {
        $type = $defaultType;
    }
    $catalogWorker = $typeCatalog[$type] ?? $typeCatalog[$defaultType] ?? [
        'label' => 'Worker ' . $workerId,
        'role' => 'adversarial',
        'focus' => 'general adversarial review',
        'temperature' => 'balanced',
    ];
    $fallbackModel = $defaultModel !== null ? $defaultModel : default_model_id();

    return [
        'id' => $workerId,
        'type' => $type,
        'label' => trim((string)($worker['label'] ?? $catalogWorker['label'])) ?: $catalogWorker['label'],
        'role' => trim((string)($worker['role'] ?? $catalogWorker['role'])) ?: $catalogWorker['role'],
        'focus' => trim((string)($worker['focus'] ?? $catalogWorker['focus'])) ?: $catalogWorker['focus'],
        'temperature' => normalize_worker_temperature($worker['temperature'] ?? $catalogWorker['temperature'] ?? 'balanced', (string)($catalogWorker['temperature'] ?? 'balanced')),
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
    $defaultModel = normalize_model_id($task['runtime']['model'] ?? ($task['model'] ?? null), default_model_id());
    $existing = [];
    foreach (task_workers($task) as $worker) {
        $existing[(string)$worker['id']] = true;
    }
    foreach (worker_slot_ids() as $workerId) {
        if (isset($existing[$workerId])) {
            continue;
        }
        return normalize_worker_definition(['id' => $workerId], $defaultModel);
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

function missing_worker_checkpoints(?array $task, array $workerState): array {
    if (!$task) {
        return [];
    }

    $missing = [];
    foreach (task_workers($task) as $worker) {
        $workerId = (string)($worker['id'] ?? '');
        if ($workerId === '') {
            continue;
        }
        if (!array_key_exists($workerId, $workerState) || $workerState[$workerId] === null) {
            $missing[] = $workerId;
        }
    }

    return $missing;
}

function target_dispatch_preflight(string $target, array $state): ?array {
    $task = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
    $workerState = is_array($state['workers'] ?? null) ? $state['workers'] : [];

    if ($target === 'summarizer') {
        $missing = missing_worker_checkpoints($task, $workerState);
        if ($missing) {
            return [
                'code' => 409,
                'message' => 'Summarizer is not ready yet. Run worker checkpoint(s) first: ' . implode(', ', $missing) . '.',
                'missingWorkers' => $missing
            ];
        }
    }

    return null;
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
    launch_background_process($phpPath, array_merge([$scriptPath], $args));
}

function build_shell_command(string $executable, array $args = []): string {
    $parts = array_merge([$executable], array_map(static function ($arg): string {
        return (string)$arg;
    }, $args));
    return implode(' ', array_map('escapeshellarg', $parts));
}

function launch_background_process(string $executable, array $args = []): void {
    $command = build_shell_command($executable, $args);
    if (PHP_OS_FAMILY === 'Windows') {
        $handle = @popen('cmd.exe /d /c start "" /b ' . $command . ' >NUL 2>NUL', 'r');
        if (!is_resource($handle)) {
            throw new RuntimeException('Failed to launch background process.');
        }
        pclose($handle);
        return;
    }

    shell_exec($command . ' > /dev/null 2>&1 &');
}

function python_cli_path(): string {
    $localAppData = getenv('LOCALAPPDATA') ?: '';
    $home = getenv('HOME') ?: '';
    $candidates = array_filter([
        getenv('LOOP_PYTHON_BIN') ?: null,
        getenv('PYTHON_BIN') ?: null,
        ROOT_PATH . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR . 'Scripts' . DIRECTORY_SEPARATOR . 'python.exe',
        ROOT_PATH . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python',
        $localAppData ? $localAppData . DIRECTORY_SEPARATOR . 'Programs' . DIRECTORY_SEPARATOR . 'Python' . DIRECTORY_SEPARATOR . 'Python312' . DIRECTORY_SEPARATOR . 'python.exe' : null,
        $localAppData ? $localAppData . DIRECTORY_SEPARATOR . 'Programs' . DIRECTORY_SEPARATOR . 'Python' . DIRECTORY_SEPARATOR . 'Python313' . DIRECTORY_SEPARATOR . 'python.exe' : null,
        $localAppData ? $localAppData . DIRECTORY_SEPARATOR . 'Programs' . DIRECTORY_SEPARATOR . 'Python' . DIRECTORY_SEPARATOR . 'Python311' . DIRECTORY_SEPARATOR . 'python.exe' : null,
        $home ? $home . DIRECTORY_SEPARATOR . '.pyenv' . DIRECTORY_SEPARATOR . 'shims' . DIRECTORY_SEPARATOR . 'python3' : null,
        '/usr/local/bin/python3',
        '/usr/bin/python3',
    ], static function ($candidate): bool {
        return is_string($candidate) && $candidate !== '';
    });

    foreach ($candidates as $candidate) {
        if (file_exists($candidate)) {
            return $candidate;
        }
    }

    throw new RuntimeException('Unable to locate a Python executable for the resident runtime.');
}

function runtime_service_script_path(): string {
    $path = RUNTIME_PATH . DIRECTORY_SEPARATOR . 'service.py';
    if (!file_exists($path)) {
        throw new RuntimeException('Python runtime service script is missing.');
    }
    return $path;
}

function runtime_service_url(): string {
    $url = trim((string)(getenv('LOOP_RUNTIME_URL') ?: 'http://127.0.0.1:8765'));
    return rtrim($url, '/');
}

function runtime_service_request(string $method, string $path, ?array $payload = null, int $timeoutSeconds = 5): array {
    $url = runtime_service_url() . $path;
    $headers = [
        'Accept: application/json',
    ];
    $content = '';
    if ($payload !== null) {
        $headers[] = 'Content-Type: application/json';
        $content = json_encode($payload, JSON_UNESCAPED_SLASHES);
    }

    $context = stream_context_create([
        'http' => [
            'method' => strtoupper($method),
            'header' => implode("\r\n", $headers),
            'content' => $content,
            'ignore_errors' => true,
            'timeout' => $timeoutSeconds,
        ]
    ]);

    $body = @file_get_contents($url, false, $context);
    $statusLine = $http_response_header[0] ?? 'HTTP/1.1 500 Runtime Error';
    $statusCode = 500;
    if (preg_match('/\s(\d{3})\s/', $statusLine, $matches)) {
        $statusCode = (int)$matches[1];
    }

    $decoded = null;
    if (is_string($body) && trim($body) !== '') {
        $candidate = json_decode($body, true);
        if (is_array($candidate)) {
            $decoded = $candidate;
        }
    }

    return [
        'statusCode' => $statusCode,
        'body' => is_string($body) ? $body : '',
        'json' => $decoded
    ];
}

function runtime_service_is_healthy(): bool {
    try {
        $response = runtime_service_request('GET', '/health', null, 2);
        return $response['statusCode'] === 200 && is_array($response['json']) && !empty($response['json']['ok']);
    } catch (Throwable $ex) {
        return false;
    }
}

function launch_background_python_service(): void {
    $pythonPath = python_cli_path();
    $scriptPath = runtime_service_script_path();
    launch_background_process($pythonPath, [
        $scriptPath,
        '--root=' . ROOT_PATH,
        '--host=127.0.0.1',
        '--port=8765'
    ]);
}

function ensure_runtime_service(): void {
    if (runtime_service_is_healthy()) {
        return;
    }

    with_lock(function (): void {
        if (runtime_service_is_healthy()) {
            return;
        }
        launch_background_python_service();
        $deadline = microtime(true) + 8.0;
        do {
            usleep(200000);
            if (runtime_service_is_healthy()) {
                return;
            }
        } while (microtime(true) < $deadline);

        throw new RuntimeException('Python runtime service did not become healthy.');
    }, 15000, 'runtime-service');
}

function run_python_runtime_target(string $target, ?array $task = null): array {
    $stateTask = $task;
    if ($stateTask === null) {
        $state = read_state();
        $stateTask = is_array($state['activeTask'] ?? null) ? $state['activeTask'] : null;
    }
    if ($stateTask === null) {
        throw new RuntimeException('No active task.');
    }

    ensure_runtime_service();
    $response = runtime_service_request('POST', '/run-target', [
        'target' => $target,
        'taskId' => $stateTask['taskId'] ?? null
    ], 300);

    append_event('runtime_dispatch', [
        'target' => $target,
        'backend' => 'python',
        'statusCode' => $response['statusCode'],
        'body' => $response['body']
    ]);

    if ($response['statusCode'] < 200 || $response['statusCode'] >= 300) {
        $message = is_array($response['json']) && !empty($response['json']['message'])
            ? (string)$response['json']['message']
            : ('Python runtime target ' . $target . ' failed.');
        $code = in_array($response['statusCode'], [400, 409], true) ? $response['statusCode'] : 500;
        throw new RuntimeException($message, $code);
    }

    $result = is_array($response['json']) && is_array($response['json']['result'])
        ? $response['json']['result']
        : null;
    if (!$result) {
        throw new RuntimeException('Python runtime target returned an invalid response.');
    }

    return [
        'target' => (string)($result['target'] ?? $target),
        'output' => (string)($result['output'] ?? ''),
        'exitCode' => (int)($result['exitCode'] ?? 0),
        'backend' => 'python'
    ];
}

function run_dispatch_target(string $target, ?array $task = null): array {
    return run_python_runtime_target($target, $task);
}
