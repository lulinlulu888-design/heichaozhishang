import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { createApp } from './app.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const { values } = parseArgs({ options: {
  port: { type: 'string', default: '7457' },
  'data-directory': { type: 'string', default: resolve(root, 'analysis/game-data') },
  'save-path': { type: 'string' },
  'tutorial-directory': { type: 'string', default: resolve(root, 'analysis/first-encounter') },
  'no-tutorial': { type: 'boolean', default: false },
  'custom-scenario': { type: 'string' },
  'city-preview': { type: 'boolean', default: false },
} });
const port = Number(values.port);
if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Port must be 0–65535');
const app = await createApp({ port, dataDirectory: resolve(values['data-directory']),
  savePath: resolve(values['save-path'] ?? resolve(root, values['city-preview'] ? 'runtime/server/city-preview.sqlite' : values['custom-scenario'] ? 'runtime/server/custom.sqlite' : 'runtime/server/hczs.sqlite')),
  tutorialDirectory: values['no-tutorial'] ? undefined : resolve(values['tutorial-directory']),
  customScenarioPath: values['custom-scenario'] ? resolve(values['custom-scenario']) : undefined,
  cityPreview: values['city-preview'] });
console.log(JSON.stringify({ event: 'ready', address: app.address, api: '/api/rebuild/v1',
  gameplayReady: false, catalogContentId: app.catalog.contentId }));
let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await app.close();
  console.log(JSON.stringify({ event: 'stopped' }));
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
