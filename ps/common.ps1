param(
    [string]$RootPath
)

function Get-DataPath {
    param([string]$Root)
    return (Join-Path $Root 'data')
}

function Get-StatePath {
    param([string]$Root)
    return (Join-Path $Root 'data\state.json')
}

function Get-EventsPath {
    param([string]$Root)
    return (Join-Path $Root 'data\events.jsonl')
}

function Get-StepsPath {
    param([string]$Root)
    return (Join-Path $Root 'data\steps.jsonl')
}

function Get-LocksPath {
    param([string]$Root)
    return (Join-Path $Root 'data\locks')
}

function Get-LockPath {
    param(
        [string]$Root,
        [string]$Name = 'loop'
    )
    return (Join-Path (Get-LocksPath -Root $Root) ($Name + '.lock'))
}

function Get-AuthPath {
    param([string]$Root)
    return (Join-Path $Root 'Auth.txt')
}

function Get-TasksPath {
    param([string]$Root)
    return (Join-Path $Root 'data\tasks')
}

function Get-OutputsPath {
    param([string]$Root)
    return (Join-Path $Root 'data\outputs')
}

function Get-TaskFilePath {
    param(
        [string]$Root,
        [string]$TaskId
    )
    return (Join-Path (Get-TasksPath -Root $Root) ($TaskId + '.json'))
}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Value
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Get-ModelCatalog {
    return @{
        'gpt-5.4' = @{ label = 'GPT-5.4'; inputPer1M = 2.50; cachedInputPer1M = 0.25; outputPer1M = 15.00 }
        'gpt-5.4-mini' = @{ label = 'GPT-5.4 mini'; inputPer1M = 0.75; cachedInputPer1M = 0.075; outputPer1M = 4.50 }
        'gpt-5.4-nano' = @{ label = 'GPT-5.4 nano'; inputPer1M = 0.20; cachedInputPer1M = 0.02; outputPer1M = 1.25 }
        'gpt-5.2' = @{ label = 'GPT-5.2'; inputPer1M = 1.75; cachedInputPer1M = 0.175; outputPer1M = 14.00 }
        'gpt-5.1' = @{ label = 'GPT-5.1'; inputPer1M = 1.25; cachedInputPer1M = 0.125; outputPer1M = 10.00 }
        'gpt-5' = @{ label = 'GPT-5'; inputPer1M = 1.25; cachedInputPer1M = 0.125; outputPer1M = 10.00 }
        'gpt-5-mini' = @{ label = 'GPT-5 mini'; inputPer1M = 0.25; cachedInputPer1M = 0.025; outputPer1M = 2.00 }
        'gpt-5-nano' = @{ label = 'GPT-5 nano'; inputPer1M = 0.05; cachedInputPer1M = 0.005; outputPer1M = 0.40 }
        'gpt-4.1' = @{ label = 'GPT-4.1'; inputPer1M = 2.00; cachedInputPer1M = 0.50; outputPer1M = 8.00 }
        'gpt-4.1-mini' = @{ label = 'GPT-4.1 mini'; inputPer1M = 0.40; cachedInputPer1M = 0.10; outputPer1M = 1.60 }
        'gpt-4.1-nano' = @{ label = 'GPT-4.1 nano'; inputPer1M = 0.10; cachedInputPer1M = 0.025; outputPer1M = 0.40 }
        'gpt-4o' = @{ label = 'GPT-4o'; inputPer1M = 2.50; cachedInputPer1M = 1.25; outputPer1M = 10.00 }
        'gpt-4o-mini' = @{ label = 'GPT-4o mini'; inputPer1M = 0.15; cachedInputPer1M = 0.075; outputPer1M = 0.60 }
    }
}

function Get-DefaultModelId {
    return 'gpt-5-mini'
}

function Normalize-ModelId {
    param(
        [string]$Model,
        [string]$Fallback = 'gpt-5-mini'
    )

    $catalog = Get-ModelCatalog
    if (-not [string]::IsNullOrWhiteSpace($Model) -and $catalog.ContainsKey($Model)) {
        return $Model
    }
    if (-not [string]::IsNullOrWhiteSpace($Fallback) -and $catalog.ContainsKey($Fallback)) {
        return $Fallback
    }
    return (Get-DefaultModelId)
}

function Get-DefaultBudgetConfig {
    return [ordered]@{
        maxTotalTokens = 250000
        maxCostUsd = 5.0
        maxOutputTokens = 1200
    }
}

function Normalize-BudgetConfig {
    param([object]$Budget)

    $default = Get-DefaultBudgetConfig
    $maxTotalTokens = $default['maxTotalTokens']
    $maxCostUsd = $default['maxCostUsd']
    $maxOutputTokens = $default['maxOutputTokens']

    if ($null -ne $Budget) {
        if ((Test-ObjectKey -Value $Budget -Key 'maxTotalTokens') -and $null -ne $Budget['maxTotalTokens']) {
            $maxTotalTokens = [Math]::Max(0, [int]$Budget['maxTotalTokens'])
        }
        if ((Test-ObjectKey -Value $Budget -Key 'maxCostUsd') -and $null -ne $Budget['maxCostUsd']) {
            $maxCostUsd = [Math]::Max(0.0, [double]$Budget['maxCostUsd'])
        }
        if ((Test-ObjectKey -Value $Budget -Key 'maxOutputTokens') -and $null -ne $Budget['maxOutputTokens']) {
            $maxOutputTokens = [Math]::Max(0, [int]$Budget['maxOutputTokens'])
        }
    }

    return [ordered]@{
        maxTotalTokens = $maxTotalTokens
        maxCostUsd = [Math]::Round($maxCostUsd, 6)
        maxOutputTokens = $maxOutputTokens
    }
}

function Coerce-Bool {
    param(
        [object]$Value,
        [bool]$Default = $false
    )

    if ($Value -is [bool]) {
        return [bool]$Value
    }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal]) {
        return ([double]$Value) -ne 0
    }
    if ($Value -is [string]) {
        $normalized = $Value.Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($normalized)) {
            return $Default
        }
        if ($normalized -in @('1', 'true', 'yes', 'on')) {
            return $true
        }
        if ($normalized -in @('0', 'false', 'no', 'off')) {
            return $false
        }
    }
    return $Default
}

function Normalize-StringList {
    param([object]$Value)

    $items = @()
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($entry in $Value) {
            $items += @(Normalize-StringList -Value $entry)
        }
    } elseif ($Value -is [string]) {
        foreach ($entry in ($Value -split "[`r`n,]+")) {
            $trimmed = $entry.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                $items += $trimmed
            }
        }
    }

    $deduped = @{}
    foreach ($item in $items) {
        $deduped[$item] = $true
    }
    return @($deduped.Keys)
}

function Normalize-StringArrayPreserveItems {
    param([object]$Value)

    $items = New-Object System.Collections.Generic.List[string]
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($entry in $Value) {
            foreach ($normalized in (Normalize-StringArrayPreserveItems -Value $entry)) {
                if (-not [string]::IsNullOrWhiteSpace($normalized)) {
                    $items.Add([string]$normalized)
                }
            }
        }
    } elseif ($Value -is [string]) {
        $trimmed = $Value.Trim()
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
            $items.Add($trimmed)
        }
    }

    $deduped = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($item in $items) {
        if (-not $seen.ContainsKey($item)) {
            $seen[$item] = $true
            $deduped.Add($item)
        }
    }

    return ,([string[]]$deduped.ToArray())
}

