import { randomUUID } from 'node:crypto';
import { ServiceError, requireObject, displayName } from '../errors.js';
import { validateSettings } from '../operational-settings.js';
import { runTransaction } from './transaction.js';
import { integer, REQUEST, UUID, stored, options, numberField, initModels, exactKeys } from './validation.js';

const actions = ['profile.create', 'profile.rename', 'hall.select', 'config.draft', 'config.publish', 'config.rollback'];
function revision(value) {
  if (!integer(value, 1) || value >= Number.MAX_SAFE_INTEGER) throw new ServiceError('INVALID_INPUT', 'A safe positive expectedRevision is required');
}
function requestId(value) {
  if (typeof value !== 'string' || !REQUEST.test(value)) throw new ServiceError('INVALID_INPUT', 'A safe requestId is required');
}
function savedSettings(value) {
  try { return validateSettings(value); } catch { stored(false); }
}
function validateAudit(value) {
  stored(value && actions.includes(value.action) && value.actor === 'local-admin' &&
    typeof value._id === 'string' && UUID.test(value._id) && integer(value.occurredAt));
  const summary = value.summary;
  if (value.action.startsWith('profile.')) {
    stored(value.targetType === 'profile' && UUID.test(value.targetId) &&
      exactKeys(summary, ['displayName', 'revision']) && integer(summary.revision, 1));
    try { displayName(summary.displayName); } catch { stored(false); }
  } else if (value.action === 'hall.select') {
    stored(value.targetType === 'hall' && UUID.test(value.targetId) &&
      exactKeys(summary, ['selectedHeroId', 'revision', 'requestId']) && integer(summary.revision, 1) &&
      (summary.selectedHeroId === null || integer(summary.selectedHeroId, 1)) && REQUEST.test(summary.requestId));
  } else {
    const keys = value.action === 'config.draft' ? ['revision', 'settings'] : ['version', 'revision', 'sourceVersion', 'settings'];
    stored(value.targetType === 'config' && value.targetId === 'config' && exactKeys(summary, keys) && integer(summary.revision, 1));
    if (value.action !== 'config.draft') stored(integer(summary.version, 1) &&
      (value.action === 'config.rollback' ? integer(summary.sourceVersion) && summary.sourceVersion < summary.version : summary.sourceVersion === null));
    savedSettings(summary.settings);
  }
}

