import { createHash, randomUUID, randomInt } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { createBattle, playCard, endTurn, validateState } from '../../../packages/battle-session/src/index.js';
import { ServiceError, requireObject } from '../errors.js';
import { materializeEnemySelection } from '../weighted-intents.js';
import { runTransaction } from './transaction.js';
import { creationRequest, requireSelectedScenario } from '../battle-creation-request.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const REQUEST = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
const hash = text => createHash('sha256').update(text).digest('hex');
const integer = (n, min = 0) => Number.isSafeInteger(n) && n >= min;
const check = condition => { if (!condition) throw new ServiceError('SAVE_CORRUPT', 'Stored battle integrity validation failed', 500); };
const bounded = (text, limit = 8 * 1024 * 1024) => typeof text === 'string' && Buffer.byteLength(text) <= limit;
const events = new Set(['DiscardRecycled', 'CardDrawn', 'BattleEnded', 'BreakdownChanged', 'HealthRestored', 'ShieldAdded', 'DamageApplied', 'BreakdownTriggered', 'EnergyChanged', 'ShieldCleared', 'StateUpdated', 'BattleStarted', 'TurnStarted', 'CardPlayed', 'CardMoved', 'EnemySkillUsed']);

function request(input, creation) {
  if (creation) return creationRequest(input);
  requireObject(input, ['requestId', 'expectedRevision', 'type', 'instanceId'], ['requestId', 'expectedRevision', 'type']);
  if (typeof input.requestId !== 'string' || !REQUEST.test(input.requestId) ||
      !integer(input.expectedRevision, 1) || !['play-card', 'end-turn'].includes(input.type) ||
      (input.type === 'play-card' ? typeof input.instanceId !== 'string' : 'instanceId' in input)) {
    throw new ServiceError('INVALID_INPUT', 'Invalid battle request');
  }
  return JSON.stringify({ requestId: input.requestId, expectedRevision: input.expectedRevision,
    type: input.type, ...(input.type === 'play-card' ? { instanceId: input.instanceId } : {}) });
}

