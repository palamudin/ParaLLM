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
$objective = [string]$task['objective']
$constraints = @($task['constraints'])
$priorSummary = $state['summary']
$priorMemoryVersion = 0
if ($null -ne $state['memoryVersion']) {
    $priorMemoryVersion = [int]$state['memoryVersion']
}

$lastRiskRequest = $null
if ($state['workers']['B']) {
    $lastRiskRequest = [string]$state['workers']['B']['requestToPeer']
}

$stepNumber = 1
if ($state['workers']['A']) {
    $stepNumber = [int]$state['workers']['A']['step'] + 1
}

function New-MockCheckpoint {
    param(
        [int]$StepNumber,
        [string]$Objective,
        [array]$Constraints,
        [object]$PriorSummary,
        [int]$PriorMemoryVersion,
        [string]$LastRiskRequest
    )

    return [ordered]@{
        workerId = 'A'
        viewpoint = 'utility'
        step = $StepNumber
        observation = "Utility-first reading of objective: $Objective"
        peerSteer = if ($LastRiskRequest) { "Response to B: $LastRiskRequest" } else { 'No peer steer received yet.' }
        sharedMemorySeen = if ($PriorSummary) { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = [string]$PriorSummary['recommendedNextAction']
        }} else { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = 'No summary available yet.'
        }}
        benefits = @(
            'Parallel branches preserve alternative solution paths',
            'Checkpoint sharing reduces duplicated work',
            'Canonical state provides continuity across cycles',
            'Sparse peer steer can correct blind spots without merging both lanes'
        )
        detriments = @(
            'Shared summaries can cause premature convergence',
            'State coupling can amplify bad assumptions'
        )
        requiredCircumstances = @(
            'Structured checkpoint schema',
            'Stable JSON persistence',
            'Clear role separation between workers and summarizer'
        )
        invalidatingCircumstances = @(
            'Freeform raw-thought sharing at high frequency',
            'Untracked state overwrites',
            'No distinction between fact and assumption'
        )
        immediateConsequences = @(
            'Faster directional alignment',
            'Lower chance of blind duplicate exploration'
        )
        downstreamConsequences = @(
            'Better continuity for iterative runs',
            'Potential long-term drift if summary quality degrades'
        )
        uncertainty = @(
            'Actual value depends on checkpoint cadence',
            'Persistence model may need locking under heavier concurrency',
            'Utility lane can overvalue momentum if steer packets are too persuasive'
        )
        reversalConditions = @(
            'If workers stop producing distinct value, reduce sharing',
            'If summaries lose critical nuance, widen checkpoint payload'
        )
        confidence = 0.74
        requestToPeer = 'Stress test this round for hidden coupling and summarize the worst likely failure mode.'
        constraintsSeen = $Constraints
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function New-LiveCheckpoint {
    param(
        [string]$ApiKey,
        [hashtable]$Runtime,
        [int]$StepNumber,
        [string]$Objective,
        [array]$Constraints,
        [object]$PriorSummary,
        [int]$PriorMemoryVersion,
        [string]$LastRiskRequest
    )

    $schema = @{
        type = 'object'
        additionalProperties = $false
        required = @('workerId', 'viewpoint', 'step', 'observation', 'peerSteer', 'sharedMemorySeen', 'benefits', 'detriments', 'requiredCircumstances', 'invalidatingCircumstances', 'immediateConsequences', 'downstreamConsequences', 'uncertainty', 'reversalConditions', 'confidence', 'requestToPeer', 'constraintsSeen')
        properties = @{
            workerId = @{ type = 'string' }
            viewpoint = @{ type = 'string' }
            step = @{ type = 'integer' }
            observation = @{ type = 'string' }
            peerSteer = @{ type = 'string' }
            sharedMemorySeen = @{
                type = 'object'
                additionalProperties = $false
                required = @('memoryVersion', 'recommendedNextAction')
                properties = @{
                    memoryVersion = @{ type = 'integer' }
                    recommendedNextAction = @{ type = 'string' }
                }
            }
            benefits = @{ type = 'array'; items = @{ type = 'string' } }
            detriments = @{ type = 'array'; items = @{ type = 'string' } }
            requiredCircumstances = @{ type = 'array'; items = @{ type = 'string' } }
            invalidatingCircumstances = @{ type = 'array'; items = @{ type = 'string' } }
            immediateConsequences = @{ type = 'array'; items = @{ type = 'string' } }
            downstreamConsequences = @{ type = 'array'; items = @{ type = 'string' } }
            uncertainty = @{ type = 'array'; items = @{ type = 'string' } }
            reversalConditions = @{ type = 'array'; items = @{ type = 'string' } }
            confidence = @{ type = 'number' }
            requestToPeer = @{ type = 'string' }
            constraintsSeen = @{ type = 'array'; items = @{ type = 'string' } }
        }
    }

    $instructions = @"
You are Worker A in a dual-process reasoning loop.
Role: utility-first analysis.
Return JSON only that matches the schema exactly.
Be concise but specific.
Preserve disagreement rather than smoothing it away.
Do not mention hidden chain-of-thought.
Set workerId to A, viewpoint to utility, and step to $StepNumber.
"@

    $summaryText = 'none'
    if ($PriorSummary) {
        $summaryText = ($PriorSummary | ConvertTo-Json -Depth 10)
    }

    $peerText = if ($LastRiskRequest) { $LastRiskRequest } else { 'No peer steer received yet.' }

    $inputText = @"
Objective:
$Objective

Constraints:
$(($Constraints -join "`n"))

Shared memory version seen:
$PriorMemoryVersion

Prior summary:
$summaryText

Latest steer from Worker B:
$peerText

Produce a utility-first checkpoint for this round.
"@

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName 'worker_a_checkpoint' -Schema $schema
    $parsed = $result['parsed']
    $parsed['updatedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    return @{
        checkpoint = $parsed
        responseId = [string]$result['response'].id
    }
}

