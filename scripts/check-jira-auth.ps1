#requires -Version 5.1
# One read-only Bearer check. No WebUI import, file/DB write, token rotation or retry.
[CmdletBinding()]
param([switch]$AllowHttp, [switch]$UseSystemProxy)

$ErrorActionPreference = 'Stop'
$handler = $client = $response = $secret = $null
$pointer = [IntPtr]::Zero
$token = $base = $null
$exitCode = 1
$stage = 'input'
try {
    $base = (Read-Host 'Jira base URL (include context path if used)').TrimEnd('/')
    $uri = $null
    if (-not [Uri]::TryCreate($base, [UriKind]::Absolute, [ref]$uri)) { throw 'input' }
    if ($uri.Scheme -notin @('https', 'http') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw 'input' }
    if ($base -match '[\s\\]' -or $uri.Host -notmatch '^[A-Za-z0-9.-]+$') { throw 'input' }
    if ($uri.AbsolutePath -notmatch '^(/|(/[A-Za-z0-9_-]+)+/?)$') { throw 'input' }
    if ($uri.Scheme -eq 'http' -and -not $AllowHttp) {
        $stage = 'http_requires_AllowHttp'
        throw 'input'
    }
    $secret = Read-Host 'Your Jira personal token (hidden)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($token -notmatch '^[\x21-\x7e]{1,4096}$') { throw 'input' }

    $stage = 'connection'
    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $handler.UseDefaultCredentials = $false
    $handler.UseProxy = [bool]$UseSystemProxy
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(15)
    $client.MaxResponseContentBufferSize = 65536
    $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $token)
    $client.DefaultRequestHeaders.Accept.ParseAdd('application/json')
    $response = $client.GetAsync($base + '/rest/api/2/myself').GetAwaiter().GetResult()
    $status = [int]$response.StatusCode
    Write-Output "HTTPStatus=$status"
    if ($status -ne 200) { $stage = 'http_status'; throw 'response' }
    $stage = 'response'
    if ($response.Content.Headers.ContentType.MediaType -ne 'application/json') { throw 'response' }
    $jiraProfile = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
    if ($jiraProfile.active -isnot [bool] -or $jiraProfile.active -ne $true -or $jiraProfile.name -isnot [string] -or -not $jiraProfile.name) { throw 'response' }
    Write-Output 'BearerAuthenticated=True'
    $exitCode = 0
}
catch {
    # Do not print exception/response text, URL, user identity or headers.
    Write-Output 'BearerAuthenticated=False'
    Write-Output "CheckStage=$stage"
}
finally {
    if ($null -ne $response) { $response.Dispose() }
    if ($null -ne $client) { $client.Dispose() }
    if ($null -ne $handler) { $handler.Dispose() }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    if ($null -ne $secret) { $secret.Dispose() }
    $token = $base = $jiraProfile = $null
}
exit $exitCode
