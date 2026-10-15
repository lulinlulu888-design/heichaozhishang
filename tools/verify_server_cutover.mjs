// Read-only comparison of an HTTP snapshot captured before a storage migration.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
const { values } = parseArgs({ options: {
  before: { type: 'string' }, address: { type: 'string', default: 'http://127.0.0.1:7460' }, report: { type: 'string' },
} });
if (!values.before) throw new Error('--before JSON snapshot is required');
const before = JSON.parse((await readFile(values.before, 'utf8')).replace(/^\uFEFF/, ''));
const api = async path => {
  const response = await fetch(values.address + '/api/rebuild/v1' + path, { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 200, path);
  return response.json();
};
const bootstrap = await api('/bootstrap');
assert.equal(bootstrap.storage, 'mongodb');
assert.deepEqual(bootstrap.profiles, before.profiles);
const battles = [];
for (const profile of bootstrap.profiles) {
  const list = await api(`/profiles/${profile.id}/battles`);
  for (const battle of list.battles) battles.push((await api(`/profiles/${profile.id}/battles/${battle.id}`)).battle);
  const hall = (await api(`/profiles/${profile.id}/hall`)).hall;
  assert.equal(hall.profileId, profile.id);
}
assert.deepEqual(battles, before.battles);
const heroes = await api('/heroes');
assert.equal(heroes.heroes.length, 35);
const result = { checkedAt: new Date().toISOString(), address: values.address, storage: bootstrap.storage,
  profileCount: before.profiles.length, battleCount: battles.length, heroCount: heroes.heroes.length,
  exactProfilesAndBattlesMatch: true, gameplayReady: bootstrap.gameplayReady };
if (values.report) await writeFile(values.report, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
