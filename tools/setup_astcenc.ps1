param([string]$Destination = (Join-Path $PSScriptRoot 'runtime\astcenc-5.7.0'))
$ErrorActionPreference = 'Stop'
$artifactUrl = 'https://github.com/ARM-software/astc-encoder/releases/download/5.7.0/astcenc-5.7.0-windows-x64.zip'
$artifactSha = 'cbde7c78adcc90d0d90ecf10f32d03f3340fbe1720cb6d6c892147d625e74d2d'
$runtimeDirectory = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$archivePath = Join-Path $runtimeDirectory 'astcenc-5.7.0-windows-x64.zip'
if (-not (Test-Path -LiteralPath $archivePath)) {
    Invoke-WebRequest -Uri $artifactUrl -OutFile $archivePath
}
if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifactSha) {
    throw "ASTC release hash does not match: $archivePath"
}
$extractDirectory = Join-Path $runtimeDirectory 'bin'
if (-not (Test-Path -LiteralPath $extractDirectory)) {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractDirectory
}
@{
    version = '5.7.0'
    source = $artifactUrl
    sha256 = $artifactSha
    checksumSource = 'https://github.com/ARM-software/astc-encoder/releases/tag/5.7.0'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'source.json') -Encoding utf8
Get-ChildItem -LiteralPath $extractDirectory -Filter '*.exe' -Recurse | Select-Object FullName
