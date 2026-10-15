import assert from 'node:assert/strict';
import { createServer, request as httpRequest } from 'node:http';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { after, before, test } from 'node:test';
import { createAdminServer } from '../serve.mjs';

let fixture;
let dist;
let app;
let backend;
let backendPort;
let junctionAvailable = false;
const calls = [];
const marker = 'HCZS_TEST_PRIVATE_RUNTIME_DO_NOT_SERVE';

function listen(server) {
  return new Promise((accept, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', accept);
  });
}

function close(server) {
  return new Promise((accept, reject) => {
    server.closeAllConnections();
    server.close(error => error ? reject(error) : accept());
  });
}

function request(target, { method = 'GET', path = '/', headers = {}, body } = {}) {
  const address = new URL(target.address);
  return new Promise((accept, reject) => {
    const req = httpRequest({ hostname: address.hostname, port: address.port, setHost: false,
      method, path, headers: { Host: address.host, ...headers } }, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('error', reject);
      res.on('end', () => accept({ status: res.statusCode, headers: res.headers,
        text: Buffer.concat(chunks).toString('utf8') }));
    });
    req.setTimeout(5_000, () => req.destroy(new Error('test request timed out')));
    req.on('error', reject);
    req.end(body);
  });
}

before(async () => {
  fixture = await mkdtemp(join(tmpdir(), 'hczs-admin-http-test-'));
  dist = join(fixture, 'dist');
  const privateDir = join(fixture, 'runtime');
  await mkdir(dist);
  await mkdir(privateDir);
  await writeFile(join(dist, 'index.html'), '<!doctype html><title>HCZS admin fixture</title>');
  await writeFile(join(dist, 'app.js'), 'globalThis.hczsFixture = true;');
  await writeFile(join(privateDir, 'state.json'), marker);
  try {
    await symlink(privateDir, join(dist, 'linked-runtime'), process.platform === 'win32' ? 'junction' : 'dir');
    junctionAvailable = true;
  } catch (error) {
    if (!['EPERM', 'EACCES', 'ENOSYS'].includes(error.code)) throw error;
  }
  backend = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const record = { method: req.method, path: req.url,
      contentType: req.headers['content-type'], origin: req.headers.origin,
      body: Buffer.concat(chunks).toString('utf8') };
    calls.push(record);
    const status = req.url.endsWith('/reject') ? 409 : 200;
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ record, status }));
  });
  await listen(backend);
  backendPort = backend.address().port;
  app = await createAdminServer({ port: 0, apiPort: backendPort, dist });
});

after(async () => {
  if (app) await app.close();
  if (backend?.listening) await close(backend);
  if (fixture) {
    // Cleanup is restricted to the exact directory returned by mkdtemp.
    const prefix = resolve(tmpdir()) + sep;
    assert.ok(resolve(fixture).startsWith(prefix));
    assert.ok(fixture.includes('hczs-admin-http-test-'));
    await rm(fixture, { recursive: true, force: true });
  }
});

test('binds only loopback and serves the local static fixture with security headers', async () => {
  assert.equal(app.server.address().address, '127.0.0.1');
  const response = await request(app);
  assert.equal(response.status, 200);
  assert.match(response.text, /HCZS admin fixture/);
  assert.match(response.headers['content-type'], /^text\/html/);
  assert.equal(response.headers['cache-control'], 'no-store');
  assert.equal(response.headers['x-content-type-options'], 'nosniff');
  assert.match(response.headers['content-security-policy'], /frame-ancestors 'none'/);
});

test('allows localhost host and a matching same-origin header', async () => {
  const port = app.server.address().port;
  const response = await request(app, { headers: { Host: `localhost:${port}`,
    Origin: `http://localhost:${port}` } });
  assert.equal(response.status, 200);
});

test('rejects foreign or missing Host before static and proxy handling', async () => {
  const previous = calls.length;
  for (const Host of ['evil.example', `127.0.0.1:${app.server.address().port}.evil.example`, '']) {
    const response = await request(app, { path: '/api/admin/v1/status', headers: { Host } });
    assert.equal(response.status, 403, `Host ${JSON.stringify(Host)}`);
    assert.equal(JSON.parse(response.text).error.code, 'HOST_NOT_ALLOWED');
  }
  assert.equal(calls.length, previous);
});

