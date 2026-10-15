[CmdletBinding()]
param(
    [switch]$ProbeOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskProject = (Resolve-Path -LiteralPath (Join-Path $taskRoot 'clients\unreal5 5.8\Hczs.uproject')).Path
$taskEngineRoot = 'D:\Program Files\Epic Games\UE_5.8'
$taskEditor = (Resolve-Path -LiteralPath (Join-Path $taskEngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe')).Path
$taskVersion = Get-Content -LiteralPath (Join-Path $taskEngineRoot 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
if ($taskVersion.MajorVersion -ne 5 -or $taskVersion.MinorVersion -ne 8 -or $taskVersion.PatchVersion -ne 3) {
    throw 'This launcher requires the verified UE 5.8.3 installation.'
}
$taskVersionLabel = '{0}.{1}.{2}-{3}' -f $taskVersion.MajorVersion, $taskVersion.MinorVersion, $taskVersion.PatchVersion, $taskVersion.Changelist

function Test-HczsEditorProcess {
    param([object]$ProcessInfo)
    if ($null -eq $ProcessInfo -or [string]::IsNullOrWhiteSpace($ProcessInfo.ExecutablePath) -or
        [string]::IsNullOrWhiteSpace($ProcessInfo.CommandLine)) {
        return $false
    }
    if (-not [string]::Equals($ProcessInfo.ExecutablePath, $taskEditor, [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }
    $taskTokens = @([regex]::Matches($ProcessInfo.CommandLine, '"([^"]*)"|([^\s"]+)') | ForEach-Object {
        if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value }
    })
    if ($taskTokens -contains '-game') { return $false }
    return @($taskTokens | Where-Object {
        [string]::Equals($_.Replace('/', '\'), $taskProject, [StringComparison]::OrdinalIgnoreCase)
    }).Count -gt 0
}

function Write-LauncherState {
    param([string]$State, [object]$EditorPid, [string]$LogPath = '')
    [ordered]@{
        status = $State
        editorPid = $EditorPid
        project = $taskProject
        engineVersion = $taskVersionLabel
        endpoint = 'http://127.0.0.1:8000/mcp'
        probeOnly = [bool]$ProbeOnly
        log = $LogPath
        mcpToolCallVerified = $false
    } | ConvertTo-Json
}

# Never take over an occupied port or stop another process.
$taskPortEndpoints = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
    Where-Object { $_.Port -eq 8000 })
if ($taskPortEndpoints.Count -gt 0) {
    if ($taskPortEndpoints.Count -ne 1 -or $taskPortEndpoints[0].Address.ToString() -ne '127.0.0.1') {
        throw 'Port 8000 has an unexpected listener. No process was stopped; inspect it before launching Unreal MCP.'
    }
    # netstat avoids the slow first-use NetTCPIP provider initialization on this host.
    $taskNetstat = @(& (Join-Path $env:SystemRoot 'System32\netstat.exe') -ano -p TCP)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the owner of port 8000; no editor was started.' }
    $taskOwnerIds = @($taskNetstat | ForEach-Object {
        if ($_ -match '^\s*TCP\s+127\.0\.0\.1:8000\s+\S+\s+LISTENING\s+(\d+)\s*$') { [uint32]$Matches[1] }
    } | Select-Object -Unique)
    if ($taskOwnerIds.Count -ne 1) {
        throw 'Port 8000 changed during inspection or its owner is unknown; retry after inspecting the listener.'
    }
    $taskOwner = Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId = {0}' -f $taskOwnerIds[0]) -OperationTimeoutSec 30
    if (-not (Test-HczsEditorProcess $taskOwner)) {
        throw ('Port 8000 belongs to PID {0}, which is not this project in the verified Unreal Editor. It was left untouched.' -f $taskOwnerIds[0])
    }
    Write-LauncherState -State 'already-running' -EditorPid $taskOwner.ProcessId
    return
}

# A full editor may still be loading before its MCP listener appears.
$taskExistingEditors = @(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'UnrealEditor.exe'" -OperationTimeoutSec 30 |
    Where-Object { Test-HczsEditorProcess $_ })
if ($taskExistingEditors.Count -gt 0) {
    Write-LauncherState -State 'editor-running-mcp-not-listening' -EditorPid @($taskExistingEditors.ProcessId)
    return
}
if ($ProbeOnly) {
    Write-LauncherState -State 'not-running' -EditorPid $null
    return
}

$taskDescriptor = Get-Content -LiteralPath $taskProject -Raw | ConvertFrom-Json
foreach ($taskPluginName in @('ModelContextProtocol', 'AllToolsets')) {
    $taskPlugin = @($taskDescriptor.Plugins | Where-Object { $_.Name -eq $taskPluginName })
    if ($taskPlugin.Count -ne 1 -or -not $taskPlugin[0].Enabled) {
        throw ('Enable {0} in Hczs.uproject before starting the MCP editor.' -f $taskPluginName)
    }
}
$taskLogs = Join-Path $taskRoot 'runtime\unreal'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskLog = Join-Path $taskLogs ('mcp-editor-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
$taskArguments = @(
    ('"{0}"' -f $taskProject),
    '-NoSplash',
    '-NoSound',
    '-Unattended',
    '-NoCompile',
    '-NoCompileEditor',
    '-ModelContextProtocolStartServer',
    '-DDC=InstalledNoZenLocalFallback',
    '-ini:Engine:[HTTPServer.Listeners]:DefaultBindAddress=127.0.0.1',
    ('-abslog="{0}"' -f $taskLog)
)
$taskProcess = Start-Process -FilePath $taskEditor -ArgumentList $taskArguments -WindowStyle Hidden -PassThru
Write-LauncherState -State 'started-awaiting-mcp' -EditorPid $taskProcess.Id -LogPath $taskLog
