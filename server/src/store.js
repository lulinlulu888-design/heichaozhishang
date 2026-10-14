import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { ServiceError, displayName, requireObject } from './errors.js';

const APPLICATION_ID = 0x48435a53;

/** Local reconstruction save format. It deliberately does not impersonate old accounts. */
export class ProfileStore {
  constructor(path) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    try {
      this.db.exec('PRAGMA busy_timeout = 5000; PRAGMA foreign_keys = ON;');
      // Check identity BEFORE changing persistent journal settings or schema.
      const { application_id: id } = this.db.prepare('PRAGMA application_id').get();
      const { user_version: version } = this.db.prepare('PRAGMA user_version').get();
      const { count } = this.db.prepare("SELECT count(*) AS count FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").get();
      if (version === 0 && id === 0 && count === 0) {
        this.db.exec(`BEGIN IMMEDIATE;
          CREATE TABLE profiles (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            selected_character_id INTEGER,
            revision INTEGER NOT NULL CHECK(revision >= 1),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
          ) STRICT;
          PRAGMA application_id = ${APPLICATION_ID};
          PRAGMA user_version = 1;
          COMMIT;`);
      } else if (id !== APPLICATION_ID || version !== 1) {
        throw new Error(`Unsupported save identity/version (${id}/${version}); existing data was not migrated`);
      }
      this.db.exec('PRAGMA journal_mode = WAL; PRAGMA synchronous = FULL;');
    } catch (error) {
      this.db.close();
      throw error;
    }
  }

  map(row) {
    return row ? { id: row.id, displayName: row.display_name, selectedCharacterId: row.selected_character_id,
      revision: row.revision, createdAt: row.created_at, updatedAt: row.updated_at } : null;
  }

  list() {
    return this.db.prepare('SELECT * FROM profiles ORDER BY created_at, id').all().map(row => this.map(row));
  }

  get(id) {
    const profile = this.map(this.db.prepare('SELECT * FROM profiles WHERE id = ?').get(id));
    if (!profile) throw new ServiceError('PROFILE_NOT_FOUND', 'Local profile does not exist', 404);
    return profile;
  }

  create(input) {
    requireObject(input, ['displayName'], ['displayName']);
    const name = displayName(input.displayName);
    const id = randomUUID();
    const now = Date.now();
    this.db.prepare('INSERT INTO profiles VALUES (?, ?, NULL, 1, ?, ?)').run(id, name, now, now);
    return this.get(id);
  }

  update(id, input, characterIds) {
    requireObject(input, ['expectedRevision', 'displayName', 'selectedCharacterId'], ['expectedRevision']);
    if (!Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 1 || Object.keys(input).length < 2) {
      throw new ServiceError('INVALID_INPUT', 'A valid expectedRevision and at least one change are required');
    }
    if ('displayName' in input) displayName(input.displayName);
    if ('selectedCharacterId' in input && input.selectedCharacterId !== null &&
        (!Number.isSafeInteger(input.selectedCharacterId) || !characterIds.has(input.selectedCharacterId))) {
      throw new ServiceError('UNKNOWN_CHARACTER', 'Character is absent from the recovered catalog');
    }
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const current = this.get(id);
      if (current.revision !== input.expectedRevision) {
        throw new ServiceError('REVISION_CONFLICT', 'Profile changed; reload it before saving again', 409);
      }
      const name = input.displayName ?? current.displayName;
      const character = 'selectedCharacterId' in input ? input.selectedCharacterId : current.selectedCharacterId;
      this.db.prepare(`UPDATE profiles SET display_name = ?, selected_character_id = ?,
        revision = revision + 1, updated_at = ? WHERE id = ? AND revision = ?`)
        .run(name, character, Date.now(), id, current.revision);
      const result = this.get(id);
      this.db.exec('COMMIT');
      return result;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  close() { this.db.close(); }
}
