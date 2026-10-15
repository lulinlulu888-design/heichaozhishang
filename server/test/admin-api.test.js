import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { request as httpRequest } from 'node:http';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from '../src/app.js';
import { fixture, request as gameRequest } from './helpers.js';
import { heroFixture } from './helpers/hero-fixture.js';

async function adminRequest(address, path, method = 'GET', body, headers = {}) {
  const response = await fetch(`${address}/api/admin/v1${path}`, { method,
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
    body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: response.status, headers: response.headers,
    body: response.status === 204 ? null : await response.json() };
}

async function appFixture(t, options = {}) {
  const files = await fixture(t);
  const app = await createApp({ ...files, port: 0, log: value => assert.fail(JSON.stringify(value)), ...options });
  files.cleanupWith(() => app.close());
  return app;
}

test('admin and game namespaces share profiles while admin only permits naming changes', async t => {
  const app = await appFixture(t);
  const created = await adminRequest(app.address, '/profiles', 'POST', { displayName: '管理测试' });
  assert.equal(created.status, 201);
  const profile = created.body.profile;
  assert.deepEqual((await gameRequest(app.address, `/profiles/${profile.id}`)).body.profile, profile);
  assert.deepEqual((await adminRequest(app.address, `/profiles/${profile.id}`)).body,
    { profile, hall: null, battles: [] });
  const before = (await adminRequest(app.address, '/profiles')).body;
  for (const change of [
    { expectedRevision: 1, selectedCharacterId: 1 },
    { expectedRevision: 1, displayName: 'Injected', selectedCharacterId: 1 },
    { expectedRevision: 1, displayName: 'Injected', unlockedHeroIds: [1] },
    { displayName: 'No revision' },
  ]) {
    const response = await adminRequest(app.address, `/profiles/${profile.id}`, 'PATCH', change);
    assert.equal(response.status, 400);
    assert.equal(response.body.error.code, 'INVALID_INPUT');
  }
  assert.deepEqual((await adminRequest(app.address, '/profiles')).body, before);
  assert.equal((await adminRequest(app.address, '/profiles', 'POST',
    { displayName: 'Invalid', selectedCharacterId: 1 })).status, 400);
  const renamed = await adminRequest(app.address, `/profiles/${profile.id}`, 'PATCH',
    { expectedRevision: 1, displayName: '已改名' });
  assert.equal(renamed.status, 200);
  assert.equal(renamed.body.profile.revision, 2);
  assert.equal(renamed.body.profile.selectedCharacterId, null);
  const conflict = await adminRequest(app.address, `/profiles/${profile.id}`, 'PATCH',
    { expectedRevision: 1, displayName: '过期' });
  assert.equal(conflict.status, 409);
  assert.equal(conflict.body.error.code, 'REVISION_CONFLICT');
  assert.deepEqual((await gameRequest(app.address, `/profiles/${profile.id}`)).body.profile, renamed.body.profile);
  const overview = (await adminRequest(app.address, '/overview')).body;
  assert.deepEqual(overview.counts, { profiles: 1, battles: 0, heroes: 0, hallVerified: 0 });
  assert.equal(overview.service.storage, 'sqlite-legacy');
  assert.equal(overview.service.gameplayReady, false);
  assert.deepEqual(overview.policy,
    { access: 'personal-loopback', authentication: 'none', legacyProtocolCompatible: false });
  assert.ok(Number.isSafeInteger(overview.generatedAt));
  assert.equal(Object.hasOwn(overview.counts, 'online'), false);
});

test('admin prefix rejects destructive routes, unavailable features and malformed requests', async t => {
  const app = await appFixture(t);
  const profile = (await adminRequest(app.address, '/profiles', 'POST', { displayName: 'Keep' })).body.profile;
  for (const [path, method] of [
    ['/profiles', 'DELETE'], [`/profiles/${profile.id}`, 'DELETE'], ['/reset', 'POST'],
    [`/profiles/${profile.id}/battles`, 'POST'], ['/profiles/not-a-uuid', 'GET'],
    ['/overview/', 'GET'], ['/status', 'GET'],
  ]) {
    const result = await adminRequest(app.address, path, method);
    assert.equal(result.status, 404, `${method} ${path}`);
    assert.equal(result.body.error.code, 'NOT_FOUND');
  }
  assert.equal((await adminRequest(app.address, '/heroes')).body.error.code, 'HERO_DIRECTORY_UNAVAILABLE');
  assert.equal((await adminRequest(app.address, '/encounters')).body.error.code, 'ENCOUNTER_UNAVAILABLE');
  assert.equal((await adminRequest(app.address, `/profiles/${profile.id}/hall`, 'PATCH',
    { requestId: 'select', expectedRevision: 0, selectedHeroId: 1 })).body.error.code, 'HALL_UNAVAILABLE');
  assert.equal((await adminRequest(app.address, `/profiles/${profile.id}/battles/${randomUUID()}`)).body.error.code,
    'BATTLE_UNAVAILABLE');
  assert.equal((await adminRequest(app.address, `/profiles/${randomUUID()}`)).body.error.code, 'PROFILE_NOT_FOUND');
  assert.equal((await adminRequest(app.address, '/overview?sample=1')).body.error.code, 'INVALID_INPUT');
  const malformed = await fetch(app.address + '/api/admin/v1/profiles',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{' });
  assert.equal(malformed.status, 400);
  assert.equal((await malformed.json()).error.code, 'INVALID_JSON');
  assert.deepEqual((await adminRequest(app.address, '/profiles')).body.profiles, [profile]);
  assert.equal((await fetch(app.address + '/api/admin/v10/overview')).status, 404);
});

test('admin shares Host and Origin checks and preserves an explicit Origin allowlist', async t => {
  const app = await appFixture(t);
  for (const origin of ['http://127.0.0.1:7470', 'http://localhost:7470',
    'http://127.0.0.1:7471', 'http://localhost:7471']) {
    const response = await adminRequest(app.address, '/overview', 'GET', undefined, { Origin: origin });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('access-control-allow-origin'), origin);
  }
  assert.equal((await adminRequest(app.address, '/overview', 'GET', undefined,
    { Origin: 'http://remote.invalid' })).body.error.code, 'ORIGIN_NOT_ALLOWED');
  const host = await new Promise((resolve, reject) => {
    httpRequest(app.address + '/api/admin/v1/overview', { headers: { Host: 'remote.invalid' } }, response => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', value => { body += value; });
      response.on('end', () => resolve({ status: response.statusCode, body: JSON.parse(body) }));
      response.on('error', reject);
    }).on('error', reject).end();
  });
  assert.equal(host.status, 403);
  assert.equal(host.body.error.code, 'HOST_NOT_ALLOWED');
  assert.equal((await adminRequest(app.address, '/profiles', 'OPTIONS', undefined,
    { Origin: 'http://127.0.0.1:7470' })).status, 204);
  const custom = await appFixture(t, { allowedOrigins: ['http://127.0.0.1:9999'] });
  assert.equal((await adminRequest(custom.address, '/overview', 'GET', undefined,
    { Origin: 'http://127.0.0.1:7470' })).status, 403);
  assert.equal((await adminRequest(custom.address, '/overview', 'GET', undefined,
    { Origin: 'http://127.0.0.1:9999' })).status, 200);
});

// Real restart verification uses only an explicitly configured replica set and a fresh test DB.
const mongoUri = process.env.HCZS_TEST_MONGODB_URI;
async function processServer(options) {
  const script = `import {createApp} from ${JSON.stringify(new URL('../src/app.js', import.meta.url).href)};
    try { const app = await createApp(JSON.parse(process.env.HCZS_ADMIN_TEST_OPTIONS));
      process.on('message', async message => { if (message === 'close') { await app.close(); process.disconnect(); } });
      process.send({address:app.address});
    } catch(error) { process.send({error:error.message}); process.disconnect(); process.exitCode=1; }`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', script], {
    windowsHide: true, stdio: ['ignore', 'ignore', 'pipe', 'ipc'],
    env: { ...process.env, HCZS_ADMIN_TEST_OPTIONS: JSON.stringify(options) },
  });
  let stderr = '';
  child.stderr.on('data', value => { stderr = (stderr + value).slice(-3000); });
  const exited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
  let first;
  try {
    first = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Admin test child startup timed out')), 20000);
      child.once('message', value => { clearTimeout(timer); resolve(value); });
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', code => { clearTimeout(timer); reject(Error(`Admin child exited ${code}: ${stderr}`)); });
    });
    if (first.error) throw Error(first.error);
  } catch (error) { child.kill(); await exited; throw error; }
  let stopped = false;
  return { address: first.address, async close() {
    if (stopped) return;
    stopped = true;
    child.send('close');
    const timer = setTimeout(() => child.kill(), 5000);
    try { assert.equal((await exited).code, 0, stderr); } finally { clearTimeout(timer); }
  } };
}