function ConvertTo-JsonArray {
    param([object]$Value)

    $list = New-Object System.Collections.ArrayList
    if ($null -eq $Value) {
        return ,$list
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($entry in $Value) {
            [void]$list.Add($entry)
        }
        return ,$list
    }

    [void]$list.Add($Value)
    return ,$list
}

function Normalize-CanonicalUrl {
    param([string]$Url)

    $candidate = ([string]$Url).Trim()
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $null
    }

    $candidate = $candidate.Trim('"', "'", '`')
    $candidate = $candidate.Trim()
    $candidate = $candidate -replace '[\uFFFD]+$', ''
    $candidate = $candidate -replace '(?i)(%EF%BF%BD)+$', ''
    $candidate = $candidate -replace '[\.,;\)\]\}>]+$', ''

    $uri = $null
    if (-not [System.Uri]::TryCreate($candidate, [System.UriKind]::Absolute, [ref]$uri)) {
        return $null
    }
    if ($uri.Scheme -notin @('http', 'https')) {
        return $null
    }
    if ([string]::IsNullOrWhiteSpace($uri.Host)) {
        return $null
    }

    $builder = New-Object System.UriBuilder($uri)
    $builder.Scheme = $uri.Scheme.ToLowerInvariant()
    $builder.Host = $uri.Host.ToLowerInvariant()
    if (($builder.Scheme -eq 'https' -and $builder.Port -eq 443) -or ($builder.Scheme -eq 'http' -and $builder.Port -eq 80)) {
        $builder.Port = -1
    }
    $builder.Fragment = ''

    $path = $builder.Path
    if (-not [string]::IsNullOrWhiteSpace($path) -and $path.Length -gt 1) {
        $builder.Path = $path.TrimEnd('/')
    }

    return $builder.Uri.AbsoluteUri
}

function Normalize-UrlArrayValues {
    param([object]$Value)

    $urls = New-Object System.Collections.Generic.List[string]
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($entry in $Value) {
            foreach ($url in (Normalize-UrlArrayValues -Value $entry)) {
                if (-not [string]::IsNullOrWhiteSpace($url)) {
                    $urls.Add([string]$url)
                }
            }
        }
    } elseif ($Value -is [string]) {
        $matches = [System.Text.RegularExpressions.Regex]::Matches($Value, 'https?://[^\s"''<>()]+')
        if ($matches.Count -gt 0) {
            foreach ($match in $matches) {
                $normalized = Normalize-CanonicalUrl -Url $match.Value
                if (-not [string]::IsNullOrWhiteSpace($normalized)) {
                    $urls.Add($normalized)
                }
            }
        } else {
            $normalized = Normalize-CanonicalUrl -Url $Value
            if (-not [string]::IsNullOrWhiteSpace($normalized)) {
                $urls.Add($normalized)
            }
        }
    }

    $deduped = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($url in $urls) {
        if (-not $seen.ContainsKey($url)) {
            $seen[$url] = $true
            $deduped.Add($url)
        }
    }

    return ,([string[]]$deduped.ToArray())
}

function Normalize-AllowedDomains {
    param([object]$Value)

    $domains = @{}
    foreach ($entry in (Normalize-StringList -Value $Value)) {
        $normalized = [string]$entry
        $normalized = $normalized -replace '^https?://', ''
        $normalized = $normalized -replace '/.*$', ''
        $normalized = $normalized.Trim().Trim('.').ToLowerInvariant()
        if (-not [string]::IsNullOrWhiteSpace($normalized)) {
            $domains[$normalized] = $true
        }
    }

    return @($domains.Keys | Select-Object -First 100)
}

function Get-DefaultResearchConfig {
    return [ordered]@{
        enabled = $false
        externalWebAccess = $true
        domains = @()
    }
}

function Normalize-ResearchConfig {
    param([object]$Config)

    $default = Get-DefaultResearchConfig
    $enabled = $default['enabled']
    $externalWebAccess = $default['externalWebAccess']
    $domains = @($default['domains'])

    if ($null -ne $Config) {
        if (Test-ObjectKey -Value $Config -Key 'enabled') {
            $enabled = Coerce-Bool -Value $Config['enabled'] -Default $enabled
        }
        if (Test-ObjectKey -Value $Config -Key 'externalWebAccess') {
            $externalWebAccess = Coerce-Bool -Value $Config['externalWebAccess'] -Default $externalWebAccess
        }
        if (Test-ObjectKey -Value $Config -Key 'domains') {
            $domains = @(Normalize-AllowedDomains -Value $Config['domains'])
        }
    }

    return [ordered]@{
        enabled = $enabled
        externalWebAccess = $externalWebAccess
        domains = $domains
    }
}

function Get-DefaultVettingConfig {
    return [ordered]@{
        enabled = $false
    }
}

function Normalize-VettingConfig {
    param([object]$Config)

    $default = Get-DefaultVettingConfig
    $enabled = $default['enabled']

    if ($null -ne $Config -and (Test-ObjectKey -Value $Config -Key 'enabled')) {
        $enabled = Coerce-Bool -Value $Config['enabled'] -Default $enabled
    }

    return [ordered]@{
        enabled = $enabled
    }
}

function Get-WebSearchToolCallPriceUsd {
    return 0.01
}

function Get-WorkerCatalog {
    param([string]$DefaultModel = 'gpt-5-mini')

    return @(
        [ordered]@{ id = 'A'; label = 'Worker A'; role = 'utility'; focus = 'benefits, feasibility, leverage, momentum'; model = $DefaultModel },
        [ordered]@{ id = 'B'; label = 'Worker B'; role = 'adversarial'; focus = 'systemic failure, coupling, downside, hidden risk'; model = $DefaultModel },
        [ordered]@{ id = 'C'; label = 'Worker C'; role = 'adversarial'; focus = 'cost ceilings, burn rate, economic drag'; model = $DefaultModel },
        [ordered]@{ id = 'D'; label = 'Worker D'; role = 'adversarial'; focus = 'security abuse, privilege escalation, hostile actors'; model = $DefaultModel },
        [ordered]@{ id = 'E'; label = 'Worker E'; role = 'adversarial'; focus = 'reliability collapse, uptime loss, brittle dependencies'; model = $DefaultModel },
        [ordered]@{ id = 'F'; label = 'Worker F'; role = 'adversarial'; focus = 'concurrency races, lock contention, timing faults'; model = $DefaultModel },
        [ordered]@{ id = 'G'; label = 'Worker G'; role = 'adversarial'; focus = 'data integrity, corruption, replay hazards'; model = $DefaultModel },
        [ordered]@{ id = 'H'; label = 'Worker H'; role = 'adversarial'; focus = 'compliance, policy drift, governance gaps'; model = $DefaultModel },
        [ordered]@{ id = 'I'; label = 'Worker I'; role = 'adversarial'; focus = 'user confusion, adoption friction, trust loss'; model = $DefaultModel },
        [ordered]@{ id = 'J'; label = 'Worker J'; role = 'adversarial'; focus = 'performance cliffs, hot paths, slow feedback'; model = $DefaultModel },
        [ordered]@{ id = 'K'; label = 'Worker K'; role = 'adversarial'; focus = 'observability blind spots, missing traces, opaque failures'; model = $DefaultModel },
        [ordered]@{ id = 'L'; label = 'Worker L'; role = 'adversarial'; focus = 'scalability failure, fan-out load, resource exhaustion'; model = $DefaultModel },
        [ordered]@{ id = 'M'; label = 'Worker M'; role = 'adversarial'; focus = 'recovery posture, rollback gaps, broken resumes'; model = $DefaultModel },
        [ordered]@{ id = 'N'; label = 'Worker N'; role = 'adversarial'; focus = 'integration mismatch, boundary contracts, interoperability'; model = $DefaultModel },
        [ordered]@{ id = 'O'; label = 'Worker O'; role = 'adversarial'; focus = 'abuse cases, spam, malicious automation'; model = $DefaultModel },
        [ordered]@{ id = 'P'; label = 'Worker P'; role = 'adversarial'; focus = 'latency budgets, throughput realism, field conditions'; model = $DefaultModel },
        [ordered]@{ id = 'Q'; label = 'Worker Q'; role = 'adversarial'; focus = 'incentive mismatch, local maxima, misuse of metrics'; model = $DefaultModel },
        [ordered]@{ id = 'R'; label = 'Worker R'; role = 'adversarial'; focus = 'scope creep, hidden complexity, disguised expansions'; model = $DefaultModel },
        [ordered]@{ id = 'S'; label = 'Worker S'; role = 'adversarial'; focus = 'maintainability drag, operator toil, handoff risk'; model = $DefaultModel },
        [ordered]@{ id = 'T'; label = 'Worker T'; role = 'adversarial'; focus = 'edge cases, chaos inputs, pathological sequences'; model = $DefaultModel },
        [ordered]@{ id = 'U'; label = 'Worker U'; role = 'adversarial'; focus = 'human factors, fatigue, procedural mistakes'; model = $DefaultModel },
        [ordered]@{ id = 'V'; label = 'Worker V'; role = 'adversarial'; focus = 'vendor lock-in, portability loss, external dependence'; model = $DefaultModel },
        [ordered]@{ id = 'W'; label = 'Worker W'; role = 'adversarial'; focus = 'privacy leakage, retention risk, oversharing'; model = $DefaultModel },
        [ordered]@{ id = 'X'; label = 'Worker X'; role = 'adversarial'; focus = 'product mismatch, weak demand signal, false confidence'; model = $DefaultModel },
        [ordered]@{ id = 'Y'; label = 'Worker Y'; role = 'adversarial'; focus = 'decision paralysis, review bottlenecks, process drag'; model = $DefaultModel },
        [ordered]@{ id = 'Z'; label = 'Worker Z'; role = 'adversarial'; focus = 'wildcard attack surfaces, overlooked weirdness, novel failure'; model = $DefaultModel }
    )
}

