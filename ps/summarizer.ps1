param(
    [string]$RootPath
)

. (Join-Path $RootPath 'ps\common.ps1') -RootPath $RootPath

function Normalize-UrlList {
    param([object]$Urls)
    return (Normalize-UrlArrayValues -Value $Urls)
}

function Normalize-WorkerIdList {
    param([object]$Ids)

    $normalized = @{}
    foreach ($id in (Normalize-StringArrayPreserveItems -Value $Ids)) {
        $candidate = ([string]$id).Trim().ToUpperInvariant()
        if ($candidate -match '^[A-Z]+$') {
            $normalized[$candidate] = $true
        }
    }
    return ,([string[]]@($normalized.Keys))
}

function Normalize-EvidenceVerdicts {
    param([object]$Verdicts)

    $normalized = @()
    foreach ($verdict in @($Verdicts)) {
        if ($null -eq $verdict) {
            continue
        }
        $claim = if (Test-ObjectKey -Value $verdict -Key 'claim') { ([string]$verdict['claim']).Trim() } else { '' }
        if ([string]::IsNullOrWhiteSpace($claim)) {
            continue
        }
        $status = if (Test-ObjectKey -Value $verdict -Key 'status') { ([string]$verdict['status']).Trim() } else { 'unvetted' }
        $rationale = if (Test-ObjectKey -Value $verdict -Key 'rationale') { ([string]$verdict['rationale']).Trim() } else { '' }
        $sourceUrls = if (Test-ObjectKey -Value $verdict -Key 'sourceUrls') { Normalize-UrlList -Urls $verdict['sourceUrls'] } else { @() }
        $supportingWorkers = if (Test-ObjectKey -Value $verdict -Key 'supportingWorkers') { Normalize-WorkerIdList -Ids $verdict['supportingWorkers'] } else { @() }
        $challengingWorkers = if (Test-ObjectKey -Value $verdict -Key 'challengingWorkers') { Normalize-WorkerIdList -Ids $verdict['challengingWorkers'] } else { @() }

        $normalized += ,([ordered]@{
            claim = $claim
            status = if ([string]::IsNullOrWhiteSpace($status)) { 'unvetted' } else { $status }
            supportingWorkers = $supportingWorkers
            challengingWorkers = $challengingWorkers
            sourceUrls = $sourceUrls
            rationale = $rationale
        })
    }
    return $normalized
}

function Truncate-TextValue {
    param(
        [object]$Value,
        [int]$MaxLength = 320
    )

    $text = ([string]$Value).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return ''
    }
    if ($text.Length -le $MaxLength) {
        return $text
    }
    return ($text.Substring(0, [Math]::Max(0, $MaxLength - 3)) + '...')
}

function Limit-StringList {
    param(
        [object]$Value,
        [int]$MaxItems = 8,
        [int]$MaxLength = 220
    )

    $items = New-Object System.Collections.Generic.List[string]
    foreach ($entry in @(Normalize-StringArrayPreserveItems -Value $Value | Select-Object -First $MaxItems)) {
        $trimmed = Truncate-TextValue -Value $entry -MaxLength $MaxLength
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
            $items.Add($trimmed)
        }
    }
    return ,([string[]]$items.ToArray())
}

function Limit-UrlList {
    param(
        [object]$Value,
        [int]$MaxItems = 10
    )

    $items = New-Object System.Collections.Generic.List[string]
    foreach ($entry in @(Normalize-UrlList -Urls $Value | Select-Object -First $MaxItems)) {
        $trimmed = ([string]$entry).Trim()
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
            $items.Add($trimmed)
        }
    }
    return ,([string[]]$items.ToArray())
}

function Project-TaskForSummary {
    param([hashtable]$Task)

    $runtime = Get-TaskRuntime -Task $Task
    $budget = Get-BudgetConfig -Task $Task
    $research = Get-ResearchConfig -Task $Task
    $vetting = Get-VettingConfig -Task $Task

    return [ordered]@{
        taskId = [string]$Task['taskId']
        objective = Truncate-TextValue -Value $Task['objective'] -MaxLength 800
        sessionContext = Truncate-TextValue -Value $Task['sessionContext'] -MaxLength 600
        constraints = @(Limit-StringList -Value $Task['constraints'] -MaxItems 12 -MaxLength 240)
        syncPolicy = if (Test-ObjectKey -Value $Task -Key 'syncPolicy') { ConvertTo-HashtableCompat -Value $Task['syncPolicy'] } else { @{} }
        runtime = [ordered]@{
            executionMode = [string]$runtime['executionMode']
            reasoningEffort = [string]$runtime['reasoningEffort']
            budget = $budget
            research = $research
            vetting = $vetting
        }
    }
}

