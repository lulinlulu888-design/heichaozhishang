import { createServer } from 'node:http';
import { loadCatalog } from './catalog.js';
import { ProfileStore } from './store.js';
import { BattleStore } from './battles.js';
import { loadTutorialScenario } from './tutorial.js';
import { loadCustomScenario } from './custom-scenario.js';
import { loadCityScenario } from './city-scenario.js';
import { ServiceError } from './errors.js';

export const API_PREFIX = '/api/rebuild/v1';
const MAX_BODY = 16 * 1024;
const SHUTDOWN_GRACE_MS = 1_000;

function jsonBody(request) {
  if (request.headers['content-type']?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    request.resume();
    return Promise.reject(new ServiceError('JSON_REQUIRED', 'Use application/json', 415));
  }
  return new Promise((resolve, reject) => {
    let size = 0;
    let failed = false;
    const parts = [];
    request.on('data', chunk => {
      if (failed) return;
      size += chunk.length;
      if (size > MAX_BODY) {
        failed = true;
        parts.length = 0;
        reject(new ServiceError('BODY_TOO_LARGE', 'Request body exceeds 16 KiB', 413));
      } else parts.push(chunk);
    });
    request.on('end', () => {
      if (failed) return;
      try { resolve(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(parts)))); }
      catch { reject(new ServiceError('INVALID_JSON', 'Request is not valid UTF-8 JSON')); }
    });
    request.on('error', reject);
    request.on('aborted', () => reject(new ServiceError('REQUEST_ABORTED', 'Request aborted')));
  });
}

