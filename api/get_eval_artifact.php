<?php
require __DIR__ . '/common.php';

ensure_eval_paths();

$runId = trim((string)($_GET['runId'] ?? ''));
$artifactId = trim((string)($_GET['artifactId'] ?? ''));
if ($runId === '' || $artifactId === '') {
    json_response(['message' => 'runId and artifactId are required.'], 400);
}

$run = read_eval_run($runId);
if (!is_array($run)) {
    json_response(['message' => 'Eval run not found.'], 404);
}

$artifactIndex = is_array($run['artifactIndex'] ?? null) ? $run['artifactIndex'] : [];
$entry = $artifactIndex[$artifactId] ?? null;
if (!is_array($entry)) {
    json_response(['message' => 'Eval artifact not found.'], 404);
}

$relativePath = (string)($entry['relativePath'] ?? '');
$artifactFile = eval_resolve_run_file($runId, $relativePath);
if ($artifactFile === null) {
    json_response(['message' => 'Eval artifact file is missing.'], 404);
}

$content = read_json_file_safe($artifactFile);
if (!is_array($content)) {
    json_response(['message' => 'Eval artifact content is invalid.'], 500);
}

json_response([
    'artifactId' => $artifactId,
    'name' => $entry['name'] ?? basename($artifactFile),
    'kind' => $entry['kind'] ?? 'artifact',
    'storage' => 'eval',
    'modifiedAt' => $entry['modifiedAt'] ?? gmdate('c', filemtime($artifactFile) ?: time()),
    'size' => $entry['size'] ?? (filesize($artifactFile) ?: 0),
    'summary' => is_array($entry['summary'] ?? null) ? $entry['summary'] : [],
    'policy' => artifact_visibility_policy(),
    'content' => $content,
]);
