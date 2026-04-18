param(
    [string]$RootPath
)

function Get-StatePath {
    param([string]$Root)
    return (Join-Path $Root 'data\state.json')
}

function Get-AuthPath {
    param([string]$Root)
    return (Join-Path $Root 'Auth.txt')
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

function Read-State {
    param([string]$Root)
    $path = Get-StatePath -Root $Root
    if (-not (Test-Path $path)) {
        return [ordered]@{
            activeTask = $null
            workers = @{ A = $null; B = $null }
            summary = $null
            memoryVersion = 0
            lastUpdated = (Get-Date).ToUniversalTime().ToString('o')
        }
    }
    $json = Get-Content -Path $path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($json)) {
        return [ordered]@{
            activeTask = $null
            workers = @{ A = $null; B = $null }
            summary = $null
            memoryVersion = 0
            lastUpdated = (Get-Date).ToUniversalTime().ToString('o')
        }
    }
    return (ConvertTo-HashtableCompat -Value ($json | ConvertFrom-Json))
}

function Write-State {
    param(
        [string]$Root,
        [hashtable]$State
    )
    $State['lastUpdated'] = (Get-Date).ToUniversalTime().ToString('o')
    $path = Get-StatePath -Root $Root
    $json = $State | ConvertTo-Json -Depth 10
    Set-Content -Path $path -Value $json -Encoding UTF8
}

function Add-Event {
    param(
        [string]$Root,
        [string]$Type,
        [hashtable]$Payload
    )
    $eventPath = Join-Path $Root 'data\events.jsonl'
    $line = [ordered]@{
        ts = (Get-Date).ToUniversalTime().ToString('o')
        type = $Type
        payload = $Payload
    } | ConvertTo-Json -Compress -Depth 10
    Add-Content -Path $eventPath -Value $line -Encoding UTF8
}

function Add-Step {
    param(
        [string]$Root,
        [string]$Stage,
        [string]$Message,
        [hashtable]$Context
    )
    $stepPath = Join-Path $Root 'data\steps.jsonl'
    $line = [ordered]@{
        ts = (Get-Date).ToUniversalTime().ToString('o')
        stage = $Stage
        message = $Message
        context = $Context
    } | ConvertTo-Json -Compress -Depth 10
    Add-Content -Path $stepPath -Value $line -Encoding UTF8
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

    if ($Task -and $Task.ContainsKey('runtime') -and $Task['runtime']) {
        foreach ($key in @('executionMode', 'model', 'reasoningEffort')) {
            if ($Task['runtime'].ContainsKey($key) -and $Task['runtime'][$key]) {
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
