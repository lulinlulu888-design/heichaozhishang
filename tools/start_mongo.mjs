// Owns only the hczs-local Compose project; never reconfigures other MongoDB instances.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { createConnection } from 'node:net';
const root = fileURLToPath(new URL('../', import.meta.url));
function docker(args, quiet = false) {
  const result = spawnSync('docker', ['compose', '-f', 'docker-compose.mongo.yml', ...args],
    { cwd: root, windowsHide: true, encoding: 'utf8', timeout: 60_000 });
  if (!quiet && result.status !== 0) throw new Error(result.stderr || result.error?.message || 'Docker Compose failed');
  return result;
}
docker(['up', '-d', 'mongo']);
const script = `try { rs.status(); } catch (e) { if (e.code !== 94) throw e; rs.initiate({_id:'hczs-local',members:[{_id:0,host:'localhost:27017'}]}); } if (!db.hello().isWritablePrimary) quit(2); print('hczs-local primary ready');`;
const deadline = Date.now() + 45_000;
while (true) {
  const result = docker(['exec', '-T', 'mongo', 'mongosh', '--quiet', '--eval', script], true);
  if (result.status === 0) { console.log(result.stdout.trim()); break; }
  if (Date.now() >= deadline) throw new Error('hczs-local MongoDB did not become primary; inspect docker compose -f docker-compose.mongo.yml logs mongo');
  await delay(500);
}
await new Promise((resolve, reject) => {
  const socket = createConnection({ host: '127.0.0.1', port: 27027 });
  socket.setTimeout(3_000, () => socket.destroy(new Error('MongoDB host port 27027 is not reachable')));
  socket.once('connect', () => { socket.destroy(); resolve(); });
  socket.once('error', reject);
});
console.log('MongoDB available on 127.0.0.1:27027 (replicaSet=hczs-local, directConnection=true)');
