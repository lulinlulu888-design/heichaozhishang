import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createApp } from '../src/app.js';
import { fixture, request } from './helpers.js';

const tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url));

test('city server offers verified tutorial and explicit city preview without changing legacy default', async t => {
  const files = await fixture(t);
  const app = await createApp({ ...files, tutorialDirectory, cityPreview: true, port: 0 });
  files.cleanupWith(() => app.close());
  const directory = (await request(app.address, '/encounters')).body;
  assert.deepEqual(directory.encounters.map(e => e.id), ['tutorial-5000', 'city-preview-10405']);
  assert.equal(directory.defaultEncounterId, 'city-preview-10405');
  assert.equal(directory.originalUnlockBehaviorVerified, false);
  assert.equal(directory.rewardsImplemented, false);
  assert.equal(directory.encounters[0].source.challengeId, 3997);
  assert.equal(directory.encounters[1].classification, 'local-reconstruction-preview');
  const bootstrap = (await request(app.address, '/bootstrap')).body;
  assert.equal(bootstrap.content.encountersId, directory.contentId);
  assert.ok(bootstrap.capabilities.includes('encounter-selection'));
  const detail = await request(app.address, '/encounters/tutorial-5000');
  assert.equal(detail.status, 200);
  assert.equal(detail.body.scenario.definition.enemy.id, '991');
  assert.equal((await request(app.address, '/tutorial')).body.definition.enemy.id, '6605');
  const p = (await request(app.address, '/profiles', 'POST', { displayName: '选关验证' })).body.profile;
  const prefix = `/profiles/${p.id}/battles`;
  const input = { requestId: 'tutorial', seed: 4, encounterId: 'tutorial-5000' };
  const selected = await request(app.address, prefix, 'POST', input);
  assert.equal(selected.status, 201);
  assert.equal(selected.body.battle.scenario.definition.enemy.id, '991');
  assert.equal((await request(app.address, prefix, 'POST', input)).body.replayed, true);
  assert.equal((await request(app.address, prefix, 'POST', { ...input, encounterId: 'city-preview-10405' })).status, 409);
  const legacy = await request(app.address, prefix, 'POST', { requestId: 'old-client', seed: 4 });
  assert.equal(legacy.body.battle.scenario.definition.enemy.id, '6605');
  assert.equal(Object.hasOwn(legacy.body.battle.scenario, 'encounterId'), false);
  for (const encounterId of [null, 5000, {}, '', 'tutorial/5000']) {
    assert.equal((await request(app.address, prefix, 'POST', { requestId: 'invalid', encounterId })).status, 400);
  }
  const unknown = await request(app.address, prefix, 'POST', { requestId: 'missing', encounterId: 'not-recovered' });
  assert.equal(unknown.status, 404);
  assert.equal(unknown.body.error.code, 'ENCOUNTER_UNAVAILABLE');
  assert.equal((await request(app.address, prefix)).body.battles.length, 2);
});

test('custom menu includes only enabled content; no tutorial means no encounter capability', async t => {
  const files = await fixture(t);
  let app = await createApp({ ...files, port: 0 });
  files.cleanupWith(() => app.close());
  assert.equal((await request(app.address, '/encounters')).status, 404);
  const boot = (await request(app.address, '/bootstrap')).body;
  assert.equal(boot.content.encountersId, null);
  assert.equal(boot.capabilities.includes('encounter-selection'), false);
  await app.close();
  app = await createApp({ ...files, tutorialDirectory, port: 0,
    customScenarioPath: fileURLToPath(new URL('../data/custom/guard-and-draw.json', import.meta.url)) });
  const directory = (await request(app.address, '/encounters')).body;
  assert.deepEqual(directory.encounters.map(e => e.id), ['tutorial-5000', 'custom']);
  assert.equal(directory.defaultEncounterId, 'custom');
  assert.equal(directory.encounters[1].source, null);
  assert.equal((await request(app.address, '/encounters/city-preview-10405')).status, 404);
});