function Normalize-WorkerDefinition {
    param(
        [object]$Worker,
        [string]$DefaultModel = 'gpt-5-mini'
    )

    $workerId = ''
    if ($null -ne $Worker -and (Test-ObjectKey -Value $Worker -Key 'id')) {
        $workerId = ([string]$Worker['id']).Trim().ToUpperInvariant()
    }
    if ($workerId -notmatch '^[A-Z]$') {
        throw "Worker ids must be single uppercase letters."
    }

    $catalogMap = @{}
    foreach ($entry in (Get-WorkerCatalog -DefaultModel $DefaultModel)) {
        $catalogMap[$entry['id']] = $entry
    }
    $catalogWorker = $catalogMap[$workerId]
    if ($null -eq $catalogWorker) {
        $catalogWorker = [ordered]@{
            id = $workerId
            label = 'Worker ' + $workerId
            role = 'adversarial'
            focus = 'general adversarial review'
            model = $DefaultModel
        }
    }

    $label = [string]$catalogWorker['label']
    $role = [string]$catalogWorker['role']
    $focus = [string]$catalogWorker['focus']
    $model = $DefaultModel

    if ($null -ne $Worker) {
        if ((Test-ObjectKey -Value $Worker -Key 'label') -and -not [string]::IsNullOrWhiteSpace([string]$Worker['label'])) {
            $label = [string]$Worker['label']
        }
        if ((Test-ObjectKey -Value $Worker -Key 'role') -and -not [string]::IsNullOrWhiteSpace([string]$Worker['role'])) {
            $role = [string]$Worker['role']
        }
        if ((Test-ObjectKey -Value $Worker -Key 'focus') -and -not [string]::IsNullOrWhiteSpace([string]$Worker['focus'])) {
            $focus = [string]$Worker['focus']
        }
        if (Test-ObjectKey -Value $Worker -Key 'model') {
            $model = Normalize-ModelId -Model ([string]$Worker['model']) -Fallback $DefaultModel
        } else {
            $model = Normalize-ModelId -Model $catalogWorker['model'] -Fallback $DefaultModel
        }
    }

    return [ordered]@{
        id = $workerId
        label = $label
        role = $role
        focus = $focus
        model = $model
    }
}

function Get-WorkerDefinitions {
    param([hashtable]$Task)

    $defaultModel = Get-DefaultModelId
    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime'] -and (Test-ObjectKey -Value $Task['runtime'] -Key 'model')) {
        $defaultModel = Normalize-ModelId -Model ([string]$Task['runtime']['model']) -Fallback (Get-DefaultModelId)
    }

    $workers = @()
    if ($Task -and (Test-ObjectKey -Value $Task -Key 'workers') -and $Task['workers']) {
        foreach ($worker in @($Task['workers'])) {
            $workers += ,(Normalize-WorkerDefinition -Worker $worker -DefaultModel $defaultModel)
        }
    }

    if ($workers.Count -eq 0) {
        $catalog = Get-WorkerCatalog -DefaultModel $defaultModel
        $workers += ,(Normalize-WorkerDefinition -Worker $catalog[0] -DefaultModel $defaultModel)
        $workers += ,(Normalize-WorkerDefinition -Worker $catalog[1] -DefaultModel $defaultModel)
    }

    return @($workers | Sort-Object id)
}

function Find-WorkerDefinition {
    param(
        [hashtable]$Task,
        [string]$WorkerId
    )

    $targetId = ([string]$WorkerId).Trim().ToUpperInvariant()
    foreach ($worker in (Get-WorkerDefinitions -Task $Task)) {
        if ($worker['id'] -eq $targetId) {
            return $worker
        }
    }
    return $null
}

function Get-SummarizerConfig {
    param([hashtable]$Task)

    $defaultModel = Get-DefaultModelId
    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime'] -and (Test-ObjectKey -Value $Task['runtime'] -Key 'model')) {
        $defaultModel = Normalize-ModelId -Model ([string]$Task['runtime']['model']) -Fallback (Get-DefaultModelId)
    }

    $label = 'Summarizer'
    $model = $defaultModel
    if ($Task -and (Test-ObjectKey -Value $Task -Key 'summarizer') -and $Task['summarizer']) {
        $summary = $Task['summarizer']
        if (Test-ObjectKey -Value $summary -Key 'label' -and -not [string]::IsNullOrWhiteSpace([string]$summary['label'])) {
            $label = [string]$summary['label']
        }
        if (Test-ObjectKey -Value $summary -Key 'model') {
            $model = Normalize-ModelId -Model ([string]$summary['model']) -Fallback $defaultModel
        }
    }

    return [ordered]@{
        id = 'summarizer'
        label = $label
        model = $model
    }
}

function Get-DefaultLoopState {
    return [ordered]@{
        status = 'idle'
        jobId = $null
        mode = 'manual'
        totalRounds = 0
        completedRounds = 0
        currentRound = 0
        delayMs = 0
        cancelRequested = $false
        queuedAt = $null
        startedAt = $null
        finishedAt = $null
        lastHeartbeatAt = $null
        lastMessage = 'Ready.'
    }
}

