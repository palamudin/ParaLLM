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

$lastUtilityRequest = $null
if ($state['workers']['A']) {
    $lastUtilityRequest = [string]$state['workers']['A']['requestToPeer']
}

$stepNumber = 1
if ($state['workers']['B']) {
    $stepNumber = [int]$state['workers']['B']['step'] + 1
}

function New-MockCheckpoint {
    param(
        [int]$StepNumber,
        [string]$Objective,
        [array]$Constraints,
        [object]$PriorSummary,
        [int]$PriorMemoryVersion,
        [string]$LastUtilityRequest
    )

    return [ordered]@{
        workerId = 'B'
        viewpoint = 'risk'
        step = $StepNumber
        observation = "Risk-first reading of objective: $Objective"
        peerSteer = if ($LastUtilityRequest) { "Response to A: $LastUtilityRequest" } else { 'No peer steer received yet.' }
        sharedMemorySeen = if ($PriorSummary) { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = [string]$PriorSummary['recommendedNextAction']
        }} else { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = 'No summary available yet.'
        }}
        benefits = @(
            'Adversarial modeling catches brittle assumptions early',
            'Conflict preservation prevents false certainty',
            'Peer steer lets the risk lane attack the utility lane where it is most confident'
        )
        detriments = @(
            'Extra coordination overhead can slow each cycle',
            'Shared state becomes a single point of corruption'
        )
        requiredCircumstances = @(
            'Strict write discipline',
            'Conflict fields preserved in summary',
            'Role-based independence until checkpoint'
        )
        invalidatingCircumstances = @(
            'Workers reading each other constantly',
            'Summarizer smoothing over disagreement',
            'No audit trail of state transitions'
        )
        immediateConsequences = @(
            'More friction before convergence',
            'Higher chance of surfacing hidden failure paths'
        )
        downstreamConsequences = @(
            'Reduced robustness if memory becomes self-referential',
            'Better resilience if contradictions remain visible'
        )
        uncertainty = @(
            'Frequency thresholds need empirical tuning',
            'PHP-triggered execution may need queueing later',
            'The risk lane can become performative if every round is forced to disagree'
        )
        reversalConditions = @(
            'If coordination cost outweighs branch value, simplify roles',
            'If event log grows noisy, compress events but keep checkpoints'
        )
        confidence = 0.79
        requestToPeer = 'Defend the minimum sharing cadence that still improves outcomes under real latency and cost limits.'
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
        [string]$LastUtilityRequest
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
You are Worker B in a dual-process reasoning loop.
Role: risk-first adversarial analysis.
Return JSON only that matches the schema exactly.
Be concise but specific.
Preserve disagreement rather than smoothing it away.
Do not mention hidden chain-of-thought.
Set workerId to B, viewpoint to risk, and step to $StepNumber.
"@

    $summaryText = 'none'
    if ($PriorSummary) {
        $summaryText = ($PriorSummary | ConvertTo-Json -Depth 10)
    }

    $peerText = if ($LastUtilityRequest) { $LastUtilityRequest } else { 'No peer steer received yet.' }

    $inputText = @"
Objective:
$Objective

Constraints:
$(($Constraints -join "`n"))

Shared memory version seen:
$PriorMemoryVersion

Prior summary:
$summaryText

Latest steer from Worker A:
$peerText

Produce a risk-first checkpoint for this round.
"@

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName 'worker_b_checkpoint' -Schema $schema
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
            $liveResult = New-LiveCheckpoint -ApiKey $apiKey -Runtime $runtime -StepNumber $stepNumber -Objective $objective -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -LastUtilityRequest $lastUtilityRequest
            $checkpoint = $liveResult['checkpoint']
            $responseId = $liveResult['responseId']
            $modeUsed = 'live'
        } catch {
            Add-Step -Root $RootPath -Stage 'worker_B' -Message 'Live API call failed; falling back to mock.' -Context @{
                taskId = $task['taskId']
                step = $stepNumber
                model = $runtime['model']
                error = $_.Exception.Message
            }
        }
    } else {
        Add-Step -Root $RootPath -Stage 'worker_B' -Message 'No API key found; falling back to mock.' -Context @{
            taskId = $task['taskId']
            step = $stepNumber
        }
    }
}

if ($null -eq $checkpoint) {
    $checkpoint = New-MockCheckpoint -StepNumber $stepNumber -Objective $objective -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -LastUtilityRequest $lastUtilityRequest
}

$checkpoint['step'] = $stepNumber
$checkpoint['workerId'] = 'B'
$checkpoint['viewpoint'] = 'risk'

$state['workers']['B'] = $checkpoint
Write-State -Root $RootPath -State $state
$checkpointJson = $checkpoint | ConvertTo-Json -Depth 10
$latestCpPath = Join-Path $RootPath ("data\checkpoints\{0}_B.json" -f $task['taskId'])
$historyCpPath = Join-Path $RootPath ("data\checkpoints\{0}_B_step{1:D3}.json" -f $task['taskId'], $stepNumber)
$checkpointJson | Set-Content -Path $latestCpPath -Encoding UTF8
$checkpointJson | Set-Content -Path $historyCpPath -Encoding UTF8
Add-Event -Root $RootPath -Type 'worker_checkpoint' -Payload @{ worker = 'B'; taskId = $task['taskId']; viewpoint = 'risk'; mode = $modeUsed }
Add-Step -Root $RootPath -Stage 'worker_B' -Message 'Worker B produced a checkpoint.' -Context @{
    taskId = $task['taskId']
    step = $stepNumber
    memoryVersionSeen = $priorMemoryVersion
    mode = $modeUsed
    model = $runtime['model']
    responseId = $responseId
    checkpointFile = [System.IO.Path]::GetFileName($historyCpPath)
}
Write-Output 'Worker B checkpoint written.'
