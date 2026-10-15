import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve, join, dirname, basename } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash, randomUUID } from 'node:crypto';
import test from 'node:test';
import { validateConfig, exportArguments, inspectProjectInputs } from '../tools/cocos-apple.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const requiredMetadata = [
  'assets/ToolchainProof.scene.meta', 'assets/ToolchainProof.ts.meta',
  'assets/TutorialBattleController.ts.meta', 'assets/TutorialBattleView.ts.meta',
  'assets/RecoveredCharacterView.ts.meta', 'assets/resources.meta', 'assets/resources/recovered.meta',
  'assets/resources/recovered/models.meta', 'assets/resources/recovered/models/elsa.meta',
  'assets/resources/recovered/models/elsa/elsa.glb.meta',
  'assets/resources/recovered/characters.meta', 'assets/resources/recovered/characters/1.png.meta',
];
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

async function projectFixture(t) {
  const directory = await mkdtemp(join(tmpdir(), 'hczs-apple-'));
  t.after(async () => {
    // Restrict recursive cleanup to this newly created direct child of tmpdir.
    assert.equal(dirname(resolve(directory)), resolve(tmpdir()));
    assert.ok(basename(directory).startsWith('hczs-apple-'));
    await rm(directory, { recursive: true, force: true });
  });
  const put = async (path, value) => {
    await mkdir(dirname(join(directory, path)), { recursive: true });
    await writeFile(join(directory, path), typeof value === 'object' ? JSON.stringify(value) : value);
  };
  const config = JSON.parse(await readFile(join(root, 'legacy/cocos-poc/build-mac.json'), 'utf8'));
  await put('build-mac.json', config);
  await put('package.json', { creator: { version: '3.8.8' } });
  for (const name of ['ToolchainProof', 'TutorialBattleController', 'TutorialBattleView', 'RecoveredCharacterView']) {
    await put(`assets/${name}.ts`, '// Synthetic migration fixture; never executed.');
  }
  await put('assets/ToolchainProof.scene', '[]');
  await put('settings/v2/packages/engine.json', '{}');
  await put('native/engine/common/localCfg.cmake', 'set(USE_V8_DEBUGGER OFF)\nset(USE_V8_DEBUGGER_FORCE OFF)\n');
  const files = [];
  for (const destination of ['assets/resources/recovered/models/elsa/elsa.glb', 'assets/resources/recovered/characters/1.png']) {
    const data = `synthetic asset bytes for ${destination}`;
    await put(destination, data);
    files.push({ destination, sha256: digest(data) });
  }
  await put('asset-provenance.json', { files });
  for (const path of requiredMetadata) {
    const importer = path.endsWith('.scene.meta') ? 'scene' : path.endsWith('.ts.meta') ? 'typescript' :
      path.endsWith('.glb.meta') ? 'gltf' : path.endsWith('.png.meta') ? 'image' : 'directory';
    await put(path, { uuid: importer === 'scene' ? config.startScene : randomUUID(), importer, userData: {} });
  }
  return { directory, put, config };
}
test('Apple configurations use the actual shared scene, Metal and synchronized generator templates', async () => {
  const meta = JSON.parse(await readFile(join(root, 'legacy/cocos-poc/assets/ToolchainProof.scene.meta'), 'utf8'));
  for (const platform of ['mac', 'ios']) {
    const bytes = await readFile(join(root, `legacy/cocos-poc/build-${platform}.json`));
    assert.deepEqual(bytes, await readFile(join(root, `tools/templates/cocos-build-${platform}.json`)));
    const config = validateConfig(JSON.parse(bytes), platform);
    assert.equal(config.startScene, meta.uuid);
    assert.equal(config.packages.native.runAfterMake, false);
  }
});

test('Creator arguments keep paths with spaces in single argv entries, without a shell', () => {
  const command = exportArguments('/Applications/Game Tools/CocosCreator.app', '/work/Black Tide/build-mac.json');
  assert.equal(command.executable, resolve('/Applications/Game Tools/CocosCreator.app/Contents/MacOS/CocosCreator'));
  assert.equal(command.args[3], 'configPath=/work/Black Tide/build-mac.json;stage=build');
  assert.throws(() => exportArguments('/Applications/CocosCreator.app', '/work/bad;stage=run'), /delimiters/);
});

test('Preflight fingerprints every scene/script/resource/ancestor meta and captures import-setting changes', async t => {
  const { directory, put } = await projectFixture(t);
  const before = await inspectProjectInputs(directory, 'mac');
  assert.deepEqual(before.metadata.map(item => item.path), [...requiredMetadata].sort());
  for (const item of before.metadata) assert.equal(item.sha256, digest(await readFile(join(directory, item.path))));
  const path = 'assets/resources/recovered/models/elsa/elsa.glb.meta';
  const meta = JSON.parse(await readFile(join(directory, path), 'utf8'));
  await put(path, { ...meta, userData: { changedImportSetting: true } });
  const after = await inspectProjectInputs(directory, 'mac');
  assert.deepEqual(after.sources, before.sources);
  assert.deepEqual(after.recoveredAssets, before.recoveredAssets);
  assert.notEqual(after.metadata.find(item => item.path === path).sha256, before.metadata.find(item => item.path === path).sha256);
  assert.deepEqual(after.metadata.filter(item => item.path !== path), before.metadata.filter(item => item.path !== path));
});

test('Missing scene, script, recovered asset or ancestor metadata fails before host/export checks', async t => {
  const { directory } = await projectFixture(t);
  for (const path of ['assets/ToolchainProof.scene.meta', 'assets/TutorialBattleController.ts.meta',
    'assets/resources/recovered/characters/1.png.meta', 'assets/resources/recovered/models/elsa.meta']) {
    const bytes = await readFile(join(directory, path));
    await rm(join(directory, path));
    await assert.rejects(inspectProjectInputs(directory, 'mac'), error => error.message === `Missing Creator metadata: ${path}`);
    await writeFile(join(directory, path), bytes);
  }
  assert.equal((await inspectProjectInputs(directory, 'mac')).metadata.length, requiredMetadata.length);
});

test('Actual scene meta UUID must match the selected build scene, not only a constant in the configuration', async t => {
  const { directory, put, config } = await projectFixture(t);
  const path = 'assets/ToolchainProof.scene.meta';
  await put(path, { uuid: randomUUID(), importer: 'scene' });
  await assert.rejects(inspectProjectInputs(directory, 'mac'), /Scene metadata UUID does not match/);
  await put(path, { uuid: config.startScene, importer: 'scene' });
  assert.equal((await inspectProjectInputs(directory, 'mac')).metadata.find(item => item.path === path).uuid, config.startScene);
});

test('An export request on Windows/Linux records the host blocker and cannot launch Creator', { skip: process.platform === 'darwin' }, async () => {
  const result = spawnSync(process.execPath, ['tools/cocos-apple.mjs', '--platform', 'ios', '--action', 'export'],
    { cwd: root, encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /require a Mac/);
  const report = JSON.parse(await readFile(join(root, 'analysis/apple-build/ios/preflight.json'), 'utf8'));
  assert.equal(report.environment.host, process.platform);
  assert.equal(report.environment.creator, null);
  assert.equal(report.environment.xcode, null);
  assert.equal(report.canExport, false);
  assert.equal(report.exported, false);
  assert.equal(report.compiled, false);
  assert.equal(report.signed, false);
  assert.equal(report.runtimeVerified, false);
});
