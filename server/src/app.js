import { createGameServices } from './services/game-services.js';
import { createAdminServices } from './services/admin-services.js';
import { createAdminRoutes, ADMIN_API_PREFIX } from './routes/admin.js';
import { createServer } from 'node:http';
import { loadCatalog } from './catalog.js';
import { loadHeroes } from './heroes.js';
import { openStorage } from './database/storage.js';
import { loadTutorialScenario } from './tutorial.js';
import { loadCustomScenario } from './custom-scenario.js';
import { loadCityScenario } from './city-scenario.js';
import { createRebuildRoutes } from './routes/rebuild.js';
import { createRequestHandler } from './http/request-handler.js';
import { createEncounterDirectory } from './encounters.js';
import { createOperationalServices } from './services/operational-services.js';
import { defaultSettings } from './operational-settings.js';

export { API_PREFIX } from './routes/rebuild.js';
const SHUTDOWN_GRACE_MS = 1_000;

/** New-client API, intentionally separate from the unverified legacy gateway. */
export async function createApp({ dataDirectory, savePath, tutorialDirectory, customScenarioPath, cityPreview = false, battleSavePath, port = 7457,
  storage = 'mongodb', mongoUri, mongoDatabase,
  allowedOrigins = ['http://127.0.0.1:7456', 'http://localhost:7456',
    'http://127.0.0.1:7470', 'http://localhost:7470', 'http://127.0.0.1:7471', 'http://localhost:7471'], log = console.error } = {}) {
  const catalog = await loadCatalog(dataDirectory);
  const heroes = await loadHeroes(dataDirectory, { optional: true });
  if (customScenarioPath && !tutorialDirectory) throw new Error('Custom scenario requires verified tutorial evidence');
  if (cityPreview && (!tutorialDirectory || customScenarioPath)) throw new Error('City preview requires tutorial evidence and cannot combine with custom scenario');
  const baseTutorial = tutorialDirectory ? await loadTutorialScenario(tutorialDirectory) : null;
  const tutorial = cityPreview ? await loadCityScenario(baseTutorial) : customScenarioPath ? await loadCustomScenario(baseTutorial, customScenarioPath) : baseTutorial;
  const encounters = createEncounterDirectory({ baseTutorial, current: tutorial, cityPreview, customScenarioPath });
  const persistence = await openStorage({ storage, mongoUri, mongoDatabase, savePath, battleSavePath, tutorial, heroes,
    operationalDefaults: defaultSettings(encounters) });
  const { hall, close: closeStores } = persistence;
  const operations = createOperationalServices({ persistence, encounters });
  const status = async () => ({ service: 'hczs-rebuild', apiVersion: 1, saveSchemaVersion: 1, storage: persistence.backend,
    hallSaveSchemaVersion: hall ? 1 : null,
    capabilities: ['recovered-catalog', 'local-profiles', ...(heroes ? ['recovered-heroes', 'hall-selection'] : []),
      ...(tutorial ? ['tutorial-battles', 'encounter-selection'] : [])],
    operational: { supported: operations.supported, ...(await operations.active()) },
    gameplayReady: false, battleMode: cityPreview ? 'city-reconstruction-preview' : customScenarioPath ? 'custom-content' : tutorial ? 'explicit-reconstruction' : null });
  const services = createGameServices({ persistence, catalog, heroes, tutorial, encounters, operations });
  const dependencies = { services, status, catalog, heroes, tutorial, encounters, operations };
  const rebuildDispatch = createRebuildRoutes(dependencies);
  const adminDispatch = createAdminRoutes({ admin: createAdminServices(dependencies) });
  const dispatch = context => context.path === ADMIN_API_PREFIX || context.path.startsWith(`${ADMIN_API_PREFIX}/`)
    ? adminDispatch(context) : rebuildDispatch(context);
  let closing = null;
  const server = createServer(createRequestHandler({ allowedOrigins, getPort: () => server.address().port,
    isClosing: () => Boolean(closing), dispatch, log }));
  server.requestTimeout = 10_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 1_000;
  try {
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(port, '127.0.0.1', () => { server.removeListener('error', reject); resolve(); });
    });
  } catch (error) { await closeStores(); throw error; }
  return {
    address: `http://127.0.0.1:${server.address().port}`,
    catalog,
    heroes,
    tutorial,
    close() {
      if (!closing) closing = new Promise((resolve, reject) => {
        // server.close stops Node's request-timeout checks. A partial body must
        // not keep shutdown pending forever after the listener is closed.
        const deadline = setTimeout(() => server.closeAllConnections(), SHUTDOWN_GRACE_MS);
        deadline.unref();
        server.close(async error => {
          clearTimeout(deadline);
          try { await closeStores(); }
          catch (storeError) { reject(storeError); return; }
          if (error) reject(error); else resolve();
        });
      });
      return closing;
    },
  };
}
