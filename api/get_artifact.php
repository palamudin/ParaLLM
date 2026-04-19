<?php
require __DIR__ . '/common.php';
ensure_data_paths();

$name = basename(trim((string)($_GET['name'] ?? '')));
if ($name === '' || !preg_match('/\.json$/i', $name)) {
    json_response(['message' => 'A valid artifact filename is required.'], 400);
}

$path = null;
$storage = null;
foreach ([OUTPUTS_PATH => 'outputs', CHECKPOINTS_PATH => 'checkpoints'] as $dir => $bucket) {
    $candidate = $dir . DIRECTORY_SEPARATOR . $name;
    if (is_file($candidate)) {
        $path = $candidate;
        $storage = $bucket;
        break;
    }
}

if ($path === null) {
    json_response(['message' => 'Artifact not found.'], 404);
}

$raw = @file_get_contents($path);
if ($raw === false || trim($raw) === '') {
    json_response(['message' => 'Artifact is empty.'], 500);
}
if (strncmp($raw, "\xEF\xBB\xBF", 3) === 0) {
    $raw = substr($raw, 3);
}

$content = json_decode($raw, true);
if (!is_array($content)) {
    json_response(['message' => 'Artifact JSON could not be parsed.'], 500);
}

$responseMeta = is_array($content['responseMeta'] ?? null) ? $content['responseMeta'] : [];

$kind = 'artifact';
if (isset($content['artifactType']) && is_string($content['artifactType']) && trim($content['artifactType']) !== '') {
    $kind = trim($content['artifactType']);
} elseif (preg_match('/_summary_round\d+\.json$/i', $name)) {
    $kind = 'summary_round';
} elseif (preg_match('/_[A-Z]_step\d+\.json$/i', $name)) {
    $kind = 'worker_step';
}

json_response([
    'name' => $name,
    'kind' => $kind,
    'storage' => $storage,
    'modifiedAt' => gmdate('c', filemtime($path)),
    'size' => filesize($path),
    'summary' => [
        'taskId' => $content['taskId'] ?? null,
        'target' => $content['target'] ?? ($content['workerId'] ?? null),
        'label' => $content['label'] ?? null,
        'mode' => $content['mode'] ?? null,
        'model' => $content['model'] ?? ($content['modelUsed'] ?? null),
        'step' => $content['step'] ?? null,
        'round' => $content['round'] ?? null,
        'responseId' => $content['responseId'] ?? null,
        'requestedMaxOutputTokens' => isset($responseMeta['requestedMaxOutputTokens']) ? (int)$responseMeta['requestedMaxOutputTokens'] : null,
        'effectiveMaxOutputTokens' => isset($responseMeta['effectiveMaxOutputTokens']) ? (int)$responseMeta['effectiveMaxOutputTokens'] : null,
        'maxOutputTokenAttempts' => array_values(array_map('intval', is_array($responseMeta['maxOutputTokenAttempts'] ?? null) ? $responseMeta['maxOutputTokenAttempts'] : [])),
        'recoveredFromIncomplete' => !empty($responseMeta['recoveredFromIncomplete']),
        'rawOutputAvailable' => isset($content['rawOutputText']) && trim((string)$content['rawOutputText']) !== '',
    ],
    'policy' => artifact_visibility_policy(),
    'content' => $content,
]);
