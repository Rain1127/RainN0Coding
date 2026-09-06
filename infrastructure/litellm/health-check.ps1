param(
    [string]$GatewayBase = 'http://127.0.0.1:4000',
    [string]$AgentKey = $env:LITELLM_API_KEY,
    [string]$MasterKey = $env:LITELLM_MASTER_KEY,
    [switch]$ContractMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Http {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string]$Uri,
        [ValidateSet('Get', 'Post')] [string]$Method = 'Get',
        [hashtable]$Headers = @{},
        [string]$Body = ''
    )

    $arguments = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        UseBasicParsing = $true
    }
    if ($Body) {
        $arguments.ContentType = 'application/json'
        $arguments.Body = $Body
    }
    $response = Invoke-WebRequest @arguments
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
        throw "$Name returned HTTP $($response.StatusCode)."
    }
    Write-Host "[PASS] $Name"
    return $response
}

$gatewayBase = $GatewayBase.TrimEnd('/')
$null = Assert-Http -Name 'LiteLLM liveness' -Uri "$gatewayBase/health/liveliness"

if ([string]::IsNullOrWhiteSpace($AgentKey)) {
    if ($ContractMode) {
        $AgentKey = 'sk-contract'
    } else {
        throw 'Set LITELLM_API_KEY or pass -AgentKey.'
    }
}
$agentHeaders = @{ Authorization = "Bearer $AgentKey" }
$models = Assert-Http -Name 'Authorized model listing' -Uri "$gatewayBase/v1/models" -Headers $agentHeaders
$modelIds = @((ConvertFrom-Json $models.Content).data.id)
foreach ($requiredModel in @('code-reasoning', 'code-structured', 'code-lightweight')) {
    if ($requiredModel -notin $modelIds) {
        throw "Authorized model listing is missing $requiredModel."
    }
}

if ([string]::IsNullOrWhiteSpace($MasterKey)) {
    if ($ContractMode) {
        $MasterKey = 'sk-contract'
    } else {
        throw 'Set LITELLM_MASTER_KEY or pass -MasterKey.'
    }
}
$metricsArguments = @{
    Name = 'Prometheus metrics'
    Uri = "$gatewayBase/metrics/"
    Headers = @{ Authorization = "Bearer $MasterKey" }
}
$metrics = Assert-Http @metricsArguments
if ($metrics.Content -notmatch 'litellm_') {
    throw 'LiteLLM metrics response contains no litellm_ metric families.'
}

if ($ContractMode) {
    $body = @{
        model = 'code-reasoning'
        messages = @(@{ role = 'user'; content = 'ping' })
    } | ConvertTo-Json -Depth 4
    $completionArguments = @{
        Name = 'Fake-provider completion'
        Uri = "$gatewayBase/v1/chat/completions"
        Method = 'Post'
        Headers = $agentHeaders
        Body = $body
    }
    $completion = Assert-Http @completionArguments
    $content = (ConvertFrom-Json $completion.Content).choices[0].message.content
    if ($content -ne 'fallback-ok') {
        throw "Unexpected contract completion: $content"
    }
}
