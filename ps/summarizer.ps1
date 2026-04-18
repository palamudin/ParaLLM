param(
    [string]$RootPath
)

. (Join-Path $RootPath 'ps\common.ps1') -RootPath $RootPath

function New-MockSummary {
    param(
        [hashtable]$Task,
        [array]$Workers,
        [hashtable]$WorkerState
    )

    $round = 0
    foreach ($worker in $Workers) {
        $checkpoint = $WorkerState[$worker['id']]
        if ($checkpoint -and [int]$checkpoint['step'] -gt $round) {
            $round = [int]$checkpoint['step']
        }
    }

    $packets = @(Expand-PeerSteerPackets -Task $Task -State @{ workers = $WorkerState })
    $conflicts = @()
    $primary = $Workers | Where-Object { $_['id'] -eq 'A' } | Select-Object -First 1
    $challengers = @($Workers | Where-Object { $_['id'] -ne 'A' } | Select-Object -First 3)
    foreach ($challenger in $challengers) {
        $conflicts += ,([ordered]@{
            topic = $challenger['focus']
            positions = @(
                [ordered]@{
                    workerId = if ($primary) { $primary['id'] } else { $Workers[0]['id'] }
                    claim = 'Momentum is only justified when it remains auditable and budget-bounded.'
                },
                [ordered]@{
                    workerId = $challenger['id']
                    claim = 'This lane argues that the design is still exposed around ' + [string]$challenger['focus'] + '.'
                }
            )
        })
    }

    return [ordered]@{
        taskId = $Task['taskId']
        round = $round
        stableFindings = @(
            'Structured checkpoints let many lanes disagree without losing continuity.',
            'Budget ceilings are mandatory once multiple model-backed lanes are active.',
            'Per-position model selection changes both quality and spend, so it must be visible.'
        )
        conflicts = $conflicts
        conditionalTruths = @(
            'More lanes help only when each lane preserves a distinct viewpoint.',
            'Adversarial expansion is useful when the spend ceiling and output cap stay hard enough to prevent runaway loops.',
            'Mixing models by position can improve robustness if the cheaper lanes carry most of the exploration.'
        )
        peerSteerPackets = $packets
        recommendedNextAction = 'Keep the default live model cheap, override only the lanes that need stronger reasoning, and review cost deltas after each round.'
        sourceWorkers = @($Workers | ForEach-Object { [string]$_['id'] })
        mergedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function New-LiveSummary {
    param(
        [string]$ApiKey,
        [hashtable]$Task,
        [array]$Workers,
        [hashtable]$WorkerState,
        [hashtable]$Runtime
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
                    required = @('topic', 'positions')
                    properties = @{
                        topic = @{ type = 'string' }
                        positions = @{
                            type = 'array'
                            items = @{
                                type = 'object'
                                additionalProperties = $false
                                required = @('workerId', 'claim')
                                properties = @{
                                    workerId = @{ type = 'string' }
                                    claim = @{ type = 'string' }
                                }
                            }
                        }
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
You are the summarizer in a sparse multi-lane reasoning loop.
Merge all worker checkpoints into a structured summary.
Preserve disagreements and conditional truths.
Do not erase contradictions.
Return JSON only that matches the schema exactly.
"@

    $inputText = @"
Task:
$(($Task | ConvertTo-Json -Depth 20))

Worker lineup:
$(($Workers | ConvertTo-Json -Depth 10))

Worker checkpoints:
$(($WorkerState | ConvertTo-Json -Depth 20))
"@

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName 'loop_summary_multi' -Schema $schema -MaxOutputTokens ([int]$Runtime['maxOutputTokens'])
    $parsed = $result['parsed']
    $parsed['mergedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    return @{
        summary = $parsed
        responseId = [string]$result['response'].id
        response = $result['response']
    }
}

$state = Read-State -Root $RootPath
$task = Get-Task -State $state
if ($null -eq $task) {
    Write-Output 'No active task.'
    exit 1
}

$workers = @(Get-WorkerDefinitions -Task $task)
$workerState = @{}
foreach ($worker in $workers) {
    if (-not $state['workers'].ContainsKey($worker['id']) -or $null -eq $state['workers'][$worker['id']]) {
        Write-Output 'All configured worker checkpoints are required before summarizing.'
        exit 1
    }
    $workerState[$worker['id']] = $state['workers'][$worker['id']]
}

$summaryConfig = Get-SummarizerConfig -Task $task
$runtime = Get-TaskRuntime -Task $task -ModelOverride $summaryConfig['model']
$summary = $null
$responseId = $null
$usageSnapshot = $null
$modeUsed = 'mock'

if ($runtime['executionMode'] -eq 'live') {
    $apiKey = Get-ApiKey -Root $RootPath
    if ($apiKey) {
        try {
            Assert-BudgetAvailable -Root $RootPath -Target 'summarizer' -Task $task
            $liveResult = New-LiveSummary -ApiKey $apiKey -Task $task -Workers $workers -WorkerState $workerState -Runtime $runtime
            $summary = $liveResult['summary']
            $responseId = $liveResult['responseId']
            $usageSnapshot = Update-UsageTracking -Root $RootPath -Target 'summarizer' -TaskId ([string]$task['taskId']) -Model $runtime['model'] -ResponseId $responseId -Response $liveResult['response']
            $modeUsed = 'live'
        } catch {
            if ($_.Exception.Message -like 'Budget limit reached:*') {
                Add-Step -Root $RootPath -Stage 'budget' -Message 'Budget stopped the summarizer before another live call.' -Context @{
                    taskId = $task['taskId']
                    model = $runtime['model']
                    error = $_.Exception.Message
                }
                throw
            }

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
    $summary = New-MockSummary -Task $task -Workers $workers -WorkerState $workerState
}

$state = Read-State -Root $RootPath
$state['summary'] = $summary
$state['memoryVersion'] = [int]$state['memoryVersion'] + 1
Write-State -Root $RootPath -State $state

$summaryJson = $summary | ConvertTo-Json -Depth 20
$summaryPath = Join-Path $RootPath ("data\checkpoints\{0}_summary.json" -f $task['taskId'])
$historySummaryPath = Join-Path $RootPath ("data\checkpoints\{0}_summary_round{1:D3}.json" -f $task['taskId'], [int]$summary['round'])
Write-Utf8NoBom -Path $summaryPath -Value $summaryJson
Write-Utf8NoBom -Path $historySummaryPath -Value $summaryJson

Add-Event -Root $RootPath -Type 'summary_written' -Payload @{
    taskId = $task['taskId']
    memoryVersion = $state['memoryVersion']
    mode = $modeUsed
    model = $runtime['model']
    sourceWorkers = @($workers | ForEach-Object { [string]$_['id'] })
}

$budgetTotals = if ($null -ne $usageSnapshot) { $usageSnapshot } else { $state['usage'] }
Add-Step -Root $RootPath -Stage 'summarizer' -Message 'Summarizer merged worker checkpoints.' -Context @{
    taskId = $task['taskId']
    round = $summary['round']
    memoryVersion = $state['memoryVersion']
    mode = $modeUsed
    model = $runtime['model']
    responseId = $responseId
    workerCount = $workers.Count
    totalTokens = if ($budgetTotals) { [int]$budgetTotals['totalTokens'] } else { 0 }
    estimatedCostUsd = if ($budgetTotals) { [double]$budgetTotals['estimatedCostUsd'] } else { 0.0 }
    checkpointFile = [System.IO.Path]::GetFileName($historySummaryPath)
}

Write-Output 'Summary written.'
