param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$gatewayRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $gatewayRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$envFile = Join-Path $gatewayRoot '.env'
$configFile = Join-Path $gatewayRoot 'config.yaml'
$requirementsFile = Join-Path $gatewayRoot 'requirements.txt'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile; copy .env.example and set secrets."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.12 -m venv $venvRoot
    & $venvPython -m pip install --disable-pip-version-check -r $requirementsFile
}

Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

if ([string]::IsNullOrWhiteSpace($env:LITELLM_MASTER_KEY)) {
    throw 'LITELLM_MASTER_KEY must be set in infrastructure/litellm/.env.'
}
if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) {
    throw 'DATABASE_URL must be set in infrastructure/litellm/.env.'
}

$port = if ($env:LITELLM_PORT) { $env:LITELLM_PORT } else { '4000' }
& $venvPython -m litellm --config $configFile --host '127.0.0.1' --port $port
