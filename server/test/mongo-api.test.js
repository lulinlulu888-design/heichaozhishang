import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:net';
import { writeFile, access } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixture, request } from './helpers.js';
import { heroFixture } from './helpers/hero-fixture.js';

// Never infer a Mongo endpoint: this suite must be explicitly pointed at a test replica set.
const uri = process.env.HCZS_TEST_MONGODB_URI;
const enabled = { skip: !uri && 'Set HCZS_TEST_MONGODB_URI to an independent test replica set' };
const tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url));

async function processServer(options) {
  const script = `import {createApp} from ${JSON.stringify(new URL('../src/app.js', import.meta.url).href)};
    try {
      const app = await createApp(JSON.parse(process.env.HCZS_MONGO_TEST_OPTIONS));
      process.on('message', async value => { if(value === 'close') { await app.close(); process.disconnect(); } });
      process.send({address:app.address});
    } catch(error) { process.send({error:error.message}); process.disconnect(); process.exitCode=1; }`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', script], {
    windowsHide: true, stdio: ['ignore', 'ignore', 'pipe', 'ipc'],
    env: { ...process.env, HCZS_MONGO_TEST_OPTIONS: JSON.stringify(options) },
  });
  let stderr = '';
  child.stderr.on('data', value => { stderr = (stderr + value).slice(-3000); });
  const exit = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
  let result;
  try {
    result = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('Mongo child startup timeout')), 20000);
      child.once('message', value => { clearTimeout(timer); resolve(value); });
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', code => { clearTimeout(timer); reject(Error(`Mongo child exited ${code}: ${stderr}`)); });
    });
  } catch (error) { child.kill(); await exit; throw error; }
  if (result.error) { child.kill(); await exit; throw Error(result.error); }
  let stopped = false;
  return { address: result.address, async close() {
    if (stopped) return;
    stopped = true;
    child.send('close');
    const timer = setTimeout(() => child.kill(), 5000);
    try { assert.equal((await exit).code, 0, stderr); } finally { clearTimeout(timer); }
  } };
}

async function setup(t, battle = false, configuration = {}) {
  const files = await fixture(t);
  const mongoDatabase = `hczs_test_${randomUUID().replaceAll('-', '')}`;
  const { default: mongoose } = await import('mongoose');
  const connection = await mongoose.createConnection(uri, { dbName: mongoDatabase, serverSelectionTimeoutMS: 5000 }).asPromise();
  const children = [];
  files.cleanupWith(async () => {
    try { for (const child of children) await child.close(); }
    finally {
      try {
        assert.match(mongoDatabase, /^hczs_test_[0-9a-f]{32}$/);
        assert.equal(connection.name, mongoDatabase);
        await connection.dropDatabase();
      } finally { await connection.close(); }
    }
  });
  await writeFile(join(files.dataDirectory, 'heroes.json'), JSON.stringify(heroFixture()));
  const options = { storage: 'mongodb', mongoUri: uri, mongoDatabase, port: 0,
    dataDirectory: files.dataDirectory, ...(battle ? { tutorialDirectory } : {}), ...configuration };
  async function start(overrides = {}) { const child = await processServer({ ...options, ...overrides }); children.push(child); return child; }
  const first = await start(), second = await start();
  return { ...files, first, second, start, connection };
}

async function profile(server) {
  const response = await request(server.address, '/profiles', 'POST', { displayName: 'Mongo独立测试' });
  assert.equal(response.status, 201, JSON.stringify(response.body));
  return response.body.profile;
}

