import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { connectDatabase } from '../src/database/connection.js';
import { migrateSqlite } from '../src/database/migrate-sqlite.js';
import { MongoProfileStore } from '../src/database/mongo-profiles.js';
import { MongoHallStore } from '../src/database/mongo-hall.js';
import { MongoBattleStore } from '../src/database/mongo-battles.js';
import { ProfileStore } from '../src/store.js';
import { HallStore } from '../src/hall-store.js';
import { BattleStore } from '../src/battles.js';
import { loadTutorialScenario } from '../src/tutorial.js';

async function fixture(t) {
  const dir = await mkdtemp(join(tmpdir(), 'hczs-migration-')), savePath = join(dir, 'save.sqlite');
  const connection = await connectDatabase({ database: `hczs_test_${randomUUID().replaceAll('-', '')}` });
  t.after(async () => { await connection.dropDatabase(); await connection.close(); await rm(dir, { recursive: true, force: true }); });
  const p = new ProfileStore(savePath), profile = p.create({ displayName: '迁移测试' });
  p.close();
  const h = new HallStore(savePath + '.hall');
  const hall = h.update(profile.id, { requestId: 'hall-1', expectedRevision: 0, selectedHeroId: 2 }, new Set([2])); h.close();
  const b = new BattleStore(savePath + '.battles');
  const creation = b.create(profile.id, await loadTutorialScenario(), { requestId: 'battle-1', seed: 9 });
  const command = { requestId: 'turn-1', expectedRevision: 1, type: 'end-turn' };
  const action = b.act(profile.id, creation.battle.id, command); b.close();
  return { connection, savePath, profile, hall, creation, action, command };
}

test('SQLite migration dry-run/apply preserves state and receipts; retry never overwrites progress', async t => {
  const f = await fixture(t), before = await Promise.all(['', '.hall', '.battles'].map(s => readFile(f.savePath + s)));
  assert.equal((await migrateSqlite(f)).status, 'dry-run');
  assert.equal(await f.connection.db.collection('profiles').countDocuments(), 0);
  assert.equal((await migrateSqlite({ ...f, apply: true })).status, 'completed');
  const p = new MongoProfileStore(f.connection), h = new MongoHallStore(f.connection), b = new MongoBattleStore(f.connection);
  assert.deepEqual(await p.get(f.profile.id), f.profile);
  assert.deepEqual(await h.get(f.profile.id), f.hall.hall);
  assert.deepEqual(await b.get(f.profile.id, f.action.battle.id), f.action.battle);
  assert.deepEqual(await b.act(f.profile.id, f.action.battle.id, f.command), { ...f.action, replayed: true });
  assert.deepEqual(await b.create(f.profile.id, {}, { requestId: 'battle-1', seed: 9 }), { ...f.creation, replayed: true });
  await h.update(f.profile.id, { requestId: 'hall-2', expectedRevision: 1, selectedHeroId: null }, new Set());
  assert.equal((await migrateSqlite({ ...f, apply: true })).status, 'already-completed');
  assert.equal((await h.get(f.profile.id)).revision, 2);
  const after = await Promise.all(['', '.hall', '.battles'].map(s => readFile(f.savePath + s)));
  assert.deepEqual(after, before);
  const source = new ProfileStore(f.savePath); source.update(f.profile.id, { expectedRevision: 1, displayName: '已变更来源' }, new Set()); source.close();
  await assert.rejects(migrateSqlite({ ...f, apply: true }), /different source/);
  assert.equal((await p.get(f.profile.id)).revision, 1);
});

test('migration refuses nonempty targets and wrong source identity', async t => {
  const f = await fixture(t);
  await f.connection.db.collection('unexpected').insertOne({ local: true });
  await assert.rejects(migrateSqlite({ ...f, apply: true }), /not empty/);
  const db = new DatabaseSync(f.savePath); db.exec('PRAGMA application_id=42'); db.close();
  await assert.rejects(migrateSqlite(f), /identity/);
  assert.equal(await f.connection.db.collection('profiles').countDocuments(), 0);
});

test('migration rejects cross-profile receipts before writing', async t => {
  const f = await fixture(t), db = new DatabaseSync(f.savePath + '.hall');
  const row = db.prepare('SELECT receipt FROM hall_requests').get(), receipt = JSON.parse(row.receipt);
  receipt.profileId = randomUUID(); db.prepare('UPDATE hall_requests SET receipt=?').run(JSON.stringify(receipt)); db.close();
  await assert.rejects(migrateSqlite({ ...f, apply: true }));
  assert.equal(await f.connection.db.collection('profiles').countDocuments(), 0);
});

test('late marker insertion failure rolls back all business documents', async t => {
  const f = await fixture(t);
  await f.connection.db.createCollection('hczs_migrations', { validator: { forbidden: { $exists: true } } });
  await assert.rejects(migrateSqlite({ ...f, apply: true }), /validation/);
  for (const name of ['profiles', 'hall_states', 'hall_requests', 'hczs_battles', 'hczs_battle_commands', 'hczs_battle_creations', 'hczs_migrations']) assert.equal(await f.connection.db.collection(name).countDocuments(), 0, name);
});

test('migration rejects missing battle history and dangling profile references', async t => {
  const f = await fixture(t), db = new DatabaseSync(f.savePath + '.battles');
  db.exec('DELETE FROM battle_commands'); db.close();
  await assert.rejects(migrateSqlite({ ...f, apply: true }));
  const h = new DatabaseSync(f.savePath + '.hall');
  h.prepare('UPDATE hall_states SET profile_id=?').run(randomUUID()); h.close();
  await assert.rejects(migrateSqlite({ ...f, apply: true }));
  assert.equal(await f.connection.db.collection('profiles').countDocuments(), 0);
});