/** New-client API, intentionally separate from the unverified legacy gateway. */
export async function createApp({ dataDirectory, savePath, tutorialDirectory, customScenarioPath, cityPreview = false, battleSavePath, port = 7457,
  allowedOrigins = ['http://127.0.0.1:7456', 'http://localhost:7456'], log = console.error } = {}) {
  const catalog = await loadCatalog(dataDirectory);
  if (customScenarioPath && !tutorialDirectory) throw new Error('Custom scenario requires verified tutorial evidence');
  if (cityPreview && (!tutorialDirectory || customScenarioPath)) throw new Error('City preview requires tutorial evidence and cannot combine with custom scenario');
  const baseTutorial = tutorialDirectory ? await loadTutorialScenario(tutorialDirectory) : null;
  const tutorial = cityPreview ? await loadCityScenario(baseTutorial) : customScenarioPath ? await loadCustomScenario(baseTutorial, customScenarioPath) : baseTutorial;
  const characterIds = new Set(catalog.characters.map(character => character.id));
  const store = new ProfileStore(savePath);
  let battles = null;
  try {
    if (tutorial) battles = new BattleStore(battleSavePath ?? (savePath === ':memory:' ? ':memory:' : `${savePath}.battles`));
  } catch (error) { store.close(); throw error; }
  const closeStores = () => { try { battles?.close(); } finally { store.close(); } };
  const origins = new Set(allowedOrigins);
  const profilePattern = new RegExp(`^${API_PREFIX}/profiles/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$`);
  const battlePattern = new RegExp(`^${API_PREFIX}/profiles/([0-9a-f-]{36})/battles(?:/([0-9a-f-]{36})(/actions)?)?$`);
  let closing = null;
  const server = createServer(async (request, response) => {
    const send = (status, value) => {
      response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
      response.end(JSON.stringify(value));
    };
    try {
      if (closing) {
        response.setHeader('Connection', 'close');
        throw new ServiceError('SHUTTING_DOWN', 'The local service is stopping', 503);
      }
      const actualPort = server.address().port;
      if (![`${'127.0.0.1'}:${actualPort}`, `localhost:${actualPort}`].includes(request.headers.host)) {
        throw new ServiceError('HOST_NOT_ALLOWED', 'Use the loopback service address', 403);
      }
      const origin = request.headers.origin;
      if (origin !== undefined) {
        if (!origins.has(origin)) throw new ServiceError('ORIGIN_NOT_ALLOWED', 'Origin is not configured', 403);
        response.setHeader('Access-Control-Allow-Origin', origin);
        response.setHeader('Vary', 'Origin');
      }
      if (request.method === 'OPTIONS') {
        response.writeHead(204, { 'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type' }).end();
        return;
      }
      const url = new URL(request.url, 'http://127.0.0.1');
      if (url.search) throw new ServiceError('INVALID_INPUT', 'Query parameters are not supported');
      const path = url.pathname;
      if (request.method === 'GET' && path === `${API_PREFIX}/status`) {
        send(200, { service: 'hczs-rebuild', apiVersion: 1, saveSchemaVersion: 1,
          capabilities: ['recovered-catalog', 'local-profiles', ...(tutorial ? ['tutorial-battles'] : [])],
          gameplayReady: false, battleMode: cityPreview ? 'city-reconstruction-preview' : customScenarioPath ? 'custom-content' : tutorial ? 'explicit-reconstruction' : null });
      } else if (request.method === 'GET' && path === `${API_PREFIX}/tutorial` && tutorial) {
        send(200, tutorial);
      } else if (request.method === 'GET' && path === `${API_PREFIX}/catalog`) {
        send(200, catalog);
      } else if (request.method === 'GET' && path === `${API_PREFIX}/profiles`) {
        send(200, { profiles: store.list() });
      } else if (request.method === 'POST' && path === `${API_PREFIX}/profiles`) {
        send(201, { profile: store.create(await jsonBody(request)) });
      } else {
        const battleMatch = battles && path.match(battlePattern);
        if (battleMatch) {
          const [, profileId, battleId, actions] = battleMatch;
          store.get(profileId);
          if (!battleId && request.method === 'GET') send(200, { battles: battles.list(profileId) });
          else if (!battleId && request.method === 'POST') {
            const input = await jsonBody(request);
            send(201, battles.create(profileId, tutorial, input));
          } else if (battleId && !actions && request.method === 'GET') {
            send(200, { battle: battles.get(profileId, battleId) });
          } else if (battleId && actions && request.method === 'POST') {
            send(200, battles.act(profileId, battleId, await jsonBody(request)));
          } else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
          return;
        }
        const match = path.match(profilePattern);
        if (match && request.method === 'GET') send(200, { profile: store.get(match[1]) });
        else if (match && request.method === 'PATCH') {
          send(200, { profile: store.update(match[1], await jsonBody(request), characterIds) });
        } else throw new ServiceError('NOT_FOUND', 'Unknown reconstruction API route', 404);
      }
    } catch (error) {
      if (response.destroyed) return;
      if (error instanceof ServiceError) send(error.status, { error: { code: error.code, message: error.message } });
      else {
        log({ event: 'request-failed', error: String(error) });
        if (!response.headersSent) send(500, { error: { code: 'INTERNAL_ERROR', message: 'The operation could not be completed' } });
        else response.destroy();
      }
    }
  });
  server.requestTimeout = 10_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 1_000;
  try {
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(port, '127.0.0.1', () => { server.removeListener('error', reject); resolve(); });
    });
  } catch (error) { closeStores(); throw error; }
  return {
    address: `http://127.0.0.1:${server.address().port}`,
    catalog,
    tutorial,
    close() {
      if (!closing) closing = new Promise((resolve, reject) => {
        // server.close stops Node's request-timeout checks. A partial body must
        // not keep shutdown pending forever after the listener is closed.
        const deadline = setTimeout(() => server.closeAllConnections(), SHUTDOWN_GRACE_MS);
        deadline.unref();
        server.close(error => {
          clearTimeout(deadline);
          try { closeStores(); }
          catch (storeError) { reject(storeError); return; }
          if (error) reject(error); else resolve();
        });
      });
      return closing;
    },
  };
}
