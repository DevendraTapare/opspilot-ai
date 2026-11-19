param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$nodeExe = (Get-Command node.exe).Source
$manifestPath = Join-Path $projectRoot 'artifacts\dashboard-processes.json'
if (Test-Path -LiteralPath $manifestPath) { throw 'Run Stop-Dashboard.ps1 before starting another dashboard.' }
Push-Location $projectRoot
try {
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
    $env:npm_config_cache = Join-Path $projectRoot 'frontend\.cache\npm'
    $env:NEXT_TELEMETRY_DISABLED = '1'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        uv sync --locked
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    }
    docker compose --profile mcp up -d --wait db
    if ($LASTEXITCODE -ne 0) { throw 'Database startup failed.' }
    docker compose build api
    if ($LASTEXITCODE -ne 0) { throw 'Backend build failed.' }
    docker compose run --rm migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed.' }
    & $pythonExe -m scripts.initialize_dashboard
    if ($LASTEXITCODE -ne 0) { throw 'Dashboard provisioning failed.' }
    docker compose --profile mcp up -d --wait api authorizer mcp
    if ($LASTEXITCODE -ne 0) { throw 'Backend startup failed.' }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        if (-not $SkipBuild) {
            npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
            npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        }
    } finally { Pop-Location }
    $backendProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m', 'opspilot.dashboard.server') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'artifacts\dashboard-api.log') -RedirectStandardError (Join-Path $projectRoot 'artifacts\dashboard-api-error.log')
    $nextBin = Join-Path $projectRoot 'frontend\node_modules\next\dist\bin\next'
    $frontendProcess = Start-Process -FilePath $nodeExe -ArgumentList @(('"' + $nextBin + '"'), 'start', '--hostname', '127.0.0.1', '--port', '3000') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'artifacts\dashboard-ui.log') -RedirectStandardError (Join-Path $projectRoot 'artifacts\dashboard-ui-error.log')
    @(
        @{ id=$backendProcess.Id; executable=$pythonExe; needle='opspilot.dashboard.server'; started=$backendProcess.StartTime.ToUniversalTime().ToString('o') },
        @{ id=$frontendProcess.Id; executable=$nodeExe; needle=$nextBin; started=$frontendProcess.StartTime.ToUniversalTime().ToString('o') }
    ) | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $response = Invoke-RestMethod 'http://127.0.0.1:3000/api/ops/health/ready' -TimeoutSec 2
            if ($response.status -eq 'ready') { $ready=$true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Dashboard did not become ready. Inspect artifacts/dashboard-*.log; use Stop-Dashboard.ps1 to stop owned processes.' }
    Write-Host 'Dashboard ready: http://127.0.0.1:3000'
    Write-Host 'Action execution remains controlled by the existing backend flag. No fixtures were reset.'
} finally { Pop-Location }
