param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$gatewayRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $gatewayRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$litellmCommand = Join-Path $venvRoot 'Scripts\litellm.exe'
$envFile = Join-Path $gatewayRoot '.env'
$configFile = Join-Path $gatewayRoot 'config.yaml'
$requirementsFile = Join-Path $gatewayRoot 'requirements.txt'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Missing $envFile; copy .env.example and set secrets."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $repositoryRoot = Split-Path -Parent (Split-Path -Parent $gatewayRoot)
    $agentPython = Join-Path $repositoryRoot 'python-agent\.venv\Scripts\python.exe'
    if ($env:LITELLM_BOOTSTRAP_PYTHON) {
        $bootstrapPython = $env:LITELLM_BOOTSTRAP_PYTHON
    } elseif (Test-Path -LiteralPath $agentPython) {
        $bootstrapPython = $agentPython
    } else {
        $bootstrapPython = (Get-Command python -ErrorAction Stop).Source
    }
    & $bootstrapPython -m venv $venvRoot
    & $venvPython -m pip install --disable-pip-version-check -r $requirementsFile
}

Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

foreach ($requiredName in @(
    'LITELLM_MASTER_KEY',
    'DATABASE_URL',
    'DEEPSEEK_API_KEY',
    'ZHIPUAI_API_KEY'
)) {
    $requiredValue = [Environment]::GetEnvironmentVariable($requiredName, 'Process')
    if ([string]::IsNullOrWhiteSpace($requiredValue)) {
        throw "$requiredName must be set in infrastructure/litellm/.env."
    }
}

if ($env:LITELLM_MASTER_KEY -eq 'sk-replace-with-random-master-key') {
    throw 'Replace the example LITELLM_MASTER_KEY before starting LiteLLM.'
}
if ($env:DATABASE_URL -match 'replace-me') {
    throw 'Replace the example PostgreSQL password in DATABASE_URL before starting LiteLLM.'
}

$port = if ($env:LITELLM_PORT) { $env:LITELLM_PORT } else { '4000' }
& $litellmCommand --config $configFile --host '127.0.0.1' --port $port