function Get-DefaultUsageBucket {
    return [ordered]@{
        calls = 0
        webSearchCalls = 0
        inputTokens = 0
        cachedInputTokens = 0
        billableInputTokens = 0
        outputTokens = 0
        reasoningTokens = 0
        totalTokens = 0
        modelCostUsd = 0.0
        toolCostUsd = 0.0
        estimatedCostUsd = 0.0
        lastModel = $null
        lastResponseId = $null
        lastUpdated = $null
    }
}

function Get-DefaultUsageState {
    $usage = Get-DefaultUsageBucket
    $usage['byTarget'] = @{}
    $usage['byModel'] = @{}
    return $usage
}

function Get-DefaultState {
    return [ordered]@{
        activeTask = $null
        workers = @{}
        summary = $null
        memoryVersion = 0
        usage = Get-DefaultUsageState
        loop = Get-DefaultLoopState
        lastUpdated = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Ensure-DataPaths {
    param([string]$Root)

    $paths = @(
        (Get-DataPath -Root $Root),
        (Join-Path $Root 'data\tasks'),
        (Get-OutputsPath -Root $Root),
        (Join-Path $Root 'data\checkpoints'),
        (Join-Path $Root 'data\jobs'),
        (Get-LocksPath -Root $Root)
    )

    foreach ($path in $paths) {
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }

    $statePath = Get-StatePath -Root $Root
    if (-not (Test-Path $statePath)) {
        Write-Utf8NoBom -Path $statePath -Value ((Get-DefaultState) | ConvertTo-Json -Depth 25)
    }

    $eventsPath = Get-EventsPath -Root $Root
    if (-not (Test-Path $eventsPath)) {
        Set-Content -Path $eventsPath -Value '' -Encoding UTF8
    }

    $stepsPath = Get-StepsPath -Root $Root
    if (-not (Test-Path $stepsPath)) {
        Set-Content -Path $stepsPath -Value '' -Encoding UTF8
    }
}

function Remove-PathTree {
    param([string]$Path)

    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-StaleLock {
    param(
        [string]$LockPath,
        [int]$StaleSeconds = 45
    )

    if (-not (Test-Path $LockPath)) {
        return $false
    }

    $item = Get-Item -LiteralPath $LockPath -ErrorAction SilentlyContinue
    if ($null -eq $item) {
        return $false
    }

    return (((Get-Date).ToUniversalTime()) - $item.LastWriteTimeUtc).TotalSeconds -gt $StaleSeconds
}

function Invoke-WithLock {
    param(
        [string]$Root,
        [scriptblock]$Script,
        [string]$Name = 'loop',
        [int]$TimeoutMs = 15000,
        [int]$StaleSeconds = 45
    )

    Ensure-DataPaths -Root $Root
    $lockPath = Get-LockPath -Root $Root -Name $Name
    $deadline = (Get-Date).ToUniversalTime().AddMilliseconds($TimeoutMs)

    while ((Get-Date).ToUniversalTime() -lt $deadline) {
        $acquired = $false

        try {
            New-Item -ItemType Directory -Path $lockPath -ErrorAction Stop | Out-Null
            $acquired = $true
        } catch {
            if (Test-StaleLock -LockPath $lockPath -StaleSeconds $StaleSeconds) {
                Remove-PathTree -Path $lockPath
                continue
            }

            Start-Sleep -Milliseconds 100
            continue
        }

        if ($acquired) {
            $ownerPath = Join-Path $lockPath 'owner.json'
            Write-Utf8NoBom -Path $ownerPath -Value (([ordered]@{
                pid = $PID
                ts = (Get-Date).ToUniversalTime().ToString('o')
            }) | ConvertTo-Json -Depth 5)

            try {
                return & $Script
            } finally {
                Remove-PathTree -Path $lockPath
            }
        }
    }

    throw 'Timed out acquiring loop lock.'
}

function ConvertTo-HashtableCompat {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [string] -or
        $Value -is [char] -or
        $Value -is [bool] -or
        $Value -is [byte] -or
        $Value -is [int16] -or
        $Value -is [int32] -or
        $Value -is [int64] -or
        $Value -is [decimal] -or
        $Value -is [double] -or
        $Value -is [single] -or
        $Value -is [datetime]) {
        return $Value
    }

    if ($Value -is [System.Collections.IDictionary]) {
        $table = @{}
        foreach ($key in $Value.Keys) {
            $table[$key] = ConvertTo-HashtableCompat -Value $Value[$key]
        }
        return $table
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $items = @()
        foreach ($item in $Value) {
            $items += ,(ConvertTo-HashtableCompat -Value $item)
        }
        return $items
    }

    if ($Value.PSObject -and $Value.PSObject.Properties.Count -gt 0) {
        $table = @{}
        foreach ($prop in $Value.PSObject.Properties) {
            $table[$prop.Name] = ConvertTo-HashtableCompat -Value $prop.Value
        }
        return $table
    }

    return $Value
}

function Test-ObjectKey {
    param(
        [object]$Value,
        [string]$Key
    )

    if ($null -eq $Value) {
        return $false
    }

    try {
        if ($Value -is [System.Collections.IDictionary]) {
            return $Value.Contains($Key)
        }
    } catch {}

    try {
        return $Value.ContainsKey($Key)
    } catch {}

    return $null -ne $Value.PSObject.Properties[$Key]
}

function Normalize-CheckpointStateValue {
    param([object]$Checkpoint)

    if ($null -eq $Checkpoint) {
        return $null
    }

    $normalized = ConvertTo-HashtableCompat -Value $Checkpoint
    if ($null -eq $normalized -or -not ($normalized -is [System.Collections.IDictionary])) {
        return $normalized
    }

    foreach ($field in @('requestTargets', 'researchQueries', 'benefits', 'detriments', 'requiredCircumstances', 'invalidatingCircumstances', 'immediateConsequences', 'downstreamConsequences', 'uncertainty', 'reversalConditions', 'constraintsSeen', 'evidenceGaps')) {
        if (Test-ObjectKey -Value $normalized -Key $field) {
            $normalized[$field] = ConvertTo-JsonArray -Value (Normalize-StringArrayPreserveItems -Value $normalized[$field])
        }
    }
    foreach ($field in @('researchSources', 'urlCitations')) {
        if (Test-ObjectKey -Value $normalized -Key $field) {
            $normalized[$field] = ConvertTo-JsonArray -Value (Normalize-UrlArrayValues -Value $normalized[$field])
        }
    }

    if (Test-ObjectKey -Value $normalized -Key 'evidenceLedger') {
        $entries = New-Object System.Collections.ArrayList
        foreach ($entry in @($normalized['evidenceLedger'])) {
            $entryValue = ConvertTo-HashtableCompat -Value $entry
            if ($entryValue -is [System.Collections.IDictionary] -and (Test-ObjectKey -Value $entryValue -Key 'sourceUrls')) {
                $entryValue['sourceUrls'] = ConvertTo-JsonArray -Value (Normalize-UrlArrayValues -Value $entryValue['sourceUrls'])
            }
            [void]$entries.Add($entryValue)
        }
        $normalized['evidenceLedger'] = $entries
    }

    return $normalized
}

function Normalize-SummaryStateValue {
    param([object]$Summary)

    if ($null -eq $Summary) {
        return $null
    }

    $normalized = ConvertTo-HashtableCompat -Value $Summary
    if ($null -eq $normalized -or -not ($normalized -is [System.Collections.IDictionary])) {
        return $normalized
    }

    foreach ($field in @('stableFindings', 'conditionalTruths', 'claimsNeedingVerification', 'sourceWorkers')) {
        if (Test-ObjectKey -Value $normalized -Key $field) {
            $normalized[$field] = ConvertTo-JsonArray -Value (Normalize-StringArrayPreserveItems -Value $normalized[$field])
        }
    }

    foreach ($field in @('peerSteerPackets', 'conflicts', 'evidenceVerdicts')) {
        if (Test-ObjectKey -Value $normalized -Key $field) {
            $items = New-Object System.Collections.ArrayList
            foreach ($entry in @($normalized[$field])) {
                $entryValue = ConvertTo-HashtableCompat -Value $entry
                if ($field -eq 'evidenceVerdicts' -and $entryValue -is [System.Collections.IDictionary]) {
                    foreach ($subField in @('supportingWorkers', 'challengingWorkers')) {
                        if (Test-ObjectKey -Value $entryValue -Key $subField) {
                            $entryValue[$subField] = ConvertTo-JsonArray -Value (Normalize-StringArrayPreserveItems -Value $entryValue[$subField])
                        }
                    }
                    if (Test-ObjectKey -Value $entryValue -Key 'sourceUrls') {
                        $entryValue['sourceUrls'] = ConvertTo-JsonArray -Value (Normalize-UrlArrayValues -Value $entryValue['sourceUrls'])
                    }
                }
                if ($field -eq 'conflicts' -and $entryValue -is [System.Collections.IDictionary] -and (Test-ObjectKey -Value $entryValue -Key 'positions')) {
                    $entryValue['positions'] = @($entryValue['positions'])
                }
                [void]$items.Add($entryValue)
            }
            $normalized[$field] = $items
        }
    }

    return $normalized
}

function Normalize-UsageBucket {
    param([object]$Bucket)

    $default = Get-DefaultUsageBucket
    $normalized = [ordered]@{
        calls = [int]$default['calls']
        webSearchCalls = [int]$default['webSearchCalls']
        inputTokens = [int]$default['inputTokens']
        cachedInputTokens = [int]$default['cachedInputTokens']
        billableInputTokens = [int]$default['billableInputTokens']
        outputTokens = [int]$default['outputTokens']
        reasoningTokens = [int]$default['reasoningTokens']
        totalTokens = [int]$default['totalTokens']
        modelCostUsd = [double]$default['modelCostUsd']
        toolCostUsd = [double]$default['toolCostUsd']
        estimatedCostUsd = [double]$default['estimatedCostUsd']
        lastModel = $default['lastModel']
        lastResponseId = $default['lastResponseId']
        lastUpdated = $default['lastUpdated']
    }

    if ($null -ne $Bucket) {
        foreach ($key in @('calls', 'webSearchCalls', 'inputTokens', 'cachedInputTokens', 'billableInputTokens', 'outputTokens', 'reasoningTokens', 'totalTokens')) {
            if ((Test-ObjectKey -Value $Bucket -Key $key) -and $null -ne $Bucket[$key]) {
                $normalized[$key] = [Math]::Max(0, [int]$Bucket[$key])
            }
        }
        foreach ($key in @('modelCostUsd', 'toolCostUsd', 'estimatedCostUsd')) {
            if ((Test-ObjectKey -Value $Bucket -Key $key) -and $null -ne $Bucket[$key]) {
                $normalized[$key] = [Math]::Round([Math]::Max(0.0, [double]$Bucket[$key]), 6)
            }
        }
        foreach ($key in @('lastModel', 'lastResponseId', 'lastUpdated')) {
            if (Test-ObjectKey -Value $Bucket -Key $key) {
                $normalized[$key] = $Bucket[$key]
            }
        }
    }

    return $normalized
}

function Normalize-UsageState {
    param([object]$Usage)

    $normalized = Normalize-UsageBucket -Bucket $Usage
    $normalized['byTarget'] = @{}
    $normalized['byModel'] = @{}

    if ($null -ne $Usage) {
        if ((Test-ObjectKey -Value $Usage -Key 'byTarget') -and $Usage['byTarget']) {
            if ($Usage['byTarget'] -is [System.Collections.IDictionary]) {
                foreach ($key in $Usage['byTarget'].Keys) {
                    $normalized['byTarget'][$key] = Normalize-UsageBucket -Bucket $Usage['byTarget'][$key]
                }
            } elseif ($Usage['byTarget'].PSObject -and $Usage['byTarget'].PSObject.Properties.Count -gt 0) {
                foreach ($entry in $Usage['byTarget'].PSObject.Properties) {
                    $normalized['byTarget'][$entry.Name] = Normalize-UsageBucket -Bucket $entry.Value
                }
            }
        }
        if ((Test-ObjectKey -Value $Usage -Key 'byModel') -and $Usage['byModel']) {
            if ($Usage['byModel'] -is [System.Collections.IDictionary]) {
                foreach ($key in $Usage['byModel'].Keys) {
                    $normalized['byModel'][$key] = Normalize-UsageBucket -Bucket $Usage['byModel'][$key]
                }
            } elseif ($Usage['byModel'].PSObject -and $Usage['byModel'].PSObject.Properties.Count -gt 0) {
                foreach ($entry in $Usage['byModel'].PSObject.Properties) {
                    $normalized['byModel'][$entry.Name] = Normalize-UsageBucket -Bucket $entry.Value
                }
            }
        }
    }

    return $normalized
}

function Normalize-State {
    param([hashtable]$State)

    $default = Get-DefaultState
    $normalized = [ordered]@{
        activeTask = $default['activeTask']
        workers = @{}
        summary = $default['summary']
        memoryVersion = $default['memoryVersion']
        usage = Get-DefaultUsageState
        loop = Get-DefaultLoopState
        lastUpdated = $default['lastUpdated']
    }

    if ($null -ne $State) {
        if (Test-ObjectKey -Value $State -Key 'activeTask') {
            $normalized['activeTask'] = $State['activeTask']
        }
        if (Test-ObjectKey -Value $State -Key 'summary') {
            $normalized['summary'] = Normalize-SummaryStateValue -Summary $State['summary']
        }
        if ((Test-ObjectKey -Value $State -Key 'memoryVersion') -and $null -ne $State['memoryVersion']) {
            $normalized['memoryVersion'] = [int]$State['memoryVersion']
        }
        if ((Test-ObjectKey -Value $State -Key 'usage') -and $State['usage']) {
            $normalized['usage'] = Normalize-UsageState -Usage $State['usage']
        }
        if ((Test-ObjectKey -Value $State -Key 'lastUpdated') -and $State['lastUpdated']) {
            $normalized['lastUpdated'] = [string]$State['lastUpdated']
        }
        if ((Test-ObjectKey -Value $State -Key 'workers') -and $State['workers']) {
            $workers = @{}
            if ($State['workers'] -is [System.Collections.IDictionary]) {
                foreach ($key in $State['workers'].Keys) {
                    $workers[$key] = $State['workers'][$key]
                    $workers[$key] = Normalize-CheckpointStateValue -Checkpoint $workers[$key]
                }
            } elseif ($State['workers'].PSObject -and $State['workers'].PSObject.Properties.Count -gt 0) {
                foreach ($entry in $State['workers'].PSObject.Properties) {
                    $workers[$entry.Name] = Normalize-CheckpointStateValue -Checkpoint $entry.Value
                }
            }
            $normalized['workers'] = $workers
        }
        if ((Test-ObjectKey -Value $State -Key 'loop') -and $State['loop']) {
            foreach ($key in (Get-DefaultLoopState).Keys) {
                if (Test-ObjectKey -Value $State['loop'] -Key $key) {
                    $normalized['loop'][$key] = $State['loop'][$key]
                }
            }
        }
    }

    return $normalized
}

function Read-StateUnlocked {
    param([string]$Root)

    Ensure-DataPaths -Root $Root
    $path = Get-StatePath -Root $Root
    if (-not (Test-Path $path)) {
        return (Get-DefaultState)
    }

    $json = Get-Content -Path $path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($json)) {
        return (Get-DefaultState)
    }

    return (Normalize-State -State (ConvertTo-HashtableCompat -Value ($json | ConvertFrom-Json)))
}

function Read-State {
    param([string]$Root)

    return Invoke-WithLock -Root $Root -Script {
        Read-StateUnlocked -Root $Root
    }
}

function Write-TaskSnapshotUnlocked {
    param(
        [string]$Root,
        [hashtable]$Task
    )

    if ($null -eq $Task -or -not (Test-ObjectKey -Value $Task -Key 'taskId')) {
        return
    }

    $taskPath = Get-TaskFilePath -Root $Root -TaskId ([string]$Task['taskId'])
    Write-Utf8NoBom -Path $taskPath -Value ($Task | ConvertTo-Json -Depth 25)
}

function Write-StateUnlocked {
    param(
        [string]$Root,
        [hashtable]$State
    )

    Ensure-DataPaths -Root $Root
    $normalized = Normalize-State -State $State
    $normalized['lastUpdated'] = (Get-Date).ToUniversalTime().ToString('o')
    $path = Get-StatePath -Root $Root
    $json = $normalized | ConvertTo-Json -Depth 25
    Write-Utf8NoBom -Path $path -Value $json
}

function Write-State {
    param(
        [string]$Root,
        [hashtable]$State
    )

    Invoke-WithLock -Root $Root -Script {
        Write-StateUnlocked -Root $Root -State $State
    } | Out-Null
}

function Add-Event {
    param(
        [string]$Root,
        [string]$Type,
        [hashtable]$Payload
    )

    $line = [ordered]@{
        ts = (Get-Date).ToUniversalTime().ToString('o')
        type = $Type
        payload = $Payload
    } | ConvertTo-Json -Compress -Depth 25

    Invoke-WithLock -Root $Root -Script {
        $eventPath = Get-EventsPath -Root $Root
        Add-Content -Path $eventPath -Value $line -Encoding UTF8
    } | Out-Null
}

function Add-Step {
    param(
        [string]$Root,
        [string]$Stage,
        [string]$Message,
        [hashtable]$Context
    )

    $line = [ordered]@{
        ts = (Get-Date).ToUniversalTime().ToString('o')
        stage = $Stage
        message = $Message
        context = $Context
    } | ConvertTo-Json -Compress -Depth 25

    Invoke-WithLock -Root $Root -Script {
        $stepPath = Get-StepsPath -Root $Root
        Add-Content -Path $stepPath -Value $line -Encoding UTF8
    } | Out-Null
}

function Get-Task {
    param([hashtable]$State)
    return $State['activeTask']
}

function Get-TaskRuntime {
    param(
        [hashtable]$Task,
        [string]$ModelOverride = $null
    )

    $runtime = [ordered]@{
        executionMode = 'live'
        model = (Get-DefaultModelId)
        reasoningEffort = 'low'
        maxOutputTokens = [int]((Get-DefaultBudgetConfig)['maxOutputTokens'])
        research = Get-DefaultResearchConfig
        vetting = Get-DefaultVettingConfig
    }

    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime']) {
        foreach ($key in @('executionMode', 'reasoningEffort')) {
            if ((Test-ObjectKey -Value $Task['runtime'] -Key $key) -and $Task['runtime'][$key]) {
                $runtime[$key] = [string]$Task['runtime'][$key]
            }
        }
        if ((Test-ObjectKey -Value $Task['runtime'] -Key 'model') -and $Task['runtime']['model']) {
            $runtime['model'] = Normalize-ModelId -Model ([string]$Task['runtime']['model']) -Fallback (Get-DefaultModelId)
        }
        if ((Test-ObjectKey -Value $Task['runtime'] -Key 'budget') -and $Task['runtime']['budget']) {
            $budget = Normalize-BudgetConfig -Budget $Task['runtime']['budget']
            $runtime['maxOutputTokens'] = [int]$budget['maxOutputTokens']
        }
        if ((Test-ObjectKey -Value $Task['runtime'] -Key 'research')) {
            $runtime['research'] = Normalize-ResearchConfig -Config $Task['runtime']['research']
        }
        if ((Test-ObjectKey -Value $Task['runtime'] -Key 'vetting')) {
            $runtime['vetting'] = Normalize-VettingConfig -Config $Task['runtime']['vetting']
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ModelOverride)) {
        $runtime['model'] = Normalize-ModelId -Model $ModelOverride -Fallback $runtime['model']
    }

    return $runtime
}

