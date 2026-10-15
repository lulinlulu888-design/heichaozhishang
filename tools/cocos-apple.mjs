// Prepare/check Apple builds. This host cannot substitute for Mac/Xcode or device validation.
import { readFile, stat, mkdir, writeFile, open } from 'node:fs/promises';
import { resolve, join, extname, posix } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { parseArgs } from 'node:util';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const PROJECT = join(ROOT, 'legacy/cocos-poc');
const SCENE = '1cce6d16-610f-45bd-8b9f-63628732ec0f';
const ensure = (value, message) => { if (!value) throw new Error(message); };
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const exists = async path => { try { return await stat(path); } catch (error) { if (error.code === 'ENOENT') return null; throw error; } };

export function validateConfig(config, platform) {
  ensure(platform === 'mac' || platform === 'ios', 'Supported platforms: mac, ios');
  ensure(config.platform === platform && config.outputName === platform && config.name === 'hczs-cocos-poc', 'Unexpected platform/output identity');
  ensure(config.buildPath === 'project://build' && config.startScene === SCENE, 'Unexpected build path or scene');
  ensure(config.scenes?.length === 1 && config.scenes[0].uuid === SCENE && config.scenes[0].url === 'db://assets/ToolchainProof.scene', 'Unexpected scene list');
  const options = config.packages?.[platform], native = config.packages?.native;
  ensure(options?.executableName === config.name && options.packageName === 'local.hczs.rebuild', 'Unexpected application identity');
  ensure(options.renderBackEnd?.metal === true && options.renderBackEnd.gles2 === false && options.renderBackEnd.gles3 === false, 'Apple configuration must select Metal only');
  ensure(native?.runAfterMake === false && native.serverMode === false && native.netMode === 0, 'Build must not run the app or change native networking mode');
  ensure(options.skipUpdateXcodeProject === false, 'Configuration requires Xcode project regeneration');
  ensure(platform === 'mac' ? options.supportM1 === true && options.targetVersion === '11.0' :
    options.targetVersion === '13.0' && options.osTarget?.iphoneos === true && options.osTarget.simulator === false &&
    options.orientation?.landscapeLeft === true && options.orientation.landscapeRight === true &&
    options.orientation.portrait === false && options.orientation.upsideDown === false, 'Unexpected platform options');
  ensure(options.developerTeam === undefined, 'Signing identity must be configured by the user in Xcode');
  return config;
}

export function exportArguments(creator, configPath) {
  ensure(typeof creator === 'string' && creator.length > 0, 'Pass --creator with your installed CocosCreator.app path');
  ensure(!/[;\r\n]/.test(configPath) && !/[;\r\n]/.test(PROJECT), 'Project paths cannot contain Creator CLI delimiters');
  const executable = extname(creator) === '.app' ? join(creator, 'Contents/MacOS/CocosCreator') : creator;
  return { executable: resolve(executable), args: ['--project', PROJECT, '--build', `configPath=${configPath};stage=build`] };
}