test('admin Mongo profile/hall CAS writes survive process restart and battle reads remain scoped',
  { skip: !mongoUri && 'Set HCZS_TEST_MONGODB_URI to an independent test replica set' }, async t => {
    const files = await fixture(t);
    const mongoDatabase = `hczs_test_admin_${randomUUID().replaceAll('-', '')}`;
    const { default: mongoose } = await import('mongoose');
    const connection = await mongoose.createConnection(mongoUri,
      { dbName: mongoDatabase, serverSelectionTimeoutMS: 5000 }).asPromise();
    const children = [];
    files.cleanupWith(async () => {
      try { for (const child of children) await child.close(); }
      finally {
        try {
          assert.match(mongoDatabase, /^hczs_test_admin_[0-9a-f]{32}$/);
          assert.equal(connection.name, mongoDatabase);
          await connection.dropDatabase();
        } finally { await connection.close(); }
      }
    });
    await writeFile(join(files.dataDirectory, 'heroes.json'), JSON.stringify(heroFixture()));
    const options = { dataDirectory: files.dataDirectory, port: 0, storage: 'mongodb', mongoUri, mongoDatabase,
      tutorialDirectory: fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url)) };
    async function start() { const child = await processServer(options); children.push(child); return child; }
    const first = await start();
    const profile = (await adminRequest(first.address, '/profiles', 'POST', { displayName: '独立Mongo后台测试' })).body.profile;
    const renamed = await adminRequest(first.address, `/profiles/${profile.id}`, 'PATCH',
      { expectedRevision: 1, displayName: '改名保存' });
    assert.equal(renamed.status, 200);
    assert.equal((await gameRequest(first.address, `/profiles/${profile.id}`, 'PATCH',
      { expectedRevision: 1, displayName: '旧值' })).status, 409);
    const select = { requestId: 'admin-select', expectedRevision: 0, selectedHeroId: 1 };
    const hall = await adminRequest(first.address, `/profiles/${profile.id}/hall`, 'PATCH', select);
    assert.equal(hall.status, 200);
    assert.equal(hall.body.replayed, false);
    const replay = await gameRequest(first.address, `/profiles/${profile.id}/hall`, 'PATCH', select);
    assert.equal(replay.body.replayed, true);
    assert.deepEqual(replay.body.hall, hall.body.hall);
    const stale = await adminRequest(first.address, `/profiles/${profile.id}/hall`, 'PATCH',
      { ...select, requestId: 'stale' });
    assert.equal(stale.status, 409);
    assert.equal(stale.body.error.code, 'REVISION_CONFLICT');
    const invalid = await adminRequest(first.address, `/profiles/${profile.id}/hall`, 'PATCH',
      { requestId: 'unavailable', expectedRevision: 1, selectedHeroId: 2 });
    assert.equal(invalid.status, 400);
    assert.equal(invalid.body.error.code, 'HALL_HERO_UNAVAILABLE');
    assert.equal((await adminRequest(first.address, `/profiles/${profile.id}/hall`, 'PATCH',
      { ...select, requestId: 'inject', expectedRevision: 1, unlocked: true })).status, 400);
    const created = await gameRequest(first.address, `/profiles/${profile.id}/battles`, 'POST',
      { requestId: 'admin-read-test', seed: 12345 });
    assert.equal(created.status, 201);
    const battle = created.body.battle;
    const other = (await adminRequest(first.address, '/profiles', 'POST', { displayName: '另一档案' })).body.profile;
    const foreign = await adminRequest(first.address, `/profiles/${other.id}/battles/${battle.id}`);
    assert.equal(foreign.status, 404);
    assert.equal(foreign.body.error.code, 'BATTLE_NOT_FOUND');
    const detail = (await adminRequest(first.address, `/profiles/${profile.id}`)).body;
    assert.deepEqual(detail.profile, renamed.body.profile);
    assert.deepEqual(detail.hall, hall.body.hall);
    assert.equal(detail.battles.length, 1);
    assert.equal(detail.battles[0].id, battle.id);
    const overview = (await adminRequest(first.address, '/overview')).body;
    assert.deepEqual(overview.counts, { profiles: 2, battles: 1, heroes: 35, hallVerified: 2 });
    assert.equal(overview.service.storage, 'mongodb');
    assert.deepEqual((await adminRequest(first.address, '/heroes')).body,
      (await gameRequest(first.address, '/heroes')).body);
    assert.deepEqual((await adminRequest(first.address, '/encounters')).body,
      (await gameRequest(first.address, '/encounters')).body);
    await first.close();
    const restarted = await start();
    assert.deepEqual((await adminRequest(restarted.address, `/profiles/${profile.id}`)).body, detail);
    assert.deepEqual((await adminRequest(restarted.address,
      `/profiles/${profile.id}/battles/${battle.id}`)).body.battle, battle);
    assert.deepEqual((await adminRequest(restarted.address, `/profiles/${profile.id}/hall`, 'PATCH', select)).body,
      { hall: hall.body.hall, replayed: true });
  });