function Get-ResearchConfig {
    param([hashtable]$Task)

    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime'] -and (Test-ObjectKey -Value $Task['runtime'] -Key 'research')) {
        return (Normalize-ResearchConfig -Config $Task['runtime']['research'])
    }

    return (Get-DefaultResearchConfig)
}

function Get-VettingConfig {
    param([hashtable]$Task)

    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime'] -and (Test-ObjectKey -Value $Task['runtime'] -Key 'vetting')) {
        return (Normalize-VettingConfig -Config $Task['runtime']['vetting'])
    }

    return (Get-DefaultVettingConfig)
}

function Get-BudgetConfig {
    param([hashtable]$Task)

    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime'] -and (Test-ObjectKey -Value $Task['runtime'] -Key 'budget')) {
        return (Normalize-BudgetConfig -Budget $Task['runtime']['budget'])
    }

    return (Get-DefaultBudgetConfig)
}

function Get-ApiKey {
    param([string]$Root)

    $path = Get-AuthPath -Root $Root
    if (-not (Test-Path $path)) {
        return $null
    }

    $key = (Get-Content -Path $path -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($key)) {
        return $null
    }

    return $key
}

function Get-ModelPricing {
    param([string]$Model)

    $catalog = Get-ModelCatalog
    $resolvedModel = Normalize-ModelId -Model $Model -Fallback (Get-DefaultModelId)
    if ($catalog.ContainsKey($resolvedModel)) {
        $pricing = $catalog[$resolvedModel]
        return [ordered]@{
            model = $resolvedModel
            inputPer1M = [double]$pricing['inputPer1M']
            cachedInputPer1M = [double]$pricing['cachedInputPer1M']
            outputPer1M = [double]$pricing['outputPer1M']
        }
    }

    return [ordered]@{
        model = $resolvedModel
        inputPer1M = 0.0
        cachedInputPer1M = 0.0
        outputPer1M = 0.0
    }
}

