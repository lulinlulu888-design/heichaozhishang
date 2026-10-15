import { ServiceError, requireObject } from '../errors.js';

/** Personal local administration. All writes use the same game-domain services. */
export function createAdminServices({ services, status, catalog, heroes, encounters, operations }) {
  return {
    async overview() {
      const profiles = await services.profiles.list();
      const battles = services.battles
        ? await Promise.all(profiles.map(profile => services.battles.list(profile.id))) : [];
      return {
        service: await status(),
        counts: {
          profiles: profiles.length,
          battles: battles.reduce((total, list) => total + list.length, 0),
          heroes: heroes?.heroes.length ?? 0,
          hallVerified: heroes?.heroes.filter(hero => hero.availability.hallPreview === 'verified').length ?? 0,
        },
        content: { catalogId: catalog.contentId, heroesId: heroes?.contentId ?? null,
          encountersId: encounters?.directory.contentId ?? null },
        policy: { access: 'personal-loopback', authentication: 'none', legacyProtocolCompatible: false },
        generatedAt: Date.now(),
      };
    },
    cards: () => catalog,
    config: () => operations.config(),
    updateDraft: input => operations.updateDraft(input),
    publish: input => operations.publish(input),
    rollback: input => operations.rollback(input),
    logs: () => operations.logs(),
    heroes() {
      if (!heroes) throw new ServiceError('HERO_DIRECTORY_UNAVAILABLE', 'Recovered hero directory is not enabled', 404);
      return heroes;
    },
    encounters() {
      if (!encounters) throw new ServiceError('ENCOUNTER_UNAVAILABLE', 'Encounter directory is not enabled', 404);
      return encounters.directory;
    },
    profiles: () => services.profiles.list(),
    async profile(id) {
      const profile = await services.profiles.get(id);
      const [hall, battles] = await Promise.all([
        services.hall ? services.hall.get(id) : null,
        services.battles ? services.battles.list(id) : [],
      ]);
      return { profile, hall, battles };
    },
    createProfile(input) {
      requireObject(input, ['displayName'], ['displayName']);
      return operations.audited('profile.create', session => services.profiles.create(input, { session }),
        profile => ({ targetType: 'profile', targetId: profile.id,
          summary: { displayName: profile.displayName, revision: profile.revision } }));
    },
    renameProfile(id, input) {
      // Administration must not grant characters or rewrite gameplay progress.
      requireObject(input, ['expectedRevision', 'displayName'], ['expectedRevision', 'displayName']);
      return operations.audited('profile.rename', session => services.profiles.update(id, input, { session }),
        profile => ({ targetType: 'profile', targetId: id,
          summary: { displayName: profile.displayName, revision: profile.revision } }));
    },
    async selectHallHero(id, input) {
      requireObject(input, ['requestId', 'expectedRevision', 'selectedHeroId'],
        ['requestId', 'expectedRevision', 'selectedHeroId']);
      await services.profiles.get(id);
      if (!services.hall) throw new ServiceError('HALL_UNAVAILABLE', 'Hall selection is not enabled', 404);
      return operations.audited('hall.select', session => services.hall.update(id, input, { session }),
        result => ({ targetType: 'hall', targetId: id,
          summary: { selectedHeroId: result.hall.selectedHeroId, revision: result.hall.revision, requestId: input.requestId } }));
    },
    async battle(profileId, battleId) {
      await services.profiles.get(profileId);
      if (!services.battles) throw new ServiceError('BATTLE_UNAVAILABLE', 'Battle storage is not enabled', 404);
      return services.battles.get(profileId, battleId);
    },
  };
}
