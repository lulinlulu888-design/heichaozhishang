// Serve the local Creator build without dependencies or access beyond loopback.
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../clients/cocos-poc/build/web-desktop');
const port = Number(process.argv[2] ?? 7456);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid port');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon', '.wasm': 'application/wasm', '.bin': 'application/octet-stream' };

const server = createServer(async (request, response) => {
  try {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405).end(); return;
    }
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    let path = resolve(root, '.' + pathname);
    if (relative(root, path).startsWith('..')) { response.writeHead(403).end(); return; }
    if ((await stat(path)).isDirectory()) path = join(path, 'index.html');
    const info = await stat(path);
    if (!info.isFile()) { response.writeHead(404).end(); return; }
    response.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream',
      'Content-Length': info.size, 'Cache-Control': 'no-store' });
    if (request.method === 'HEAD') response.end();
    else createReadStream(path).on('error', () => response.destroy()).pipe(response);
  } catch {
    if (!response.headersSent) response.writeHead(404).end('Not found');
    else response.destroy();
  }
});
server.listen(port, '127.0.0.1', () => console.log(`Cocos proof: http://127.0.0.1:${port}/`));