test('legacy SQLite exposes read-only defaults without pretending to persist configuration or logs', async t => {
  const app = await appFixture(t);
  const config = (await adminRequest(app.address, '/config')).body;
  assert.equal(config.supported, false);
  assert.equal(config.active.version, 0);
  assert.equal(config.active.settings.allowNewProfiles, true);
  assert.equal(config.active.settings.defaultEncounterId, null);
  const status = (await gameRequest(app.address, '/status')).body;
  assert.equal(status.operational.supported, false);
  assert.equal(status.gameplayReady, false);
  for (const [path, method, input] of [
    ['/config/draft', 'PATCH', { expectedRevision: 0, settings: config.active.settings }],
    ['/config/publish', 'POST', { expectedRevision: 0, requestId: 'unsupported' }],
    ['/config/rollback', 'POST', { expectedRevision: 0, version: 0, requestId: 'unsupported' }],
    ['/logs', 'GET', undefined],
  ]) {
    const response = await adminRequest(app.address, path, method, input);
    assert.equal(response.status, 501);
    assert.equal(response.body.error.code, 'OPERATIONAL_STORAGE_UNSUPPORTED');
  }
  assert.deepEqual((await adminRequest(app.address, '/cards')).body, (await gameRequest(app.address, '/catalog')).body);
  assert.deepEqual((await adminRequest(app.address, '/config')).body, config);
});

