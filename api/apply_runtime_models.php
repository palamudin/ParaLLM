<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$model = normalize_model_id((string)post_value('model', default_model_id()), default_model_id());
$summarizerModel = normalize_model_id((string)post_value('summarizerModel', $model), $model);

$state = recover_loop_state_if_needed();
if (empty($state['activeTask']) || !is_array($state['activeTask'])) {
    json_response(['message' => 'No active task. Start one first.'], 400);
}
if (loop_is_active($state)) {
    json_response(['message' => 'The autonomous loop is active. Cancel it before changing runtime settings.'], 409);
}

$activeTask = $state['activeTask'];
$runtime = is_array($activeTask['runtime'] ?? null) ? $activeTask['runtime'] : [];
$currentBudget = normalize_budget_config(is_array($runtime['budget'] ?? null) ? $runtime['budget'] : []);
$currentResearch = normalize_research_config(is_array($runtime['research'] ?? null) ? $runtime['research'] : []);
$currentLocalFiles = normalize_local_file_tool_config(is_array($runtime['localFiles'] ?? null) ? $runtime['localFiles'] : []);
$currentGitHubTools = normalize_github_tool_config(is_array($runtime['githubTools'] ?? null) ? $runtime['githubTools'] : []);
$currentDynamicSpinup = normalize_dynamic_spinup_config(is_array($runtime['dynamicSpinup'] ?? null) ? $runtime['dynamicSpinup'] : []);
$currentVetting = normalize_vetting_config(is_array($runtime['vetting'] ?? null) ? $runtime['vetting'] : []);
$currentLoop = normalize_loop_preferences(is_array($activeTask['preferredLoop'] ?? null) ? $activeTask['preferredLoop'] : []);
$currentReasoningEffort = trim((string)($runtime['reasoningEffort'] ?? 'low'));
if (!in_array($currentReasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $currentReasoningEffort = 'low';
}

$reasoningEffort = trim((string)post_value('reasoningEffort', $currentReasoningEffort));
if (!in_array($reasoningEffort, ['none', 'low', 'medium', 'high', 'xhigh'], true)) {
    $reasoningEffort = $currentReasoningEffort;
}

$budget = normalize_budget_config([
    'maxTotalTokens' => post_int_value('maxTotalTokens', $currentBudget['maxTotalTokens']),
    'maxCostUsd' => post_float_value('maxCostUsd', $currentBudget['maxCostUsd']),
    'maxOutputTokens' => post_int_value('maxOutputTokens', $currentBudget['maxOutputTokens']),
    'targets' => (function () use ($currentBudget): array {
        $raw = post_value('budgetTargets', null);
        if ($raw === null) {
            return is_array($currentBudget['targets'] ?? null) ? $currentBudget['targets'] : [];
        }
        $decoded = json_decode((string)$raw, true);
        return is_array($decoded) ? $decoded : [];
    })(),
]);
$preferredLoop = normalize_loop_preferences([
    'rounds' => post_int_value('loopRounds', $currentLoop['rounds']),
    'delayMs' => post_int_value('loopDelayMs', $currentLoop['delayMs']),
]);
$research = normalize_research_config([
    'enabled' => post_value('researchEnabled', $currentResearch['enabled']),
    'externalWebAccess' => post_value('researchExternalWebAccess', $currentResearch['externalWebAccess']),
    'domains' => post_value('researchDomains', $currentResearch['domains']),
]);
$localFiles = normalize_local_file_tool_config([
    'enabled' => post_value('localFilesEnabled', $currentLocalFiles['enabled']),
    'roots' => post_value('localFileRoots', $currentLocalFiles['roots']),
]);
$githubTools = normalize_github_tool_config([
    'enabled' => post_value('githubToolsEnabled', $currentGitHubTools['enabled']),
    'repos' => post_value('githubAllowedRepos', $currentGitHubTools['repos']),
]);
$dynamicSpinup = normalize_dynamic_spinup_config([
    'enabled' => post_value('dynamicSpinupEnabled', $currentDynamicSpinup['enabled']),
]);
$vetting = normalize_vetting_config([
    'enabled' => post_value('vettingEnabled', $currentVetting['enabled']),
]);

$updatedState = mutate_state(function (array $state) use ($model, $summarizerModel, $reasoningEffort, $budget, $preferredLoop, $research, $localFiles, $githubTools, $dynamicSpinup, $vetting): array {
    if (!is_array($state['activeTask'] ?? null)) {
        throw new RuntimeException('No active task.');
    }

    $task = $state['activeTask'];
    $workers = task_workers($task);
    foreach ($workers as &$worker) {
        $worker['model'] = $model;
    }
    unset($worker);

    $task['workers'] = $workers;
    $task['runtime'] = is_array($task['runtime'] ?? null) ? $task['runtime'] : [];
    $task['runtime']['model'] = $model;
    $task['runtime']['reasoningEffort'] = $reasoningEffort;
    $task['runtime']['budget'] = $budget;
    $task['runtime']['research'] = $research;
    $task['runtime']['localFiles'] = $localFiles;
    $task['runtime']['githubTools'] = $githubTools;
    $task['runtime']['dynamicSpinup'] = $dynamicSpinup;
    $task['runtime']['vetting'] = $vetting;
    $task['preferredLoop'] = $preferredLoop;

    $summary = summarizer_config($task);
    $summary['model'] = $summarizerModel;
    $task['summarizer'] = $summary;

    $state['activeTask'] = $task;
    $state['draft'] = build_draft_from_task($task);
    return $state;
});

write_task_snapshot($updatedState['activeTask']);
append_step('model', 'Applied settings runtime and loop selection to the active task.', [
    'taskId' => $updatedState['activeTask']['taskId'] ?? null,
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel,
    'reasoningEffort' => $reasoningEffort,
    'budget' => $budget,
    'research' => $research,
    'localFiles' => $localFiles,
    'githubTools' => $githubTools,
    'dynamicSpinup' => $dynamicSpinup,
    'vetting' => $vetting,
    'preferredLoop' => $preferredLoop,
    'workerCount' => count(task_workers($updatedState['activeTask']))
]);

json_response([
    'message' => 'Applied runtime settings to the active task.',
    'workerModel' => $model,
    'summarizerModel' => $summarizerModel,
    'reasoningEffort' => $reasoningEffort,
    'budget' => $budget,
    'research' => $research,
    'localFiles' => $localFiles,
    'githubTools' => $githubTools,
    'dynamicSpinup' => $dynamicSpinup,
    'vetting' => $vetting,
    'preferredLoop' => $preferredLoop
]);