// Project-only validation is separate from host checks, so a temporary project
// can exercise migration failures without touching real assets or launching tools.
export async function inspectProjectInputs(project, platform) {
  ensure(platform === 'mac' || platform === 'ios', 'Supported platforms: mac, ios');
  const configPath = join(project, `build-${platform}.json`);
  const configBytes = await readFile(configPath);
  const config = validateConfig(JSON.parse(configBytes.toString()), platform);
  const packageInfo = JSON.parse(await readFile(join(project, 'package.json'), 'utf8'));
  ensure(packageInfo.creator?.version === '3.8.8', 'This preparation targets Creator 3.8.8');
  const sourcePaths = ['assets/ToolchainProof.ts', 'assets/TutorialBattleController.ts', 'assets/TutorialBattleView.ts',
    'assets/TargetArrowGeometry.ts',
    'assets/EnemyTurnPresentation.ts',
    'assets/EndTurnView.ts',
    'assets/VictoryTitleView.ts', 'assets/resources/recovered/result-ui/victory-title.json',
    'assets/resources/recovered/result-ui/provenance.json',
    'assets/resources/recovered/prologue/player-orientation.json',
        'assets/resources/recovered/end-turn/end-turn.json',
    'assets/CardSelectionView.ts', 'assets/resources/recovered/card-selection/selection.json',
    'assets/TargetArrowView.ts', 'assets/resources/recovered/target-arrow/provenance.json',
    'assets/resources/recovered/target-arrow/target-arrow.effect',
    'assets/RecoveredCharacterView.ts', 'assets/ToolchainProof.scene', 'settings/v2/packages/engine.json',
    'native/engine/common/localCfg.cmake', 'asset-provenance.json', 'assets/resources/recovered/models/elsa/elsa.glb'];
  const sources = [];
  for (const path of sourcePaths) {
    const bytes = await readFile(join(project, path));
    sources.push({ path, bytes: bytes.length, sha256: sha(bytes) });
  }
  const provenance = JSON.parse(await readFile(join(project, 'asset-provenance.json'), 'utf8'));
  ensure(Array.isArray(provenance.files) && provenance.files.length > 0, 'Recovered asset inventory is missing');
  const recoveredAssets = [];
  for (const item of provenance.files) {
    ensure(typeof item.destination === 'string' && item.destination.startsWith('assets/') &&
      !item.destination.includes('\\') && !item.destination.split('/').some(part => part === '..' || part === '') &&
      /^[a-f0-9]{64}$/.test(item.sha256), 'Invalid recovered asset record');
    const bytes = await readFile(join(project, item.destination));
    ensure(sha(bytes) === item.sha256, `Recovered asset differs from its conversion record: ${item.destination}`);
    recoveredAssets.push({ path: item.destination, bytes: bytes.length, sha256: item.sha256 });
  }
  // A .meta is an import input, not a disposable Creator cache. Include the
  // scene, scripts, every recovered asset, and their asset-directory ancestors.
  // The project assets root itself has no assets.meta in Creator projects.
  const metadataPaths = new Set();
  for (const path of [...sourcePaths.filter(path => path.startsWith('assets/')), ...recoveredAssets.map(item => item.path)]) {
    metadataPaths.add(`${path}.meta`);
    for (let parent = posix.dirname(path); parent !== 'assets' && parent !== '.'; parent = posix.dirname(parent)) {
      metadataPaths.add(`${parent}.meta`);
    }
  }
  const metadata = [];
  for (const path of [...metadataPaths].sort()) {
    let bytes;
    try { bytes = await readFile(join(project, path)); }
    catch (error) {
      if (error.code === 'ENOENT') throw new Error(`Missing Creator metadata: ${path}`);
      throw error;
    }
    const meta = JSON.parse(bytes.toString());
    ensure(meta && typeof meta.uuid === 'string' && meta.uuid.length > 0 &&
      typeof meta.importer === 'string' && meta.importer.length > 0, `Invalid Creator metadata: ${path}`);
    if (path === 'assets/ToolchainProof.scene.meta') {
      ensure(meta.importer === 'scene' && meta.uuid === config.startScene && meta.uuid === config.scenes[0].uuid,
        'Scene metadata UUID does not match the configured start scene');
    }
    metadata.push({ path, bytes: bytes.length, sha256: sha(bytes), uuid: meta.uuid, importer: meta.importer });
  }
  const nativeConfig = await readFile(join(project, 'native/engine/common/localCfg.cmake'), 'utf8');
  ensure(/set\(USE_V8_DEBUGGER OFF/.test(nativeConfig) && /set\(USE_V8_DEBUGGER_FORCE OFF/.test(nativeConfig), 'Keep the native debugger disabled');
  return { configPath, config, configSha256: sha(configBytes), sources, recoveredAssets, metadata };
}

async function inspect(platform, creator) {
  const { configPath, config, configSha256, sources, recoveredAssets, metadata } = await inspectProjectInputs(PROJECT, platform);
  const blockers = [], environment = { host: process.platform, arch: process.arch, creator: null, xcode: null };
  if (process.platform !== 'darwin') blockers.push('Apple exports require a Mac; no Creator or Xcode process was launched on this host.');
  if (!creator) blockers.push('Provide --creator pointing to the installed Creator 3.8.8 app on the Mac.');
  else {
    const command = exportArguments(creator, configPath);
    environment.creator = { executable: command.executable, present: !!(await exists(command.executable))?.isFile() };
    if (!environment.creator.present) blockers.push('Creator executable is missing.');
    // A .app carries an inspectable version; an arbitrary binary path is rejected.
    if (extname(creator) !== '.app') blockers.push('Use the .app path so the Creator version can be checked.');
    else if (process.platform === 'darwin' && environment.creator.present) {
      const result = spawnSync('/usr/libexec/PlistBuddy', ['-c', 'Print :CFBundleShortVersionString', join(creator, 'Contents/Info.plist')], { encoding: 'utf8', timeout: 10000 });
      environment.creator.version = result.stdout?.trim() ?? null;
      if (result.status !== 0 || environment.creator.version !== '3.8.8') blockers.push('Creator app version is not verified as 3.8.8.');
    }
  }
  if (process.platform === 'darwin') {
    const result = spawnSync('/usr/bin/xcodebuild', ['-version'], { encoding: 'utf8', timeout: 10000 });
    environment.xcode = { exitCode: result.status, output: (result.stdout || result.stderr || '').trim() };
    if (result.status !== 0 || !/^Xcode /m.test(result.stdout ?? '')) blockers.push('Xcode is not available or has unfinished setup.');
  }
  return { configPath, config, report: { scope: 'Source/configuration and host preflight; not an Apple binary or runtime validation',
    platform, configSha256, sources, recoveredAssets, metadata, environment, blockers, canExport: blockers.length === 0,
    exported: false, compiled: false, signed: false, installed: false, runtimeVerified: false } };
}

async function main() {
  const { values } = parseArgs({ options: { platform: { type: 'string', default: 'mac' },
    action: { type: 'string', default: 'check' }, creator: { type: 'string' } } });
  ensure(['check', 'export'].includes(values.action), 'Supported actions: check, export');
  const { configPath, report } = await inspect(values.platform, values.creator);
  const directory = join(ROOT, 'analysis/apple-build', values.platform);
  await mkdir(directory, { recursive: true });
  const reportPath = join(directory, 'preflight.json');
  await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
  if (values.action === 'export') {
    ensure(report.canExport, report.blockers.join('\n'));
    const { executable, args } = exportArguments(values.creator, configPath);
    const output = await open(join(directory, 'export.stdout.log'), 'w');
    const errors = await open(join(directory, 'export.stderr.log'), 'w');
    let exitCode;
    try {
      exitCode = await new Promise((yes, no) => {
        const child = spawn(executable, args, { cwd: ROOT, shell: false, stdio: ['ignore', output.fd, errors.fd] });
        child.once('error', no); child.once('exit', yes);
      });
    } finally { await output.close(); await errors.close(); }
    report.exportExitCode = exitCode;
    report.exported = exitCode === 36 && !!(await exists(join(PROJECT, 'build', values.platform, 'data')))?.isDirectory();
    await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    ensure(report.exported, 'Creator export did not finish successfully; inspect logs.');
  }
  console.log(JSON.stringify({ ...report, sources: report.sources.map(item => item.path),
    recoveredAssets: report.recoveredAssets.map(item => item.path), metadata: report.metadata.map(item => item.path), reportPath }, null, 2));
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
