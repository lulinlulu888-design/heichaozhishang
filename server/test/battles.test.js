import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createApp } from '../src/app.js';
import { BattleStore } from '../src/battles.js';
import { ProfileStore } from '../src/store.js';
import { loadTutorialScenario } from '../src/tutorial.js';
import { fixture, request } from './helpers.js';

const tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter', import.meta.url));
const realData = fileURLToPath(new URL('../../analysis/game-data', import.meta.url));
async function setup(t) {
  const files = await fixture(t);
  const options = { ...files, dataDirectory: realData, tutorialDirectory, port: 0, log: e => assert.fail(JSON.stringify(e)) };
  let app = await createApp(options);
  files.cleanupWith(() => app.close());
  const { body: { profile } } = await request(app.address, '/profiles', 'POST', { displayName: '教学战斗验证' });
  const prefix = `/profiles/${profile.id}/battles`;
  const created = await request(app.address, prefix, 'POST', { requestId: 'initial-battle', seed: 123456 });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const retried = await request(app.address, prefix, 'POST', { requestId: 'initial-battle', seed: 123456 });
  assert.equal(retried.body.replayed, true);
  assert.deepEqual(retried.body.battle, created.body.battle);
  assert.equal((await request(app.address, prefix)).body.battles.length, 1);
  assert.equal((await request(app.address, prefix, 'POST', { requestId: 'initial-battle', seed: 2 })).status, 409);
  return { files, profile, prefix, battle: created.body.battle, get app() { return app; },
    async reopen() { await app.close(); app = await createApp(options); } };
}
function command(battle, n) {
  const playable = battle.state.piles.hand.find(instanceId => {
    const card = battle.state.cards.find(c => c.instanceId === instanceId);
    return battle.scenario.definition.cards[card.cardId].cost <= battle.state.energy;
  });
  return { requestId: `test-action-${n}`, expectedRevision: battle.revision,
    ...(playable ? { type: 'play-card', instanceId: playable } : { type: 'end-turn' }) };
}

test('real tutorial data can be played through the HTTP API, saved, resumed and won', async t => {
  const run = await setup(t);
  let battle = run.battle;
  assert.equal(battle.state.player.hp.numeric_type, 'binary64');
  assert.equal(battle.state.player.hp.hex, '0x1.ba33333333334p+10');
  assert.equal(battle.state.enemy.hp.decimal, '4600');
  assert.equal(battle.state.cards.length, 7);
  const initialProfile = (await request(run.app.address, `/profiles/${run.profile.id}`)).body.profile;
  const first = await request(run.app.address, `${run.prefix}/${battle.id}/actions`, 'POST', command(battle, 0));
  assert.equal(first.status, 200, JSON.stringify(first.body));
  battle = first.body.battle;
  assert.ok(Number(battle.state.enemy.hp.decimal) < 4600);
  await run.reopen();
  assert.deepEqual((await request(run.app.address, `${run.prefix}/${battle.id}`)).body.battle, battle);
  let n = 1;
  while (battle.state.status === 'player-turn' && n < 150) {
    const next = await request(run.app.address, `${run.prefix}/${battle.id}/actions`, 'POST', command(battle, n++));
    assert.equal(next.status, 200, JSON.stringify(next.body));
    battle = next.body.battle;
  }
  assert.equal(battle.state.status, 'won');
  assert.equal(battle.state.outcomeReason, 'enemy-defeated');
  await run.reopen();
  assert.deepEqual((await request(run.app.address, `${run.prefix}/${battle.id}`)).body.battle, battle);
  const terminal = await request(run.app.address, `${run.prefix}/${battle.id}/actions`, 'POST',
    { requestId: 'after-win', expectedRevision: battle.revision, type: 'end-turn' });
  assert.equal(terminal.status, 400);
  assert.deepEqual((await request(run.app.address, `/profiles/${run.profile.id}`)).body.profile, initialProfile,
    'No unverified original reward is silently credited');
  assert.equal((await request(run.app.address, '/status')).body.gameplayReady, false);
});

test('battle commands are atomic, revision guarded, and retryable without duplicate effects', async t => {
  const run = await setup(t), initial = run.battle;
  const path = `${run.prefix}/${initial.id}/actions`;
  const invalid = await request(run.app.address, path, 'POST',
    { requestId: 'bad-card', expectedRevision: 1, type: 'play-card', instanceId: 'missing' });
  assert.equal(invalid.status, 400);
  assert.deepEqual((await request(run.app.address, `${run.prefix}/${initial.id}`)).body.battle, initial);
  const input = command(initial, 0);
  const first = await request(run.app.address, path, 'POST', input);
  assert.equal(first.status, 200);
  const retry = await request(run.app.address, path, 'POST', input);
  assert.equal(retry.status, 200);
  assert.equal(retry.body.replayed, true);
  assert.deepEqual(retry.body.battle, first.body.battle);
  const collision = await request(run.app.address, path, 'POST', { ...input, expectedRevision: 2 });
  assert.equal(collision.status, 409);
  const next = command(first.body.battle, 1);
  const competing = { requestId: 'competing', expectedRevision: first.body.battle.revision, type: 'end-turn' };
  const responses = await Promise.all([request(run.app.address, path, 'POST', next), request(run.app.address, path, 'POST', competing)]);
  assert.deepEqual(responses.map(r => r.status).sort(), [200, 409]);
  assert.equal((await request(run.app.address, `${run.prefix}/${initial.id}`)).body.battle.revision, 3);
  await run.reopen();
  assert.equal((await request(run.app.address, path, 'POST', input)).body.replayed, true);
  assert.equal((await request(run.app.address, `${run.prefix}/${initial.id}`)).body.battle.revision, 3);
});

test('a battle cannot be read or acted on through another local profile', async t => {
  const run = await setup(t);
  const other = (await request(run.app.address, '/profiles', 'POST', { displayName: '另一个档案' })).body.profile;
  const wrong = `/profiles/${other.id}/battles/${run.battle.id}`;
  assert.equal((await request(run.app.address, wrong)).status, 404);
  assert.equal((await request(run.app.address, `${wrong}/actions`, 'POST', command(run.battle, 0))).status, 404);
  assert.deepEqual((await request(run.app.address, `/profiles/${other.id}/battles`)).body.battles, []);
});

test('battle SQLite failures roll back state and retry ledger together; profile DB identity is preserved', async t => {
  const files = await fixture(t);
  const profiles = new ProfileStore(files.savePath);
  const profile = profiles.create({ displayName: '事务验证' });
  assert.throws(() => new BattleStore(files.savePath), /Unsupported battle save identity/);
  assert.equal(profiles.get(profile.id).displayName, '事务验证');
  profiles.close();
  const store = new BattleStore(`${files.savePath}.battles`);
  files.cleanupWith(() => store.close());
  const first = store.create(profile.id, await loadTutorialScenario(tutorialDirectory), { requestId: 'create-1', seed: 9 }).battle;
  const input = command(first, 0);
  store.db.exec("CREATE TRIGGER reject_command BEFORE INSERT ON battle_commands BEGIN SELECT RAISE(ABORT, 'test storage failure'); END;");
  assert.throws(() => store.act(profile.id, first.id, input), /test storage failure/);
  assert.deepEqual(store.get(profile.id, first.id), first);
  assert.equal(store.db.prepare('SELECT count(*) AS n FROM battle_commands').get().n, 0);
  store.db.exec('DROP TRIGGER reject_command');
  assert.equal(store.act(profile.id, first.id, input).battle.revision, 2);
});
