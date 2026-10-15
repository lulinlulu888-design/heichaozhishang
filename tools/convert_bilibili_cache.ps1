param(
    [string]$CacheRoot = (Join-Path $env:USERPROFILE 'Videos/bilibili'),
    [string]$OutputRoot,
    [string]$Only,
    [string]$FFmpegDirectory,
    [int]$FrameInterval = 15,
    [double[]]$At = @(),
    [switch]$List
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'),
    (Join-Path $projectRoot '.venv/Scripts/python.exe')
)
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') { $pythonCandidates += $pythonCommand.Source }
$referencePython = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $referencePython) { throw 'Python 3.10+ not found. Run tools/reference/convert_bilibili_cache.py with your Python installation.' }

$referenceArgs = @('-X', 'utf8', (Join-Path $PSScriptRoot 'reference/convert_bilibili_cache.py'), '--cache-root', $CacheRoot, '--frame-interval', $FrameInterval)
if ($OutputRoot) { $referenceArgs += @('--output-root', $OutputRoot) }
if ($Only) { $referenceArgs += @('--only', $Only) }
if ($List) { $referenceArgs += '--list' }
foreach ($second in $At) { $referenceArgs += @('--at', $second.ToString([System.Globalization.CultureInfo]::InvariantCulture)) }
if (-not $List) {
    $toolConfig = Join-Path $projectRoot 'runtime/reference-tools.json'
    if ($FFmpegDirectory) {
        $referenceArgs += @('--ffmpeg', (Join-Path $FFmpegDirectory 'ffmpeg.exe'), '--ffprobe', (Join-Path $FFmpegDirectory 'ffprobe.exe'))
    } elseif (Test-Path -LiteralPath $toolConfig -PathType Leaf) {
        $referenceTools = Get-Content -LiteralPath $toolConfig -Raw | ConvertFrom-Json
        $referenceArgs += @('--ffmpeg', $referenceTools.ffmpeg, '--ffprobe', $referenceTools.ffprobe)
    }
}
& $referencePython @referenceArgs
exit $LASTEXITCODE
