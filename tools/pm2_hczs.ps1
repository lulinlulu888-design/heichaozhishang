param(
  [ValidateSet('list', 'start', 'restart', 'stop', 'logs', 'save')]
  [string]$Action = 'list',
  [ValidateSet('battle','admin')][string]$Service = 'battle'
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtime = Join-Path $projectRoot 'runtime/pm2'
$pm2Command = Get-Command pm2 -ErrorAction Stop
$pm2Package = Join-Path (Split-Path $pm2Command.Source -Parent) 'node_modules/pm2'
if (!(Test-Path -LiteralPath (Join-Path $pm2Package 'paths.js'))) {
  throw 'Cannot locate installed PM2 beside its command shim. Install PM2 with npm install -g pm2.'
}
$nodeCommand = (Get-Command node -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
# Installed PM2 overwrites environment pipe settings on Windows after applying them.
# This process-local preload wraps its paths factory; global npm files are untouched.
$preload = Join-Path $runtime 'isolated-paths.cjs'
@'
const path = require('node:path');
const crypto = require('node:crypto');
const fs = require('node:fs');
const home = path.resolve(process.env.HCZS_PM2_HOME);
if (path.resolve(process.env.PM2_HOME) !== home) throw Error('HCZS PM2 home mismatch');
const pathsFile = path.join(process.env.HCZS_PM2_PACKAGE, 'paths.js');
const original = require(pathsFile);
const identity = crypto.createHash('sha256').update(home.toLowerCase() + '\0' + require('node:os').userInfo().username).digest('hex').slice(0, 20);
function isolated(requestedHome) {
  const result = original(requestedHome);
  if (path.resolve(result.PM2_HOME) !== home) throw Error('Refusing non-project PM2 home');
  for (const [key, suffix] of [['DAEMON_RPC_PORT', 'rpc'], ['DAEMON_PUB_PORT', 'pub'], ['INTERACTOR_RPC_PORT', 'interactor']]) {
    result[key] = process.platform === 'win32' ? `\\\\.\\pipe\\hczs-${identity}-${suffix}` : path.join(home, `${suffix}.sock`);
  }
  return result;
}
require.cache[require.resolve(pathsFile)].exports = isolated;
const config = isolated(home);
fs.writeFileSync(path.join(home, 'isolation.json'), JSON.stringify({home, rpc:config.DAEMON_RPC_PORT, pub:config.DAEMON_PUB_PORT}, null, 2));
'@ | Set-Content -LiteralPath $preload -Encoding utf8
$keys = @('PM2_HOME', 'HCZS_PM2_HOME', 'HCZS_PM2_PACKAGE', 'NODE_OPTIONS', 'PM2_NO_INTERACTION', 'PM2_DISCRETE_MODE')
$previous = @{}
foreach ($key in $keys) { $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
try {
  $env:PM2_HOME = $runtime
  $env:HCZS_PM2_HOME = $runtime
  $env:HCZS_PM2_PACKAGE = $pm2Package
  $env:NODE_OPTIONS = '--require "' + $preload.Replace('\', '/') + '"'
  $env:PM2_NO_INTERACTION = 'true'
  $env:PM2_DISCRETE_MODE = 'true'
  $taskProcessName='hczs-'+$Service
  $cliArgs = switch ($Action) {
    'list' { @('list') }
    'start' { @('start', (Join-Path $projectRoot 'ecosystem.config.cjs'), '--only', $taskProcessName) }
    'restart' { @('restart', $taskProcessName, '--update-env') }
    'stop' { @('stop', $taskProcessName) }
    'logs' { @('logs', $taskProcessName, '--lines', '50', '--nostream') }
    'save' { @('save') }
  }
  & $nodeCommand (Join-Path $pm2Package 'bin/pm2') @cliArgs
  if ($LASTEXITCODE -ne 0) { throw "Project PM2 command failed (exit $LASTEXITCODE)" }
} finally {
  foreach ($key in $keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
