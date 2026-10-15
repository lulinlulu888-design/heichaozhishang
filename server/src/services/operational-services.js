import { ServiceError, requireObject } from '../errors.js';
import { defaultSettings, validateEnabledDefault } from '../operational-settings.js';

export function createOperationalServices({ persistence, encounters }) {
  const store = persistence.admin;
  const settings = defaultSettings(encounters);
  const fallback = () => ({ supported: false, draft: { revision: 0, settings: { ...settings }, updatedAt: null },
    active: { version: 0, settings: { ...settings }, publishedAt: null, kind: 'initial', sourceVersion: null }, releases: [] });
  const unsupported = () => { throw new ServiceError('OPERATIONAL_STORAGE_UNSUPPORTED', 'Durable admin configuration and logs require MongoDB storage', 501); };
  return {
    supported: Boolean(store),
    config: () => store ? store.get() : fallback(),
    active: session => store ? store.active(session) : fallback().active,
    async updateDraft(input) {
      if (!store) return unsupported();
      requireObject(input, ['expectedRevision', 'settings'], ['expectedRevision', 'settings']);
      validateEnabledDefault(input.settings, encounters);
      return store.updateDraft(input);
    },
    publish: input => store ? store.publish(input, 'publish', settings => validateEnabledDefault(settings, encounters)) : unsupported(),
    rollback: input => store ? store.publish(input, 'rollback', settings => validateEnabledDefault(settings, encounters)) : unsupported(),
    async logs() { return store ? { supported: true, logs: await store.recentLogs() } : unsupported(); },
    audited: (action, operation, describe) => store ? store.audited(action, operation, describe) : operation(null),
  };
}
