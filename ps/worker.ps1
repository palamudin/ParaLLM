param(
    [string]$RootPath,
    [string]$WorkerId
)

. (Join-Path $RootPath 'ps\common.ps1') -RootPath $RootPath

function Get-DefaultRequestTargets {
    param(
        [hashtable]$Task,
        [string]$CurrentWorkerId
    )

    $allWorkers = @(Get-WorkerDefinitions -Task $Task)
    $peerIds = @($allWorkers | Where-Object { $_['id'] -ne $CurrentWorkerId } | ForEach-Object { [string]$_['id'] })
    if ($peerIds.Count -eq 0) {
        return @()
    }
    if ($CurrentWorkerId -eq 'A' -and $peerIds -contains 'B') {
        return @('B')
    }
    if ($CurrentWorkerId -ne 'A' -and $peerIds -contains 'A') {
        return @('A')
    }
    return @($peerIds[0])
}

function Normalize-RequestTargets {
    param(
        [object]$Targets,
        [hashtable]$Task,
        [string]$CurrentWorkerId
    )

    $validTargets = @{}
    foreach ($worker in (Get-WorkerDefinitions -Task $Task)) {
        if ($worker['id'] -ne $CurrentWorkerId) {
            $validTargets[[string]$worker['id']] = $true
        }
    }

    $normalized = @()
    foreach ($target in @($Targets)) {
        $candidate = ([string]$target).Trim().ToUpperInvariant()
        if ($validTargets.ContainsKey($candidate)) {
            $normalized += $candidate
        }
    }

    if ($normalized.Count -gt 0) {
        return ,([string[]]@($normalized | Select-Object -Unique))
    }

    return (Get-DefaultRequestTargets -Task $Task -CurrentWorkerId $CurrentWorkerId)
}

function Normalize-UrlList {
    param([object]$Urls)
    return (Normalize-UrlArrayValues -Value $Urls)
}

function Normalize-EvidenceLedger {
    param([object]$Ledger)

    $normalized = @()
    foreach ($entry in @($Ledger)) {
        if ($null -eq $entry) {
            continue
        }
        $claim = if (Test-ObjectKey -Value $entry -Key 'claim') { ([string]$entry['claim']).Trim() } else { '' }
        if ([string]::IsNullOrWhiteSpace($claim)) {
            continue
        }
        $supportLevel = if (Test-ObjectKey -Value $entry -Key 'supportLevel') { ([string]$entry['supportLevel']).Trim() } else { 'weak' }
        $note = if (Test-ObjectKey -Value $entry -Key 'note') { ([string]$entry['note']).Trim() } else { '' }
        $sourceUrls = if (Test-ObjectKey -Value $entry -Key 'sourceUrls') { Normalize-UrlList -Urls $entry['sourceUrls'] } else { @() }

        $normalized += ,([ordered]@{
            claim = $claim
            supportLevel = if ([string]::IsNullOrWhiteSpace($supportLevel)) { 'weak' } else { $supportLevel }
            sourceUrls = $sourceUrls
            note = $note
        })
    }

    return $normalized
}

