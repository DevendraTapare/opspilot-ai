param([switch]$StopBackend)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$manifestPath = Join-Path $projectRoot 'artifacts\dashboard-processes.json'
if (Test-Path -LiteralPath $manifestPath) {
    $records = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($record in $records) {
        $processInfo = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$record.id)
        if ($processInfo) {
            $runningProcess = Get-Process -Id ([int]$record.id)
            $startedAt = $runningProcess.StartTime.ToUniversalTime().ToString('o')
            if ($processInfo.ExecutablePath -ne $record.executable -or $startedAt -ne $record.started -or -not $processInfo.CommandLine.Contains([string]$record.needle)) {
                throw 'Process identity changed; refusing to stop an unrelated process.'
            }
            # These are the two direct project-owned hosts; no global node/python termination.
            Stop-Process -Id ([int]$record.id)
        }
    }
    Remove-Item -LiteralPath $manifestPath
}
if ($StopBackend) {
    Push-Location $projectRoot
    try {
        docker compose --profile mcp stop api mcp authorizer db
        if ($LASTEXITCODE -ne 0) { throw 'Project backend stop failed.' }
    } finally { Pop-Location }
}
Write-Host 'Owned dashboard processes stopped. No volumes or unrelated containers were removed.'
