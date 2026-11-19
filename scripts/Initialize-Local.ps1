$ErrorActionPreference = 'Stop'
$opspilotRoot = Split-Path -Parent $PSScriptRoot
$opspilotEnv = Join-Path $opspilotRoot '.env'
if (Test-Path -LiteralPath $opspilotEnv) {
    Write-Output 'Existing .env preserved.'
    exit 0
}
function New-OpsPilotSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$opspilotPassword = New-OpsPilotSecret
$opspilotToken = New-OpsPilotSecret
$opspilotLines = @(
    "OPSPILOT_CONTROL_TOKEN=$opspilotToken",
    'POSTGRES_USER=opspilot',
    "POSTGRES_PASSWORD=$opspilotPassword",
    'POSTGRES_DB=opspilot',
    "OPSPILOT_DATABASE_URL=postgresql+psycopg://opspilot:$opspilotPassword@127.0.0.1:55432/opspilot",
    'OPSPILOT_API_PORT=8084',
    'OPSPILOT_DB_PORT=55432',
    'OPSPILOT_LOG_LEVEL=INFO'
)
[System.IO.File]::WriteAllLines($opspilotEnv, $opspilotLines, [System.Text.UTF8Encoding]::new($false))
Write-Output 'Created local .env with generated secrets. Secret values were not printed.'