/** Local reconstruction state; never a claim of original game protocol compatibility. */
export class MongoBattleStore {
  constructor(connection) {
    this.connection = connection;
    const Schema = connection.base.Schema;
    const str = { type: String, required: true };
    const num = min => ({ type: Number, required: true, validate: n => integer(n, min) });
    const make = (name, collection, fields, indexes) => {
      const schema = new Schema({ schemaVersion: { type: Number, required: true, enum: [1] }, ...fields }, { collection, versionKey: false, strict: 'throw', autoIndex: false, bufferCommands: false });
      for (const [keys, options] of indexes) schema.index(keys, options);
      return connection.models[name] ?? connection.model(name, schema);
    };
    this.battles = make('HczsBattle', 'hczs_battles', { id: str, profile_id: str, scenario_json: str, scenario_hash: str, state_json: str, state_hash: str, revision: num(1), created_at: num(0), updated_at: num(0) }, [[{ id: 1 }, { unique: true }], [{ profile_id: 1, created_at: 1, id: 1 }, {}]]);
    this.commands = make('HczsBattleCommand', 'hczs_battle_commands', { battle_id: str, command_id: str, request_json: str, request_hash: str, result_json: str, result_hash: str }, [[{ battle_id: 1, command_id: 1 }, { unique: true }]]);
    this.creations = make('HczsBattleCreation', 'hczs_battle_creations', { profile_id: str, request_id: str, battle_id: str, request_json: str, request_hash: str, result_json: str, result_hash: str }, [[{ profile_id: 1, request_id: 1 }, { unique: true }]]);
  }
  async init() {
    // Explicitly create collections before first transaction on a fresh database.
    for (const model of [this.battles, this.commands, this.creations]) { await model.createCollection(); await model.createIndexes(); }
  }
  decode(row) {
    if (!row) throw new ServiceError('BATTLE_NOT_FOUND', 'Battle does not exist in this profile', 404);
    check(row.schemaVersion === 1 && typeof row.id === 'string' && UUID.test(row.id) && typeof row.profile_id === 'string' && UUID.test(row.profile_id));
    check(integer(row.revision, 1) && integer(row.created_at) && integer(row.updated_at) && row.updated_at >= row.created_at);
    check(bounded(row.scenario_json, 4 * 1024 * 1024) && bounded(row.state_json) && hash(row.scenario_json) === row.scenario_hash && hash(row.state_json) === row.state_hash);
    const scenario = JSON.parse(row.scenario_json), state = validateState(scenario.definition, JSON.parse(row.state_json));
    check(state.actionIndex + 1 === row.revision);
    return { id: row.id, profileId: row.profile_id, revision: row.revision, scenario, state, createdAt: row.created_at, updatedAt: row.updated_at };
  }
  validateReceipt(row, current, kind) {
    const creation = kind === 'creation';
    check(row.schemaVersion === 1 && bounded(row.request_json) && bounded(row.result_json));
    check(hash(row.request_json) === row.request_hash && hash(row.result_json) === row.result_hash && row.battle_id === current.id);
    const input = JSON.parse(row.request_json), result = JSON.parse(row.result_json);
    check(request(input, creation) === row.request_json && input.requestId === (creation ? row.request_id : row.command_id));
    check(!creation || row.profile_id === current.profileId);
    check(result && Object.keys(result).sort().join(',') === 'battle,events,replayed' && result.replayed === false);
    const b = result.battle;
    check(b && Object.keys(b).sort().join(',') === 'createdAt,id,profileId,revision,scenario,state,updatedAt');
    check(b.id === current.id && b.profileId === current.profileId && b.createdAt === current.createdAt && integer(b.updatedAt) && b.updatedAt >= b.createdAt && b.updatedAt <= current.updatedAt);
    check(integer(b.revision, 1) && b.revision <= current.revision && b.revision === (creation ? 1 : input.expectedRevision + 1));
    check(isDeepStrictEqual(b.scenario, current.scenario));
    check(isDeepStrictEqual(validateState(b.scenario.definition, b.state), b.state));
    check(b.state.actionIndex + 1 === b.revision);
    if (b.revision === current.revision) check(isDeepStrictEqual(b.state, current.state) && b.updatedAt === current.updatedAt);
    check(Array.isArray(result.events) && result.events.length > 0 && result.events.length <= 100000);
    check(result.events.every(e => e && typeof e === 'object' && !Array.isArray(e) && events.has(e.type)));
    const last = result.events.at(-1);
    check(last.type === 'StateUpdated' && isDeepStrictEqual(last.state, b.state));
    if (creation) {
      check(!Object.hasOwn(input, 'encounterId') || b.scenario.encounterId === input.encounterId);
      const first = result.events[0];
      check(b.updatedAt === b.createdAt && first.type === 'BattleStarted' && first.definitionId === b.state.definitionId && integer(first.seed) && first.seed <= 0xffffffff && (!('seed' in input) || input.seed === first.seed));
    } else {
      check(!result.events.some(e => e.type === 'BattleStarted'));
      const played = result.events.filter(e => e.type === 'CardPlayed');
      check(input.type === 'play-card'
        ? played.length === 1 && result.events[0] === played[0] && played[0].instanceId === input.instanceId
        : played.length === 0);
    }
    return result;
  }
  async get(profileId, id, session = null) { return this.decode(await this.battles.findOne({ id, profile_id: profileId }).session(session).lean()); }
  async list(profileId) {
    return (await this.battles.find({ profile_id: profileId }).sort({ created_at: 1, id: 1 }).lean()).map(row => {
      const b = this.decode(row);
      return { id: b.id, revision: b.revision, definitionId: b.state.definitionId, status: b.state.status, round: b.state.round, createdAt: b.createdAt, updatedAt: b.updatedAt };
    });
  }
  receipt(fields, requestJson, result) {
    const resultJson = JSON.stringify(result);
    check(bounded(resultJson));
    return { ...fields, schemaVersion: 1, request_json: requestJson, request_hash: hash(requestJson), result_json: resultJson, result_hash: hash(resultJson) };
  }
  async create(profileId, scenario, input, { selectScenario = null } = {}) {
    if (typeof profileId !== 'string' || !UUID.test(profileId)) throw new ServiceError('INVALID_INPUT', 'A valid profile ID is required');
    const requestJson = request(input, true);
    return runTransaction(this.connection, async session => {
      const prior = await this.creations.findOne({ profile_id: profileId, request_id: input.requestId }).session(session).lean();
      if (prior) {
        if (prior.request_json !== requestJson) throw new ServiceError('COMMAND_CONFLICT', 'Request ID was used for a different creation', 409);
        return { ...this.validateReceipt(prior, await this.get(profileId, prior.battle_id, session), 'creation'), replayed: true };
      }
      const selected = selectScenario ? await selectScenario(session) : scenario;
      requireSelectedScenario(selected, input);
      const sourceJson = JSON.stringify(selected);
      if (!bounded(sourceJson, 4 * 1024 * 1024)) throw new Error('Battle scenario exceeds size budget');
      const seed = input.seed ?? randomInt(0, 0x100000000);
      const owned = materializeEnemySelection(JSON.parse(sourceJson), seed), scenarioJson = JSON.stringify(owned);
      if (!bounded(scenarioJson, 4 * 1024 * 1024)) throw new Error('Battle scenario exceeds size budget');
      const next = createBattle(owned.definition, seed), stateJson = JSON.stringify(next.state), id = randomUUID(), now = Date.now();
      const row = { schemaVersion: 1, id, profile_id: profileId, scenario_json: scenarioJson, scenario_hash: hash(scenarioJson), state_json: stateJson, state_hash: hash(stateJson), revision: 1, created_at: now, updated_at: now };
      const result = { battle: this.decode(row), events: next.events, replayed: false };
      const receipt = this.receipt({ profile_id: profileId, request_id: input.requestId, battle_id: id }, requestJson, result);
      this.validateReceipt(receipt, result.battle, 'creation');
      await this.battles.create([row], { session });
      await this.creations.create([receipt], { session });
      return result;
    });
  }
  async act(profileId, id, input) {
    const requestJson = request(input, false);
    return runTransaction(this.connection, async session => {
      const current = await this.get(profileId, id, session);
      const prior = await this.commands.findOne({ battle_id: id, command_id: input.requestId }).session(session).lean();
      if (prior) {
        if (prior.request_json !== requestJson) throw new ServiceError('COMMAND_CONFLICT', 'Request ID was used for a different command', 409);
        return { ...this.validateReceipt(prior, current, 'command'), replayed: true };
      }
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Battle changed; reload it before acting again', 409);
      let next;
      try { next = input.type === 'play-card' ? playCard(current.scenario.definition, current.state, input.instanceId) : endTurn(current.scenario.definition, current.state); }
      catch (error) { if (error instanceof TypeError || error instanceof RangeError) throw new ServiceError('INVALID_BATTLE_ACTION', error.message); throw error; }
      if (!integer(current.revision + 1, 1)) throw new Error('Battle revision exhausted');
      const stateJson = JSON.stringify(next.state), now = Math.max(Date.now(), current.updatedAt);
      check(bounded(stateJson));
      const result = { battle: { ...current, state: next.state, revision: current.revision + 1, updatedAt: now }, events: next.events, replayed: false };
      const receipt = this.receipt({ battle_id: id, command_id: input.requestId }, requestJson, result);
      this.validateReceipt(receipt, result.battle, 'command');
      const update = await this.battles.updateOne({ id, profile_id: profileId, revision: current.revision }, { $set: { state_json: stateJson, state_hash: hash(stateJson), revision: result.battle.revision, updated_at: now } }, { session, runValidators: true });
      if (update.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Battle changed; reload it before acting again', 409);
      await this.commands.create([receipt], { session });
      return result;
    });
  }
  close() { /* Connection lifecycle belongs to the application. */ }
}