test('Mongo profiles and hall transactions survive processes and serialize concurrent retries', enabled, async t => {
  const run = await setup(t), p = await profile(run.first);
  const old = await request(run.first.address, `/profiles/${p.id}`, 'PATCH', { expectedRevision: 1, selectedCharacterId: 2 });
  assert.equal(old.status, 200);
  assert.equal((await request(run.second.address, `/profiles/${p.id}`, 'PATCH',
    { expectedRevision: 1, selectedCharacterId: 1 })).status, 409);
  const path = `/profiles/${p.id}/hall`;
  const input = { requestId: 'shared', expectedRevision: 0, selectedHeroId: 1 };
  const same = await Promise.all([run.first, run.second].map(s => request(s.address, path, 'PATCH', input)));
  assert.deepEqual(same.map(r => r.status), [200, 200]);
  assert.deepEqual(same.map(r => r.body.replayed).sort(), [false, true]);
  assert.deepEqual(same[0].body.hall, same[1].body.hall);
  assert.equal(same[0].body.hall.revision, 1);
  assert.equal(same[0].body.hall.selectedHeroId, 1);
  const raced = await Promise.all([run.first, run.second].map((s, i) => request(s.address, path, 'PATCH',
    { requestId: `race-${i}`, expectedRevision: 1, selectedHeroId: null })));
  assert.deepEqual(raced.map(r => r.status).sort(), [200, 409]);
  await run.first.close(); await run.second.close();
  const third = await run.start();
  assert.deepEqual((await request(third.address, `/profiles/${p.id}`)).body.profile, old.body.profile);
  assert.equal((await request(third.address, path)).body.hall.revision, 2);
  const replay = await request(third.address, path, 'PATCH', input);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.hall, same[0].body.hall);
  assert.equal((await request(third.address, path)).body.hall.revision, 2);
  assert.equal((await request(third.address, path, 'PATCH', { ...input, selectedHeroId: null })).status, 409);
  const beforeInvalid = (await request(third.address, path)).body.hall;
  assert.equal((await request(third.address, path, 'PATCH',
    { requestId: 'invalid', expectedRevision: 2, selectedHeroId: 2 })).status, 400);
  assert.deepEqual((await request(third.address, path)).body.hall, beforeInvalid);
  const other = await profile(third);
  assert.equal((await request(third.address, `/profiles/${other.id}/hall`)).body.hall.revision, 0);
  const bootstrap = (await request(third.address, '/bootstrap')).body;
  assert.ok(bootstrap.capabilities.includes('hall-selection'));
  assert.equal(bootstrap.content.heroesId, (await request(third.address, '/heroes')).body.contentId);
  await assert.rejects(access(run.savePath), { code: 'ENOENT' });
});

test('Mongo battle create/actions are idempotent across two processes and restart', enabled, async t => {
  const run = await setup(t, true), p = await profile(run.first);
  const prefix = `/profiles/${p.id}/battles`;
  const input = { requestId: 'create', seed: 123456 };
  const creates = await Promise.all([run.first, run.second].map(s => request(s.address, prefix, 'POST', input)));
  assert.ok(creates.every(r => r.status === 200 || r.status === 201), JSON.stringify(creates));
  assert.deepEqual(creates.map(r => r.body.replayed).sort(), [false, true]);
  assert.deepEqual(creates[0].body.battle, creates[1].body.battle);
  const battle = creates[0].body.battle;
  assert.equal((await request(run.first.address, prefix)).body.battles.length, 1);
  const path = `${prefix}/${battle.id}`, actions = `${path}/actions`;
  const command = { requestId: 'turn', expectedRevision: battle.revision, type: 'end-turn' };
  const same = await Promise.all([run.first, run.second].map(s => request(s.address, actions, 'POST', command)));
  assert.deepEqual(same.map(r => r.status), [200, 200]);
  assert.deepEqual(same.map(r => r.body.replayed).sort(), [false, true]);
  assert.deepEqual(same[0].body.battle, same[1].body.battle);
  const revision = same[0].body.battle.revision;
  const raced = await Promise.all([run.first, run.second].map((s, i) => request(s.address, actions, 'POST',
    { requestId: `battle-race-${i}`, expectedRevision: revision, type: 'end-turn' })));
  assert.deepEqual(raced.map(r => r.status).sort(), [200, 409]);
  const latest = raced.find(r => r.status === 200).body.battle;
  await run.first.close(); await run.second.close();
  const third = await run.start();
  assert.deepEqual((await request(third.address, path)).body.battle, latest);
  const replay = await request(third.address, actions, 'POST', command);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(replay.body.battle, same[0].body.battle);
  assert.deepEqual((await request(third.address, path)).body.battle, latest);
  const original = await request(third.address, prefix, 'POST', input);
  assert.equal(original.body.replayed, true);
  assert.deepEqual(original.body.battle, battle);
  const other = await profile(third);
  assert.equal((await request(third.address, `/profiles/${other.id}/battles/${battle.id}`)).status, 404);
  let current = latest;
  for (let i = 0; current.state.status === 'player-turn' && i < 150; i++) {
    const instanceId = current.state.piles.hand.find(id => {
      const card = current.state.cards.find(value => value.instanceId === id);
      return current.scenario.definition.cards[card.cardId].cost <= current.state.energy;
    });
    const result = await request(third.address, actions, 'POST', {
      requestId: `playthrough-${i}`, expectedRevision: current.revision,
      ...(instanceId ? { type: 'play-card', instanceId } : { type: 'end-turn' }),
    });
    assert.equal(result.status, 200, JSON.stringify(result.body));
    current = result.body.battle;
  }
  assert.equal(current.state.status, 'won');
  assert.deepEqual((await request(third.address, `/profiles/${p.id}`)).body.profile, p,
    'Reconstructed battle rewards must not invent original-account progress');
});

