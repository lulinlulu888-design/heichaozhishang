export function createAdminController({ admin }) {
  return {
    overview: async ({ send }) => send(200, await admin.overview()),
    cards: ({ send }) => send(200, admin.cards()),
    config: async ({ send }) => send(200, await admin.config()),
    updateDraft: async ({ send, readBody }) => send(200, await admin.updateDraft(await readBody())),
    publish: async ({ send, readBody }) => send(200, await admin.publish(await readBody())),
    rollback: async ({ send, readBody }) => send(200, await admin.rollback(await readBody())),
    logs: async ({ send }) => send(200, await admin.logs()),
    heroes: ({ send }) => send(200, admin.heroes()),
    encounters: ({ send }) => send(200, admin.encounters()),
    profiles: async ({ send }) => send(200, { profiles: await admin.profiles() }),
    profile: async ({ send }, id) => send(200, await admin.profile(id)),
    createProfile: async ({ readBody, send }) => send(201, { profile: await admin.createProfile(await readBody()) }),
    renameProfile: async ({ readBody, send }, id) => send(200, { profile: await admin.renameProfile(id, await readBody()) }),
    selectHallHero: async ({ readBody, send }, id) => send(200, await admin.selectHallHero(id, await readBody())),
    battle: async ({ send }, profileId, battleId) => send(200, { battle: await admin.battle(profileId, battleId) }),
  };
}
