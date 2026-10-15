import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request as httpRequest } from 'node:http';
import { createRequestHandler } from '../src/http/request-handler.js';

async function start(t, dispatch, log = () => {}) {
  const server = createServer(createRequestHandler({ allowedOrigins: ['http://localhost:7456'],
    getPort: () => server.address().port, isClosing: () => false, dispatch, log }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}

test('Koa boundary preserves JSON errors, CORS and does not expose internal exception details', async t => {
  const logs = [];
  const address = await start(t, () => { throw new Error('private database credentials'); }, e => logs.push(e));
  const response = await fetch(address, { headers: { Origin: 'http://localhost:7456' } });
  assert.equal(response.status, 500);
  assert.equal(response.headers.get('access-control-allow-origin'), 'http://localhost:7456');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.match(response.headers.get('content-type'), /^application\/json/);
  assert.deepEqual(await response.json(), { error: { code: 'INTERNAL_ERROR', message: 'The operation could not be completed' } });
  assert.deepEqual(logs, [{ event: 'request-failed', error: 'Error' }]);
});

test('Koa boundary retains strict UTF-8 and body limits before dispatching a write', async t => {
  let writes = 0;
  const address = await start(t, async ({ readBody, send }) => { const body = await readBody(); writes++; send(201, body); });
  for (const [body, status, code] of [
    [Buffer.from([0x22, 0xff, 0x22]), 400, 'INVALID_JSON'],
    ['"' + 'x'.repeat(17000) + '"', 413, 'BODY_TOO_LARGE'],
  ]) {
    const response = await fetch(address, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
    assert.equal(response.status, status);
    assert.equal((await response.json()).error.code, code);
  }
  assert.equal(writes, 0);
});

test('forwarded host cannot bypass the loopback Host check with Koa', async t => {
  let calls = 0;
  const address = await start(t, ({ send }) => { calls++; send(200, {}); });
  const response = await new Promise((resolve, reject) => {
    const req = httpRequest(address, { headers: { Host: 'external.invalid', 'X-Forwarded-Host': new URL(address).host } }, res => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(body) }));
      res.on('error', reject);
    });
    req.on('error', reject);
    req.end();
  });
  assert.equal(response.status, 403);
  assert.equal(response.body.error.code, 'HOST_NOT_ALLOWED');
  assert.equal(calls, 0);
});

test('body reading rejects when the client disconnects during a profile lookup', { timeout: 3_000 }, async t => {
  let enteredResolve, lookupResolve, finishedResolve;
  const entered = new Promise(resolve => { enteredResolve = resolve; });
  const lookup = new Promise(resolve => { lookupResolve = resolve; });
  const finished = new Promise(resolve => { finishedResolve = resolve; });
  let writes = 0;
  const address = await start(t, async ({ request, readBody, send }) => {
    enteredResolve(request);
    // Hall and battle controllers await the profile query before reading JSON.
    await lookup;
    try { await readBody(); }
    catch (error) { finishedResolve(error); throw error; }
    writes++;
    finishedResolve(null);
    send(201, {});
  });
  const req = httpRequest(address, { method: 'POST', headers: {
    'Content-Type': 'application/json', 'Content-Length': '100',
  } });
  req.on('error', () => {}); // Closing this incomplete request intentionally resets the client.
  t.after(() => { lookupResolve(); req.destroy(); });
  req.flushHeaders();
  const incoming = await entered;
  const aborted = new Promise(resolve => incoming.once('aborted', resolve));
  req.destroy();
  await aborted;
  assert.equal(incoming.aborted, true);
  assert.equal(incoming.complete, false);
  lookupResolve();
  let deadline;
  try {
    const error = await Promise.race([finished, new Promise((_, reject) => {
      deadline = setTimeout(() => reject(new Error('Aborted body reading did not finish')), 1_000);
    })]);
    assert.equal(error?.code, 'REQUEST_ABORTED');
    assert.equal(writes, 0);
  } finally { clearTimeout(deadline); }
});
