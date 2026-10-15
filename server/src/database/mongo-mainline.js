import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { ServiceError, requireObject } from '../errors.js';
import { completedChallenge, projectMainline } from '../mainline.js';
import { runTransaction } from './transaction.js';
import { UUID, REQUEST, integer, requireProfileId, stored, exactKeys, options, numberField, initModels } from './validation.js';

const sha = text => createHash('sha256').update(text).digest('hex');
/** One bounded chapter document per profile; independent immutable request receipts. */
export class MongoMainlineStore {
  constructor(connection, definition, profiles, battles) {
    Object.assign(this, { connection, definition, profiles, battles });
    const Schema = connection.base.Schema;
    const completion = new Schema({ challengeId: numberField(1), battleId: { type: String, required: true, match: UUID },
      battleRevision: numberField(1), completedAt: numberField() }, { ...options, _id: false });
    const state = new Schema({ _id: { type: String, required: true }, profileId: { type: String, required: true, match: UUID },
      activityId: { type: Number, required: true, enum: [2] }, schemaVersion: { type: Number, required: true, enum: [1] },
      contentId: { type: String, required: true }, revision: numberField(1), updatedAt: numberField(),
      completed: { type: [completion], required: true, validate: value => value.length <= definition.nodes.length } },
    { ...options, collection: 'mainline_states' });
    state.index({ profileId: 1, activityId: 1 }, { unique: true });
    const request = new Schema({ _id: { type: String, required: true }, schemaVersion: { type: Number, required: true, enum: [1] },
      profileId: { type: String, required: true, match: UUID }, requestId: { type: String, required: true, match: REQUEST },
      payload: { type: String, required: true }, result: { type: String, required: true }, resultHash: { type: String, required: true } },
    { ...options, collection: 'mainline_requests' });
    request.index({ profileId: 1, requestId: 1 }, { unique: true });
    this.states = connection.models.HczsMainlineState ?? connection.model('HczsMainlineState', state);
    this.requests = connection.models.HczsMainlineRequest ?? connection.model('HczsMainlineRequest', request);
  }
  async init() { await initModels([this.states, this.requests]); }
  key(id) { return JSON.stringify([id, this.definition.activityId]); }
  map(row, id) {
    if (!row) return { profileId: id, revision: 0, completed: [], updatedAt: null };
    stored(exactKeys(row, ['_id', 'schemaVersion', 'profileId', 'activityId', 'contentId', 'revision', 'updatedAt', 'completed'])
      && row._id === this.key(id) && row.schemaVersion === 1 && row.profileId === id && row.activityId === this.definition.activityId
      && row.contentId === this.definition.contentId && integer(row.revision, 1) && integer(row.updatedAt)
      && Array.isArray(row.completed) && row.completed.length <= this.definition.nodes.length && row.revision === row.completed.length);
    const ids = new Set(), battleIds = new Set();
    for (const done of row.completed) {
      stored(exactKeys(done, ['challengeId', 'battleId', 'battleRevision', 'completedAt']) && typeof done.battleId === 'string'
        && UUID.test(done.battleId) && integer(done.battleRevision, 1) && integer(done.completedAt) && done.completedAt <= row.updatedAt
        && !ids.has(done.challengeId) && !battleIds.has(done.battleId));
      const node = this.definition.nodes.find(n => n.id === done.challengeId);
      stored(node && node.predecessors.every(id => ids.has(id)));
      ids.add(done.challengeId); battleIds.add(done.battleId);
    }
    return { profileId: id, revision: row.revision, completed: row.completed, updatedAt: row.updatedAt };
  }
  async get(id) {
    requireProfileId(id); await this.profiles.get(id);
    return projectMainline(this.definition, this.map(await this.states.findById(this.key(id)).lean(), id));
  }
  async settle(id, input) {
    requireProfileId(id);
    requireObject(input, ['requestId', 'expectedRevision', 'contentId', 'battleId'], ['requestId', 'expectedRevision', 'contentId', 'battleId']);
    if (typeof input.requestId !== 'string' || !REQUEST.test(input.requestId) || !integer(input.expectedRevision)
      || input.expectedRevision >= Number.MAX_SAFE_INTEGER || typeof input.contentId !== 'string' || !/^[a-f0-9]{64}$/.test(input.contentId)
      || typeof input.battleId !== 'string' || !UUID.test(input.battleId)) throw new ServiceError('INVALID_INPUT', 'A valid settlement command is required');
    const payload = JSON.stringify({ expectedRevision: input.expectedRevision, contentId: input.contentId, battleId: input.battleId });
    const requestKey = JSON.stringify([id, input.requestId]);
    return runTransaction(this.connection, async session => {
      await this.profiles.get(id, session);
      const prior = await this.requests.findById(requestKey).session(session).lean();
      if (prior) {
        stored(exactKeys(prior, ['_id', 'schemaVersion', 'profileId', 'requestId', 'payload', 'result', 'resultHash'])
          && prior._id === requestKey && prior.schemaVersion === 1 && prior.profileId === id && prior.requestId === input.requestId
          && typeof prior.payload === 'string' && typeof prior.result === 'string' && sha(prior.result) === prior.resultHash);
        if (prior.payload !== payload) throw new ServiceError('REQUEST_ID_CONFLICT', 'requestId belongs to a different settlement', 409);
        let result; try { result = JSON.parse(prior.result); } catch { stored(false); }
        stored(result?.campaign?.profileId === id && result.campaign.contentId === input.contentId
          && result.campaign.revision === input.expectedRevision + 1 && result.settlement?.battleId === input.battleId
          && Array.isArray(result.rewards) && result.rewards.length === 0 && result.replayed === false);
        const c = result.campaign;
        const historical = this.map({ _id: this.key(id), schemaVersion: 1, profileId: id, activityId: this.definition.activityId,
          contentId: c.contentId, revision: c.revision, updatedAt: c.updatedAt, completed: c.completed }, id);
        stored(exactKeys(result, ['campaign', 'settlement', 'rewards', 'replayed'])
          && isDeepStrictEqual(projectMainline(this.definition, historical), c)
          && c.completed.some(row => isDeepStrictEqual(row, result.settlement)));
        return { ...result, replayed: true };
      }
      if (input.contentId !== this.definition.contentId) throw new ServiceError('CONTENT_CHANGED', 'Reload the mainline definition before settling', 409);
      const current = this.map(await this.states.findById(this.key(id)).session(session).lean(), id);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Mainline progress changed; reload before settling', 409);
      const battle = await this.battles.get(id, input.battleId, session);
      const node = completedChallenge(this.definition, current, battle);
      const now = Math.max(Date.now(), current.updatedAt ?? 0);
      const done = { challengeId: node.id, battleId: battle.id, battleRevision: battle.revision, completedAt: now };
      const next = { ...current, revision: current.revision + 1, updatedAt: now, completed: [...current.completed, done] };
      if (current.revision === 0) await this.states.create([{ _id: this.key(id), schemaVersion: 1, profileId: id,
        activityId: this.definition.activityId, contentId: this.definition.contentId, revision: next.revision, updatedAt: now, completed: next.completed }], { session });
      else {
        const saved = await this.states.updateOne({ _id: this.key(id), revision: current.revision },
          { $set: { revision: next.revision, updatedAt: now, completed: next.completed } }, { session, runValidators: true });
        if (saved.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Mainline progress changed', 409);
      }
      const campaign = projectMainline(this.definition, next);
      const result = { campaign, settlement: done, rewards: [], replayed: false };
      const text = JSON.stringify(result);
      await this.requests.create([{ _id: requestKey, schemaVersion: 1, profileId: id, requestId: input.requestId,
        payload, result: text, resultHash: sha(text) }], { session });
      return result;
    });
  }
}