test('Mongo city ultimate generation and eight-hit use are each exactly once across processes and restart', enabled, async t => {
  const run = await setup(t, true, {cityPreview:true}), p = await profile(run.first);
  const prefix = `/profiles/${p.id}/battles`;
  const created = await request(run.first.address,prefix,'POST',{requestId:'city-ultimate',seed:0});
  assert.equal(created.status,201,JSON.stringify(created.body));
  let battle = created.body.battle;
  const path = `${prefix}/${battle.id}`, actions = `${path}/actions`;
  for (const instanceId of ['tutorial-card-1','tutorial-card-2']) {
    const response = await request(run.first.address,actions,'POST',{
      requestId:instanceId,expectedRevision:battle.revision,type:'play-card',instanceId});
    assert.equal(response.status,200,JSON.stringify(response.body)); battle = response.body.battle;
  }
  const third = {requestId:'third',expectedRevision:battle.revision,type:'play-card',instanceId:'tutorial-card-3'};
  const generated = await Promise.all([run.first,run.second].map(server => request(server.address,actions,'POST',third)));
  assert.deepEqual(generated.map(r => r.status),[200,200]);
  assert.deepEqual(generated.map(r => r.body.replayed).sort(),[false,true]);
  assert.deepEqual(generated[0].body.battle,generated[1].body.battle);
  battle = generated[0].body.battle;
  assert.equal(battle.state.ultimate.generatedTotal,1);
  assert.deepEqual(battle.state.cards.at(-1),{instanceId:'ultimate:1',cardId:'410104'});
  const generatedBattle = battle;
  const spent = await request(run.first.address,actions,'POST',{requestId:'spend-energy',expectedRevision:battle.revision,
    type:'play-card',instanceId:'tutorial-card-4'});
  assert.equal(spent.status,200,JSON.stringify(spent.body)); battle = spent.body.battle;
  assert.equal(battle.state.energy,0);
  const use = {requestId:'use-ultimate',expectedRevision:battle.revision,type:'play-card',instanceId:'ultimate:1'};
  const used = await Promise.all([run.first,run.second].map(server => request(server.address,actions,'POST',use)));
  assert.deepEqual(used.map(r => r.status),[200,200]);
  assert.deepEqual(used.map(r => r.body.replayed).sort(),[false,true]);
  assert.deepEqual(used[0].body.events,used[1].body.events);
  assert.deepEqual(used[0].body.events.filter(e => e.type === 'DamageApplied').map(e => e.amount),['72','72','144','144','144','289','289','289']);
  const final = used[0].body.battle;
  assert.equal(final.state.energy,battle.state.energy);
  assert.deepEqual(final.state.piles.removed,['ultimate:1']);
  await run.first.close(); await run.second.close();
  const restarted = await run.start();
  assert.deepEqual((await request(restarted.address,path)).body.battle,final);
  const replay = await request(restarted.address,actions,'POST',use);
  assert.equal(replay.status,200,JSON.stringify(replay.body));
  assert.equal(replay.body.replayed,true); assert.deepEqual(replay.body.battle,final);
  assert.deepEqual((await request(restarted.address,actions,'POST',third)).body.battle,generatedBattle);
  assert.deepEqual((await request(restarted.address,path)).body.battle,final);
});

