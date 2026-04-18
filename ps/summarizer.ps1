param(
    [string]$RootPath
)

. (Join-Path $RootPath 'ps\common.ps1') -RootPath $RootPath

$state = Read-State -Root $RootPath
$task = Get-Task -State $state
if ($null -eq $task) {
    Write-Output 'No active task.'
    exit 1
}

$runtime = Get-TaskRuntime -Task $task
$workerA = $state['workers']['A']
$workerB = $state['workers']['B']
if ($null -eq $workerA -or $null -eq $workerB) {
    Write-Output 'Both worker checkpoints are required before summarizing.'
    exit 1
}

function New-MockSummary {
    param(
        [hashtable]$Task,
        [hashtable]$WorkerA,
        [hashtable]$WorkerB
    )

    return [ordered]@{
        taskId = $Task['taskId']
        round = [Math]::Max([int]$WorkerA['step'], [int]$WorkerB['step'])
        stableFindings = @(
            'Structured checkpoints are mandatory for usable mid-process sharing.',
            'Independent roles plus a shared state object improve continuity.',
            'Over-sharing raw reasoning would damage parallel search quality.',
            'Peer steer packets can be useful if they stay brief and role-bounded.'
        )
        conflicts = @(
            [ordered]@{
                topic = 'Coupling tradeoff'
                workerA = 'Shared summaries reduce duplicate work and improve continuity.'
                workerB = 'Shared summaries increase convergence risk and error propagation.'
            },
            [ordered]@{
                topic = 'Checkpoint frequency'
                workerA = 'Regular checkpoints help steer branches.'
                workerB = 'High-frequency checkpoints can collapse independence.'
            }
        )
        conditionalTruths = @(
            'This architecture is useful when checkpoint cadence stays sparse and structured.',
            'It becomes brittle when summaries overwrite contradictions or assumptions are treated as facts.',
            'A steer packet is safer than a raw-thought dump when two lanes need mid-process influence.'
        )
        peerSteerPackets = @(
            [ordered]@{
                from = 'A'
                to = 'B'
                message = [string]$WorkerA['requestToPeer']
            },
            [ordered]@{
                from = 'B'
                to = 'A'
                message = [string]$WorkerB['requestToPeer']
            }
        )
        recommendedNextAction = 'Run another round and inspect whether peer steer sharpens disagreement without collapsing independence.'
        sourceWorkers = @('A', 'B')
        mergedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function New-LiveSummary {
    param(
        [string]$ApiKey,
        [hashtable]$Runtime,
        [hashtable]$Task,
        [hashtable]$WorkerA,
        [hashtable]$WorkerB
    )

    $schema = @{
        type = 'object'
        additionalProperties = $false
        required = @('taskId', 'round', 'stableFindings', 'conflicts', 'conditionalTruths', 'peerSteerPackets', 'recommendedNextAction', 'sourceWorkers')
        properties = @{
            taskId = @{ type = 'string' }
            round = @{ type = 'integer' }
            stableFindings = @{ type = 'array'; items = @{ type = 'string' } }
            conflicts = @{
                type = 'array'
                items = @{
                    type = 'object'
                    additionalProperties = $false
                    required = @('topic', 'workerA', 'workerB')
                    properties = @{
                        topic = @{ type = 'string' }
                        workerA = @{ type = 'string' }
                        workerB = @{ type = 'string' }
                    }
                }
            }
            conditionalTruths = @{ type = 'array'; items = @{ type = 'string' } }
            peerSteerPackets = @{
                type = 'array'
                items = @{
                    type = 'object'
                    additionalProperties = $false
                    required = @('from', 'to', 'message')
                    properties = @{
                        from = @{ type = 'string' }
                        to = @{ type = 'string' }
                        message = @{ type = 'string' }
                    }
                }
            }
            recommendedNextAction = @{ type = 'string' }
            sourceWorkers = @{ type = 'array'; items = @{ type = 'string' } }
        }
    }

    $instructions = @"
You are the summarizer in a dual-process reasoning loop.
Merge the two worker checkpoints into a structured summary.
Preserve disagreements and conditional truths.
Return JSON only that matches the schema exactly.
"@

    $inputText = @"
Task:
$(($Task | ConvertTo-Json -Depth 10))

Worker A checkpoint:
$(($WorkerA | ConvertTo-Json -Depth 10))

Worker B checkpoint:
$(($WorkerB | ConvertTo-Json -Depth 10))
"@

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName 'loop_summary' -Schema $schema
    $parsed = $result['parsed']
    $parsed['mergedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    return @{
        summary = $parsed
        responseId = [string]$result['response'].id
    }
}

$summary = $null
$responseId = $null
$modeUsed = 'mock'

if ($runtime['executionMode'] -eq 'live') {
    $apiKey = Get-ApiKey -Root $RootPath
    if ($apiKey) {
        try {
            $liveResult = New-LiveSummary -ApiKey $apiKey -Runtime $runtime -Task $task -WorkerA $workerA -WorkerB $workerB
            $summary = $liveResult['summary']
            $responseId = $liveResult['responseId']
            $modeUsed = 'live'
        } catch {
            Add-Step -Root $RootPath -Stage 'summarizer' -Message 'Live API call failed; falling back to mock.' -Context @{
                taskId = $task['taskId']
                model = $runtime['model']
                error = $_.Exception.Message
            }
        }
    } else {
        Add-Step -Root $RootPath -Stage 'summarizer' -Message 'No API key found; falling back to mock.' -Context @{
            taskId = $task['taskId']
        }
    }
}

if ($null -eq $summary) {
    $summary = New-MockSummary -Task $task -WorkerA $workerA -WorkerB $workerB
}

$state['summary'] = $summary
$state['memoryVersion'] = [int]$state['memoryVersion'] + 1
Write-State -Root $RootPath -State $state
$summaryPath = Join-Path $RootPath ("data\checkpoints\{0}_summary.json" -f $task['taskId'])
$summary | ConvertTo-Json -Depth 10 | Set-Content -Path $summaryPath -Encoding UTF8
Add-Event -Root $RootPath -Type 'summary_written' -Payload @{ taskId = $task['taskId']; memoryVersion = $state['memoryVersion']; mode = $modeUsed }
Add-Step -Root $RootPath -Stage 'summarizer' -Message 'Summarizer merged worker checkpoints.' -Context @{
    taskId = $task['taskId']
    round = $summary['round']
    memoryVersion = $state['memoryVersion']
    mode = $modeUsed
    model = $runtime['model']
    responseId = $responseId
}
Write-Output 'Summary written.'
