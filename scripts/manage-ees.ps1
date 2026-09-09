<#
One operator entry point for the existing Windows EES instance.
Settings and data stay outside Git. This does not synchronize Agent Pack items.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Init', 'Update', 'Status', 'Diagnose', 'ProbeImports', 'Plan', 'Prepare', 'Deploy', 'Rollback', 'Start', 'Stop', 'Apply', 'Restore')]
    [string]$Action,
    [string]$Config = (Join-Path $env:LOCALAPPDATA 'EES-Agent-POC\deployment\config.json'),
    [string]$SourcePython,
    [string]$WorkingDirectory,
    [string]$DataDirectory,
    [string]$ListenHost,
    [int]$Port,
    [string]$UvPath,
    [string]$Bundle,
    [string]$Commit,
    [string]$Wheelhouse,
    [ValidateRange(1, 900)]
    [int]$HealthTimeout,
    [switch]$UseWindowsCA,
    [switch]$CheckOnly,
    [switch]$Resume,
    [switch]$Summary,
    [string]$GitProxy
)

$ErrorActionPreference = 'Stop'
if ($UseWindowsCA -and $Action -ne 'Deploy') {
    throw 'UseWindowsCA is supported only with Deploy.'
}
if ($CheckOnly -and $Action -ne 'Apply') { throw 'CheckOnly is supported only with Apply.' }
if ($Resume -and $Action -ne 'Apply') { throw 'Resume is supported only with Apply.' }
if ($Summary -and $Action -notin @('Apply', 'Restore', 'Start', 'Stop', 'Status')) {
    throw 'Summary is supported with Apply/Restore/Start/Stop/Status only.'
}
$repoPath = Split-Path $PSScriptRoot -Parent

if ($Action -eq 'Update') {
    $gitArgs = @('-C', $repoPath)
    if ($GitProxy) { $gitArgs = @('-c', "http.proxy=$GitProxy") + $gitArgs }
    $branch = & git @gitArgs branch --show-current
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Update requires the existing main checkout.' }
    $changes = & git @gitArgs status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Preserve and review tracked local edits before updating.' }
    & git @gitArgs fetch origin main
    if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed; the server was not changed.' }
    & git @gitArgs merge --ff-only origin/main
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward update failed; no forced checkout was performed.' }
    return
}

if ($Action -eq 'Init') {
    if (-not $SourcePython -or -not $WorkingDirectory -or -not $DataDirectory -or -not $ListenHost -or -not $Port) {
        throw 'Init requires SourcePython, WorkingDirectory, DataDirectory, ListenHost and Port from the existing server.'
    }
    if (-not $UvPath) { $UvPath = (Get-Command uv -CommandType Application -ErrorAction Stop).Source }
    $operatorPython = $SourcePython
} else {
    if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Register the existing environment with Init first.' }
    $localConfig = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    $operatorPython = $localConfig.source_python
}

if (-not $operatorPython -or -not (Test-Path -LiteralPath $operatorPython -PathType Leaf)) {
    throw 'The registered Python environment is unavailable. Preserve its uv cache and inspect the existing installation.'
}
$pythonOptions = @('-I', '-B')
if ($Action -in @('Diagnose', 'ProbeImports')) { $pythonOptions += @('-S', '-B') }
$pythonAction = $Action.ToLowerInvariant()
if ($Action -eq 'ProbeImports') { $pythonAction = 'probe-imports' }
$operationArgs = $pythonOptions + @((Join-Path $PSScriptRoot 'manage_ees.py'), $pythonAction, '--config', $Config)
if ($Action -eq 'Init') {
    $operationArgs += @('--source-python', $SourcePython, '--cwd', $WorkingDirectory,
        '--data-dir', $DataDirectory, '--listen-host', $ListenHost, '--port', "$Port", '--uv', $UvPath)
}
if ($Bundle) { $operationArgs += @('--bundle', $Bundle) }
if ($Commit) { $operationArgs += @('--commit', $Commit) }
if ($Wheelhouse) { $operationArgs += @('--wheelhouse', $Wheelhouse) }
if ($PSBoundParameters.ContainsKey('HealthTimeout')) {
    $operationArgs += @('--health-timeout', "$HealthTimeout")
}
if ($UseWindowsCA) { $operationArgs += '--use-windows-ca' }
if ($CheckOnly) { $operationArgs += '--check-only' }
if ($Resume) { $operationArgs += '--resume' }
if ($Summary) { $operationArgs += '--summary' }
& $operatorPython @operationArgs
if ($LASTEXITCODE -ne 0) { throw "EES operation stopped (exit $LASTEXITCODE)." }