async function operationsFixture(t, { child = true } = {}) {
  const files = await fixture(t);
  const mongoDatabase = `hczs_test_admin_${randomUUID().replaceAll('-', '')}`;
  const { default: mongoose } = await import('mongoose');
  const connection = await mongoose.createConnection(mongoUri,
    { dbName: mongoDatabase, serverSelectionTimeoutMS: 5000 }).asPromise();
  const servers = [];
  files.cleanupWith(async () => {
    try { for (const server of servers) await server.close(); }
    finally {
      try {
        assert.match(mongoDatabase, /^hczs_test_admin_[0-9a-f]{32}$/);
        assert.equal(connection.name, mongoDatabase);
        await connection.dropDatabase();
      } finally { await connection.close(); }
    }
  });
  await writeFile(join(files.dataDirectory, 'heroes.json'), JSON.stringify(heroFixture()));
  const options = { dataDirectory: files.dataDirectory, port: 0, storage: 'mongodb', mongoUri, mongoDatabase,
    cityPreview: true, tutorialDirectory: fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url)) };
  async function start() {
    const server = child ? await processServer(options) : await createApp({ ...options, log: () => {} });
    servers.push(server);
    return server;
  }
  return { connection, start, first: await start() };
}
const mongoEnabled = { skip: !mongoUri && 'Set HCZS_TEST_MONGODB_URI to an independent test replica set' };