/** Independent hczs admin collections on the application-owned Mongoose connection. */
export class MongoOperationsStore {
  constructor(connection) {
    this.connection = connection;
    const Schema = connection.base.Schema;
    const settings = new Schema({ serverName: { type: String, required: true }, motd: { type: String, default: '' },
      allowNewProfiles: { type: Boolean, required: true }, allowNewBattles: { type: Boolean, required: true },
      defaultEncounterId: { type: String, default: null } }, { ...options, _id: false });
    const state = new Schema({ _id: { type: String, required: true, enum: ['config'] }, schemaVersion: numberField(1),
      revision: numberField(1), settings: { type: settings, required: true }, activeVersion: numberField(), updatedAt: numberField() },
    { ...options, collection: 'hczs_admin_config' });
    const release = new Schema({ _id: numberField(), schemaVersion: numberField(1), settings: { type: settings, required: true },
      publishedAt: numberField(), kind: { type: String, enum: ['initial', 'publish', 'rollback'], required: true },
      sourceVersion: { type: Number, default: null }, actor: { type: String, enum: ['system-init', 'local-admin'], required: true } },
    { ...options, collection: 'hczs_admin_releases' });
    const receipt = new Schema({ _id: { type: String, required: true, match: REQUEST }, schemaVersion: numberField(1),
      payload: { type: String, required: true }, result: { type: Schema.Types.Mixed, required: true } },
    { ...options, collection: 'hczs_admin_requests' });
    const audit = new Schema({ _id: { type: String, required: true }, schemaVersion: numberField(1),
      action: { type: String, enum: actions, required: true }, actor: { type: String, enum: ['local-admin'], required: true },
      targetType: { type: String, enum: ['profile', 'hall', 'config'], required: true }, targetId: { type: String, required: true },
      summary: { type: Schema.Types.Mixed, required: true }, occurredAt: numberField() },
    { ...options, collection: 'hczs_admin_logs' });
    audit.index({ occurredAt: -1, _id: -1 });
    this.states = connection.models.HczsAdminConfig ?? connection.model('HczsAdminConfig', state);
    this.releases = connection.models.HczsAdminRelease ?? connection.model('HczsAdminRelease', release);
    this.requests = connection.models.HczsAdminRequest ?? connection.model('HczsAdminRequest', receipt);
    this.logs = connection.models.HczsAdminLog ?? connection.model('HczsAdminLog', audit);
  }
  async init(defaults) {
    validateSettings(defaults);
    await initModels([this.states, this.releases, this.requests, this.logs]);
    await runTransaction(this.connection, async session => {
      const current = await this.states.findById('config').session(session).lean();
      if (!current) {
        // Refuse partial/corrupt admin state rather than resetting published history.
        stored(await this.releases.countDocuments().session(session) === 0 && await this.requests.countDocuments().session(session) === 0 &&
          await this.logs.countDocuments().session(session) === 0);
        const now = Date.now();
        await this.releases.create([{ _id: 0, schemaVersion: 1, settings: defaults, publishedAt: now,
          kind: 'initial', sourceVersion: null, actor: 'system-init' }], { session });
        await this.states.create([{ _id: 'config', schemaVersion: 1, revision: 1, settings: defaults,
          activeVersion: 0, updatedAt: now }], { session });
      }
      await this.get(session);
    });
  }
  mapState(row) {
    stored(exactKeys(row, ['_id', 'schemaVersion', 'revision', 'settings', 'activeVersion', 'updatedAt']) &&
      row._id === 'config' && row.schemaVersion === 1 && integer(row.revision, 1) && integer(row.activeVersion) &&
      row.activeVersion < row.revision && integer(row.updatedAt));
    return { revision: row.revision, settings: savedSettings(row.settings), updatedAt: row.updatedAt };
  }
  mapRelease(row) {
    stored(exactKeys(row, ['_id', 'schemaVersion', 'settings', 'publishedAt', 'kind', 'sourceVersion', 'actor']) &&
      row.schemaVersion === 1 && integer(row._id) && integer(row.publishedAt) &&
      (row._id === 0 ? row.kind === 'initial' && row.actor === 'system-init' && row.sourceVersion === null
        : row.actor === 'local-admin' && (row.kind === 'publish' ? row.sourceVersion === null
          : row.kind === 'rollback' && integer(row.sourceVersion) && row.sourceVersion < row._id)));
    return { version: row._id, settings: savedSettings(row.settings), publishedAt: row.publishedAt,
      kind: row.kind, sourceVersion: row.sourceVersion };
  }
  async get(session = null) {
    const row = await this.states.findById('config').session(session).lean();
    const draft = this.mapState(row);
    const active = this.mapRelease(await this.releases.findById(row.activeVersion).session(session).lean());
    const releases = (await this.releases.find({ _id: { $lte: active.version } }).sort({ _id: -1 }).limit(100).session(session).lean())
      .map(value => this.mapRelease(value));
    stored(releases.length === Math.min(active.version + 1, 100) && releases.every((value, index) => value.version === active.version - index));
    return { supported: true, draft, active, releases };
  }
  async active(session = null) {
    const row = await this.states.findById('config').session(session).lean();
    this.mapState(row);
    return this.mapRelease(await this.releases.findById(row.activeVersion).session(session).lean());
  }
  async audit(action, description, session) {
    if (!actions.includes(action)) throw new Error('Unknown admin audit action');
    const log = { _id: randomUUID(), schemaVersion: 1, action, actor: 'local-admin', ...description, occurredAt: Date.now() };
    validateAudit(log);
    await this.logs.create([log], { session });
  }
  async audited(action, operation, describe) {
    return runTransaction(this.connection, async session => {
      const result = await operation(session);
      if (!result?.replayed) await this.audit(action, describe(result), session);
      return result;
    });
  }
  async updateDraft(input) {
    requireObject(input, ['expectedRevision', 'settings'], ['expectedRevision', 'settings']);
    revision(input.expectedRevision);
    const settings = validateSettings(input.settings);
    return runTransaction(this.connection, async session => {
      const row = await this.states.findById('config').session(session).lean();
      const current = this.mapState(row);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Configuration changed; reload before saving', 409);
      const result = await this.states.updateOne({ _id: 'config', revision: current.revision },
        { $set: { revision: current.revision + 1, settings, updatedAt: Math.max(Date.now(), current.updatedAt) } }, { session, runValidators: true });
      if (result.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Configuration changed; reload before saving', 409);
      await this.audit('config.draft', { targetType: 'config', targetId: 'config',
        summary: { revision: current.revision + 1, settings } }, session);
      return this.get(session);
    });
  }
  async publish(input, kind, assertEnabled) {
    const keys = kind === 'rollback' ? ['expectedRevision', 'version', 'requestId'] : ['expectedRevision', 'requestId'];
    requireObject(input, keys, keys);
    revision(input.expectedRevision); requestId(input.requestId);
    if (kind === 'rollback' && !integer(input.version)) throw new ServiceError('INVALID_INPUT', 'A nonnegative rollback version is required');
    const payload = JSON.stringify({ kind, expectedRevision: input.expectedRevision,
      ...(kind === 'rollback' ? { version: input.version } : {}) });
    return runTransaction(this.connection, async session => {
      const receipt = await this.requests.findById(input.requestId).session(session).lean();
      if (receipt) {
        stored(exactKeys(receipt, ['_id', 'schemaVersion', 'payload', 'result']) && receipt.schemaVersion === 1 &&
          typeof receipt.payload === 'string' && receipt.result?.supported === true);
        if (receipt.payload !== payload) throw new ServiceError('REQUEST_ID_CONFLICT', 'requestId belongs to another configuration operation', 409);
        this.validateSnapshot(receipt.result);
        stored(receipt.result.draft.revision === input.expectedRevision + 1 && receipt.result.active.kind === kind &&
          receipt.result.active.sourceVersion === (kind === 'rollback' ? input.version : null) &&
          JSON.stringify(receipt.result.draft.settings) === JSON.stringify(receipt.result.active.settings));
        return { config: receipt.result, replayed: true };
      }
      const row = await this.states.findById('config').session(session).lean();
      const current = this.mapState(row);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Configuration changed; reload before publishing', 409);
      const settings = kind === 'rollback'
        ? this.mapReleaseOrMissing(await this.releases.findById(input.version).session(session).lean()).settings : current.settings;
      assertEnabled(settings);
      if (row.activeVersion >= Number.MAX_SAFE_INTEGER - 1) throw new ServiceError('CONFIG_VERSION_EXHAUSTED', 'Configuration version limit reached', 409);
      const version = row.activeVersion + 1, now = Math.max(Date.now(), current.updatedAt);
      await this.releases.create([{ _id: version, schemaVersion: 1, settings, publishedAt: now, kind,
        sourceVersion: kind === 'rollback' ? input.version : null, actor: 'local-admin' }], { session });
      const changed = await this.states.updateOne({ _id: 'config', revision: current.revision },
        { $set: { revision: current.revision + 1, settings, activeVersion: version, updatedAt: now } }, { session, runValidators: true });
      if (changed.modifiedCount !== 1) throw new ServiceError('REVISION_CONFLICT', 'Configuration changed; reload before publishing', 409);
      await this.audit(`config.${kind}`, { targetType: 'config', targetId: 'config',
        summary: { version, revision: current.revision + 1, sourceVersion: kind === 'rollback' ? input.version : null, settings } }, session);
      const config = await this.get(session);
      await this.requests.create([{ _id: input.requestId, schemaVersion: 1, payload, result: config }], { session });
      return { config, replayed: false };
    });
  }
  mapReleaseOrMissing(row) {
    if (!row) throw new ServiceError('CONFIG_VERSION_NOT_FOUND', 'Configuration release does not exist', 404);
    return this.mapRelease(row);
  }
  validateSnapshot(value) {
    stored(exactKeys(value, ['supported', 'draft', 'active', 'releases']) && value.supported === true &&
      exactKeys(value.draft, ['revision', 'settings', 'updatedAt']) && integer(value.draft.revision, 1) && integer(value.draft.updatedAt) &&
      Array.isArray(value.releases) && value.releases.length >= 1 && value.releases.length <= 100);
    savedSettings(value.draft.settings);
    for (const release of [value.active, ...value.releases]) {
      stored(exactKeys(release, ['version', 'settings', 'publishedAt', 'kind', 'sourceVersion']));
      this.mapRelease({ _id: release.version, schemaVersion: 1, settings: release.settings, publishedAt: release.publishedAt,
        kind: release.kind, sourceVersion: release.sourceVersion, actor: release.version === 0 ? 'system-init' : 'local-admin' });
    }
    stored(value.active.version < value.draft.revision && JSON.stringify(value.active) === JSON.stringify(value.releases[0]) &&
      value.releases.length === Math.min(value.active.version + 1, 100) &&
      value.releases.every((release, index) => release.version === value.active.version - index));
  }
  async recentLogs() {
    return (await this.logs.find().sort({ occurredAt: -1, _id: -1 }).limit(100).lean()).map(row => {
      stored(exactKeys(row, ['_id', 'schemaVersion', 'action', 'actor', 'targetType', 'targetId', 'summary', 'occurredAt']) &&
        row.schemaVersion === 1);
      validateAudit(row);
      return { id: row._id, action: row.action, actor: row.actor, targetType: row.targetType, targetId: row.targetId,
        summary: row.summary, occurredAt: row.occurredAt };
    });
  }
}
