import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { fixture, request } from './helpers.js';
import { heroFixture } from './helpers/hero-fixture.js';

// Every instance is a separate Node process with ephemeral ports and temporary saves.
// IPC shutdown waits for close() before the fixture can remove its directory.
async function start(files) {
  const script = `import {createApp} from ${JSON.stringify(new URL('../src/app.js', import.meta.url).href)};
    const app = await createApp(JSON.parse(process.env.HCZS_HALL_TEST_OPTIONS));
    process.on('message', async message => {
      if (message === 'close') { await app.close(); process.disconnect(); }
    });
    process.send({event:'ready',address:app.address});`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', script], {
    windowsHide: true, stdio: ['ignore', 'ignore', 'pipe', 'ipc'],
    env: { ...process.env, HCZS_HALL_TEST_OPTIONS: JSON.stringify({
      storage: 'sqlite', port: 0, dataDirectory: files.dataDirectory, savePath: files.savePath,
    }) },
  });
  let errors = '';
  child.stderr.on('data', value => { errors = (errors + value).slice(-4000); });
  const ended = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
  const address = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { child.kill(); reject(Error('Hall test server startup timed out')); }, 10_000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', code => { clearTimeout(timer); reject(Error(`Hall test server exit ${code}: ${errors}`)); });
    child.on('message', message => { if (message?.event === 'ready') { clearTimeout(timer); resolve(message.address); } });
  });
  let stopping;
  return { address, stop() {
    if (!stopping) stopping = (async () => {
      if (child.exitCode !== null || child.signalCode !== null) return;
      child.send('close');
      const timer = setTimeout(() => child.kill(), 5000);
      try {
        const result = await ended;
        assert.equal(result.code, 0, `Unclean child shutdown: ${JSON.stringify(result)} ${errors}`);
      } finally { clearTimeout(timer); }
    })();
    return stopping;
  } };
}

async function hallFixture(t, withHeroes = true) {
  const files = await fixture(t);
  if (withHeroes) await writeFile(join(files.dataDirectory, 'heroes.json'), JSON.stringify(heroFixture()));
  let server = await start(files);
  files.cleanupWith(async () => { if (server) await server.stop(); });
  return { ...files, get address() { return server.address; }, async restart() {
    await server.stop(); server = null; server = await start(files);
  } };
}

async function createProfile(app, name) {
  const result = await request(app.address, '/profiles', 'POST', { displayName: name });
  assert.equal(result.status, 201);
  return result.body.profile;
}

function hallRows(app) {
  const db = new DatabaseSync(`${app.savePath}.hall`, { readOnly: true });
  try {
    return {
      states: db.prepare('SELECT * FROM hall_states ORDER BY profile_id').all(),
      receipts: db.prepare('SELECT * FROM hall_requests ORDER BY profile_id, request_id').all(),
    };
  } finally { db.close(); }
}

test('bootstrap advertises actual optional hero content and independent hall state', async t => {
  const app = await hallFixture(t);
  const profile = await createProfile(app, '大厅档案');
  const bootstrap = await request(app.address, '/bootstrap');
  const catalog = await request(app.address, '/catalog');
  const heroes = await request(app.address, '/heroes');
  assert.equal(bootstrap.status, 200);
  assert.equal(heroes.status, 200);
  assert.equal(bootstrap.body.service, 'hczs-rebuild');
  assert.equal(bootstrap.body.apiVersion, 1);
  assert.equal(bootstrap.body.gameplayReady, false);
  assert.ok(bootstrap.body.capabilities.includes('recovered-heroes'));
  assert.ok(bootstrap.body.capabilities.includes('hall-selection'));
  assert.equal(bootstrap.body.content.catalogId, catalog.body.contentId);
  assert.equal(bootstrap.body.content.heroesId, heroes.body.contentId);
  assert.deepEqual(bootstrap.body.profiles, [profile]);
  assert.equal(heroes.body.heroes.length, 35);
  assert.deepEqual(heroes.body.heroes.filter(hero => hero.availability.hallPreview === 'verified').map(hero => hero.id), [1, 3, 33]);
  assert.deepEqual((await request(app.address, `/profiles/${profile.id}/hall`)).body.hall,
    { profileId: profile.id, revision: 0, selectedHeroId: null, updatedAt: null });
});

test('Future hall preference persists across a Node restart without granting battle eligibility', async t => {
  const app = await hallFixture(t);
  const profile = await createProfile(app, '未来大厅恢复');
  const path = `/profiles/${profile.id}/hall`;
  const command = {requestId:'choose-future',expectedRevision:0,selectedHeroId:3};
  const saved = await request(app.address,path,'PATCH',command);
  assert.equal(saved.status,200);
  assert.equal(saved.body.hall.selectedHeroId,3);
  await app.restart();
  assert.deepEqual((await request(app.address,path)).body.hall,saved.body.hall);
  assert.equal((await request(app.address,path,'PATCH',command)).body.replayed,true);
  const heroes = (await request(app.address,'/heroes')).body.heroes;
  assert.equal(heroes.find(hero=>hero.id===3).availability.fullBattle,'not-verified');
  assert.equal((await request(app.address,path,'PATCH',{requestId:'stale-future',expectedRevision:0,selectedHeroId:1})).status,409);
});