function Get-ResponseOutputText {
    param([object]$Response)

    if ($null -eq $Response -or $null -eq $Response.output) {
        return $null
    }

    foreach ($item in $Response.output) {
        if ($item.type -eq 'message' -and $null -ne $item.content) {
            foreach ($content in $item.content) {
                if ($content.type -eq 'output_text' -and $content.text) {
                    return [string]$content.text
                }
            }
        }
    }

    return $null
}

function Get-WebSearchCallItems {
    param([object]$Response)

    $items = @()
    if ($null -eq $Response -or $null -eq $Response.output) {
        return $items
    }

    foreach ($item in $Response.output) {
        if ($null -ne $item -and $item.type -eq 'web_search_call') {
            $items += ,$item
        }
    }

    return $items
}

function Get-ResponseWebSearchQueries {
    param([object]$Response)

    $queries = @{}
    foreach ($item in (Get-WebSearchCallItems -Response $Response)) {
        if ($null -ne $item.action) {
            if ($null -ne $item.action.query -and -not [string]::IsNullOrWhiteSpace([string]$item.action.query)) {
                $queries[[string]$item.action.query] = $true
            }
            if ($null -ne $item.action.queries) {
                foreach ($query in @($item.action.queries)) {
                    if ($null -ne $query -and -not [string]::IsNullOrWhiteSpace([string]$query)) {
                        $queries[[string]$query] = $true
                    }
                }
            }
        }
    }

    return @($queries.Keys)
}

