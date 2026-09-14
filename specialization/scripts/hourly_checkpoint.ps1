param(
    [string]$Root = "C:\temp\loop"
)

$ErrorActionPreference = "SilentlyContinue"
$timestamp = (Get-Date).ToString("o")
$taskDir = Join-Path $Root "specialization\tasks"
$outputDir = Join-Path $Root "Specialization\output"
New-Item -ItemType Directory -Force -Path $taskDir | Out-Null

$health = $null
$state = $null
try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:8787/health" -Method Get -TimeoutSec 5 } catch {}
try { $state = Invoke-RestMethod -Uri "http://127.0.0.1:8787/v1/state" -Method Get -TimeoutSec 8 } catch {}

$latestOutput = Get-ChildItem -Path $outputDir -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 5 FullName, LastWriteTime, Length

$record = [ordered]@{
    timestamp = $timestamp
    paraHealthOk = [bool]($health -and $health.ok)
    loopStatus = if ($state) { [string]$state.loop.status } else { $null }
    dispatchStatus = if ($state) { [string]$state.dispatch.status } else { $null }
    latestOutput = $latestOutput
    reminder = "Review specialization state: Blender terrain/road proof, source notes, Para mission, next test."
}

$json = $record | ConvertTo-Json -Depth 8 -Compress
Add-Content -Path (Join-Path $taskDir "hourly_checkpoint.jsonl") -Value $json

$summary = @"
# Latest Hourly Specialization Checkpoint

- Time: $timestamp
- Para health ok: $($record.paraHealthOk)
- Loop status: $($record.loopStatus)
- Dispatch status: $($record.dispatchStatus)
- Latest output count: $(@($latestOutput).Count)

Next: inspect `specialization/tasks/hourly_checkpoint.jsonl`, then continue Blender/GIS specialization from the newest output artifact.
"@

Set-Content -Path (Join-Path $taskDir "latest_checkpoint.md") -Value $summary -Encoding UTF8