test('hall HTTP commits and retry receipts survive a new Node process without changing the old selection', async t => {
  const app = await hallFixture(t);
  const profile = await createProfile(app, '进程恢复');
  const oldChoice = await request(app.address, `/profiles/${profile.id}`, 'PATCH', { expectedRevision: 1, selectedCharacterId: 2 });
  assert.equal(oldChoice.status, 200);
  const path = `/profiles/${profile.id}/hall`;
  const command = { requestId: 'choose-initial-elsa', expectedRevision: 0, selectedHeroId: 1 };
  const saved = await request(app.address, path, 'PATCH', command);
  assert.equal(saved.status, 200, JSON.stringify(saved.body));
  assert.equal(saved.body.replayed, false);
  assert.equal(saved.body.hall.revision, 1);
  assert.equal(saved.body.hall.selectedHeroId, 1);
  assert.ok(Number.isSafeInteger(saved.body.hall.updatedAt));
  const replay = await request(app.address, path, 'PATCH', command);
  assert.equal(replay.status, 200);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.hall, saved.body.hall);
  await app.restart();
  assert.deepEqual((await request(app.address, path)).body.hall, saved.body.hall);
  const restoredReceipt = await request(app.address, path, 'PATCH', command);
  assert.equal(restoredReceipt.status, 200);
  assert.equal(restoredReceipt.body.replayed, true);
  assert.deepEqual(restoredReceipt.body.hall, saved.body.hall);
  assert.deepEqual((await request(app.address, `/profiles/${profile.id}`)).body.profile, oldChoice.body.profile);
  for (const invalid of [
    { requestId: 'stale-revision', expectedRevision: 0, selectedHeroId: null },
    { requestId: command.requestId, expectedRevision: 0, selectedHeroId: null },
  ]) assert.equal((await request(app.address, path, 'PATCH', invalid)).status, 409);
  assert.deepEqual((await request(app.address, path)).body.hall, saved.body.hall);
  const cleared = await request(app.address, path, 'PATCH', { requestId: 'clear-hall', expectedRevision: 1, selectedHeroId: null });
  assert.equal(cleared.status, 200);
  assert.equal(cleared.body.hall.selectedHeroId, null);
  assert.equal(cleared.body.hall.revision, 2);
  // A late retry returns its historical receipt, but must not roll current state backwards.
  assert.deepEqual((await request(app.address, path, 'PATCH', command)).body.hall, saved.body.hall);
  assert.deepEqual((await request(app.address, path)).body.hall, cleared.body.hall);
});

test('invalid hall HTTP commands and missing profiles do not mutate either profile', async t => {
  const app = await hallFixture(t);
  const first = await createProfile(app, '第一档'), second = await createProfile(app, '第二档');
  const path = `/profiles/${first.id}/hall`;
  const before = (await request(app.address, path)).body;
  const rowsBefore = hallRows(app);
  assert.deepEqual(rowsBefore, { states: [], receipts: [] });
  const commands = [
    {}, { requestId: '', expectedRevision: 0, selectedHeroId: 33 },
    { requestId: 'unsupported', expectedRevision: 0, selectedHeroId: 2 },
    { requestId: 'unknown', expectedRevision: 0, selectedHeroId: 9999 },
    { requestId: 'string', expectedRevision: 0, selectedHeroId: '33' },
    { requestId: 'negative', expectedRevision: -1, selectedHeroId: 33 },
    { requestId: 'extra', expectedRevision: 0, selectedHeroId: 33, profileId: second.id },
  ];
  for (const body of commands) {
    const result = await request(app.address, path, 'PATCH', body);
    assert.ok(result.status >= 400 && result.status < 500, JSON.stringify(result));
  }
  const missing = '/profiles/00000000-0000-0000-0000-000000000000/hall';
  assert.equal((await request(app.address, missing)).status, 404);
  assert.equal((await request(app.address, missing, 'PATCH', { requestId: 'missing', expectedRevision: 0, selectedHeroId: 33 })).status, 404);
  assert.deepEqual((await request(app.address, path)).body, before);
  assert.deepEqual(hallRows(app), rowsBefore, 'Rejected requests and GET must not create state or retry receipts');
  assert.deepEqual((await request(app.address, `/profiles/${first.id}`)).body.profile, first);
  assert.deepEqual((await request(app.address, `/profiles/${second.id}`)).body.profile, second);
  const accepted = await request(app.address, path, 'PATCH', { requestId: 'unsupported', expectedRevision: 0, selectedHeroId: 33 });
  assert.equal(accepted.status, 200, 'Rejected commands must not reserve request IDs');
  assert.equal(accepted.body.hall.revision, 1);
  assert.equal((await request(app.address, `/profiles/${second.id}/hall`)).body.hall.revision, 0);
});

test('without a hero directory no hero/hall capability or endpoints are exposed', async t => {
  const app = await hallFixture(t, false);
  const profile = await createProfile(app, '旧服务');
  const bootstrap = await request(app.address, '/bootstrap');
  assert.equal(bootstrap.status, 200);
  assert.equal(bootstrap.body.content.heroesId, null);
  assert.ok(!bootstrap.body.capabilities.includes('recovered-heroes'));
  assert.ok(!bootstrap.body.capabilities.includes('hall-selection'));
  assert.equal((await request(app.address, '/heroes')).status, 404);
  assert.equal((await request(app.address, `/profiles/${profile.id}/hall`)).status, 404);
  assert.equal((await request(app.address, `/profiles/${profile.id}/hall`, 'PATCH',
    { requestId: 'absent', expectedRevision: 0, selectedHeroId: 33 })).status, 404);
  assert.deepEqual((await request(app.address, `/profiles/${profile.id}`)).body.profile, profile);
});