function Project-WorkerRosterForSummary {
    param([array]$Workers)

    $projected = New-Object System.Collections.ArrayList
    foreach ($worker in @($Workers)) {
        [void]$projected.Add([ordered]@{
            id = [string]$worker['id']
            label = [string]$worker['label']
            role = [string]$worker['role']
            focus = Truncate-TextValue -Value $worker['focus'] -MaxLength 180
            model = [string]$worker['model']
        })
    }
    return $projected
}

function Project-WorkerCheckpointForSummary {
    param([object]$Checkpoint)

    $value = ConvertTo-HashtableCompat -Value $Checkpoint
    if ($null -eq $value -or -not ($value -is [System.Collections.IDictionary])) {
        return $null
    }

    $ledger = New-Object System.Collections.ArrayList
    foreach ($entry in @($value['evidenceLedger'] | Select-Object -First 6)) {
        $entryValue = ConvertTo-HashtableCompat -Value $entry
        if ($null -eq $entryValue -or -not ($entryValue -is [System.Collections.IDictionary])) {
            continue
        }

        [void]$ledger.Add([ordered]@{
            claim = Truncate-TextValue -Value $entryValue['claim'] -MaxLength 260
            supportLevel = [string]$entryValue['supportLevel']
            sourceUrls = @(Limit-UrlList -Value $entryValue['sourceUrls'] -MaxItems 6)
            note = Truncate-TextValue -Value $entryValue['note'] -MaxLength 220
        })
    }

    return [ordered]@{
        workerId = [string]$value['workerId']
        label = [string]$value['label']
        role = [string]$value['role']
        focus = Truncate-TextValue -Value $value['focus'] -MaxLength 180
        step = if (Test-ObjectKey -Value $value -Key 'step') { [int]$value['step'] } else { 0 }
        observation = Truncate-TextValue -Value $value['observation'] -MaxLength 420
        benefits = @(Limit-StringList -Value $value['benefits'] -MaxItems 4 -MaxLength 180)
        detriments = @(Limit-StringList -Value $value['detriments'] -MaxItems 4 -MaxLength 180)
        requiredCircumstances = @(Limit-StringList -Value $value['requiredCircumstances'] -MaxItems 4 -MaxLength 180)
        invalidatingCircumstances = @(Limit-StringList -Value $value['invalidatingCircumstances'] -MaxItems 4 -MaxLength 180)
        immediateConsequences = @(Limit-StringList -Value $value['immediateConsequences'] -MaxItems 4 -MaxLength 180)
        downstreamConsequences = @(Limit-StringList -Value $value['downstreamConsequences'] -MaxItems 4 -MaxLength 180)
        uncertainty = @(Limit-StringList -Value $value['uncertainty'] -MaxItems 4 -MaxLength 180)
        reversalConditions = @(Limit-StringList -Value $value['reversalConditions'] -MaxItems 4 -MaxLength 180)
        researchMode = [string]$value['researchMode']
        researchQueries = @(Limit-StringList -Value $value['researchQueries'] -MaxItems 6 -MaxLength 180)
        researchSources = @(Limit-UrlList -Value $value['researchSources'] -MaxItems 10)
        urlCitations = @(Limit-UrlList -Value $value['urlCitations'] -MaxItems 10)
        evidenceLedger = $ledger
        evidenceGaps = @(Limit-StringList -Value $value['evidenceGaps'] -MaxItems 6 -MaxLength 180)
        confidence = if (Test-ObjectKey -Value $value -Key 'confidence') { [double]$value['confidence'] } else { 0.0 }
        requestToPeer = Truncate-TextValue -Value $value['requestToPeer'] -MaxLength 220
        requestTargets = @(Normalize-WorkerIdList -Ids $value['requestTargets'])
        sharedMemorySeen = if (Test-ObjectKey -Value $value -Key 'sharedMemorySeen') { ConvertTo-HashtableCompat -Value $value['sharedMemorySeen'] } else { @{} }
    }
}

function Project-WorkerStateForSummary {
    param(
        [hashtable]$WorkerState,
        [array]$Workers
    )

    $projected = New-Object System.Collections.ArrayList
    foreach ($worker in @($Workers)) {
        if (-not $WorkerState.ContainsKey($worker['id'])) {
            continue
        }
        $checkpoint = Project-WorkerCheckpointForSummary -Checkpoint $WorkerState[$worker['id']]
        if ($null -ne $checkpoint) {
            [void]$projected.Add($checkpoint)
        }
    }
    return $projected
}

