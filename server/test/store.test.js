import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { DatabaseSync } from 'node:sqlite';
import { ProfileStore } from '../src/store.js';
import { fixture } from './helpers.js';

test('a real SQLite file preserves selected character and revision after reopen', async t => {
  const { savePath, cleanupWith } = await fixture(t);
  const first = new ProfileStore(savePath);
  const original = first.create({ displayName: '重温存档' });
  const saved = first.update(original.id, { expectedRevision: 1, selectedCharacterId: 2 }, new Set([1, 2]));
  first.close();
  const second = new ProfileStore(savePath);
  cleanupWith(() => second.close());
  assert.deepEqual(second.get(original.id), saved);
  assert.equal(saved.revision, 2);
  assert.equal(saved.selectedCharacterId, 2);
  assert.equal(second.list().length, 1);
});

test('stale revisions and invalid input cannot replace a saved choice', async t => {
  const { savePath, cleanupWith } = await fixture(t);
  const first = new ProfileStore(savePath);
  const second = new ProfileStore(savePath);
  cleanupWith(() => { first.close(); second.close(); });
  const original = first.create({ displayName: 'Test' });
  first.update(original.id, { expectedRevision: 1, selectedCharacterId: 1 }, new Set([1, 2]));
  assert.throws(() => second.update(original.id, { expectedRevision: 1, selectedCharacterId: 2 }, new Set([1, 2])),
    { code: 'REVISION_CONFLICT', status: 409 });
  for (const change of [
    { expectedRevision: 2, selectedCharacterId: 999 },
    { expectedRevision: 2, selectedCharacterId: '2' },
    { expectedRevision: 2, displayName: 'bad\nname' },
    { expectedRevision: 2, coins: 999 },
    { expectedRevision: 2 },
  ]) assert.throws(() => first.update(original.id, change, new Set([1, 2])));
  assert.equal(second.get(original.id).revision, 2);
  assert.equal(second.get(original.id).selectedCharacterId, 1);
});

test('a storage failure rolls back the transaction and allows subsequent writes', async t => {
  const { savePath, cleanupWith } = await fixture(t);
  const store = new ProfileStore(savePath);
  cleanupWith(() => store.close());
  const original = store.create({ displayName: 'Before' });
  store.db.exec(`CREATE TRIGGER reject_update AFTER UPDATE ON profiles
    BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END;`);
  assert.throws(() => store.update(original.id, { expectedRevision: 1, displayName: 'After' }, new Set()), /injected storage failure/);
  assert.deepEqual(store.get(original.id), original);
  store.db.exec('DROP TRIGGER reject_update');
  assert.equal(store.update(original.id, { expectedRevision: 1, displayName: 'After' }, new Set()).revision, 2);
});

test('unknown save versions and unrelated databases are preserved, not reset', async t => {
  const { savePath } = await fixture(t);
  let db = new DatabaseSync(savePath);
  db.exec("CREATE TABLE unrelated (data TEXT); INSERT INTO unrelated VALUES ('keep me');");
  db.close();
  const before = await readFile(savePath);
  assert.throws(() => new ProfileStore(savePath), /Unsupported save/);
  assert.deepEqual(await readFile(savePath), before);
  db = new DatabaseSync(savePath);
  db.exec('PRAGMA application_id = 1212373587; PRAGMA user_version = 99');
  db.close();
  const unknown = await readFile(savePath);
  assert.throws(() => new ProfileStore(savePath), /Unsupported save/);
  assert.deepEqual(await readFile(savePath), unknown);
});

test('SQL-like display names remain plain text and do not modify schema', async t => {
  const { savePath, cleanupWith } = await fixture(t);
  const store = new ProfileStore(savePath);
  cleanupWith(() => store.close());
  const name = "x'); DROP TABLE profiles;--";
  assert.equal(store.create({ displayName: name }).displayName, name);
  assert.equal(store.list().length, 1);
  assert.throws(() => store.create({ displayName: ' Valid ', selectedCharacterId: 1 }));
});