$checkpoint = $null
$responseId = $null
$modeUsed = 'mock'

if ($runtime['executionMode'] -eq 'live') {
    $apiKey = Get-ApiKey -Root $RootPath
    if ($apiKey) {
        try {
            $liveResult = New-LiveCheckpoint -ApiKey $apiKey -Runtime $runtime -StepNumber $stepNumber -Objective $objective -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -LastRiskRequest $lastRiskRequest
            $checkpoint = $liveResult['checkpoint']
            $responseId = $liveResult['responseId']
            $modeUsed = 'live'
        } catch {
            Add-Step -Root $RootPath -Stage 'worker_A' -Message 'Live API call failed; falling back to mock.' -Context @{
                taskId = $task['taskId']
                step = $stepNumber
                model = $runtime['model']
                error = $_.Exception.Message
            }
        }
    } else {
        Add-Step -Root $RootPath -Stage 'worker_A' -Message 'No API key found; falling back to mock.' -Context @{
            taskId = $task['taskId']
            step = $stepNumber
        }
    }
}

if ($null -eq $checkpoint) {
    $checkpoint = New-MockCheckpoint -StepNumber $stepNumber -Objective $objective -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -LastRiskRequest $lastRiskRequest
}

$checkpoint['step'] = $stepNumber
$checkpoint['workerId'] = 'A'
$checkpoint['viewpoint'] = 'utility'

$state['workers']['A'] = $checkpoint
Write-State -Root $RootPath -State $state
$cpPath = Join-Path $RootPath ("data\checkpoints\{0}_A.json" -f $task['taskId'])
$checkpoint | ConvertTo-Json -Depth 10 | Set-Content -Path $cpPath -Encoding UTF8
Add-Event -Root $RootPath -Type 'worker_checkpoint' -Payload @{ worker = 'A'; taskId = $task['taskId']; viewpoint = 'utility'; mode = $modeUsed }
Add-Step -Root $RootPath -Stage 'worker_A' -Message 'Worker A produced a checkpoint.' -Context @{
    taskId = $task['taskId']
    step = $stepNumber
    memoryVersionSeen = $priorMemoryVersion
    mode = $modeUsed
    model = $runtime['model']
    responseId = $responseId
}
Write-Output 'Worker A checkpoint written.'