function Get-ResponseWebSearchSources {
    param([object]$Response)

    $urls = @{}
    foreach ($item in (Get-WebSearchCallItems -Response $Response)) {
        if ($null -eq $item.action -or $null -eq $item.action.sources) {
            continue
        }
        foreach ($source in @($item.action.sources)) {
            if ($null -ne $source.url -and -not [string]::IsNullOrWhiteSpace([string]$source.url)) {
                $urls[[string]$source.url] = $true
            }
        }
    }

    return @($urls.Keys)
}

function Get-ResponseUrlCitations {
    param([object]$Response)

    $urls = @{}
    if ($null -eq $Response -or $null -eq $Response.output) {
        return @()
    }

    foreach ($item in $Response.output) {
        if ($null -eq $item -or $item.type -ne 'message' -or $null -eq $item.content) {
            continue
        }
        foreach ($content in @($item.content)) {
            if ($null -eq $content.annotations) {
                continue
            }
            foreach ($annotation in @($content.annotations)) {
                if ($null -ne $annotation -and $annotation.type -eq 'url_citation' -and $null -ne $annotation.url -and -not [string]::IsNullOrWhiteSpace([string]$annotation.url)) {
                    $urls[[string]$annotation.url] = $true
                }
            }
        }
    }

    return @($urls.Keys)
}

function Get-ResponseUsageDelta {
    param(
        [object]$Response,
        [string]$Model
    )

    if ($null -eq $Response -or $null -eq $Response.usage) {
        return $null
    }

    $inputTokens = 0
    $cachedInputTokens = 0
    $outputTokens = 0
    $reasoningTokens = 0
    $totalTokens = 0

    if ($null -ne $Response.usage.input_tokens) {
        $inputTokens = [int]$Response.usage.input_tokens
    }
    if ($null -ne $Response.usage.output_tokens) {
        $outputTokens = [int]$Response.usage.output_tokens
    }
    if ($null -ne $Response.usage.total_tokens) {
        $totalTokens = [int]$Response.usage.total_tokens
    }
    if ($null -ne $Response.usage.input_tokens_details -and $null -ne $Response.usage.input_tokens_details.cached_tokens) {
        $cachedInputTokens = [int]$Response.usage.input_tokens_details.cached_tokens
    }
    if ($null -ne $Response.usage.output_tokens_details -and $null -ne $Response.usage.output_tokens_details.reasoning_tokens) {
        $reasoningTokens = [int]$Response.usage.output_tokens_details.reasoning_tokens
    }

    $billableInputTokens = [Math]::Max(0, $inputTokens - $cachedInputTokens)
    $webSearchCalls = @((Get-WebSearchCallItems -Response $Response)).Count
    $pricing = Get-ModelPricing -Model $Model
    $modelCostUsd = (($billableInputTokens * [double]$pricing['inputPer1M']) + ($cachedInputTokens * [double]$pricing['cachedInputPer1M']) + ($outputTokens * [double]$pricing['outputPer1M'])) / 1000000.0
    $toolCostUsd = $webSearchCalls * (Get-WebSearchToolCallPriceUsd)
    $estimatedCostUsd = $modelCostUsd + $toolCostUsd

    return [ordered]@{
        calls = 1
        webSearchCalls = $webSearchCalls
        inputTokens = $inputTokens
        cachedInputTokens = $cachedInputTokens
        billableInputTokens = $billableInputTokens
        outputTokens = $outputTokens
        reasoningTokens = $reasoningTokens
        totalTokens = $totalTokens
        modelCostUsd = [Math]::Round($modelCostUsd, 6)
        toolCostUsd = [Math]::Round($toolCostUsd, 6)
        estimatedCostUsd = [Math]::Round($estimatedCostUsd, 6)
    }
}

function Merge-UsageBucket {
    param(
        [object]$Bucket,
        [hashtable]$Delta,
        [string]$Model,
        [string]$ResponseId
    )

    $merged = Normalize-UsageBucket -Bucket $Bucket
    foreach ($key in @('calls', 'webSearchCalls', 'inputTokens', 'cachedInputTokens', 'billableInputTokens', 'outputTokens', 'reasoningTokens', 'totalTokens')) {
        $merged[$key] = [int]$merged[$key] + [int]$Delta[$key]
    }
    foreach ($key in @('modelCostUsd', 'toolCostUsd', 'estimatedCostUsd')) {
        $merged[$key] = [Math]::Round(([double]$merged[$key] + [double]$Delta[$key]), 6)
    }
    $merged['lastModel'] = $Model
    $merged['lastResponseId'] = $ResponseId
    $merged['lastUpdated'] = (Get-Date).ToUniversalTime().ToString('o')
    return $merged
}

function Update-UsageTracking {
    param(
        [string]$Root,
        [string]$Target,
        [string]$TaskId,
        [string]$Model,
        [string]$ResponseId,
        [object]$Response
    )

    $delta = Get-ResponseUsageDelta -Response $Response -Model $Model
    if ($null -eq $delta) {
        return $null
    }

    return Invoke-WithLock -Root $Root -Script {
        $state = Read-StateUnlocked -Root $Root
        $state = Normalize-State -State $state
        $usage = Normalize-UsageState -Usage $state['usage']
        $existingByTarget = if ($usage['byTarget'] -is [System.Collections.IDictionary]) { $usage['byTarget'] } else { @{} }
        $existingByModel = if ($usage['byModel'] -is [System.Collections.IDictionary]) { $usage['byModel'] } else { @{} }
        $usage = Merge-UsageBucket -Bucket $usage -Delta $delta -Model $Model -ResponseId $ResponseId
        $usage['byTarget'] = $existingByTarget
        $usage['byModel'] = $existingByModel

        if ($null -eq $usage['byTarget'] -or -not ($usage['byTarget'] -is [System.Collections.IDictionary])) {
            $usage['byTarget'] = @{}
        }
        if ($null -eq $usage['byModel'] -or -not ($usage['byModel'] -is [System.Collections.IDictionary])) {
            $usage['byModel'] = @{}
        }

        if (-not $usage['byTarget'].ContainsKey($Target)) {
            $usage['byTarget'][$Target] = Get-DefaultUsageBucket
        }
        $usage['byTarget'][$Target] = Merge-UsageBucket -Bucket $usage['byTarget'][$Target] -Delta $delta -Model $Model -ResponseId $ResponseId

        if (-not $usage['byModel'].ContainsKey($Model)) {
            $usage['byModel'][$Model] = Get-DefaultUsageBucket
        }
        $usage['byModel'][$Model] = Merge-UsageBucket -Bucket $usage['byModel'][$Model] -Delta $delta -Model $Model -ResponseId $ResponseId

        $state['usage'] = $usage
        if ($state['activeTask'] -and (Test-ObjectKey -Value $state['activeTask'] -Key 'taskId') -and $state['activeTask']['taskId'] -eq $TaskId) {
            $state['activeTask']['usage'] = $usage
            Write-TaskSnapshotUnlocked -Root $Root -Task $state['activeTask']
        }
        Write-StateUnlocked -Root $Root -State $state
        return $usage
    }
}