function New-MockSummary {
    param(
        [hashtable]$Task,
        [array]$Workers,
        [hashtable]$WorkerState,
        [hashtable]$VettingConfig
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
        vettingSummary = if ($VettingConfig['enabled']) {
            'Mock vetting suggests the checkpoint schema is ready for evidence review, but the claims still need live sourced validation.'
        } else {
            'Vetting is disabled; this summary preserves conflicts but does not score evidence quality.'
        }
        evidenceVerdicts = @(
            [ordered]@{
                claim = 'Budget ceilings are necessary once multiple live lanes are active.'
                status = if ($VettingConfig['enabled']) { 'weak' } else { 'unvetted' }
                supportingWorkers = @('A', 'B')
                challengingWorkers = @()
                sourceUrls = @()
                rationale = 'Mock mode cannot confirm the claim with live source evidence, but both lanes converge on it as an operating principle.'
            }
        )
        claimsNeedingVerification = @(
            'Any claim that relies on current external facts rather than local design intent.',
            'Any recommendation that assumes the current pricing or capability mix stays unchanged.'
        )
        evidenceCoverage = [ordered]@{
            supported = 0
            mixed = 0
            weak = if ($VettingConfig['enabled']) { 1 } else { 0 }
            unsupported = 0
            unvetted = if ($VettingConfig['enabled']) { 0 } else { 1 }
        }
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
        [hashtable]$Runtime,
        [hashtable]$VettingConfig
    )

    $schema = @{
        type = 'object'
        additionalProperties = $false
        required = @('taskId', 'round', 'stableFindings', 'conflicts', 'conditionalTruths', 'vettingSummary', 'evidenceVerdicts', 'claimsNeedingVerification', 'evidenceCoverage', 'peerSteerPackets', 'recommendedNextAction', 'sourceWorkers')
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
            vettingSummary = @{ type = 'string' }
            evidenceVerdicts = @{
                type = 'array'
                items = @{
                    type = 'object'
                    additionalProperties = $false
                    required = @('claim', 'status', 'supportingWorkers', 'challengingWorkers', 'sourceUrls', 'rationale')
                    properties = @{
                        claim = @{ type = 'string' }
                        status = @{ type = 'string' }
                        supportingWorkers = @{ type = 'array'; items = @{ type = 'string' } }
                        challengingWorkers = @{ type = 'array'; items = @{ type = 'string' } }
                        sourceUrls = @{ type = 'array'; items = @{ type = 'string' } }
                        rationale = @{ type = 'string' }
                    }
                }
            }
            claimsNeedingVerification = @{ type = 'array'; items = @{ type = 'string' } }
            evidenceCoverage = @{
                type = 'object'
                additionalProperties = $false
                required = @('supported', 'mixed', 'weak', 'unsupported', 'unvetted')
                properties = @{
                    supported = @{ type = 'integer' }
                    mixed = @{ type = 'integer' }
                    weak = @{ type = 'integer' }
                    unsupported = @{ type = 'integer' }
                    unvetted = @{ type = 'integer' }
                }
            }
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
Act as the evidence vetter for the shared memory.
Preserve disagreements and conditional truths.
Do not erase contradictions.
Judge worker claims using the evidence they provide.
Prefer evidence already cited by workers instead of restating every detail.
Do not upgrade weak evidence into a supported fact.
Do not do new research.
If vetting is disabled, keep verdicts conservative and mark unsupported confidence clearly.
Return JSON only that matches the schema exactly.
"@

    $taskProjection = Project-TaskForSummary -Task $Task
    $rosterProjection = Project-WorkerRosterForSummary -Workers $Workers
    $workerProjection = Project-WorkerStateForSummary -WorkerState $WorkerState -Workers $Workers

    $inputText = @"
Task brief:
$(($taskProjection | ConvertTo-Json -Depth 12))

Worker lineup:
$(($rosterProjection | ConvertTo-Json -Depth 10))

Vetting enabled:
$($VettingConfig['enabled'])

Worker checkpoint digests:
$(($workerProjection | ConvertTo-Json -Depth 14))
"@

    $result = Invoke-OpenAIJson -ApiKey $ApiKey -Model $Runtime['model'] -ReasoningEffort $Runtime['reasoningEffort'] -Instructions $instructions -InputText $inputText -SchemaName 'loop_summary_multi' -Schema $schema -MaxOutputTokens ([int]$Runtime['maxOutputTokens'])
    $parsed = $result['parsed']
    $parsed['evidenceVerdicts'] = @(Normalize-EvidenceVerdicts -Verdicts $parsed['evidenceVerdicts'])
    $parsed['claimsNeedingVerification'] = @(Normalize-StringArrayPreserveItems -Value $parsed['claimsNeedingVerification'])
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
$vettingConfig = Get-VettingConfig -Task $task
$summary = $null
$responseId = $null
$response = $null
$usageSnapshot = $null
$modeUsed = 'mock'

if ($runtime['executionMode'] -eq 'live') {
    $apiKey = Get-ApiKey -Root $RootPath
    if ($apiKey) {
        try {
            Assert-BudgetAvailable -Root $RootPath -Target 'summarizer' -Task $task
            $liveResult = New-LiveSummary -ApiKey $apiKey -Task $task -Workers $workers -WorkerState $workerState -Runtime $runtime -VettingConfig $vettingConfig
            $summary = $liveResult['summary']
            $responseId = $liveResult['responseId']
            $response = $liveResult['response']
            $usageSnapshot = Update-UsageTracking -Root $RootPath -Target 'summarizer' -TaskId ([string]$task['taskId']) -Model $runtime['model'] -ResponseId $responseId -Response $response
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
    $summary = New-MockSummary -Task $task -Workers $workers -WorkerState $workerState -VettingConfig $vettingConfig
}

$summary['stableFindings'] = Normalize-StringArrayPreserveItems -Value $summary['stableFindings']
$summary['conditionalTruths'] = Normalize-StringArrayPreserveItems -Value $summary['conditionalTruths']
$summary['claimsNeedingVerification'] = Normalize-StringArrayPreserveItems -Value $summary['claimsNeedingVerification']
$summary['sourceWorkers'] = Normalize-WorkerIdList -Ids $summary['sourceWorkers']
$summary['evidenceVerdicts'] = Normalize-EvidenceVerdicts -Verdicts $summary['evidenceVerdicts']

$state = Read-State -Root $RootPath
$state['summary'] = $summary
$state['memoryVersion'] = [int]$state['memoryVersion'] + 1
Write-State -Root $RootPath -State $state

$summaryJson = (Normalize-SummaryStateValue -Summary $summary) | ConvertTo-Json -Depth 20
$summaryPath = Join-Path $RootPath ("data\checkpoints\{0}_summary.json" -f $task['taskId'])
$historySummaryPath = Join-Path $RootPath ("data\checkpoints\{0}_summary_round{1:D3}.json" -f $task['taskId'], [int]$summary['round'])
Write-Utf8NoBom -Path $summaryPath -Value $summaryJson
Write-Utf8NoBom -Path $historySummaryPath -Value $summaryJson

$summaryOutputArtifact = [ordered]@{
    taskId = [string]$task['taskId']
    artifactType = 'summary_output'
    target = 'summarizer'
    label = [string]$summaryConfig['label']
    mode = $modeUsed
    model = [string]$runtime['model']
    round = [int]$summary['round']
    capturedAt = (Get-Date).ToUniversalTime().ToString('o')
    responseId = $responseId
    rawOutputText = if ($null -ne $response) { Get-ResponseOutputText -Response $response } else { $null }
    responseMeta = if ($null -ne $response) {
        [ordered]@{
            status = if ($null -ne $response.status) { [string]$response.status } else { 'completed' }
            usageDelta = Get-ResponseUsageDelta -Response $response -Model $runtime['model']
        }
    } else {
        $null
    }
    output = Normalize-SummaryStateValue -Summary $summary
}
$summaryOutputJson = $summaryOutputArtifact | ConvertTo-Json -Depth 25
$latestSummaryOutputPath = Join-Path (Get-OutputsPath -Root $RootPath) ("{0}_summary_output.json" -f $task['taskId'])
$historySummaryOutputPath = Join-Path (Get-OutputsPath -Root $RootPath) ("{0}_summary_round{1:D3}_output.json" -f $task['taskId'], [int]$summary['round'])
Write-Utf8NoBom -Path $latestSummaryOutputPath -Value $summaryOutputJson
Write-Utf8NoBom -Path $historySummaryOutputPath -Value $summaryOutputJson

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
    vettingEnabled = [bool]$vettingConfig['enabled']
    totalTokens = if ($budgetTotals) { [int]$budgetTotals['totalTokens'] } else { 0 }
    estimatedCostUsd = if ($budgetTotals) { [double]$budgetTotals['estimatedCostUsd'] } else { 0.0 }
    checkpointFile = [System.IO.Path]::GetFileName($historySummaryPath)
    outputFile = [System.IO.Path]::GetFileName($historySummaryOutputPath)
}

Write-Output 'Summary written.'
