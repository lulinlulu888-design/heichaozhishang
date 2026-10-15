// Local admin UI and a bounded same-origin proxy to the game service.
import { createServer } from 'node:http';
import { readFile, realpath, stat } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2' };

export async function createAdminServer({ port = 7470, apiPort = 7460, dist = resolve(directory, 'dist') } = {}) {
  if (![port, apiPort].every(n => Number.isInteger(n) && n >= 0 && n <= 65535) || apiPort === 0)
    throw new Error('Invalid local admin/service port');
  await stat(resolve(dist, 'index.html'));
  const realDist = await realpath(dist);
  const server = createServer(async (request, response) => {
    const send = (status, body, type = 'application/json; charset=utf-8') => {
      response.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'" });
      response.end(body);
    };
    try {
      const localPort = server.address().port;
      if (![`127.0.0.1:${localPort}`, `localhost:${localPort}`].includes(request.headers.host))
        return send(403, JSON.stringify({ error: { code: 'HOST_NOT_ALLOWED', message: 'Use the local admin address' } }));
      const origin = request.headers.origin;
      if (origin !== undefined && ![`http://127.0.0.1:${localPort}`, `http://localhost:${localPort}`].includes(origin))
        return send(403, JSON.stringify({ error: { code: 'ORIGIN_NOT_ALLOWED', message: 'Use the local admin page' } }));
      const url = new URL(request.url, `http://127.0.0.1:${localPort}`);
      if (url.pathname.startsWith('/api/')) {
        if (!/^\/api\/admin\/v1(?:\/[a-z0-9-]+)+$/.test(url.pathname) || url.search
          || !['GET', 'POST', 'PATCH'].includes(request.method))
          return send(404, JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Unknown admin API route' } }));
        const chunks = [];
        let bytes = 0;
        for await (const chunk of request) {
          bytes += chunk.length;
          if (bytes > 64 * 1024) return send(413, JSON.stringify({ error: { code: 'BODY_TOO_LARGE', message: 'Request body is too large' } }));
          chunks.push(chunk);
        }
        const body = chunks.length ? Buffer.concat(chunks) : undefined;
        const headers = { 'Content-Type': request.headers['content-type'] ?? 'application/json' };
        if (origin) headers.Origin = origin;
        let upstream;
        try {
          upstream = await fetch(`http://127.0.0.1:${apiPort}${url.pathname}`, {
            method: request.method, headers, body, redirect: 'error', signal: AbortSignal.timeout(10_000),
          });
        } catch {
          return send(502, JSON.stringify({ error: { code: 'SERVICE_UNAVAILABLE', message: '本地游戏服务连接失败，请检查服务状态' } }));
        }
        return send(upstream.status, await upstream.text());
      }
      if (!['GET', 'HEAD'].includes(request.method)) return send(405, 'Method not allowed', 'text/plain; charset=utf-8');
      const pathname = decodeURIComponent(url.pathname);
      const filename = resolve(dist, pathname === '/' ? 'index.html' : `.${pathname}`);
      if (!filename.startsWith(resolve(dist) + sep)) return send(404, 'Not found', 'text/plain; charset=utf-8');
      let content;
      try {
        const realFile = await realpath(filename);
        if (!realFile.startsWith(realDist + sep)) return send(404, 'Not found', 'text/plain; charset=utf-8');
        content = await readFile(realFile);
      }
      catch { return send(404, 'Not found', 'text/plain; charset=utf-8'); }
      send(200, request.method === 'HEAD' ? '' : content, mime[extname(filename)] ?? 'application/octet-stream');
    } catch {
      if (!response.destroyed && !response.headersSent)
        send(400, JSON.stringify({ error: { code: 'INVALID_REQUEST', message: 'Invalid local admin request' } }));
    }
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 1_000;
  await new Promise((accept, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', accept); });
  return { address: `http://127.0.0.1:${server.address().port}`, server,
    close: () => new Promise((accept, reject) => {
      const timer = setTimeout(() => server.closeAllConnections(), 2000);
      timer.unref();
      server.close(error => { clearTimeout(timer); error ? reject(error) : accept(); });
    }) };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const app = await createAdminServer({ port: Number(process.env.HCZS_ADMIN_PORT ?? 7470),
    apiPort: Number(process.env.HCZS_ADMIN_API_PORT ?? 7460) });
  console.log(JSON.stringify({ event: 'admin-ready', address: app.address, api: '/api/admin/v1', scope: 'personal-loopback-admin' }));
  let stopping = false;
  const stop = async () => { if (!stopping) { stopping = true; await app.close(); } };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
}
