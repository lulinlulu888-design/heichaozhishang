import { ServiceError } from '../errors.js';
import { API_PREFIX } from '../routes/api-prefix.js';

export function createRebuildController({ services, status, catalog, heroes, tutorial, encounters }) {
  return {
    async content({ request, path, readBody, send }, encounterId) {
      if (request.method === 'GET' && path === `${API_PREFIX}/status`) {
        send(200, await status());
      } else if (request.method === 'GET' && path === `${API_PREFIX}/bootstrap`) {
        send(200, { ...(await status()), profiles: await services.profiles.list(), content: { catalogId: catalog.contentId, heroesId: heroes?.contentId ?? null,
          encountersId: encounters?.directory.contentId ?? null, ...(services.mainline ? { mainlineId: services.mainline.contentId } : {}) },
          endpoints: { status: `${API_PREFIX}/status`, catalog: `${API_PREFIX}/catalog`, profiles: `${API_PREFIX}/profiles`,
            ...(heroes ? { heroes: `${API_PREFIX}/heroes`, hall: `${API_PREFIX}/profiles/{profileId}/hall` } : {}),
            ...(tutorial ? { tutorial: `${API_PREFIX}/tutorial`, encounters: `${API_PREFIX}/encounters`, battles: `${API_PREFIX}/profiles/{profileId}/battles` } : {}),
            ...(services.mainline ? { mainline: `${API_PREFIX}/profiles/{profileId}/mainline`, settlements: `${API_PREFIX}/profiles/{profileId}/mainline/settlements` } : {}) } });
      } else if (request.method === 'GET' && path === `${API_PREFIX}/encounters` && encounters) {
        send(200, encounters.directory);
      } else if (request.method === 'GET' && encounters && encounterId !== undefined) {
        const scenario = encounters.resolve(encounterId);
        if (!scenario) throw new ServiceError('ENCOUNTER_UNAVAILABLE', 'Encounter is not enabled on this server', 404);
        send(200, { scenario });
      } else if (request.method === 'GET' && path === `${API_PREFIX}/heroes` && heroes) {
        send(200, heroes);
      } else if (request.method === 'GET' && path === `${API_PREFIX}/tutorial` && tutorial) {
        send(200, tutorial);
      } else if (request.method === 'GET' && path === `${API_PREFIX}/catalog`) {
        send(200, catalog);
      } else if (request.method === 'GET' && path === `${API_PREFIX}/profiles`) {
        send(200, { profiles: await services.profiles.list() });
      } else if (request.method === 'POST' && path === `${API_PREFIX}/profiles`) {
        send(201, { profile: await services.profiles.create(await readBody()) });
      } else return false;
      return true;
    },
    async mainline({ request, readBody, send }, params) {
      const [profileId, settlement] = params;
      if (request.method === 'GET' && !settlement) send(200, { campaign: await services.mainline.get(profileId) });
      else if (request.method === 'POST' && settlement) send(200, await services.mainline.settle(profileId, await readBody()));
      else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
    },
    async hall({ request, readBody, send }, params) {
      const [profileId] = params;
      await services.profiles.get(profileId);
      if (request.method === 'GET') send(200, { hall: await services.hall.get(profileId) });
      else if (request.method === 'PATCH') send(200, await services.hall.update(profileId, await readBody()));
      else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
    },
    async battle({ request, readBody, send }, params) {
      const [profileId, battleId, actions] = params;
      await services.profiles.get(profileId);
      if (!battleId && request.method === 'GET') send(200, { battles: await services.battles.list(profileId) });
      else if (!battleId && request.method === 'POST') {
        const input = await readBody();
        send(201, await services.battles.create(profileId, input));
      } else if (battleId && !actions && request.method === 'GET') {
        send(200, { battle: await services.battles.get(profileId, battleId) });
      } else if (battleId && actions && request.method === 'POST') {
        send(200, await services.battles.act(profileId, battleId, await readBody()));
      } else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
    },
    async profile({ request, readBody, send }, params) {
      if (request.method === 'GET') send(200, { profile: await services.profiles.get(params[0]) });
      else if (request.method === 'PATCH') {
        send(200, { profile: await services.profiles.update(params[0], await readBody()) });
      } else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
    },
  };
}
