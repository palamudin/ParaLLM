<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$state = recover_loop_state_if_needed();
$existingDraft = normalize_draft_state(isset($state['draft']) && is_array($state['draft']) ? $state['draft'] : []);

$constraintsRaw = post_value('constraints', json_encode($existingDraft['constraints'], JSON_UNESCAPED_SLASHES));
$constraints = json_decode((string)$constraintsRaw, true);
if (!is_array($constraints)) {
    $constraints = $existingDraft['constraints'];
}

$workers = $existingDraft['workers'];
$workersRaw = post_value('workers', null);
if ($workersRaw !== null) {
    $decodedWorkers = json_decode((string)$workersRaw, true);
    if (is_array($decodedWorkers)) {
        $workers = $decodedWorkers;
    }
}

$summarizerHarness = $existingDraft['summarizerHarness'];
$summarizerHarnessRaw = post_value('summarizerHarness', null);
if ($summarizerHarnessRaw !== null) {
    $decodedHarness = json_decode((string)$summarizerHarnessRaw, true);
    if (is_array($decodedHarness)) {
        $summarizerHarness = $decodedHarness;
    }
}

$budgetTargets = $existingDraft['budgetTargets'] ?? default_budget_config()['targets'];
$budgetTargetsRaw = post_value('budgetTargets', null);
if ($budgetTargetsRaw !== null) {
    $decodedBudgetTargets = json_decode((string)$budgetTargetsRaw, true);
    if (is_array($decodedBudgetTargets)) {
        $budgetTargets = $decodedBudgetTargets;
    }
}

$draft = normalize_draft_state(array_merge($existingDraft, [
    'objective' => trim((string)post_value('objective', $existingDraft['objective'])),
    'constraints' => $constraints,
    'sessionContext' => trim((string)post_value('sessionContext', $existingDraft['sessionContext'])),
    'executionMode' => post_value('executionMode', $existingDraft['executionMode']),
    'model' => post_value('model', $existingDraft['model']),
    'summarizerModel' => post_value('summarizerModel', $existingDraft['summarizerModel']),
    'reasoningEffort' => post_value('reasoningEffort', $existingDraft['reasoningEffort']),
    'maxCostUsd' => post_value('maxCostUsd', $existingDraft['maxCostUsd']),
    'maxTotalTokens' => post_value('maxTotalTokens', $existingDraft['maxTotalTokens']),
    'maxOutputTokens' => post_value('maxOutputTokens', $existingDraft['maxOutputTokens']),
    'budgetTargets' => $budgetTargets,
    'researchEnabled' => post_value('researchEnabled', $existingDraft['researchEnabled']),
    'researchExternalWebAccess' => post_value('researchExternalWebAccess', $existingDraft['researchExternalWebAccess']),
    'researchDomains' => post_value('researchDomains', $existingDraft['researchDomains']),
    'vettingEnabled' => post_value('vettingEnabled', $existingDraft['vettingEnabled']),
    'summarizerHarness' => $summarizerHarness,
    'loopRounds' => post_value('loopRounds', $existingDraft['loopRounds']),
    'loopDelayMs' => post_value('loopDelayMs', $existingDraft['loopDelayMs']),
    'workers' => $workers,
    'updatedAt' => gmdate('c'),
]));

$updatedState = mutate_state(function (array $state) use ($draft): array {
    $state['draft'] = $draft;
    return $state;
});

json_response([
    'message' => 'Draft saved.',
    'draft' => $updatedState['draft']
]);
