import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { listHallProfiles, createHallLocalState, applyHallLocalState } from './templates/hall-local-state.js';

const profile = { id: '11111111-1111-1111-1111-111111111111', displayName: '本地旅人', revision: 3 };
test('explicit selection only; unknown growth stays unknown', () => {
  assert.equal(createHallLocalState([profile], null).profile, null);
  assert.throws(() => createHallLocalState([profile], 'missing'));
  const state = createHallLocalState([profile], profile.id);
  assert.equal(state.profile.displayName, profile.displayName);
  assert.equal(state.growth.level, null);
  assert.equal(state.growth.experience, null);
});
test('GET-only loopback endpoint and rejection of bad payloads', async () => {
  const calls = [];
  const fetchImpl = async (...args) => { calls.push(args); return { ok: true, json: async () => ({ profiles: [profile] }) }; };
  assert.equal((await listHallProfiles(7460, { fetchImpl }))[0].id, profile.id);
  assert.equal(calls[0][0], 'http://127.0.0.1:7460/api/rebuild/v1/profiles');
  assert.equal(calls[0][1].method, 'GET');
  assert.equal(calls[0][1].credentials, 'omit');
  await assert.rejects(listHallProfiles('7460', { fetchImpl }));
  await assert.rejects(listHallProfiles(7460, { fetchImpl: async () => ({ ok: true, json: async () => ({ profiles: [profile, profile] }) }) }));
  await assert.rejects(listHallProfiles(7460, { fetchImpl: async () => ({ ok: false, status: 503 }) }));
});
test('patch actual extracted source trees without mutating the evidence; reject layout drift', async () => {
  const layouts = JSON.parse(await readFile(new URL('../analysis/hall/ui-dependencies/report.json', import.meta.url), 'utf8'));
  const before = JSON.stringify(layouts);
  const state = createHallLocalState([profile], profile.id);
  const after = applyHallLocalState(layouts, state);
  assert.equal(JSON.stringify(layouts), before);
  for (const patch of state.patches) {
    let node = after.layouts.find(l => l.path === patch.layout).tree;
    for (const name of patch.path.split('.')) node = node.children.find(c => c.name === name);
    for (const [key, value] of Object.entries(patch.values)) assert.equal(node[key], value);
  }
  assert.throws(() => applyHallLocalState({ layouts: [] }, state));
  const bindings = JSON.parse(await readFile(new URL('../analysis/hall/state/widget-paths.json', import.meta.url), 'utf8'));
  assert.equal(bindings.find(b => b.module === 4567 && b.widget === '_wPlayerName').path, state.patches[0].path);
});