function New-MockCheckpoint {
    param(
        [hashtable]$Task,
        [hashtable]$Worker,
        [hashtable]$Runtime,
        [hashtable]$ResearchConfig,
        [int]$StepNumber,
        [array]$Constraints,
        [object]$PriorSummary,
        [int]$PriorMemoryVersion,
        [array]$PeerMessages
    )

    $viewpoint = if ($Worker['role'] -eq 'utility') { 'utility' } else { 'adversarial' }
    $defaultTargets = Get-DefaultRequestTargets -Task $Task -CurrentWorkerId $Worker['id']
    $peerText = if ($PeerMessages.Count -gt 0) {
        ($PeerMessages | ForEach-Object { '{0}: {1}' -f $_['from'], $_['message'] }) -join "`n"
    } else {
        'No peer steer received yet.'
    }
    $researchMode = if ($ResearchConfig['enabled']) { 'mock_research' } else { 'mock' }

    $requestToPeer = if ($Worker['role'] -eq 'utility') {
        'Pressure-test whether the expected upside survives real-world constraints without adding hidden coordination drag.'
    } else {
        'Defend why the plan survives the failure mode centered on ' + [string]$Worker['focus'] + '.'
    }

    return [ordered]@{
        workerId = $Worker['id']
        label = $Worker['label']
        role = $Worker['role']
        viewpoint = $viewpoint
        focus = $Worker['focus']
        step = $StepNumber
        modelUsed = $Runtime['model']
        observation = ('{0} reading of objective with focus on {1}.' -f $Worker['label'], $Worker['focus'])
        peerSteer = $peerText
        sharedMemorySeen = if ($PriorSummary) { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = [string]$PriorSummary['recommendedNextAction']
        }} else { [ordered]@{
            memoryVersion = $PriorMemoryVersion
            recommendedNextAction = 'No summary available yet.'
        }}
        benefits = @(
            ('Keeps an explicit lane focused on ' + [string]$Worker['focus']),
            'Preserves parallel disagreement instead of forcing one blended answer',
            'Supports sparse steer packets without merging all process state'
        )
        detriments = @(
            'Adds more coordination cost as the roster expands',
            'Can magnify review noise if every lane argues without discipline'
        )
        requiredCircumstances = @(
            'Structured checkpoint schema',
            'Stable locked state updates',
            'A hard distinction between observations, risks, and requests to peers'
        )
        invalidatingCircumstances = @(
            'Freeform high-frequency raw-thought sharing',
            'Missing budget ceilings for live runs',
            'Untracked worker additions or silent model changes'
        )
        immediateConsequences = @(
            ('More coverage over blind spots tied to ' + [string]$Worker['focus']),
            'Higher coordination load per round'
        )
        downstreamConsequences = @(
            'Better auditability of why a lane disagreed',
            'Higher spend risk if worker growth is not capped by budget'
        )
        uncertainty = @(
            'The useful number of simultaneous lanes is task-dependent',
            'Per-position model choice can improve outcomes or just waste budget',
            'Steer packets need tuning so they influence without collapsing independence'
        )
        reversalConditions = @(
            'Reduce this lane if it stops adding distinct evidence',
            'Raise or lower sharing cadence only after checking budget and convergence behavior'
        )
        researchMode = $researchMode
        researchQueries = if ($ResearchConfig['enabled']) { @($Task['objective']) } else { @() }
        researchSources = @()
        urlCitations = @()
        evidenceLedger = @(
            [ordered]@{
                claim = 'Parallel lane separation keeps this viewpoint explicit instead of flattening it into a single answer.'
                supportLevel = 'weak'
                sourceUrls = @()
                note = 'Mock mode only; this is a scaffolded claim and still needs grounded evidence.'
            },
            [ordered]@{
                claim = 'Budget ceilings and model controls are necessary once multiple lanes can run live.'
                supportLevel = 'weak'
                sourceUrls = @()
                note = 'Mock mode only; production confidence depends on live accounting and observed loop behavior.'
            }
        )
        evidenceGaps = @(
            'No live web sources were consulted in mock mode.',
            'Claims should be re-run with grounded research before being treated as supported.'
        )
        confidence = if ($Worker['role'] -eq 'utility') { 0.72 } else { 0.77 }
        requestToPeer = $requestToPeer
        requestTargets = $defaultTargets
        constraintsSeen = $Constraints
        updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function New-LiveCheckpoint {
    param(
        [string]$ApiKey,
        [hashtable]$Task,
        [hashtable]$Worker,
        [hashtable]$Runtime,
        [hashtable]$ResearchConfig,
        [int]$StepNumber,
        [array]$Constraints,
        [object]$PriorSummary,
        [int]$PriorMemoryVersion,
        [array]$PeerMessages
    )

    $peerTargets = @((Get-WorkerDefinitions -Task $Task) | Where-Object { $_['id'] -ne $Worker['id'] } | ForEach-Object { [string]$_['id'] })
    $schema = @{
        type = 'object'
        additionalProperties = $false
        required = @('workerId', 'label', 'role', 'viewpoint', 'focus', 'step', 'modelUsed', 'observation', 'peerSteer', 'sharedMemorySeen', 'benefits', 'detriments', 'requiredCircumstances', 'invalidatingCircumstances', 'immediateConsequences', 'downstreamConsequences', 'uncertainty', 'reversalConditions', 'researchMode', 'researchQueries', 'researchSources', 'urlCitations', 'evidenceLedger', 'evidenceGaps', 'confidence', 'requestToPeer', 'requestTargets', 'constraintsSeen')
        properties = @{
            workerId = @{ type = 'string' }
            label = @{ type = 'string' }
            role = @{ type = 'string' }
            viewpoint = @{ type = 'string' }
            focus = @{ type = 'string' }
            step = @{ type = 'integer' }
            modelUsed = @{ type = 'string' }
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
            researchMode = @{ type = 'string' }
            researchQueries = @{ type = 'array'; items = @{ type = 'string' } }
            researchSources = @{ type = 'array'; items = @{ type = 'string' } }
            urlCitations = @{ type = 'array'; items = @{ type = 'string' } }
            evidenceLedger = @{
                type = 'array'
                items = @{
                    type = 'object'
                    additionalProperties = $false
                    required = @('claim', 'supportLevel', 'sourceUrls', 'note')
                    properties = @{
                        claim = @{ type = 'string' }
                        supportLevel = @{ type = 'string' }
                        sourceUrls = @{ type = 'array'; items = @{ type = 'string' } }
                        note = @{ type = 'string' }
                    }
                }
            }
            evidenceGaps = @{ type = 'array'; items = @{ type = 'string' } }
            confidence = @{ type = 'number' }
            requestToPeer = @{ type = 'string' }
            requestTargets = @{ type = 'array'; items = @{ type = 'string' } }
            constraintsSeen = @{ type = 'array'; items = @{ type = 'string' } }
        }
    }

    $peerText = if ($PeerMessages.Count -gt 0) {
        ($PeerMessages | ForEach-Object { '{0}: {1}' -f $_['from'], $_['message'] }) -join "`n"
    } else {
        'No peer steer received yet.'
    }

    $summaryText = if ($PriorSummary) { $PriorSummary | ConvertTo-Json -Depth 15 } else { 'none' }
    $instructions = @"
You are $($Worker['label']) in a sparse multi-lane reasoning loop.
Role: $($Worker['role']).
Your special focus is: $($Worker['focus']).
Return JSON only that matches the schema exactly.
Be concise but specific.
Preserve disagreement rather than smoothing it away.
Do not reveal hidden chain-of-thought.
Set workerId to $($Worker['id']), label to $($Worker['label']), role to $($Worker['role']), focus to $($Worker['focus']), modelUsed to $($Runtime['model']), and step to $StepNumber.
requestTargets must only contain peers from this list: $($peerTargets -join ', ').
If researchMode is web_search, use the web search tool before answering and keep evidence grounded in URLs actually consulted.
Every evidenceLedger item must capture one concrete claim, its supportLevel, the relevant sourceUrls, and a short note on why the evidence matters.
If evidence is missing or weak, say so in evidenceGaps instead of overstating certainty.
"@

    $researchDescription = if ($ResearchConfig['enabled']) {
        'Enabled. Workers may use web_search.'
    } else {
        'Disabled. Workers must reason from existing context only.'
    }
    $researchDomainsText = if ($ResearchConfig['domains'].Count -gt 0) {
        $ResearchConfig['domains'] -join ', '
    } else {
        'none'
    }

    $inputText = @"
Objective:
$([string]$Task['objective'])

Constraints:
$(($Constraints -join "`n"))

Worker roster:
$(($Task['workers'] | ConvertTo-Json -Depth 10))

Research policy:
$researchDescription
externalWebAccess: $($ResearchConfig['externalWebAccess'])
allowedDomains: $researchDomainsText

Shared memory version seen:
$PriorMemoryVersion

Prior summary:
$summaryText

Peer steer addressed to this lane:
$peerText

Produce a checkpoint from your assigned viewpoint.
"@

    $tools = @()
    $toolChoice = $null
    $include = @()
    if ($ResearchConfig['enabled']) {
        $webSearchTool = [ordered]@{
            type = 'web_search'
            external_web_access = [bool]$ResearchConfig['externalWebAccess']
        }
        if ($ResearchConfig['domains'].Count -gt 0) {
            $webSearchTool['filters'] = [ordered]@{
                allowed_domains = @($ResearchConfig['domains'])
            }
        }
        $tools = @($webSearchTool)
        $toolChoice = 'auto'
        $include = @('web_search_call.action.sources')
    }

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName ('worker_' + $Worker['id'].ToLowerInvariant() + '_checkpoint') -Schema $schema -MaxOutputTokens ([int]$Runtime['maxOutputTokens']) -Tools $tools -ToolChoice $toolChoice -Include $include
    $parsed = $result['parsed']
    $parsed['researchQueries'] = @(Normalize-StringArrayPreserveItems -Value $result['webSearchQueries'])
    $parsed['researchSources'] = @(Normalize-UrlList -Urls $result['webSearchSources'])
    $parsed['urlCitations'] = @(Normalize-UrlList -Urls $result['urlCitations'])
    $parsed['researchMode'] = if ($parsed['researchSources'].Count -gt 0 -or $parsed['researchQueries'].Count -gt 0) { 'web_search' } elseif ($ResearchConfig['enabled']) { 'research_requested_no_sources' } else { 'model_only' }
    $parsed['evidenceLedger'] = @(Normalize-EvidenceLedger -Ledger $parsed['evidenceLedger'])
    $parsed['evidenceGaps'] = @(Normalize-StringList -Value $parsed['evidenceGaps'])
    $parsed['updatedAt'] = (Get-Date).ToUniversalTime().ToString('o')
    return @{
        checkpoint = $parsed
        responseId = [string]$result['response'].id
        response = $result['response']
    }
}

$workerId = ([string]$WorkerId).Trim().ToUpperInvariant()
if ($workerId -notmatch '^[A-Z]$') {
    Write-Output 'A single uppercase worker id is required.'
    exit 1
}

$state = Read-State -Root $RootPath
$task = Get-Task -State $state
if ($null -eq $task) {
    Write-Output 'No active task.'
    exit 1
}

$worker = Find-WorkerDefinition -Task $task -WorkerId $workerId
if ($null -eq $worker) {
    Write-Output ('Unknown worker id: ' + $workerId)
    exit 1
}

$runtime = Get-TaskRuntime -Task $task -ModelOverride $worker['model']
$researchConfig = Get-ResearchConfig -Task $task
$constraints = @($task['constraints'])
$priorSummary = $state['summary']
$priorMemoryVersion = 0
if ($null -ne $state['memoryVersion']) {
    $priorMemoryVersion = [int]$state['memoryVersion']
}

$stepNumber = 1
if ($state['workers'].ContainsKey($workerId) -and $null -ne $state['workers'][$workerId]) {
    $stepNumber = [int]$state['workers'][$workerId]['step'] + 1
}

$peerMessages = @(Get-PeerSteerMessages -State $state -Task $task -WorkerId $workerId)
$checkpoint = $null
$responseId = $null
$response = $null
$usageSnapshot = $null
$modeUsed = 'mock'

if ($runtime['executionMode'] -eq 'live') {
    $apiKey = Get-ApiKey -Root $RootPath
    if ($apiKey) {
        try {
            Assert-BudgetAvailable -Root $RootPath -Target $workerId -Task $task
            $liveResult = New-LiveCheckpoint -ApiKey $apiKey -Task $task -Worker $worker -Runtime $runtime -ResearchConfig $researchConfig -StepNumber $stepNumber -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -PeerMessages $peerMessages
            $checkpoint = $liveResult['checkpoint']
            $responseId = $liveResult['responseId']
            $response = $liveResult['response']
            $usageSnapshot = Update-UsageTracking -Root $RootPath -Target $workerId -TaskId ([string]$task['taskId']) -Model $runtime['model'] -ResponseId $responseId -Response $response
            $modeUsed = 'live'
        } catch {
            if ($_.Exception.Message -like 'Budget limit reached:*') {
                Add-Step -Root $RootPath -Stage 'budget' -Message ('Budget stopped ' + $worker['label'] + ' before another live call.') -Context @{
                    taskId = $task['taskId']
                    workerId = $workerId
                    model = $runtime['model']
                    error = $_.Exception.Message
                }
                throw
            }

            Add-Step -Root $RootPath -Stage ('worker_' + $workerId) -Message 'Live API call failed; falling back to mock.' -Context @{
                taskId = $task['taskId']
                workerId = $workerId
                step = $stepNumber
                model = $runtime['model']
                error = $_.Exception.Message
            }
        }
    } else {
        Add-Step -Root $RootPath -Stage ('worker_' + $workerId) -Message 'No API key found; falling back to mock.' -Context @{
            taskId = $task['taskId']
            workerId = $workerId
            step = $stepNumber
        }
    }
}

if ($null -eq $checkpoint) {
    $checkpoint = New-MockCheckpoint -Task $task -Worker $worker -Runtime $runtime -ResearchConfig $researchConfig -StepNumber $stepNumber -Constraints $constraints -PriorSummary $priorSummary -PriorMemoryVersion $priorMemoryVersion -PeerMessages $peerMessages
}

$checkpoint['step'] = $stepNumber
$checkpoint['workerId'] = $workerId
$checkpoint['label'] = $worker['label']
$checkpoint['role'] = $worker['role']
$checkpoint['focus'] = $worker['focus']
$checkpoint['modelUsed'] = $runtime['model']
$checkpoint['benefits'] = Normalize-StringArrayPreserveItems -Value $checkpoint['benefits']
$checkpoint['detriments'] = Normalize-StringArrayPreserveItems -Value $checkpoint['detriments']
$checkpoint['requiredCircumstances'] = Normalize-StringArrayPreserveItems -Value $checkpoint['requiredCircumstances']
$checkpoint['invalidatingCircumstances'] = Normalize-StringArrayPreserveItems -Value $checkpoint['invalidatingCircumstances']
$checkpoint['immediateConsequences'] = Normalize-StringArrayPreserveItems -Value $checkpoint['immediateConsequences']
$checkpoint['downstreamConsequences'] = Normalize-StringArrayPreserveItems -Value $checkpoint['downstreamConsequences']
$checkpoint['uncertainty'] = Normalize-StringArrayPreserveItems -Value $checkpoint['uncertainty']
$checkpoint['reversalConditions'] = Normalize-StringArrayPreserveItems -Value $checkpoint['reversalConditions']
$checkpoint['constraintsSeen'] = Normalize-StringArrayPreserveItems -Value $checkpoint['constraintsSeen']
$checkpoint['researchQueries'] = Normalize-StringArrayPreserveItems -Value $checkpoint['researchQueries']
$checkpoint['researchSources'] = Normalize-UrlList -Urls $checkpoint['researchSources']
$checkpoint['urlCitations'] = Normalize-UrlList -Urls $checkpoint['urlCitations']
$checkpoint['evidenceLedger'] = Normalize-EvidenceLedger -Ledger $checkpoint['evidenceLedger']
$checkpoint['evidenceGaps'] = Normalize-StringArrayPreserveItems -Value $checkpoint['evidenceGaps']
$checkpoint['requestTargets'] = Normalize-RequestTargets -Targets $checkpoint['requestTargets'] -Task $task -CurrentWorkerId $workerId

$state = Read-State -Root $RootPath
$state['workers'][$workerId] = $checkpoint
Write-State -Root $RootPath -State $state

$checkpointJson = $checkpoint | ConvertTo-Json -Depth 20
$latestCpPath = Join-Path $RootPath ("data\checkpoints\{0}_{1}.json" -f $task['taskId'], $workerId)
$historyCpPath = Join-Path $RootPath ("data\checkpoints\{0}_{1}_step{2:D3}.json" -f $task['taskId'], $workerId, $stepNumber)
Write-Utf8NoBom -Path $latestCpPath -Value $checkpointJson
Write-Utf8NoBom -Path $historyCpPath -Value $checkpointJson

$outputArtifact = [ordered]@{
    taskId = [string]$task['taskId']
    artifactType = 'worker_output'
    target = $workerId
    label = [string]$worker['label']
    mode = $modeUsed
    model = [string]$runtime['model']
    step = $stepNumber
    capturedAt = (Get-Date).ToUniversalTime().ToString('o')
    responseId = $responseId
    rawOutputText = if ($null -ne $response) { Get-ResponseOutputText -Response $response } else { $null }
    responseMeta = if ($null -ne $response) {
        [ordered]@{
            status = if ($null -ne $response.status) { [string]$response.status } else { 'completed' }
            usageDelta = Get-ResponseUsageDelta -Response $response -Model $runtime['model']
            webSearchQueries = ConvertTo-JsonArray -Value @(Get-ResponseWebSearchQueries -Response $response)
            webSearchSources = ConvertTo-JsonArray -Value @(Get-ResponseWebSearchSources -Response $response)
            urlCitations = ConvertTo-JsonArray -Value @(Get-ResponseUrlCitations -Response $response)
        }
    } else {
        $null
    }
    output = Normalize-CheckpointStateValue -Checkpoint $checkpoint
}
$outputArtifactJson = $outputArtifact | ConvertTo-Json -Depth 25
$latestOutputPath = Join-Path (Get-OutputsPath -Root $RootPath) ("{0}_{1}_output.json" -f $task['taskId'], $workerId)
$historyOutputPath = Join-Path (Get-OutputsPath -Root $RootPath) ("{0}_{1}_step{2:D3}_output.json" -f $task['taskId'], $workerId, $stepNumber)
Write-Utf8NoBom -Path $latestOutputPath -Value $outputArtifactJson
Write-Utf8NoBom -Path $historyOutputPath -Value $outputArtifactJson

Add-Event -Root $RootPath -Type 'worker_checkpoint' -Payload @{
    worker = $workerId
    label = $worker['label']
    taskId = $task['taskId']
    role = $worker['role']
    model = $runtime['model']
    mode = $modeUsed
}

$budgetTotals = if ($null -ne $usageSnapshot) { $usageSnapshot } else { $state['usage'] }
Add-Step -Root $RootPath -Stage ('worker_' + $workerId) -Message ($worker['label'] + ' produced a checkpoint.') -Context @{
    taskId = $task['taskId']
    workerId = $workerId
    step = $stepNumber
    memoryVersionSeen = $priorMemoryVersion
    mode = $modeUsed
    model = $runtime['model']
    researchMode = [string]$checkpoint['researchMode']
    researchSourceCount = @($checkpoint['researchSources']).Count
    responseId = $responseId
    totalTokens = if ($budgetTotals) { [int]$budgetTotals['totalTokens'] } else { 0 }
    estimatedCostUsd = if ($budgetTotals) { [double]$budgetTotals['estimatedCostUsd'] } else { 0.0 }
    checkpointFile = [System.IO.Path]::GetFileName($historyCpPath)
    outputFile = [System.IO.Path]::GetFileName($historyOutputPath)
}

Write-Output ($worker['label'] + ' checkpoint written.')