test('unavailable Mongo aborts startup without silently creating SQLite saves', enabled, async t => {
  const files = await fixture(t);
  const socket = createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  await assert.rejects(processServer({ dataDirectory: files.dataDirectory, port: 0,
    mongoUri: `mongodb://127.0.0.1:${port}/?serverSelectionTimeoutMS=500&connectTimeoutMS=500`,
    mongoDatabase: `hczs_test_${randomUUID().replaceAll('-', '')}` }), /connect|selection|ECONNREFUSED|Mongo/i);
  await assert.rejects(access(files.savePath), { code: 'ENOENT' });
});

test('Mongo rejects foreign identity, unsupported version and unclaimed nonempty databases', enabled, async t => {
  const files = await fixture(t);
  const { default: mongoose } = await import('mongoose');
  const { connectDatabase } = await import('../src/database/connection.js');
  for (const scenario of ['foreign', 'version', 'unclaimed']) {
    const database = `hczs_test_${randomUUID().replaceAll('-', '')}`;
    const raw = await mongoose.createConnection(uri, { dbName: database, serverSelectionTimeoutMS: 5000 }).asPromise();
    files.cleanupWith(async () => { try { await raw.dropDatabase(); } finally { await raw.close(); } });
    if (scenario === 'unclaimed') await raw.db.collection('unrelated').insertOne({ _id: 'keep', value: 42 });
    else await raw.db.collection('hczs_metadata').insertOne({ _id: 'schema',
      project: scenario === 'foreign' ? 'another-project' : 'hczs-rebuild', version: scenario === 'version' ? 999 : 1 });
    const names = await raw.db.listCollections({}, { nameOnly: true }).toArray();
    const before = await Promise.all(names.map(async ({ name }) => [name, await raw.db.collection(name).find().toArray()]));
    await assert.rejects(connectDatabase({ uri, database }), scenario === 'unclaimed' ? /Refusing to adopt/ : /identity\/version/);
    const afterNames = await raw.db.listCollections({}, { nameOnly: true }).toArray();
    assert.deepEqual(afterNames.map(v => v.name).sort(), names.map(v => v.name).sort());
    for (const [name, rows] of before) assert.deepEqual(await raw.db.collection(name).find().toArray(), rows);
  }
});

test('Mongo hall rejects corrupt receipts and rolls state back if receipt persistence fails', enabled, async t => {
  const run = await setup(t), p = await profile(run.first);
  const path = `/profiles/${p.id}/hall`;
  const command = { requestId: 'atomic', expectedRevision: 0, selectedHeroId: 33 };
  const db = run.connection.db;
  // Server-side validator fails the second write after the state upsert within the transaction.
  await db.command({ collMod: 'hall_requests', validator: { impossibleTestField: { $exists: true } }, validationLevel: 'strict', validationAction: 'error' });
  const failed = await request(run.first.address, path, 'PATCH', command);
  assert.equal(failed.status, 500);
  assert.equal(await db.collection('hall_states').countDocuments({ _id: p.id }), 0);
  assert.equal(await db.collection('hall_requests').countDocuments({ profileId: p.id }), 0);
  await db.command({ collMod: 'hall_requests', validator: {} });
  const accepted = await request(run.second.address, path, 'PATCH', command);
  assert.equal(accepted.status, 200, JSON.stringify(accepted.body));
  assert.equal(accepted.body.hall.revision, 1);
  const savedState = await db.collection('hall_states').findOne({ _id: p.id });
  await db.collection('hall_requests').updateOne({ profileId: p.id, requestId: 'atomic' }, { $set: { 'receipt.revision': 999 } });
  const corruptReceipt = await db.collection('hall_requests').findOne({ profileId: p.id, requestId: 'atomic' });
  const corrupt = await request(run.first.address, path, 'PATCH', command);
  assert.equal(corrupt.status, 500);
  assert.deepEqual(await db.collection('hall_states').findOne({ _id: p.id }), savedState);
  assert.deepEqual(await db.collection('hall_requests').findOne({ profileId: p.id, requestId: 'atomic' }), corruptReceipt);
});