test('Mongo configuration drafts, immutable publish/rollback, CAS and policy take effect across processes', mongoEnabled, async t => {
  const { first, connection, start } = await operationsFixture(t);
  const second = await start();
  const initial = (await adminRequest(first.address, '/config')).body;
  assert.equal(initial.supported, true);
  assert.equal(initial.draft.revision, 1);
  assert.equal(initial.active.version, 0);
  assert.equal(initial.active.kind, 'initial');
  assert.equal(initial.active.settings.defaultEncounterId, 'city-preview-10405');
  assert.deepEqual(initial.draft.settings, initial.active.settings);
  assert.deepEqual((await adminRequest(first.address, '/logs')).body, { supported: true, logs: [] });
  const profile = (await adminRequest(first.address, '/profiles', 'POST', { displayName: '运营隔离测试' })).body.profile;
  const createInput = { requestId: 'before-pause', seed: 34567 };
  const beforePause = await gameRequest(first.address, `/profiles/${profile.id}/battles`, 'POST', createInput);
  assert.equal(beforePause.status, 201);
  assert.equal(beforePause.body.battle.scenario.definition.id.includes('city'), true);
  const paused = { ...initial.draft.settings, motd: '维护公告\n仅暂停新建', allowNewProfiles: false,
    allowNewBattles: false, defaultEncounterId: 'tutorial-5000' };
  const draft = await adminRequest(first.address, '/config/draft', 'PATCH', { expectedRevision: 1, settings: paused });
  assert.equal(draft.status, 200);
  assert.equal(draft.body.draft.revision, 2);
  assert.deepEqual(draft.body.active, initial.active, 'Draft changes must not activate policy');
  assert.equal((await gameRequest(second.address, '/profiles', 'POST', { displayName: '草稿不生效' })).status, 201);
  const publishInput = { expectedRevision: 2, requestId: 'publish-paused' };
  const same = await Promise.all([first, second].map(server => adminRequest(server.address, '/config/publish', 'POST', publishInput)));
  assert.deepEqual(same.map(result => result.status), [200, 200]);
  assert.deepEqual(same.map(result => result.body.replayed).sort(), [false, true]);
  assert.deepEqual(same[0].body.config, same[1].body.config);
  const published = same[0].body.config;
  assert.equal(published.active.version, 1);
  assert.equal(published.draft.revision, 3);
  assert.deepEqual(published.active.settings, paused);
  const status = (await gameRequest(second.address, '/status')).body;
  assert.deepEqual(status.operational.settings, paused);
  assert.equal(status.operational.version, 1);
  assert.equal(status.gameplayReady, false);
  for (const server of [first, second]) {
    const rejected = await gameRequest(server.address, '/profiles', 'POST', { displayName: '暂停后' });
    assert.equal(rejected.status, 403);
    assert.equal(rejected.body.error.code, 'PROFILE_CREATION_DISABLED');
  }
  assert.equal((await adminRequest(first.address, '/profiles', 'POST', { displayName: '管理员也遵守开关' })).status, 403);
  const disabledBattle = await gameRequest(second.address, `/profiles/${profile.id}/battles`, 'POST',
    { requestId: 'new-disabled', seed: 34567 });
  assert.equal(disabledBattle.status, 403);
  assert.equal(disabledBattle.body.error.code, 'BATTLE_CREATION_DISABLED');
  const replay = await gameRequest(second.address, `/profiles/${profile.id}/battles`, 'POST', createInput);
  assert.equal(replay.status, 201);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.battle, beforePause.body.battle);
  const action = await gameRequest(second.address, `/profiles/${profile.id}/battles/${beforePause.body.battle.id}/actions`, 'POST',
    { requestId: 'during-maintenance', expectedRevision: 1, type: 'end-turn' });
  assert.equal(action.status, 200);
  assert.equal(action.body.battle.revision, 2);
  const renamed = await adminRequest(first.address, `/profiles/${profile.id}`, 'PATCH',
    { expectedRevision: 1, displayName: '维护仍可改名' });
  assert.equal(renamed.status, 200);
  const rollbackInput = { expectedRevision: 3, version: 0, requestId: 'rollback-defaults' };
  const rollback = await adminRequest(first.address, '/config/rollback', 'POST', rollbackInput);
  assert.equal(rollback.status, 200);
  assert.equal(rollback.body.config.active.version, 2);
  assert.equal(rollback.body.config.active.sourceVersion, 0);
  assert.equal(rollback.body.config.active.kind, 'rollback');
  assert.equal(rollback.body.config.draft.revision, 4);
  assert.deepEqual(rollback.body.config.active.settings, initial.active.settings);
  assert.deepEqual(rollback.body.config.releases.find(release => release.version === 1), published.active);
  const resumed = { ...initial.active.settings, motd: '服务已恢复', defaultEncounterId: 'tutorial-5000' };
  const raced = await Promise.all([first, second].map(server => adminRequest(server.address, '/config/draft', 'PATCH',
    { expectedRevision: 4, settings: resumed })));
  assert.deepEqual(raced.map(result => result.status).sort(), [200, 409]);
  const latest = await adminRequest(second.address, '/config/publish', 'POST',
    { expectedRevision: 5, requestId: 'publish-tutorial' });
  assert.equal(latest.status, 200);
  assert.equal(latest.body.config.active.version, 3);
  const newDefault = await gameRequest(first.address, `/profiles/${profile.id}/battles`, 'POST',
    { requestId: 'new-default', seed: 34568 });
  assert.equal(newDefault.status, 201);
  assert.equal(newDefault.body.battle.scenario.encounterId, 'tutorial-5000');
  assert.equal((await gameRequest(first.address, `/profiles/${profile.id}/battles/${beforePause.body.battle.id}`)).body.battle.scenario.definition.id.includes('city'), true);
  const explicit = await gameRequest(first.address, `/profiles/${profile.id}/battles`, 'POST',
    { requestId: 'explicit-city', seed: 34569, encounterId: 'city-preview-10405' });
  assert.equal(explicit.status, 201);
  assert.equal(explicit.body.battle.scenario.encounterId, 'city-preview-10405');
  assert.equal((await adminRequest(first.address, '/config/rollback', 'POST',
    { expectedRevision: 6, version: 999, requestId: 'missing-version' })).body.error.code, 'CONFIG_VERSION_NOT_FOUND');
  assert.equal((await adminRequest(first.address, '/config/draft', 'PATCH',
    { expectedRevision: 6, settings: { ...resumed, defaultEncounterId: 'missing' } })).body.error.code, 'ENCOUNTER_UNAVAILABLE');
  assert.equal((await adminRequest(first.address, '/config/draft', 'PATCH',
    { expectedRevision: 6, settings: { ...resumed, currency: 999 } })).body.error.code, 'INVALID_INPUT');
  assert.equal((await adminRequest(first.address, '/config/publish', 'POST',
    { expectedRevision: 6, requestId: 'publish-paused' })).body.error.code, 'REQUEST_ID_CONFLICT');
  const logs = (await adminRequest(first.address, '/logs')).body.logs;
  assert.equal(logs.filter(log => log.action === 'config.publish').length, 2);
  assert.equal(logs.filter(log => log.action === 'config.rollback').length, 1);
  assert.ok(logs.every(log => log.actor === 'local-admin' && Number.isSafeInteger(log.occurredAt)));
  assert.equal(await connection.db.collection('hczs_admin_releases').countDocuments(), 4);
  assert.deepEqual((await adminRequest(first.address, '/config/publish', 'POST', publishInput)).body,
    { config: published, replayed: true });
  assert.deepEqual((await adminRequest(first.address, '/config')).body, latest.body.config);
  assert.deepEqual((await adminRequest(first.address, '/logs')).body.logs, logs);
  await first.close(); await second.close();
  const restarted = await start();
  assert.deepEqual((await adminRequest(restarted.address, '/config')).body, latest.body.config);
  assert.deepEqual((await adminRequest(restarted.address, '/logs')).body.logs, logs);
  assert.deepEqual((await adminRequest(restarted.address, `/profiles/${profile.id}`)).body.profile, renamed.body.profile);
});

