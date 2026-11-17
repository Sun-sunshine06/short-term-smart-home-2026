$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sidecarEnv = Join-Path $repoRoot 'local\sidecar.env'
if (Test-Path -LiteralPath $sidecarEnv) {
    foreach ($line in Get-Content -LiteralPath $sidecarEnv) {
        if ($line -match '^(HOST|PORT|SIDECAR_URL|SIDECAR_TOKEN|UNO_PORT|UNO_BAUD|UNO_DEVICE_ID|UNO_SERIAL_ENABLED)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
}
Push-Location -LiteralPath $repoRoot
try {
    & uv run --with-requirements backend/requirements.txt python backend/app.py
} finally {
    Pop-Location
}