test('Mongo battle transaction rolls state back when its command receipt fails', enabled, async t => {
  const run = await setup(t, true), p = await profile(run.first);
  const prefix = `/profiles/${p.id}/battles`;
  const created = await request(run.first.address, prefix, 'POST', { requestId: 'rollback-create', seed: 123456 });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const before = created.body.battle, path = `${prefix}/${before.id}`;
  const db = run.connection.db;
  const rowsBefore = await db.collection('hczs_battle_commands').find().toArray();
  await db.command({ collMod: 'hczs_battle_commands', validator: { impossibleTestField: { $exists: true } }, validationLevel: 'strict', validationAction: 'error' });
  const command = { requestId: 'rollback-action', expectedRevision: before.revision, type: 'end-turn' };
  assert.equal((await request(run.first.address, `${path}/actions`, 'POST', command)).status, 500);
  assert.deepEqual((await request(run.second.address, path)).body.battle, before);
  assert.deepEqual(await db.collection('hczs_battle_commands').find().toArray(), rowsBefore);
  await db.command({ collMod: 'hczs_battle_commands', validator: {} });
  const retry = await request(run.second.address, `${path}/actions`, 'POST', command);
  assert.equal(retry.status, 200, JSON.stringify(retry.body));
  assert.equal(retry.body.replayed, false);
  assert.equal(retry.body.battle.revision, before.revision + 1);
});

test('Mongo encounter selection survives mode removal and keeps retries scoped to original selection', enabled, async t => {
  const run = await setup(t, true, { cityPreview: true }), p = await profile(run.first);
  const prefix = `/profiles/${p.id}/battles`;
  const firstInput = { requestId: 'selected-first', seed: 5000, encounterId: 'tutorial-5000' };
  const first = await request(run.first.address, prefix, 'POST', firstInput);
  assert.equal(first.status, 201);
  assert.equal(first.body.battle.scenario.definition.enemy.id, '991');
  const cityInput = { requestId: 'selected-city', seed: 10, encounterId: 'city-preview-10405' };
  const created = await Promise.all([run.first, run.second].map(s => request(s.address, prefix, 'POST', cityInput)));
  assert.deepEqual(created.map(r => r.status), [201, 201]);
  assert.deepEqual(created.map(r => r.body.replayed).sort(), [false, true]);
  assert.deepEqual(created[0].body.battle, created[1].body.battle);
  const city = created[0].body.battle;
  assert.equal(city.scenario.definition.enemy.id, '6605');
  assert.equal((await request(run.first.address, prefix, 'POST', { ...cityInput, encounterId: 'tutorial-5000' })).status, 409);
  const oldInput = { requestId: 'legacy-default', seed: 12 };
  const old = await request(run.first.address, prefix, 'POST', oldInput);
  assert.equal(old.status, 201);
  assert.equal(old.body.battle.scenario.definition.enemy.id, '6605');
  await run.first.close(); await run.second.close();
  const third = await run.start({ cityPreview: false });
  assert.deepEqual((await request(third.address, '/encounters')).body.encounters.map(e => e.id), ['tutorial-5000']);
  assert.equal((await request(third.address, '/encounters/city-preview-10405')).status, 404);
  const retry = await request(third.address, prefix, 'POST', cityInput);
  assert.equal(retry.status, 201);
  assert.equal(retry.body.replayed, true);
  assert.deepEqual(retry.body.battle, city);
  assert.deepEqual((await request(third.address, prefix, 'POST', oldInput)).body.battle, old.body.battle);
  const rejected = await request(third.address, prefix, 'POST', { ...cityInput, requestId: 'new-disabled-city' });
  assert.equal(rejected.status, 404);
  assert.equal((await request(third.address, prefix)).body.battles.length, 3);
  const resumed = await request(third.address, `${prefix}/${city.id}/actions`, 'POST',
    { requestId: 'continue-saved-city', expectedRevision: 1, type: 'end-turn' });
  assert.equal(resumed.status, 200);
  assert.equal(resumed.body.battle.revision, 2);
  assert.equal(resumed.body.battle.scenario.encounterId, cityInput.encounterId);
});
