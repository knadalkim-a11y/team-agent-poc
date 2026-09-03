#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$BaseUrl = $env:OPENWEBUI_BASE_URL,

    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $BaseUrl = "http://127.0.0.1:8080"
}

$baseUri = $null
if (-not [Uri]::TryCreate($BaseUrl, [UriKind]::Absolute, [ref]$baseUri)) {
    throw "BaseUrl이 올바른 URL이 아닙니다: $BaseUrl"
}

if (@("http", "https") -notcontains $baseUri.Scheme) {
    throw "BaseUrl은 http 또는 https URL이어야 합니다."
}

if (-not $baseUri.IsLoopback) {
    throw "현재 POC smoke test는 localhost 연결만 허용합니다."
}

if (-not [string]::IsNullOrWhiteSpace($baseUri.UserInfo)) {
    throw "BaseUrl에 계정이나 비밀번호를 포함하지 마세요."
}

$normalizedBaseUrl = $BaseUrl.TrimEnd("/")

Add-Type -AssemblyName System.Net.Http

$handler = [System.Net.Http.HttpClientHandler]::new()
$handler.UseProxy = $false
$handler.AllowAutoRedirect = $true

$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
$client.DefaultRequestHeaders.UserAgent.ParseAdd("team-agent-poc-smoke-test/1.0")

$checks = @(
    @{ Name = "Backend health"; Url = "$normalizedBaseUrl/health" },
    @{ Name = "Web UI"; Url = "$normalizedBaseUrl/" }
)

try {
    foreach ($check in $checks) {
        $response = $null

        try {
            $response = $client.GetAsync($check.Url).GetAwaiter().GetResult()

            if (-not $response.IsSuccessStatusCode) {
                throw "HTTP $([int]$response.StatusCode)"
            }

            Write-Host (
                "PASS  {0,-16} HTTP {1}" -f $check.Name, [int]$response.StatusCode
            ) -ForegroundColor Green
        }
        catch {
            throw ("FAIL  {0}: {1}" -f $check.Name, $_.Exception.Message)
        }
        finally {
            if ($null -ne $response) {
                $response.Dispose()
            }
        }
    }

    Write-Host ""
    Write-Host "Open WebUI local smoke test passed." -ForegroundColor Green
    Write-Host "Hermes와 사내 모델은 아직 호출하지 않았습니다."
}
finally {
    $client.Dispose()
    $handler.Dispose()
}
