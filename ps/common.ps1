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

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Value
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
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

function Get-DefaultState {
    return [ordered]@{
        activeTask = $null
        workers = @{ A = $null; B = $null }
        summary = $null
        memoryVersion = 0
        loop = Get-DefaultLoopState
        lastUpdated = (Get-Date).ToUniversalTime().ToString('o')
    }
}

function Ensure-DataPaths {
    param([string]$Root)

    $paths = @(
        (Get-DataPath -Root $Root),
        (Join-Path $Root 'data\tasks'),
        (Join-Path $Root 'data\checkpoints'),
        (Get-LocksPath -Root $Root)
    )

    foreach ($path in $paths) {
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }

    $statePath = Get-StatePath -Root $Root
    if (-not (Test-Path $statePath)) {
        Write-Utf8NoBom -Path $statePath -Value (Get-DefaultState | ConvertTo-Json -Depth 20)
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
        [int]$StaleSeconds = 900
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
        [int]$StaleSeconds = 900
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
            ([ordered]@{
                pid = $PID
                ts = (Get-Date).ToUniversalTime().ToString('o')
            } | ConvertTo-Json -Depth 5) | Set-Content -Path $ownerPath -Encoding UTF8

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

function Normalize-State {
    param([hashtable]$State)

    $default = Get-DefaultState
    $normalized = [ordered]@{
        activeTask = $default['activeTask']
        workers = @{ A = $null; B = $null }
        summary = $default['summary']
        memoryVersion = $default['memoryVersion']
        loop = Get-DefaultLoopState
        lastUpdated = $default['lastUpdated']
    }

    if ($null -ne $State) {
        if (Test-ObjectKey -Value $State -Key 'activeTask') {
            $normalized['activeTask'] = $State['activeTask']
        }
        if (Test-ObjectKey -Value $State -Key 'summary') {
            $normalized['summary'] = $State['summary']
        }
        if ((Test-ObjectKey -Value $State -Key 'memoryVersion') -and $null -ne $State['memoryVersion']) {
            $normalized['memoryVersion'] = [int]$State['memoryVersion']
        }
        if ((Test-ObjectKey -Value $State -Key 'lastUpdated') -and $State['lastUpdated']) {
            $normalized['lastUpdated'] = [string]$State['lastUpdated']
        }
        if ((Test-ObjectKey -Value $State -Key 'workers') -and $State['workers']) {
            if (Test-ObjectKey -Value $State['workers'] -Key 'A') {
                $normalized['workers']['A'] = $State['workers']['A']
            }
            if (Test-ObjectKey -Value $State['workers'] -Key 'B') {
                $normalized['workers']['B'] = $State['workers']['B']
            }
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

function Write-StateUnlocked {
    param(
        [string]$Root,
        [hashtable]$State
    )

    Ensure-DataPaths -Root $Root
    $normalized = Normalize-State -State $State
    $normalized['lastUpdated'] = (Get-Date).ToUniversalTime().ToString('o')
    $path = Get-StatePath -Root $Root
    $json = $normalized | ConvertTo-Json -Depth 20
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
    } | ConvertTo-Json -Compress -Depth 20

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
    } | ConvertTo-Json -Compress -Depth 20

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
    param([hashtable]$Task)

    $runtime = @{
        executionMode = 'live'
        model = 'gpt-5-mini'
        reasoningEffort = 'low'
    }

    if ($Task -and (Test-ObjectKey -Value $Task -Key 'runtime') -and $Task['runtime']) {
        foreach ($key in @('executionMode', 'model', 'reasoningEffort')) {
            if ((Test-ObjectKey -Value $Task['runtime'] -Key $key) -and $Task['runtime'][$key]) {
                $runtime[$key] = [string]$Task['runtime'][$key]
            }
        }
    }

    return $runtime
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

function Invoke-OpenAIJson {
    param(
        [string]$ApiKey,
        [string]$Model,
        [string]$ReasoningEffort,
        [string]$Instructions,
        [string]$InputText,
        [string]$SchemaName,
        [hashtable]$Schema
    )

    $headers = @{
        Authorization = "Bearer $ApiKey"
    }

    $body = @{
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
    } | ConvertTo-Json -Depth 20

    $response = Invoke-RestMethod -Method Post -Uri 'https://api.openai.com/v1/responses' -Headers $headers -ContentType 'application/json' -Body $body
    $text = Get-ResponseOutputText -Response $response
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw 'Model response did not include output_text.'
    }

    return @{
        response = $response
        parsed = ConvertTo-HashtableCompat -Value ($text | ConvertFrom-Json)
    }
}
