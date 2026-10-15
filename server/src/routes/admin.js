import { ServiceError } from '../errors.js';
import { createAdminController } from '../controllers/admin-controller.js';

export const ADMIN_API_PREFIX = '/api/admin/v1';
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const profilePattern = new RegExp(`^${ADMIN_API_PREFIX}/profiles/(${UUID})$`);
const hallPattern = new RegExp(`^${ADMIN_API_PREFIX}/profiles/(${UUID})/hall$`);
const battlePattern = new RegExp(`^${ADMIN_API_PREFIX}/profiles/(${UUID})/battles/(${UUID})$`);

/** Distinct namespace, shared loopback/Host/Origin/JSON boundary with the game API. */
export function createAdminRoutes(dependencies) {
  const controller = createAdminController(dependencies);
  return async context => {
    const { request: { method }, path } = context;
    if (method === 'GET') {
      if (path === `${ADMIN_API_PREFIX}/overview`) return controller.overview(context);
      if (path === `${ADMIN_API_PREFIX}/cards`) return controller.cards(context);
      if (path === `${ADMIN_API_PREFIX}/config`) return controller.config(context);
      if (path === `${ADMIN_API_PREFIX}/logs`) return controller.logs(context);
      if (path === `${ADMIN_API_PREFIX}/heroes`) return controller.heroes(context);
      if (path === `${ADMIN_API_PREFIX}/encounters`) return controller.encounters(context);
      if (path === `${ADMIN_API_PREFIX}/profiles`) return controller.profiles(context);
      const profile = path.match(profilePattern);
      if (profile) return controller.profile(context, profile[1]);
      const battle = path.match(battlePattern);
      if (battle) return controller.battle(context, battle[1], battle[2]);
    } else if (method === 'POST') {
      if (path === `${ADMIN_API_PREFIX}/profiles`) return controller.createProfile(context);
      if (path === `${ADMIN_API_PREFIX}/config/publish`) return controller.publish(context);
      if (path === `${ADMIN_API_PREFIX}/config/rollback`) return controller.rollback(context);
    } else if (method === 'PATCH') {
      if (path === `${ADMIN_API_PREFIX}/config/draft`) return controller.updateDraft(context);
      const profile = path.match(profilePattern);
      if (profile) return controller.renameProfile(context, profile[1]);
      const hall = path.match(hallPattern);
      if (hall) return controller.selectHallHero(context, hall[1]);
    }
    throw new ServiceError('NOT_FOUND', 'Unknown local administration API route', 404);
  };
}
