param(
    [string]$GatewayBase = 'http://127.0.0.1:4000'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($env:LITELLM_MASTER_KEY)) {
    throw 'Set LITELLM_MASTER_KEY in the current process before provisioning.'
}

$body = @{
    key_alias = 'python-agent'
    models = @('code-reasoning', 'code-structured', 'code-lightweight')
    rpm_limit = 20
    tpm_limit = 200000
    max_budget = 10
    budget_duration = '30d'
} | ConvertTo-Json

$requestArguments = @{
    Method = 'Post'
    Uri = "$($GatewayBase.TrimEnd('/'))/key/generate"
    Headers = @{ Authorization = "Bearer $env:LITELLM_MASTER_KEY" }
    ContentType = 'application/json'
    Body = $body
}
$result = Invoke-RestMethod @requestArguments

if ([string]::IsNullOrWhiteSpace($result.key)) {
    throw 'LiteLLM did not return a virtual key.'
}

Write-Host '[PASS] Created python-agent virtual key. Copy the next line once.'
Write-Output $result.key
