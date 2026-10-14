import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { request as httpRequest } from 'node:http';
import { once } from 'node:events';
import { createApp } from '../src/app.js';
import { loadCatalog } from '../src/catalog.js';
import { ProfileStore } from '../src/store.js';
import { fixture, request } from './helpers.js';

async function appFixture(t) {
  const files = await fixture(t);
  const app = await createApp({ ...files, port: 0, log: error => assert.fail(JSON.stringify(error)) });
  files.cleanupWith(() => app.close());
  return { ...files, ...app };
}

test('live HTTP API loads the catalog, creates a local profile, and saves a choice', async t => {
  const app = await appFixture(t);
  const status = await request(app.address, '/status');
  assert.equal(status.body.gameplayReady, false);
  const catalog = await request(app.address, '/catalog');
  assert.equal(catalog.body.characters[0].name, 'Fixture Hero');
  assert.equal(catalog.body.cards[0].cost, 1);
  assert.equal(catalog.body.cards[0].damage, undefined);
  const created = await request(app.address, '/profiles', 'POST', { displayName: '本地玩家' });
  assert.equal(created.status, 201);
  assert.equal(created.body.profile.selectedCharacterId, null);
  const id = created.body.profile.id;
  const saved = await request(app.address, `/profiles/${id}`, 'PATCH', { expectedRevision: 1, selectedCharacterId: 2 });
  assert.equal(saved.status, 200);
  assert.equal(saved.body.profile.revision, 2);
  assert.deepEqual((await request(app.address, `/profiles/${id}`)).body.profile, saved.body.profile);
});

test('two requests using one revision yield one write and one conflict', async t => {
  const app = await appFixture(t);
  const { body: { profile } } = await request(app.address, '/profiles', 'POST', { displayName: 'Concurrent' });
  const responses = await Promise.all([1, 2].map(selectedCharacterId => request(app.address,
    `/profiles/${profile.id}`, 'PATCH', { expectedRevision: 1, selectedCharacterId })));
  assert.deepEqual(responses.map(value => value.status).sort(), [200, 409]);
  const final = await request(app.address, `/profiles/${profile.id}`);
  assert.equal(final.body.profile.revision, 2);
  assert.equal(final.body.profile.selectedCharacterId, responses.find(r => r.status === 200).body.profile.selectedCharacterId);
});

test('shutdown bounds an unfinished JSON body, is idempotent, and releases SQLite', async t => {
  const app = await appFixture(t);
  const { body: { profile } } = await request(app.address, '/profiles', 'POST', { displayName: 'Committed' });
  const pending = httpRequest(app.address + '/api/rebuild/v1/profiles', { method: 'POST', headers: {
    'Content-Type': 'application/json', 'Content-Length': '100', Expect: '100-continue',
  } });
  // Forced shutdown intentionally resets the client's incomplete request.
  pending.on('error', () => {});
  const disconnected = new Promise(resolve => pending.once('close', resolve));
  const ready = once(pending, 'continue');
  pending.flushHeaders();
  await ready; // The service has accepted the headers, so this is an active request.
  pending.write('{');
  const closing = app.close();
  assert.equal(app.close(), closing);
  let timeout;
  try {
    await Promise.race([closing, new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error('Shutdown did not complete within 3 seconds')), 3_000);
    })]);
    await disconnected;
    assert.equal(app.close(), closing);
    assert.equal(existsSync(app.savePath + '-wal'), false);
    assert.equal(existsSync(app.savePath + '-shm'), false);
    const reopened = new ProfileStore(app.savePath);
    try { assert.deepEqual(reopened.list(), [profile]); }
    finally { reopened.close(); }
  } finally {
    clearTimeout(timeout);
    pending.destroy();
    await closing;
  }
});

test('malformed, excessive and unsupported bodies leave the database unchanged', async t => {
  const app = await appFixture(t);
  for (const [body, type, status] of [['{', 'application/json', 400],
    ['{}', 'text/plain', 415], ['x'.repeat(16 * 1024 + 1), 'application/json', 413],
    ['null', 'application/json', 400]]) {
    const response = await fetch(app.address + '/api/rebuild/v1/profiles', {
      method: 'POST', headers: { 'Content-Type': type }, body,
    });
    assert.equal(response.status, status);
    await response.arrayBuffer();
  }
  assert.deepEqual((await request(app.address, '/profiles')).body.profiles, []);
});

test('only configured browser origins and local host names can access the service', async t => {
  const app = await appFixture(t);
  const allowed = await request(app.address, '/catalog', 'GET', undefined, { Origin: 'http://127.0.0.1:7456' });
  assert.equal(allowed.headers.get('access-control-allow-origin'), 'http://127.0.0.1:7456');
  const denied = await request(app.address, '/profiles', 'POST', { displayName: 'No' }, { Origin: 'https://example.invalid' });
  assert.equal(denied.status, 403);
  assert.equal(denied.headers.get('access-control-allow-origin'), null);
  const hostStatus = await new Promise((resolve, reject) => {
    httpRequest(app.address + '/api/rebuild/v1/catalog', { headers: { Host: 'example.invalid' } }, response => {
      response.resume(); resolve(response.statusCode);
    }).on('error', reject).end();
  });
  assert.equal(hostStatus, 403);
  assert.equal((await request(app.address, '/profiles', 'OPTIONS', undefined,
    { Origin: 'http://localhost:7456' })).status, 204);
  assert.deepEqual((await request(app.address, '/profiles')).body.profiles, []);
});

test('legacy-looking routes and unknown characters never return pretend success', async t => {
  const app = await appFixture(t);
  assert.equal((await fetch(app.address + '/login', { method: 'POST' })).status, 404);
  const { body: { profile } } = await request(app.address, '/profiles', 'POST', { displayName: 'Test' });
  assert.equal((await request(app.address, `/profiles/${profile.id}`, 'PATCH',
    { expectedRevision: 1, selectedCharacterId: 9001 })).status, 400);
  assert.equal((await request(app.address, `/profiles/${profile.id}`)).body.profile.revision, 1);
});

test('bad catalog provenance or missing fields stops startup before creating a save', async t => {
  const files = await fixture(t);
  const path = join(files.dataDirectory, 'characters.json');
  const value = JSON.parse(await readFile(path));
  value.source.index = 1;
  await writeFile(path, JSON.stringify(value));
  await assert.rejects(createApp({ ...files, port: 0 }), /unexpected source/);
  assert.equal(existsSync(files.savePath), false);
  value.source.index = 8995;
  delete value.rows[0].fields.CharImage;
  await writeFile(path, JSON.stringify(value));
  await assert.rejects(loadCatalog(files.dataDirectory), /CharImage/);
});

const recovered = fileURLToPath(new URL('../../analysis/game-data', import.meta.url));
test('real APK data projects three named characters and real costs without invented damage',
  { skip: !existsSync(join(recovered, 'characters.json')) }, async () => {
    const catalog = await loadCatalog(recovered);
    assert.deepEqual(catalog.characters.map(character => character.name), ['艾尔莎', '琳', '未来']);
    assert.deepEqual(catalog.cards.map(card => card.cost), [1, 2, 0, 1]);
    assert.equal(catalog.cards[0].name, '二连斩击');
    assert.equal(catalog.sources.cards.decodedSha256, 'c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09');
    assert.ok(catalog.cards.every(card => !('damage' in card)));
  });
