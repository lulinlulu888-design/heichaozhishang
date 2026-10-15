import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { ServiceError, requireObject } from './errors.js';

const APPLICATION_ID = 0x4843484c; // HCHL: independent local hall state, not legacy accounts.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function profileId(value) {
  if (typeof value !== 'string' || !UUID.test(value)) throw new ServiceError('INVALID_INPUT', 'A canonical local profile UUID is required');
}

export class HallStore {
  constructor(path) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    try {
      this.db.exec('PRAGMA busy_timeout = 5000;');
      const identity = () => ({
        id: this.db.prepare('PRAGMA application_id').get().application_id,
        version: this.db.prepare('PRAGMA user_version').get().user_version,
        count: this.db.prepare("SELECT count(*) AS count FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").get().count,
      });
      let current = identity();
      if (current.id === 0 && current.version === 0 && current.count === 0) {
        this.db.exec('BEGIN IMMEDIATE');
        try {
          current = identity();
          if (current.id === 0 && current.version === 0 && current.count === 0) this.db.exec(`
            CREATE TABLE hall_states (
              profile_id TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision >= 1),
              selected_hero_id INTEGER, updated_at INTEGER NOT NULL
            ) STRICT;
            CREATE TABLE hall_requests (
              profile_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, receipt TEXT NOT NULL,
              PRIMARY KEY(profile_id, request_id)
            ) STRICT;
            PRAGMA application_id = ${APPLICATION_ID}; PRAGMA user_version = 1;`);
          else if (current.id !== APPLICATION_ID || current.version !== 1) throw new Error('Unsupported hall save identity/version');
          this.db.exec('COMMIT');
        } catch (error) { this.db.exec('ROLLBACK'); throw error; }
      } else if (current.id !== APPLICATION_ID || current.version !== 1) {
        throw new Error(`Unsupported hall save identity/version (${current.id}/${current.version}); existing data was not migrated`);
      }
      // Only a recognized independent hall database may change persistent journal settings.
      this.db.exec('PRAGMA journal_mode = WAL; PRAGMA synchronous = FULL;');
    } catch (error) { this.db.close(); throw error; }
  }

  get(id) {
    profileId(id);
    const row = this.db.prepare('SELECT * FROM hall_states WHERE profile_id = ?').get(id);
    return row ? { profileId: id, revision: row.revision, selectedHeroId: row.selected_hero_id, updatedAt: row.updated_at }
      : { profileId: id, revision: 0, selectedHeroId: null, updatedAt: null };
  }

  update(id, input, selectableIds) {
    profileId(id);
    requireObject(input, ['requestId', 'expectedRevision', 'selectedHeroId'], ['requestId', 'expectedRevision', 'selectedHeroId']);
    if (Object.keys(input).length !== 3 || typeof input.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(input.requestId) ||
        !Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 0 || input.expectedRevision >= Number.MAX_SAFE_INTEGER) {
      throw new ServiceError('INVALID_INPUT', 'A safe requestId and nonnegative expectedRevision are required');
    }
    if (input.selectedHeroId !== null && (!Number.isSafeInteger(input.selectedHeroId) || input.selectedHeroId <= 0)) {
      throw new ServiceError('HALL_HERO_UNAVAILABLE', 'Hero is not available in the recovered hall catalog');
    }
    const payload = JSON.stringify({ expectedRevision: input.expectedRevision, selectedHeroId: input.selectedHeroId });
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const saved = this.db.prepare('SELECT payload, receipt FROM hall_requests WHERE profile_id = ? AND request_id = ?').get(id, input.requestId);
      if (saved) {
        if (saved.payload !== payload) throw new ServiceError('REQUEST_ID_CONFLICT', 'requestId already belongs to a different hall update', 409);
        const hall = JSON.parse(saved.receipt);
        this.db.exec('COMMIT');
        return { hall, replayed: true };
      }
      if (input.selectedHeroId !== null && !selectableIds.has(input.selectedHeroId)) {
        throw new ServiceError('HALL_HERO_UNAVAILABLE', 'Hero is not available in the recovered hall catalog');
      }
      const current = this.get(id);
      if (current.revision !== input.expectedRevision) throw new ServiceError('REVISION_CONFLICT', 'Hall state changed; reload it before saving', 409);
      const hall = { profileId: id, revision: current.revision + 1, selectedHeroId: input.selectedHeroId, updatedAt: Date.now() };
      this.db.prepare(`INSERT INTO hall_states VALUES (?, ?, ?, ?) ON CONFLICT(profile_id) DO UPDATE SET
        revision = excluded.revision, selected_hero_id = excluded.selected_hero_id, updated_at = excluded.updated_at`)
        .run(id, hall.revision, hall.selectedHeroId, hall.updatedAt);
      this.db.prepare('INSERT INTO hall_requests VALUES (?, ?, ?, ?)').run(id, input.requestId, payload, JSON.stringify(hall));
      this.db.exec('COMMIT');
      return { hall, replayed: false };
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }
  close() { this.db.close(); }
}
