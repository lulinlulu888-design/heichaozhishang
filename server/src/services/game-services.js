import { ServiceError } from '../errors.js';

// Application policy and persistence calls, independent of HTTP transport.
export function createGameServices({ persistence, catalog, heroes, tutorial, encounters, operations }) {
  const { store, hall, battles } = persistence;
  const characterIds = new Set(catalog.characters.map(character => character.id));
  const hallHeroIds = new Set(heroes?.heroes.filter(hero => hero.availability.hallPreview === 'verified').map(hero => hero.id) ?? []);
  return {
    profiles: {
      list: () => store.list(),
      get: id => store.get(id),
      create: async (input, { session = null } = {}) => {
        const active = await operations.active(session);
        if (!active.settings.allowNewProfiles) throw new ServiceError('PROFILE_CREATION_DISABLED', 'New local profiles are disabled by the active configuration', 403);
        return store.create(input, session);
      },
      update: (id, input, { session = null } = {}) => store.update(id, input, characterIds, session),
    },
    hall: hall ? {
      get: id => hall.get(id),
      update: (id, input, { session = null } = {}) => hall.update(id, input, hallHeroIds, session),
    } : null,
    battles: battles ? {
      list: profileId => battles.list(profileId),
      get: (profileId, battleId) => battles.get(profileId, battleId),
      create: async (profileId, input) => {
        const selectScenario = async session => {
          const active = await operations.active(session);
          if (!active.settings.allowNewBattles) {
            throw new ServiceError('BATTLE_CREATION_DISABLED', 'New battles are disabled by the active configuration', 403);
          }
          return input && Object.hasOwn(input, 'encounterId') ? encounters.resolve(input.encounterId)
            : active.settings.defaultEncounterId === encounters.directory.defaultEncounterId ? tutorial
              : encounters.resolve(active.settings.defaultEncounterId);
        };
        // Mongo checks creation receipts before reading policy inside its transaction,
        // so pauses/default changes do not invalidate historical creation retries.
        return persistence.backend === 'mongodb'
          ? battles.create(profileId, null, input, { selectScenario })
          : battles.create(profileId, await selectScenario(), input);
      },
      act: (profileId, battleId, input) => battles.act(profileId, battleId, input),
    } : null,
  };
}
