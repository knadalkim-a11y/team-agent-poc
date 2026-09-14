<#
One operator entry point for the existing Windows EES instance.
Settings and data stay outside Git. ApplyDemo manages only the declared demo assets.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Init', 'Update', 'Upgrade', 'ApplyDemo', 'Status', 'Diagnose', 'ProbeImports', 'Plan', 'Prepare', 'Deploy', 'Rollback', 'Start', 'Stop', 'Apply', 'Restore')]
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
    [switch]$ResetUpdateToken,
    [switch]$ResetDemoToken,
    [string]$WebUIUrl,
    [string]$EesModelId,
    [string]$WebUICaFile,
    [string]$GitProxy
)

$ErrorActionPreference = 'Stop'
if ($ResetUpdateToken -and $Action -notin @('Upgrade', 'ApplyDemo')) { throw 'ResetUpdateToken is supported only with Upgrade or ApplyDemo.' }
if (($ResetDemoToken -or $WebUIUrl -or $EesModelId -or $WebUICaFile) -and $Action -ne 'ApplyDemo') {
    throw 'Demo connection options are supported only with ApplyDemo.'
}
if ($Action -eq 'ApplyDemo' -and ($Bundle -or $Commit -or $Wheelhouse -or $GitProxy -or $HealthTimeout)) {
    throw 'ApplyDemo reuses the saved environment and verified main checkout; omit program deployment options.'
}
if ($Action -eq 'Upgrade' -and ($Bundle -or $Commit -or $Wheelhouse -or $GitProxy)) {
    throw 'Upgrade selects a verified artifact and reuses the saved Git proxy; omit Bundle/Commit/Wheelhouse/GitProxy.'
}
if ($UseWindowsCA -and $Action -notin @('Deploy', 'Start')) {
    throw 'UseWindowsCA is supported only with Deploy or Start.'
}
if ($CheckOnly -and $Action -notin @('Apply', 'Start')) { throw 'CheckOnly is supported only with Apply or Start.' }
if ($CheckOnly -and $UseWindowsCA) { throw 'CheckOnly cannot change runtime trust.' }
if ($Resume -and $Action -ne 'Apply') { throw 'Resume is supported only with Apply.' }
if ($Summary -and $Action -notin @('Apply', 'Restore', 'Start', 'Stop', 'Status', 'Upgrade', 'ApplyDemo')) {
    throw 'Summary is supported with Apply/Restore/Start/Stop/Status/Upgrade/ApplyDemo only.'
}
$repoPath = Split-Path $PSScriptRoot -Parent

if ($Action -eq 'Update') {
    # Registered Update shares the same lock as program operations. The
    # original Git-only bootstrap remains available before initial registration.
    if (Test-Path -LiteralPath $Config -PathType Leaf) {
        $updateConfig = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
        $updatePython = $updateConfig.source_python
        if (-not $updatePython -or -not (Test-Path -LiteralPath $updatePython -PathType Leaf)) {
            throw 'The registered Python environment is unavailable; preserve the existing installation.'
        }
        $updateArgs = @('-I', '-B', (Join-Path $PSScriptRoot 'ees_upgrade.py'), '--config', $Config, '--update-only')
        if ($GitProxy) { $updateArgs += @('--git-proxy', $GitProxy) }
        & $updatePython @updateArgs
        if ($LASTEXITCODE -ne 0) { throw 'EES update stopped; use the final EES summary.' }
        return
    }
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
if ($Action -eq 'ApplyDemo') {
    $demoArgs = $pythonOptions + @((Join-Path $PSScriptRoot 'ees_apply_demo.py'), '--config', $Config)
    if ($ResetDemoToken) { $demoArgs += '--reset-token' }
    if ($ResetUpdateToken) { $demoArgs += '--reset-update-token' }
    if ($WebUIUrl) { $demoArgs += @('--webui-url', $WebUIUrl) }
    if ($EesModelId) { $demoArgs += @('--ees-model-id', $EesModelId) }
    if ($WebUICaFile) { $demoArgs += @('--ca-file', $WebUICaFile) }
    & $operatorPython @demoArgs
    if ($LASTEXITCODE -ne 0) { throw 'EES demo apply stopped; use the final EES summary.' }
    return
}
if ($Action -eq 'Upgrade') {
    $upgradeArgs = $pythonOptions + @((Join-Path $PSScriptRoot 'ees_upgrade.py'), '--config', $Config)
    if ($PSBoundParameters.ContainsKey('HealthTimeout')) { $upgradeArgs += @('--health-timeout', "$HealthTimeout") }
    if ($ResetUpdateToken) { $upgradeArgs += '--reset-token' }
    & $operatorPython @upgradeArgs
    if ($LASTEXITCODE -ne 0) { throw 'EES upgrade stopped; use the final EES summary.' }
    return
}
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
