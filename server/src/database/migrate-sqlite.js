import { DatabaseSync } from 'node:sqlite';
import { existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { MongoProfileStore } from './mongo-profiles.js';
import { MongoHallStore } from './mongo-hall.js';
import { MongoBattleStore } from './mongo-battles.js';
import { runTransaction } from './transaction.js';
import { REQUEST, integer, exactKeys, stored } from './validation.js';

const sha = text => createHash('sha256').update(text).digest('hex');
const columns = {
  profiles: ['id', 'display_name', 'selected_character_id', 'revision', 'created_at', 'updated_at'],
  hall_states: ['profile_id', 'revision', 'selected_hero_id', 'updated_at'],
  hall_requests: ['profile_id', 'request_id', 'payload', 'receipt'],
  battles: ['id', 'profile_id', 'scenario_json', 'scenario_hash', 'state_json', 'revision', 'created_at', 'updated_at'],
  battle_commands: ['battle_id', 'command_id', 'request_json', 'result_json'],
  battle_creations: ['profile_id', 'request_id', 'request_json', 'result_json', 'battle_id'],
};
const specs = [
  ['', 0x48435a53, { profiles: 'id' }],
  ['.hall', 0x4843484c, { hall_states: 'profile_id', hall_requests: 'profile_id, request_id' }],
  ['.battles', 0x48434254, { battles: 'id', battle_commands: 'battle_id, command_id', battle_creations: 'profile_id, request_id' }],
];

/** Source writers MUST be stopped: separate SQLite files cannot share one snapshot. */
export function readSqliteSnapshot(savePath) {
  const opened = [], sources = [];
  try {
    for (const [suffix, applicationId, tables] of specs) {
      const path = savePath + suffix;
      if (!existsSync(path)) {
        if (!suffix) throw new Error('Source profile database does not exist');
        sources.push({ suffix, applicationId, version: 1, missing: true, tables: Object.fromEntries(Object.keys(tables).map(k => [k, []])) });
        continue;
      }
      const db = new DatabaseSync(path, { readOnly: true }); opened.push(db);
      db.exec('BEGIN');
      if (db.prepare('PRAGMA application_id').get().application_id !== applicationId || db.prepare('PRAGMA user_version').get().user_version !== 1) throw new Error(`Wrong SQLite identity/version: ${suffix || 'profiles'}`);
      if (db.prepare('PRAGMA quick_check').get().quick_check !== 'ok') throw new Error('SQLite integrity check failed');
      const names = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all().map(r => r.name);
      if (!isDeepStrictEqual(names, Object.keys(tables).sort())) throw new Error('Unexpected SQLite tables');
      for (const table of names) {
        const actual = db.prepare(`PRAGMA table_info(${table})`).all().map(r => r.name);
        if (!isDeepStrictEqual(actual, columns[table])) throw new Error(`Unexpected SQLite columns: ${table}`);
      }
      const rows = Object.fromEntries(Object.entries(tables).map(([table, order]) => [table, db.prepare(`SELECT * FROM ${table} ORDER BY ${order}`).all().map(r => ({ ...r }))]));
      sources.push({ suffix, applicationId, version: 1, missing: false, tables: rows });
    }
    return { sources, digest: sha(JSON.stringify(sources)) };
  } finally { for (const db of opened) db.close(); }
}

function transform(snapshot, stores) {
  const tables = Object.assign({}, ...snapshot.sources.map(s => s.tables));
  const profiles = tables.profiles.map(r => ({ _id: r.id, schemaVersion: 1, displayName: r.display_name, selectedCharacterId: r.selected_character_id, revision: r.revision, createdAt: r.created_at, updatedAt: r.updated_at }));
  for (const r of profiles) stores.profiles.map(r);
  const ids = new Set(profiles.map(r => r._id));
  const states = tables.hall_states.map(r => ({ _id: r.profile_id, schemaVersion: 1, revision: r.revision, selectedHeroId: r.selected_hero_id, updatedAt: r.updated_at }));
  const stateMap = new Map(states.map(r => [r._id, r]));
  for (const r of states) { stored(ids.has(r._id)); stores.hall.map(r, r._id); }
  const requests = tables.hall_requests.map(r => {
    stored(ids.has(r.profile_id) && REQUEST.test(r.request_id));
    const payload = JSON.parse(r.payload), receipt = JSON.parse(r.receipt), state = stateMap.get(r.profile_id);
    stored(exactKeys(payload, ['expectedRevision', 'selectedHeroId']) && integer(payload.expectedRevision) && payload.expectedRevision < Number.MAX_SAFE_INTEGER && (payload.selectedHeroId === null || integer(payload.selectedHeroId, 1)) && JSON.stringify(payload) === r.payload);
    stored(exactKeys(receipt, ['profileId', 'revision', 'selectedHeroId', 'updatedAt']) && receipt.profileId === r.profile_id && receipt.revision === payload.expectedRevision + 1 && receipt.selectedHeroId === payload.selectedHeroId && integer(receipt.updatedAt));
    stored(state && receipt.revision <= state.revision && receipt.updatedAt <= state.updatedAt);
    if (receipt.revision === state.revision) stored(isDeepStrictEqual(receipt, stores.hall.map(state, state._id)));
    return { _id: JSON.stringify([r.profile_id, r.request_id]), schemaVersion: 1, profileId: r.profile_id, requestId: r.request_id, payload: r.payload, receipt };
  });
  for (const state of states) {
    const revisions = requests.filter(r => r.profileId === state._id).map(r => r.receipt.revision);
    stored(revisions.length === state.revision && new Set(revisions).size === state.revision);
  }
  const battles = tables.battles.map(r => ({ ...r, schemaVersion: 1, state_hash: sha(r.state_json) }));
  const battleMap = new Map();
  for (const r of battles) { stored(ids.has(r.profile_id)); battleMap.set(r.id, stores.battles.decode(r)); }
  const receipts = (rows, kind) => rows.map(r => {
    const current = battleMap.get(r.battle_id); stored(current);
    if (kind === 'creation') stored(ids.has(r.profile_id) && current.profileId === r.profile_id);
    const row = { ...r, schemaVersion: 1, request_hash: sha(r.request_json), result_hash: sha(r.result_json) };
    stores.battles.validateReceipt(row, current, kind);
    return row;
  });
  const commands = receipts(tables.battle_commands, 'command'), creations = receipts(tables.battle_creations, 'creation');
  for (const battle of battles) {
    const history = commands.filter(r => r.battle_id === battle.id).map(r => JSON.parse(r.result_json).battle.revision);
    stored(creations.filter(r => r.battle_id === battle.id).length === 1 && history.length === battle.revision - 1 && new Set(history).size === history.length);
  }
  return { profiles, hall_states: states, hall_requests: requests, hczs_battles: battles,
    hczs_battle_commands: commands, hczs_battle_creations: creations };
}

export async function migrateSqlite({ connection, savePath, apply = false }) {
  if (!/^hczs_[a-z0-9_]{1,52}$/.test(connection.name)) throw new Error('Dedicated hczs_ database required');
  const metadata = await connection.db.collection('hczs_metadata').findOne({ _id: 'schema' });
  if (metadata?.project !== 'hczs-rebuild' || metadata.version !== 1) throw new Error('Wrong Mongo schema identity');
  const snapshot = readSqliteSnapshot(savePath);
  const stores = { profiles: new MongoProfileStore(connection), hall: new MongoHallStore(connection), battles: new MongoBattleStore(connection) };
  const data = transform(snapshot, stores), counts = Object.fromEntries(Object.entries(data).map(([key, rows]) => [key, rows.length]));
  const markerCollection = connection.db.collection('hczs_migrations');
  const prior = await markerCollection.findOne({ _id: 'sqlite-v1' });
  if (prior) {
    if (prior.digest !== snapshot.digest) throw new Error('Migration target already contains a different source');
    if (prior.kind !== 'sqlite-v1' || !isDeepStrictEqual(prior.counts, counts)) throw new Error('Corrupt migration marker');
    return { status: 'already-completed', digest: snapshot.digest, counts };
  }
  async function requireEmpty(session) {
    const collections = await connection.db.listCollections({}, { nameOnly: true }).toArray();
    for (const { name } of collections) {
      if (name === 'hczs_metadata' || name.startsWith('system.')) continue;
      if (await connection.db.collection(name).findOne({}, { session, projection: { _id: 1 } })) throw new Error(`Migration target is not empty: ${name}`);
    }
  }
  await requireEmpty();
  if (!apply) return { status: 'dry-run', digest: snapshot.digest, counts };
  for (const store of Object.values(stores)) await store.init();
  if (!(await connection.db.listCollections({ name: 'hczs_migrations' }).toArray()).length) await connection.createCollection('hczs_migrations');
  await runTransaction(connection, async session => {
    const completed = await markerCollection.findOne({ _id: 'sqlite-v1' }, { session });
    if (completed) {
      if (completed.digest !== snapshot.digest) throw new Error('Migration target already contains a different source');
      return;
    }
    await requireEmpty(session);
    for (const [name, rows] of Object.entries(data)) if (rows.length) await connection.db.collection(name).insertMany(rows, { session });
    await markerCollection.insertOne({ _id: 'sqlite-v1', digest: snapshot.digest, kind: 'sqlite-v1', counts, completedAt: Date.now() }, { session });
  });
  return { status: 'completed', digest: snapshot.digest, counts };
}
