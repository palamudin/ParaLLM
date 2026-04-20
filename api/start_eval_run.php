<?php
require __DIR__ . '/common.php';

ensure_eval_paths();

$suiteCatalog = load_eval_suite_catalog();
$armCatalog = load_eval_arm_catalog();
$suiteItems = [];
foreach ($suiteCatalog['items'] as $item) {
    $suiteItems[(string)$item['suiteId']] = $item;
}
$armItems = [];
foreach ($armCatalog['items'] as $item) {
    $armItems[(string)$item['armId']] = $item;
}

$suiteId = trim((string)post_value('suiteId', ''));
if ($suiteId === '' || !isset($suiteItems[$suiteId])) {
    json_response(['message' => 'Choose a valid eval suite first.'], 400);
}

$armIdsRaw = post_value('armIds', '[]');
$armIds = json_decode((string)$armIdsRaw, true);
if (!is_array($armIds)) {
    $armIds = normalize_string_list((string)$armIdsRaw);
}
$armIds = array_values(array_unique(array_filter(array_map(static function ($value): string {
    return trim((string)$value);
}, $armIds), static function (string $value): bool {
    return $value !== '';
})));
if (!$armIds) {
    json_response(['message' => 'Choose at least one eval arm.'], 400);
}
foreach ($armIds as $armId) {
    if (!isset($armItems[$armId])) {
        json_response(['message' => 'Unknown eval arm: ' . $armId], 400);
    }
}

$replicates = max(1, min(5, post_int_value('replicates', 1)));
$loopSweepRaw = trim((string)post_value('loopSweep', '1'));
$loopSweep = [];
foreach (preg_split('/[\s,]+/', $loopSweepRaw) ?: [] as $chunk) {
    $chunk = trim((string)$chunk);
    if ($chunk === '') {
        continue;
    }
    if (!ctype_digit($chunk)) {
        json_response(['message' => 'Loop sweep must contain only integers such as 1,2,3.'], 400);
    }
    $value = max(1, min(12, (int)$chunk));
    if (!in_array($value, $loopSweep, true)) {
        $loopSweep[] = $value;
    }
}
if (!$loopSweep) {
    $loopSweep = [1];
}

$judgeModel = normalize_model_id((string)post_value('judgeModel', 'gpt-5.4'), 'gpt-5.4');
$runId = 'eval-' . date('Ymd-His') . '-' . substr(md5(uniqid('', true)), 0, 6);

$run = [
    'runId' => $runId,
    'status' => 'queued',
    'createdAt' => gmdate('c'),
    'updatedAt' => gmdate('c'),
    'startedAt' => null,
    'completedAt' => null,
    'suiteId' => $suiteId,
    'armIds' => $armIds,
    'replicates' => $replicates,
    'loopSweep' => $loopSweep,
    'judgeModel' => $judgeModel,
    'current' => null,
    'summary' => null,
    'artifactIndex' => [],
    'cases' => [],
    'error' => null,
];

write_eval_run($run);

try {
    launch_eval_runner($runId);
} catch (Throwable $ex) {
    $run['status'] = 'error';
    $run['completedAt'] = gmdate('c');
    $run['error'] = $ex->getMessage();
    write_eval_run($run);
    json_response(['message' => $ex->getMessage()], 500);
}

json_response([
    'message' => 'Eval run queued.',
    'runId' => $runId,
    'suiteId' => $suiteId,
    'armIds' => $armIds,
    'replicates' => $replicates,
    'loopSweep' => $loopSweep,
    'judgeModel' => $judgeModel,
]);
