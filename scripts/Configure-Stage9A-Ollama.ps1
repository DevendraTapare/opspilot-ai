# Dot-source this file after the separately approved runtime/model installation.
# This script never installs, pulls, loads or runs a model. Only local metadata is read.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$opspilotModel = 'qwen3:4b-q4_K_M'
$opspilotEndpoint = 'http://127.0.0.1:11434'
$opspilotExpectedDigest = 'sha256:2bfd38a7daaf4b1037efe517ccb73d1a3bbd4822cf89f1a82be1569050a114e0'

try {
    $opspilotTags = Invoke-RestMethod -Uri "$opspilotEndpoint/api/tags" -TimeoutSec 5
} catch {
    throw 'Local Ollama is unavailable. No installation, model pull or fixture fallback was attempted.'
}
$opspilotInstalled = @($opspilotTags.models | Where-Object {
    $_.name -eq $opspilotModel -or $_.model -eq $opspilotModel
})
if ($opspilotInstalled.Count -ne 1) {
    throw 'The approved exact model is not installed. This script will not download it.'
}
$opspilotReportedDigest = ([string]$opspilotInstalled[0].digest) -replace '^sha256:', ''
if ($opspilotReportedDigest -ne ($opspilotExpectedDigest -replace '^sha256:', '')) {
    throw 'Model digest differs from the reviewed artifact. Review the change before inference.'
}
$opspilotMetadata = Invoke-RestMethod -Uri "$opspilotEndpoint/api/show" -Method Post `
    -ContentType 'application/json' -Body (@{ model = $opspilotModel } | ConvertTo-Json) `
    -TimeoutSec 10
if (@($opspilotMetadata.capabilities) -notcontains 'tools') {
    throw 'Installed model metadata does not advertise tool calling.'
}
$opspilotContext = $opspilotMetadata.model_info.PSObject.Properties['qwen3.context_length']
if ($null -eq $opspilotContext -or [long]$opspilotContext.Value -lt 16384) {
    throw 'Model metadata does not establish support for the existing 16384-token adapter context.'
}

# Process environment only. No dotenv file, user-wide setting or credential is written.
$env:OPSPILOT_AGENT_PROVIDER = 'ollama'
$env:OPSPILOT_AGENT_MODEL = $opspilotModel
$env:OPSPILOT_AGENT_BASE_URL = $opspilotEndpoint
Remove-Item -LiteralPath Env:OPSPILOT_AGENT_API_KEY -ErrorAction SilentlyContinue
$env:LANGSMITH_TRACING = 'false'
$env:LANGCHAIN_TRACING_V2 = 'false'
Write-Host "Configured local provider: ollama; model: $opspilotModel"
Write-Host "Reviewed digest: $opspilotExpectedDigest"
Write-Host 'Use --mode real explicitly. No inference or MCP action was executed by configuration.'
