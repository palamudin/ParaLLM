<?php
require __DIR__ . '/common.php';

ensure_eval_paths();

function build_eval_run_preview(array $run): array {
    $summary = is_array($run['summary'] ?? null) ? $run['summary'] : [];
    return [
        'runId' => $run['runId'] ?? null,
        'suiteId' => $run['suiteId'] ?? null,
        'status' => $run['status'] ?? 'unknown',
        'createdAt' => $run['createdAt'] ?? null,
        'updatedAt' => $run['updatedAt'] ?? null,
        'startedAt' => $run['startedAt'] ?? null,
        'completedAt' => $run['completedAt'] ?? null,
        'replicates' => isset($run['replicates']) ? (int)$run['replicates'] : 0,
        'loopSweep' => array_values(array_map('intval', is_array($run['loopSweep'] ?? null) ? $run['loopSweep'] : [])),
        'judgeModel' => $run['judgeModel'] ?? null,
        'current' => is_array($run['current'] ?? null) ? $run['current'] : null,
        'error' => $run['error'] ?? null,
        'summary' => [
            'caseCount' => isset($summary['caseCount']) ? (int)$summary['caseCount'] : 0,
            'variantCount' => isset($summary['variantCount']) ? (int)$summary['variantCount'] : 0,
            'errorCount' => isset($summary['errorCount']) ? (int)$summary['errorCount'] : 0,
            'totalTokens' => isset($summary['totalTokens']) ? (int)$summary['totalTokens'] : 0,
            'estimatedCostUsd' => isset($summary['estimatedCostUsd']) ? (float)$summary['estimatedCostUsd'] : 0.0,
            'averageQuality' => is_array($summary['averageQuality'] ?? null) ? $summary['averageQuality'] : [],
            'averageControl' => is_array($summary['averageControl'] ?? null) ? $summary['averageControl'] : [],
            'variants' => array_slice(is_array($summary['variants'] ?? null) ? $summary['variants'] : [], 0, 8),
        ],
    ];
}

$suiteCatalog = load_eval_suite_catalog();
$armCatalog = load_eval_arm_catalog();

$selectedRunId = trim((string)($_GET['runId'] ?? ''));
$runFiles = array_slice(list_eval_run_files(), 0, 16);
$runs = [];
$selectedRun = null;

foreach ($runFiles as $runFile) {
    $run = read_json_file_safe($runFile);
    if (!is_array($run)) {
        continue;
    }
    $runs[] = build_eval_run_preview($run);
    if ($selectedRunId !== '' && ($run['runId'] ?? null) === $selectedRunId) {
        $selectedRun = $run;
    }
}

if ($selectedRun === null && $selectedRunId === '' && $runFiles) {
    $latest = read_json_file_safe($runFiles[0]);
    if (is_array($latest)) {
        $selectedRun = $latest;
        $selectedRunId = (string)($latest['runId'] ?? '');
    }
}

if ($selectedRun !== null) {
    $artifacts = [];
    foreach ((array)($selectedRun['artifactIndex'] ?? []) as $entry) {
        if (!is_array($entry)) {
            continue;
        }
        $artifacts[] = $entry;
    }
    usort($artifacts, static function (array $a, array $b): int {
        $timeCompare = strcmp((string)($b['modifiedAt'] ?? ''), (string)($a['modifiedAt'] ?? ''));
        if ($timeCompare !== 0) {
            return $timeCompare;
        }
        return strcmp((string)($a['name'] ?? ''), (string)($b['name'] ?? ''));
    });
    $selectedRun['artifacts'] = $artifacts;
}

json_response([
    'suites' => $suiteCatalog['items'],
    'suiteErrors' => $suiteCatalog['errors'],
    'arms' => $armCatalog['items'],
    'armErrors' => $armCatalog['errors'],
    'runs' => $runs,
    'selectedRunId' => $selectedRunId !== '' ? $selectedRunId : null,
    'selectedRun' => $selectedRun,
]);
