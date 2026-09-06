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
$requirementsStamp = Join-Path $venvRoot '.requirements.sha256'

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
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create LiteLLM virtual environment."
    }
}

$requirementsHash = (Get-FileHash -LiteralPath $requirementsFile -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $requirementsStamp) {
    (Get-Content -LiteralPath $requirementsStamp -Raw).Trim()
} else {
    ''
}
$requirementsChanged = $installedHash -ne $requirementsHash
if ($requirementsChanged) {
    & $venvPython -m pip install --disable-pip-version-check -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install LiteLLM gateway dependencies."
    }
}

$env:PATH = "$(Join-Path $venvRoot 'Scripts');$env:PATH"
$env:PYTHONUTF8 = '1'
$env:npm_config_cache = Join-Path $venvRoot 'npm-cache'
$env:PRISMA_HOME_DIR = Join-Path $venvRoot 'prisma-home'
$env:PRISMA_BINARY_CACHE_DIR = Join-Path $env:PRISMA_HOME_DIR 'binaries'
$env:PRISMA_NODEENV_CACHE_DIR = Join-Path $env:PRISMA_HOME_DIR 'nodeenv'
# LiteLLM 1.98 falls back to os.kill(pid, 0) for its engine watcher on
# Windows, which terminates the Prisma query engine instead of probing it.
# Keep the watchdog enabled in Linux containers; disable it only here.
$env:PRISMA_HEALTH_WATCHDOG_ENABLED = 'false'
New-Item -ItemType Directory -Path $env:npm_config_cache -Force | Out-Null

& $venvPython -c "from prisma import Prisma; assert hasattr(Prisma(), '_Prisma__engine')" 2>$null
$prismaReady = $LASTEXITCODE -eq 0
if ($requirementsChanged -or -not $prismaReady) {
    $prismaSchema = Join-Path $venvRoot 'Lib\site-packages\litellm_proxy_extras\schema.prisma'
    if (-not (Test-Path -LiteralPath $prismaSchema)) {
        throw "LiteLLM Prisma schema not found at $prismaSchema."
    }
    & $venvPython -m prisma generate --schema $prismaSchema
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate the LiteLLM Prisma client."
    }
    Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -NoNewline
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
