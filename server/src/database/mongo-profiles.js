import { randomUUID } from 'node:crypto';
import { ServiceError, displayName, requireObject } from '../errors.js';
import { runTransaction } from './transaction.js';
import { UUID, integer, requireProfileId, stored, exactKeys, options, numberField, initModels } from './validation.js';

export class MongoProfileStore {
  constructor(connection) {
    this.connection = connection;
    const schema = new connection.base.Schema({
      _id: { type: String, required: true, match: UUID }, schemaVersion: { type: Number, required: true, enum: [1] },
      displayName: { type: String, required: true }, selectedCharacterId: { type: Number, default: null, validate: v => v === null || integer(v, 1) },
      revision: numberField(1), createdAt: numberField(), updatedAt: numberField(),
    }, { ...options, collection: 'profiles' });
    schema.index({ createdAt: 1, _id: 1 });
    this.model = connection.models.HczsProfile ?? connection.model('HczsProfile', schema);
  }
  async init() { await initModels([this.model]); }
  map(row) {
    if (!row) return null;
    stored(exactKeys(row, ['_id', 'schemaVersion', 'displayName', 'selectedCharacterId', 'revision', 'createdAt', 'updatedAt']));
    stored(typeof row._id === 'string' && UUID.test(row._id) && row.schemaVersion === 1 && integer(row.revision, 1) && integer(row.createdAt) && integer(row.updatedAt) && row.updatedAt >= row.createdAt && (row.selectedCharacterId === null || integer(row.selectedCharacterId, 1)));
    try { displayName(row.displayName); } catch { stored(false); }
    return { id: row._id, displayName: row.displayName, selectedCharacterId: row.selectedCharacterId, revision: row.revision, createdAt: row.createdAt, updatedAt: row.updatedAt };
  }
  async list() { return (await this.model.find().sort({ createdAt: 1, _id: 1 }).lean()).map(row => this.map(row)); }
  async get(id, session = null) {
    requireProfileId(id); const result = this.map(await this.model.findById(id).session(session).lean());
    if (!result) throw new ServiceError('PROFILE_NOT_FOUND', 'Local profile does not exist', 404);
    return result;
  }
  async create(input, session = null) {
    requireObject(input, ['displayName'], ['displayName']); const name = displayName(input.displayName), id = randomUUID(), now = Date.now();
    const row = { _id: id, schemaVersion: 1, displayName: name, selectedCharacterId: null, revision: 1, createdAt: now, updatedAt: now };
    if (session) await this.model.create([row], { session });
    else await this.model.create(row);
    return this.map(row);
  }
  async update(id, input, characterIds, transactionSession = null) {
    requireProfileId(id); requireObject(input, ['expectedRevision', 'displayName', 'selectedCharacterId'], ['expectedRevision']);
    if (!integer(input.expectedRevision, 1) || input.expectedRevision >= Number.MAX_SAFE_INTEGER || Object.keys(input).length < 2) throw new ServiceError('INVALID_INPUT', 'A valid expectedRevision and at least one change are required');
    if ('displayName' in input) displayName(input.displayName);
    if ('selectedCharacterId' in input && input.selectedCharacterId !== null && (!integer(input.selectedCharacterId, 1) || !characterIds.has(input.selectedCharacterId))) throw new ServiceError('UNKNOWN_CHARACTER', 'Character is absent from the recovered catalog');
    const update = async session => {
      const current = this.map(await this.model.findById(id).session(session).lean());
      if (!current) throw new ServiceError('PROFILE_NOT_FOUND', 'Local profile does not exist', 404);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Profile changed; reload it before saving again', 409);
      const set = { displayName: input.displayName ?? current.displayName, selectedCharacterId: 'selectedCharacterId' in input ? input.selectedCharacterId : current.selectedCharacterId, revision: current.revision + 1, updatedAt: Math.max(Date.now(), current.updatedAt) };
      const result = await this.model.updateOne({ _id: id, revision: current.revision }, { $set: set }, { session, runValidators: true });
      if (result.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Profile changed; reload it before saving again', 409);
      return { ...current, ...set };
    };
    return transactionSession ? update(transactionSession) : runTransaction(this.connection, update);
  }
  async close() {} // Shared connection is owned by the application lifecycle.
}
