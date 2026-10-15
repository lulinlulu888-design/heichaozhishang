import { ServiceError } from '../errors.js';
import { API_PREFIX } from './api-prefix.js';
import { createRebuildController } from '../controllers/rebuild-controller.js';
export { API_PREFIX } from './api-prefix.js';

export function createRebuildRoutes(dependencies) {
  const { services } = dependencies;
  const controller = createRebuildController(dependencies);
  const profilePattern = new RegExp(`^${API_PREFIX}/profiles/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$`);
  const battlePattern = new RegExp(`^${API_PREFIX}/profiles/([0-9a-f-]{36})/battles(?:/([0-9a-f-]{36})(/actions)?)?$`);
  const hallPattern = new RegExp(`^${API_PREFIX}/profiles/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/hall$`);
  const encounterPattern = new RegExp(`^${API_PREFIX}/encounters/([a-z][a-z0-9-]{0,79})$`);
  return async function dispatch(context) {
    const { path } = context;
    const encounter = path.match(encounterPattern);
    if (await controller.content(context, encounter?.[1])) return;
    const hall = services.hall && path.match(hallPattern);
    if (hall) return controller.hall(context, hall.slice(1));
    const battle = services.battles && path.match(battlePattern);
    if (battle) return controller.battle(context, battle.slice(1));
    const profile = path.match(profilePattern);
    if (profile) return controller.profile(context, profile.slice(1));
    throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
  };
}