test('Mongo audit failures roll back admin profile, hall, draft, publish and rollback writes', mongoEnabled, async t => {
  const { first, connection } = await operationsFixture(t, { child: false });
  const profile = (await adminRequest(first.address, '/profiles', 'POST', { displayName: '审计原子性测试' })).body.profile;
  const original = (await adminRequest(first.address, '/config')).body;
  const logsBefore = (await adminRequest(first.address, '/logs')).body.logs;
  async function rejectAudit() {
    await connection.db.command({ collMod: 'hczs_admin_logs', validator: { action: { $eq: 'forbidden-in-test' } }, validationLevel: 'strict' });
  }
  async function allowAudit() { await connection.db.command({ collMod: 'hczs_admin_logs', validator: {} }); }
  await rejectAudit();
  const mutations = [
    ['/profiles', 'POST', { displayName: '不能留下未审计档案' }],
    [`/profiles/${profile.id}`, 'PATCH', { expectedRevision: 1, displayName: '不能留下改名' }],
    [`/profiles/${profile.id}/hall`, 'PATCH', { requestId: 'no-audit-hall', expectedRevision: 0, selectedHeroId: 1 }],
    ['/config/draft', 'PATCH', { expectedRevision: 1, settings: { ...original.draft.settings, motd: '不能留下草稿' } }],
    ['/config/publish', 'POST', { expectedRevision: 1, requestId: 'no-audit-publish' }],
  ];
  for (const [path, method, input] of mutations) {
    const response = await adminRequest(first.address, path, method, input);
    assert.equal(response.status, 500, path);
    assert.equal(response.body.error.code, 'INTERNAL_ERROR');
  }
  assert.deepEqual((await adminRequest(first.address, '/profiles')).body.profiles, [profile]);
  assert.deepEqual((await adminRequest(first.address, `/profiles/${profile.id}`)).body.hall,
    { profileId: profile.id, revision: 0, selectedHeroId: null, updatedAt: null });
  assert.deepEqual((await adminRequest(first.address, '/config')).body, original);
  assert.deepEqual((await adminRequest(first.address, '/logs')).body.logs, logsBefore);
  assert.equal(await connection.db.collection('hall_requests').countDocuments(), 0);
  assert.equal(await connection.db.collection('hczs_admin_requests').countDocuments(), 0);
  assert.equal(await connection.db.collection('hczs_admin_releases').countDocuments(), 1);
  await allowAudit();
  const published = await adminRequest(first.address, '/config/publish', 'POST',
    { expectedRevision: 1, requestId: 'publish-with-audit' });
  assert.equal(published.status, 200);
  await rejectAudit();
  const rollbackInput = { expectedRevision: 2, version: 0, requestId: 'rollback-with-audit' };
  assert.equal((await adminRequest(first.address, '/config/rollback', 'POST', rollbackInput)).status, 500);
  assert.deepEqual((await adminRequest(first.address, '/config')).body, published.body.config);
  assert.equal(await connection.db.collection('hczs_admin_releases').countDocuments(), 2);
  assert.equal(await connection.db.collection('hczs_admin_requests').countDocuments(), 1);
  await allowAudit();
  const rollback = await adminRequest(first.address, '/config/rollback', 'POST', rollbackInput);
  assert.equal(rollback.status, 200);
  assert.equal(rollback.body.config.active.version, 2);
  assert.equal((await adminRequest(first.address, '/logs')).body.logs.length, 3);
});
