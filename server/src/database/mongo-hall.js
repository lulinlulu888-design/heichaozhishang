import { ServiceError, requireObject } from '../errors.js';
import { runTransaction } from './transaction.js';
import { UUID, REQUEST, integer, requireProfileId, stored, exactKeys, options, numberField, initModels } from './validation.js';
const nullableHero = { type: Number, default: null, validate: v => v === null || integer(v, 1) };
function hallValue(hall, id) {
  stored(exactKeys(hall, ['profileId', 'revision', 'selectedHeroId', 'updatedAt']) && hall.profileId === id && integer(hall.revision, 1) && (hall.selectedHeroId === null || integer(hall.selectedHeroId, 1)) && integer(hall.updatedAt));
  return hall;
}
export class MongoHallStore {
  constructor(connection) {
    this.connection = connection;
    const Schema = connection.base.Schema;
    const state = new Schema({ _id: { type: String, required: true, match: UUID }, schemaVersion: { type: Number, required: true, enum: [1] }, revision: numberField(1), selectedHeroId: nullableHero, updatedAt: numberField() }, { ...options, collection: 'hall_states' });
    const receipt = new Schema({ profileId: { type: String, required: true, match: UUID }, revision: numberField(1), selectedHeroId: nullableHero, updatedAt: numberField() }, { ...options, _id: false });
    const request = new Schema({ _id: { type: String, required: true }, schemaVersion: { type: Number, required: true, enum: [1] }, profileId: { type: String, required: true, match: UUID }, requestId: { type: String, required: true, match: REQUEST }, payload: { type: String, required: true }, receipt: { type: receipt, required: true } }, { ...options, collection: 'hall_requests' });
    request.index({ profileId: 1, requestId: 1 }, { unique: true });
    this.states = connection.models.HczsHallState ?? connection.model('HczsHallState', state);
    this.requests = connection.models.HczsHallRequest ?? connection.model('HczsHallRequest', request);
  }
  async init() { await initModels([this.states, this.requests]); }
  map(row, id) {
    if (!row) return { profileId: id, revision: 0, selectedHeroId: null, updatedAt: null };
    stored(exactKeys(row, ['_id', 'schemaVersion', 'revision', 'selectedHeroId', 'updatedAt']) && row._id === id && row.schemaVersion === 1);
    return hallValue({ profileId: row._id, revision: row.revision, selectedHeroId: row.selectedHeroId, updatedAt: row.updatedAt }, id);
  }
  async get(id) { requireProfileId(id); return this.map(await this.states.findById(id).lean(), id); }
  async update(id, input, selectableIds, transactionSession = null) {
    requireProfileId(id);
    requireObject(input, ['requestId', 'expectedRevision', 'selectedHeroId'], ['requestId', 'expectedRevision', 'selectedHeroId']);
    if (Object.keys(input).length !== 3 || typeof input.requestId !== 'string' || !REQUEST.test(input.requestId) || !integer(input.expectedRevision) || input.expectedRevision >= Number.MAX_SAFE_INTEGER) throw new ServiceError('INVALID_INPUT', 'A safe requestId and nonnegative expectedRevision are required');
    if (input.selectedHeroId !== null && !integer(input.selectedHeroId, 1)) throw new ServiceError('HALL_HERO_UNAVAILABLE', 'Hero is not available in the recovered hall catalog');
    const payload = JSON.stringify({ expectedRevision: input.expectedRevision, selectedHeroId: input.selectedHeroId });
    const requestKey = JSON.stringify([id, input.requestId]);
    const update = async session => {
      const saved = await this.requests.findById(requestKey).session(session).lean();
      if (saved) {
        stored(exactKeys(saved, ['_id', 'schemaVersion', 'profileId', 'requestId', 'payload', 'receipt']) && saved._id === requestKey && saved.schemaVersion === 1 && saved.profileId === id && saved.requestId === input.requestId && typeof saved.payload === 'string');
        let original; try { original = JSON.parse(saved.payload); } catch { stored(false); }
        stored(exactKeys(original, ['expectedRevision', 'selectedHeroId']) && integer(original.expectedRevision) && original.expectedRevision < Number.MAX_SAFE_INTEGER && (original.selectedHeroId === null || integer(original.selectedHeroId, 1)) && JSON.stringify(original) === saved.payload);
        const hall = hallValue(saved.receipt, id);
        stored(hall.revision === original.expectedRevision + 1 && hall.selectedHeroId === original.selectedHeroId);
        if (saved.payload !== payload) throw new ServiceError('REQUEST_ID_CONFLICT', 'requestId already belongs to a different hall update', 409);
        return { hall, replayed: true };
      }
      if (input.selectedHeroId !== null && !selectableIds.has(input.selectedHeroId)) throw new ServiceError('HALL_HERO_UNAVAILABLE', 'Hero is not available in the recovered hall catalog');
      const current = this.map(await this.states.findById(id).session(session).lean(), id);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Hall state changed; reload it before saving', 409);
      const hall = { profileId: id, revision: current.revision + 1, selectedHeroId: input.selectedHeroId, updatedAt: Math.max(Date.now(), current.updatedAt ?? 0) };
      if (current.revision === 0) await this.states.create([{ _id: id, schemaVersion: 1, revision: hall.revision, selectedHeroId: hall.selectedHeroId, updatedAt: hall.updatedAt }], { session });
      else {
        const result = await this.states.updateOne({ _id: id, revision: current.revision }, { $set: { revision: hall.revision, selectedHeroId: hall.selectedHeroId, updatedAt: hall.updatedAt } }, { session, runValidators: true });
        if (result.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Hall state changed; reload it before saving', 409);
      }
      await this.requests.create([{ _id: requestKey, schemaVersion: 1, profileId: id, requestId: input.requestId, payload, receipt: hall }], { session });
      return { hall, replayed: false };
    };
    return transactionSession ? update(transactionSession) : runTransaction(this.connection, update);
  }
  async close() {} // Application owns the shared connection.
}