test('rejects foreign and null origins before forwarding a write request', async () => {
  const previous = calls.length;
  for (const Origin of ['https://evil.example', 'null', `http://localhost:${app.server.address().port + 1}`]) {
    const response = await request(app, { method: 'POST', path: '/api/admin/v1/content',
      headers: { Origin, 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(response.status, 403);
    assert.equal(JSON.parse(response.text).error.code, 'ORIGIN_NOT_ALLOWED');
  }
  assert.equal(calls.length, previous);
});

test('does not expose sibling runtime files through traversal or direct paths', async () => {
  for (const path of ['/runtime/state.json', '/../runtime/state.json', '/%2e%2e/runtime/state.json',
    '/%2e%2e%2fruntime/state.json', '/..%5cruntime%5cstate.json', '/%2e%2e%5cruntime%5cstate.json',
    '/%2f..%2fruntime%2fstate.json']) {
    const response = await request(app, { path });
    assert.equal(response.status, 404, path);
    assert.ok(!response.text.includes(marker), path);
  }
});

test('rejects malformed URI escapes without exposing a server exception', async () => {
  const response = await request(app, { path: '/%ZZ' });
  assert.equal(response.status, 400);
  assert.equal(JSON.parse(response.text).error.code, 'INVALID_REQUEST');
});

test('does not follow a distribution junction to private runtime files', async t => {
  if (!junctionAvailable) return t.skip('OS does not allow a fixture junction/symlink');
  const response = await request(app, { path: '/linked-runtime/state.json' });
  assert.equal(response.status, 404);
  assert.ok(!response.text.includes(marker));
});

test('serves static HEAD without a body and rejects static mutation', async () => {
  const head = await request(app, { method: 'HEAD', path: '/app.js' });
  assert.equal(head.status, 200);
  assert.equal(head.text, '');
  assert.match(head.headers['content-type'], /^text\/javascript/);
  const post = await request(app, { method: 'POST', path: '/app.js', body: 'overwrite' });
  assert.equal(post.status, 405);
});

test('proxy forwards only bounded admin GET, POST and PATCH with exact payloads', async () => {
  const origin = app.address;
  for (const method of ['GET', 'POST', 'PATCH']) {
    const body = method === 'GET' ? undefined : JSON.stringify({ characterId: 1, note: '艾尔莎' });
    const response = await request(app, { method, path: '/api/admin/v1/content/hall-preview',
      headers: { Origin: origin, 'Content-Type': 'application/json' }, body });
    assert.equal(response.status, 200);
    assert.match(response.headers['content-type'], /^application\/json/);
    const record = JSON.parse(response.text).record;
    assert.equal(record.method, method);
    assert.equal(record.path, '/api/admin/v1/content/hall-preview');
    assert.equal(record.body, body ?? '');
    assert.equal(record.origin, origin);
    assert.equal(record.contentType, 'application/json');
  }
});

test('blocks game APIs, query strings, invalid route characters and unsupported proxy methods', async () => {
  const previous = calls.length;
  for (const [path, method] of [['/api/rebuild/v1/profiles', 'POST'], ['/api/admin/v1', 'GET'],
    ['/api/admin/v1/status?x=1', 'GET'], ['/api/admin/v1/Status', 'GET'],
    ['/api/admin/v1/status.json', 'GET'], ['/api/admin/v1/%73tatus', 'GET'],
    ['/api/admin/v1/status', 'DELETE'], ['/api/admin/v1/status', 'PUT'],
    ['/api/admin/v1/status', 'OPTIONS'], ['/api/admin/v1/status', 'HEAD']]) {
    const response = await request(app, { path, method });
    assert.equal(response.status, 404, `${method} ${path}`);
  }
  assert.equal(calls.length, previous);
});

test('rejects over-limit JSON before forwarding', async () => {
  const previous = calls.length;
  const response = await request(app, { method: 'POST', path: '/api/admin/v1/content',
    headers: { 'Content-Type': 'application/json' }, body: 'x'.repeat(64 * 1024 + 1) });
  assert.equal(response.status, 413);
  assert.equal(JSON.parse(response.text).error.code, 'BODY_TOO_LARGE');
  assert.equal(calls.length, previous);
});

test('preserves a backend JSON error status', async () => {
  const response = await request(app, { path: '/api/admin/v1/reject' });
  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.text).status, 409);
});

test('returns bounded JSON 502 when the isolated backend is unavailable and closes cleanly', async () => {
  const reservation = createServer();
  await listen(reservation);
  const unavailablePort = reservation.address().port;
  await close(reservation);
  const independent = await createAdminServer({ port: 0, apiPort: unavailablePort, dist });
  try {
    const response = await request(independent, { path: '/api/admin/v1/status' });
    assert.equal(response.status, 502);
    assert.equal(JSON.parse(response.text).error.code, 'SERVICE_UNAVAILABLE');
    assert.match(response.headers['content-type'], /^application\/json/);
  } finally {
    await independent.close();
  }
  assert.equal(independent.server.listening, false);
});

test('validates listen ports and requires the frontend index before opening a socket', async () => {
  for (const options of [{ port: -1 }, { port: 65536 }, { port: 1.5 }, { apiPort: 0 }, { apiPort: -1 }]) {
    await assert.rejects(createAdminServer({ ...options, dist }), /Invalid local admin\/service port/);
  }
  await assert.rejects(createAdminServer({ port: 0, apiPort: backendPort, dist: join(fixture, 'missing') }),
    { code: 'ENOENT' });
});
