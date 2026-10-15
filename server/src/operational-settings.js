import { ServiceError, requireObject } from './errors.js';

export const SETTING_FIELDS = ['serverName', 'motd', 'allowNewProfiles', 'allowNewBattles', 'defaultEncounterId'];
export function defaultSettings(encounters) {
  return { serverName: '黑潮之上 · 本地重建', motd: '', allowNewProfiles: true, allowNewBattles: true,
    defaultEncounterId: encounters?.directory.defaultEncounterId ?? null };
}
export function validateSettings(settings) {
  requireObject(settings, SETTING_FIELDS, SETTING_FIELDS);
  if (typeof settings.serverName !== 'string' || settings.serverName !== settings.serverName.trim() ||
      [...settings.serverName].length < 1 || [...settings.serverName].length > 64 ||
      /[\u0000-\u001f\u007f]/u.test(settings.serverName) ||
      typeof settings.motd !== 'string' || [...settings.motd].length > 1000 ||
      /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(settings.motd) ||
      typeof settings.allowNewProfiles !== 'boolean' || typeof settings.allowNewBattles !== 'boolean' ||
      (settings.defaultEncounterId !== null && (typeof settings.defaultEncounterId !== 'string' ||
        !/^[a-z][a-z0-9-]{0,79}$/.test(settings.defaultEncounterId)))) {
    throw new ServiceError('INVALID_SETTINGS', 'Operational settings have invalid values');
  }
  return Object.fromEntries(SETTING_FIELDS.map(key => [key, settings[key]]));
}
export function validateEnabledDefault(settings, encounters) {
  validateSettings(settings);
  if (encounters ? !encounters.resolve(settings.defaultEncounterId) : settings.defaultEncounterId !== null) {
    throw new ServiceError('ENCOUNTER_UNAVAILABLE', 'Default encounter must be enabled on this server', 400);
  }
}