function Get-BudgetStatus {
    param(
        [hashtable]$Task,
        [hashtable]$Usage
    )

    $budget = Get-BudgetConfig -Task $Task
    $normalizedUsage = Normalize-UsageState -Usage $Usage
    $reasons = @()

    if ([int]$budget['maxTotalTokens'] -gt 0 -and [int]$normalizedUsage['totalTokens'] -ge [int]$budget['maxTotalTokens']) {
        $reasons += ('tokens {0}/{1}' -f [int]$normalizedUsage['totalTokens'], [int]$budget['maxTotalTokens'])
    }
    if ([double]$budget['maxCostUsd'] -gt 0 -and [double]$normalizedUsage['estimatedCostUsd'] -ge [double]$budget['maxCostUsd']) {
        $reasons += ('estimated cost ${0:N4}/${1:N4}' -f [double]$normalizedUsage['estimatedCostUsd'], [double]$budget['maxCostUsd'])
    }

    return [ordered]@{
        exceeded = ($reasons.Count -gt 0)
        message = ($reasons -join '; ')
        budget = $budget
        usage = $normalizedUsage
    }
}

function Assert-BudgetAvailable {
    param(
        [string]$Root,
        [string]$Target,
        [hashtable]$Task
    )

    $state = Read-State -Root $Root
    $status = Get-BudgetStatus -Task $Task -Usage $state['usage']
    if ($status['exceeded']) {
        throw ('Budget limit reached: ' + $status['message'])
    }
}

function Invoke-OpenAIJson {
    param(
        [string]$ApiKey,
        [string]$Model,
        [string]$ReasoningEffort,
        [string]$Instructions,
        [string]$InputText,
        [string]$SchemaName,
        [hashtable]$Schema,
        [int]$MaxOutputTokens = 0,
        [object[]]$Tools = @(),
        [object]$ToolChoice = $null,
        [string[]]$Include = @()
    )

    $headers = @{
        Authorization = "Bearer $ApiKey"
    }

    $bodyObject = [ordered]@{
        model = $Model
        instructions = $Instructions
        input = $InputText
        reasoning = @{
            effort = $ReasoningEffort
        }
        text = @{
            verbosity = 'low'
            format = @{
                type = 'json_schema'
                name = $SchemaName
                strict = $true
                schema = $Schema
            }
        }
    }

    if ($MaxOutputTokens -gt 0) {
        $bodyObject['max_output_tokens'] = $MaxOutputTokens
    }
    if ($Tools -and @($Tools).Count -gt 0) {
        $bodyObject['tools'] = @($Tools)
    }
    if ($null -ne $ToolChoice) {
        $bodyObject['tool_choice'] = $ToolChoice
    }
    if ($Include -and @($Include).Count -gt 0) {
        $bodyObject['include'] = @($Include)
    }

    $body = $bodyObject | ConvertTo-Json -Depth 25
    try {
        $response = Invoke-RestMethod -Method Post -Uri 'https://api.openai.com/v1/responses' -Headers $headers -ContentType 'application/json' -Body $body
    } catch {
        $apiError = $_.Exception.Message
        $responseBody = $null
        if ($_.Exception.Response) {
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $responseBody = $reader.ReadToEnd()
                    $reader.Dispose()
                    $stream.Dispose()
                }
            } catch {}
        }

        if (-not [string]::IsNullOrWhiteSpace($responseBody)) {
            throw ('OpenAI API request failed: ' + $apiError + ' | ' + $responseBody)
        }

        throw ('OpenAI API request failed: ' + $apiError)
    }
    if ($null -ne $response.error) {
        throw ('Model response error: ' + ($response.error | ConvertTo-Json -Depth 10))
    }

    $text = Get-ResponseOutputText -Response $response
    if ([string]::IsNullOrWhiteSpace($text)) {
        if ($response.status -eq 'incomplete' -and $null -ne $response.incomplete_details -and $response.incomplete_details.reason) {
            throw ('Model response incomplete: ' + [string]$response.incomplete_details.reason)
        }
        throw 'Model response did not include output_text.'
    }

    if ($response.status -eq 'incomplete' -and $null -ne $response.incomplete_details -and $response.incomplete_details.reason) {
        throw ('Model response incomplete: ' + [string]$response.incomplete_details.reason)
    }

    try {
        $parsed = ConvertTo-HashtableCompat -Value ($text | ConvertFrom-Json)
    } catch {
        if ($response.status -eq 'incomplete' -and $null -ne $response.incomplete_details -and $response.incomplete_details.reason) {
            throw ('Model response incomplete: ' + [string]$response.incomplete_details.reason)
        }
        throw ('Model response JSON parse failed: ' + $_.Exception.Message)
    }

    return @{
        response = $response
        parsed = $parsed
        webSearchQueries = @(Get-ResponseWebSearchQueries -Response $response)
        webSearchSources = @(Get-ResponseWebSearchSources -Response $response)
        urlCitations = @(Get-ResponseUrlCitations -Response $response)
    }
}

function Get-PeerSteerMessages {
    param(
        [hashtable]$State,
        [hashtable]$Task,
        [string]$WorkerId
    )

    $messages = @()
    foreach ($peer in (Get-WorkerDefinitions -Task $Task)) {
        if ($peer['id'] -eq $WorkerId) {
            continue
        }
        if (-not $State['workers'].ContainsKey($peer['id'])) {
            continue
        }
        $checkpoint = $State['workers'][$peer['id']]
        if ($null -eq $checkpoint) {
            continue
        }

        $targets = @()
        if ((Test-ObjectKey -Value $checkpoint -Key 'requestTargets') -and $checkpoint['requestTargets']) {
            $targets = @($checkpoint['requestTargets'])
        }

        if ($targets.Count -gt 0 -and -not ($targets -contains $WorkerId -or $targets -contains '*')) {
            continue
        }

        $message = $null
        if (Test-ObjectKey -Value $checkpoint -Key 'requestToPeer') {
            $message = [string]$checkpoint['requestToPeer']
        }
        if ([string]::IsNullOrWhiteSpace($message)) {
            continue
        }

        $messages += ,([ordered]@{
            from = $peer['id']
            message = $message
        })
    }

    return $messages
}

function Expand-PeerSteerPackets {
    param([hashtable]$Task, [hashtable]$State)

    $packets = @()
    foreach ($worker in (Get-WorkerDefinitions -Task $Task)) {
        if (-not $State['workers'].ContainsKey($worker['id'])) {
            continue
        }
        $checkpoint = $State['workers'][$worker['id']]
        if ($null -eq $checkpoint) {
            continue
        }
        $message = $null
        if (Test-ObjectKey -Value $checkpoint -Key 'requestToPeer') {
            $message = [string]$checkpoint['requestToPeer']
        }
        if ([string]::IsNullOrWhiteSpace($message)) {
            continue
        }

        $targets = @()
        if ((Test-ObjectKey -Value $checkpoint -Key 'requestTargets') -and $checkpoint['requestTargets']) {
            $targets = @($checkpoint['requestTargets'])
        }
        if ($targets.Count -eq 0) {
            $targets = @('*')
        }

        foreach ($target in $targets) {
            $packets += ,([ordered]@{
                from = $worker['id']
                to = [string]$target
                message = $message
            })
        }
    }

    return $packets
}
