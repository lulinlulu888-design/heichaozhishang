import { createHash, randomUUID, randomInt } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { createBattle, playCard, endTurn, validateState } from '../../packages/battle-session/src/index.js';
import { ServiceError, requireObject } from './errors.js';
import { materializeEnemySelection } from './weighted-intents.js';
import { creationRequest, requireSelectedScenario } from './battle-creation-request.js';

const APPLICATION_ID = 0x48434254;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const digest = text => createHash('sha256').update(text).digest('hex');

/** New reconstruction battles, stored independently of existing profile schema. */
export class BattleStore {
  constructor(path) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    try {
      this.db.exec('PRAGMA busy_timeout = 5000; PRAGMA foreign_keys = ON;');
      const { application_id: id } = this.db.prepare('PRAGMA application_id').get();
      const { user_version: version } = this.db.prepare('PRAGMA user_version').get();
      const { count } = this.db.prepare("SELECT count(*) AS count FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").get();
      if (id === 0 && version === 0 && count === 0) {
        this.db.exec(`BEGIN IMMEDIATE;
          CREATE TABLE battles (
            id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
            scenario_json TEXT NOT NULL, scenario_hash TEXT NOT NULL,
            state_json TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1),
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
          ) STRICT;
          CREATE INDEX battles_profile ON battles(profile_id, created_at);
          CREATE TABLE battle_commands (
            battle_id TEXT NOT NULL REFERENCES battles(id), command_id TEXT NOT NULL,
            request_json TEXT NOT NULL, result_json TEXT NOT NULL,
            PRIMARY KEY(battle_id, command_id)
          ) STRICT;
          CREATE TABLE battle_creations (
            profile_id TEXT NOT NULL, request_id TEXT NOT NULL,
            request_json TEXT NOT NULL, result_json TEXT NOT NULL,
            battle_id TEXT NOT NULL REFERENCES battles(id),
            PRIMARY KEY(profile_id, request_id)
          ) STRICT;
          PRAGMA application_id = ${APPLICATION_ID}; PRAGMA user_version = 1; COMMIT;`);
      } else if (id !== APPLICATION_ID || version !== 1) {
        throw new Error(`Unsupported battle save identity/version (${id}/${version}); existing data was not migrated`);
      }
      this.db.exec('PRAGMA journal_mode = WAL; PRAGMA synchronous = FULL;');
    } catch (error) { this.db.close(); throw error; }
  }

  decode(row) {
    if (!row) throw new ServiceError('BATTLE_NOT_FOUND', 'Battle does not exist in this profile', 404);
    if (digest(row.scenario_json) !== row.scenario_hash) throw new Error('Battle scenario integrity mismatch');
    const scenario = JSON.parse(row.scenario_json);
    const state = validateState(scenario.definition, JSON.parse(row.state_json));
    return { id: row.id, profileId: row.profile_id, revision: row.revision,
      scenario, state, createdAt: row.created_at, updatedAt: row.updated_at };
  }

  get(profileId, id) {
    return this.decode(this.db.prepare('SELECT * FROM battles WHERE id = ? AND profile_id = ?').get(id, profileId));
  }

  list(profileId) {
    return this.db.prepare('SELECT * FROM battles WHERE profile_id = ? ORDER BY created_at, id').all(profileId)
      .map(row => {
        const b = this.decode(row);
        return { id: b.id, revision: b.revision, definitionId: b.state.definitionId,
          status: b.state.status, round: b.state.round, createdAt: b.createdAt, updatedAt: b.updatedAt };
      });
  }

  create(profileId, scenario, input) {
    if (!UUID.test(profileId)) throw new ServiceError('INVALID_INPUT', 'A valid profile ID is required');
    const requestJson = creationRequest(input);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const prior = this.db.prepare('SELECT request_json, result_json FROM battle_creations WHERE profile_id = ? AND request_id = ?')
        .get(profileId, input.requestId);
      if (prior) {
        if (prior.request_json !== requestJson) throw new ServiceError('COMMAND_CONFLICT', 'Request ID was used for a different creation', 409);
        const result = JSON.parse(prior.result_json);
        this.db.exec('COMMIT');
        return { ...result, replayed: true };
      }
      requireSelectedScenario(scenario, input);
      let scenarioJson = JSON.stringify(scenario);
      if (!scenarioJson || Buffer.byteLength(scenarioJson) > 4 * 1024 * 1024) throw new Error('Battle scenario exceeds size budget');
      const seed = input.seed ?? randomInt(0, 0x100000000);
      const ownedScenario = materializeEnemySelection(JSON.parse(scenarioJson), seed);
      scenarioJson = JSON.stringify(ownedScenario);
      if (Buffer.byteLength(scenarioJson) > 4 * 1024 * 1024) throw new Error('Battle scenario exceeds size budget');
      const next = createBattle(ownedScenario.definition, seed);
      const id = randomUUID(), now = Date.now();
      this.db.prepare('INSERT INTO battles VALUES (?, ?, ?, ?, ?, 1, ?, ?)')
        .run(id, profileId, scenarioJson, digest(scenarioJson), JSON.stringify(next.state), now, now);
      const result = { battle: this.get(profileId, id), events: next.events, replayed: false };
      this.db.prepare('INSERT INTO battle_creations VALUES (?, ?, ?, ?, ?)')
        .run(profileId, input.requestId, requestJson, JSON.stringify(result), id);
      this.db.exec('COMMIT');
      return result;
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }

  act(profileId, id, input) {
    requireObject(input, ['requestId', 'expectedRevision', 'type', 'instanceId'], ['requestId', 'expectedRevision', 'type']);
    if (typeof input.requestId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/.test(input.requestId) ||
        !Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 1 ||
        !['play-card', 'end-turn'].includes(input.type) ||
        (input.type === 'play-card' ? typeof input.instanceId !== 'string' : 'instanceId' in input)) {
      throw new ServiceError('INVALID_INPUT', 'Invalid battle command');
    }
    // Stable serialization makes key order irrelevant but keeps revision in the identity.
    const requestJson = JSON.stringify({ requestId: input.requestId, expectedRevision: input.expectedRevision,
      type: input.type, ...(input.type === 'play-card' ? { instanceId: input.instanceId } : {}) });
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const current = this.get(profileId, id);
      const previous = this.db.prepare('SELECT request_json, result_json FROM battle_commands WHERE battle_id = ? AND command_id = ?')
        .get(id, input.requestId);
      if (previous) {
        if (previous.request_json !== requestJson) throw new ServiceError('COMMAND_CONFLICT', 'Request ID was used for a different command', 409);
        const result = JSON.parse(previous.result_json);
        this.db.exec('COMMIT');
        return { ...result, replayed: true };
      }
      if (current.revision !== input.expectedRevision) {
        throw new ServiceError('REVISION_CONFLICT', 'Battle changed; reload it before acting again', 409);
      }
      let next;
      try {
        next = input.type === 'play-card'
          ? playCard(current.scenario.definition, current.state, input.instanceId)
          : endTurn(current.scenario.definition, current.state);
      } catch (error) {
        if (error instanceof TypeError || error instanceof RangeError) {
          throw new ServiceError('INVALID_BATTLE_ACTION', error.message);
        }
        throw error;
      }
      if (!Number.isSafeInteger(current.revision + 1)) throw new Error('Battle revision exhausted');
      const update = this.db.prepare('UPDATE battles SET state_json = ?, revision = revision + 1, updated_at = ? WHERE id = ? AND revision = ?')
        .run(JSON.stringify(next.state), Date.now(), id, current.revision);
      if (update.changes !== 1) throw new Error('Battle write conflict inside transaction');
      const result = { battle: this.get(profileId, id), events: next.events, replayed: false };
      this.db.prepare('INSERT INTO battle_commands VALUES (?, ?, ?, ?)')
        .run(id, input.requestId, requestJson, JSON.stringify(result));
      this.db.exec('COMMIT');
      return result;
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }

  close() { this.db.close(); }
}
