#requires -Version 5.1

[CmdletBinding()]
param(
    [string]$ProxyUrl = $env:CORP_PROXY_URL,
    [string]$NoProxy = $env:CORP_NO_PROXY
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$listenAddress = "127.0.0.1"
$port = 8080
$openWebuiVersion = "0.11.3"
$pythonVersion = "3.11"

$localAppData = [Environment]::GetFolderPath("LocalApplicationData")
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    throw "LOCALAPPDATA 경로를 확인할 수 없습니다."
}

$openWebuiRoot = Join-Path $localAppData "EES-Agent-POC\open-webui"
$dataDir = Join-Path $openWebuiRoot "data"

if (-not [string]::IsNullOrWhiteSpace($ProxyUrl)) {
    $proxyUri = $null

    if (-not [Uri]::TryCreate($ProxyUrl, [UriKind]::Absolute, [ref]$proxyUri)) {
        throw "CORP_PROXY_URL은 http://host:port 형식의 절대 URL이어야 합니다."
    }

    if (@("http", "https") -notcontains $proxyUri.Scheme) {
        throw "프록시 URL은 http 또는 https 방식만 사용할 수 있습니다."
    }

    if (-not [string]::IsNullOrWhiteSpace($proxyUri.UserInfo)) {
        throw "프록시 URL에 계정이나 비밀번호를 넣지 마세요."
    }

    $env:HTTP_PROXY = $proxyUri.AbsoluteUri
    $env:HTTPS_PROXY = $proxyUri.AbsoluteUri
    Write-Host "Corporate proxy configured for this process."
}

if (-not [string]::IsNullOrWhiteSpace($NoProxy) -and $NoProxy -match "[\r\n]") {
    throw "CORP_NO_PROXY에는 줄바꿈을 사용할 수 없습니다."
}

$noProxyEntries = @("127.0.0.1", "localhost", "::1")
if (-not [string]::IsNullOrWhiteSpace($NoProxy)) {
    $noProxyEntries += @($NoProxy -split ",")
}

$env:NO_PROXY = (
    $noProxyEntries |
        ForEach-Object { $_.Trim() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
) -join ","

# uv가 Windows 인증서 저장소의 사내 CA를 사용하도록 설정합니다.
$env:UV_SYSTEM_CERTS = "true"

# 현재 POC에서는 Ollama 연결을 사용하지 않습니다.
$env:ENABLE_OLLAMA_API = "False"
$env:DATA_DIR = $dataDir

$uvxCommand = Get-Command "uvx" -CommandType Application -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($null -eq $uvxCommand) {
    throw "uvx를 찾을 수 없습니다. uv 설치와 PATH 설정을 확인하세요."
}

$activeListeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
$portUsers = @($activeListeners | Where-Object { $_.Port -eq $port })

if ($portUsers.Count -gt 0) {
    throw "로컬 TCP 포트 $port가 이미 사용 중입니다. 기존 프로세스를 확인하세요."
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Write-Host ""
Write-Host "Open WebUI v$openWebuiVersion"
Write-Host "URL      : http://$($listenAddress):$port"
Write-Host "Data     : $dataDir"
Write-Host "Python   : $pythonVersion"
Write-Host ""
Write-Host "첫 실행에서는 Python 패키지와 임베딩 모델을 다운로드할 수 있습니다."
Write-Host "종료하려면 Ctrl+C를 누르세요."
Write-Host ""

$uvxArgs = @(
    "--python", $pythonVersion,
    "open-webui@$openWebuiVersion",
    "serve",
    "--host", $listenAddress,
    "--port", "$port"
)

Push-Location $openWebuiRoot

try {
    & $uvxCommand.Source @uvxArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Open WebUI가 종료 코드 $LASTEXITCODE 로 중단되었습니다."
    }
}
finally {
    Pop-Location
}
