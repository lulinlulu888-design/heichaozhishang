import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { BattleStore } from '../src/battles.js';
import { fixture } from './helpers.js';
import { int, toTagged } from '../../packages/battle-core/src/index.js';

const hp = n => toTagged(int(n));
function scenario() {
  return { kind: 'synthetic-status-persistence', definition: {
    id: 'synthetic-status-save', player: { id: 'p', name: 'P', maxHp: hp(100) }, enemy: { id: 'e', name: 'E', maxHp: hp(100) },
    statusRules: { policy: 'breakdown-reconstruction-v1', attack: { player: hp(10), enemy: hp(101) } },
    deck: [{ instanceId: 'heal-1', cardId: 'heal' }],
    cards: { heal: { name: 'Heal', cost: 0, effects: [{ type: 'heal', target: 'self', amount: '10' }] } },
    enemySkills: { apply: { effects: [{ type: 'breakdown', target: 'opponent', stacks: 2 }] }, wait: { effects: [] } },
    enemyIntents: [['apply']], enemyFallback: ['wait'], initialDraw: 1, roundDraw: 1,
    energyPerRound: 1, handLimit: 1, maxRounds: 10,
  } };
}
const childCode = `
import { readFileSync } from 'node:fs';
import { BattleStore } from ${JSON.stringify(new URL('../src/battles.js', import.meta.url).href)};
const input = JSON.parse(readFileSync(0, 'utf8'));
const store = new BattleStore(input.path);
try {
  const before = store.get(input.profile, input.id);
  const result = store.act(input.profile, input.id, input.command);
  process.stdout.write(JSON.stringify({ before, result }));
} finally { store.close(); }
`;

test('v2 status survives SQLite and a fresh Node process; retried tick/heal never repeats', async t => {
  const files = await fixture(t), path = `${files.savePath}.status`, profile = randomUUID();
  let store = new BattleStore(path);
  files.cleanupWith(() => store?.close());
  const config = scenario();
  const created = store.create(profile, config, { requestId: 'create', seed: 3 }).battle;
  const inflicted = store.act(profile, created.id,
    { requestId: 'inflict', expectedRevision: 1, type: 'end-turn' }).battle;
  assert.equal(inflicted.state.breakdown.player, 2);
  assert.equal(inflicted.state.player.hp.decimal, '100');
  store.close(); store = null;
  const tick = { requestId: 'tick', expectedRevision: 2, type: 'end-turn' };
  const child = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', childCode], {
    input: JSON.stringify({ path, profile, id: created.id, command: tick }), encoding: 'utf8', timeout: 15000,
  }));
  assert.deepEqual(child.before, inflicted);
  assert.equal(child.result.battle.state.player.hp.decimal, '60');
  assert.equal(child.result.battle.state.breakdown.player, 2);
  store = new BattleStore(path);
  const replay = store.act(profile, created.id, tick);
  assert.equal(replay.replayed, true);
  assert.deepEqual(replay.events, child.result.events);
  assert.deepEqual(store.get(profile, created.id), child.result.battle);
  // Changing the source config after creation cannot alter a saved battle.
  config.definition.statusRules.attack.enemy = hp(9999);
  const heal = { requestId: 'heal', expectedRevision: 3, type: 'play-card', instanceId: 'heal-1' };
  const recovered = store.act(profile, created.id, heal);
  assert.equal(recovered.battle.state.player.hp.decimal, '70');
  assert.equal(recovered.battle.state.breakdown.player, 1);
  assert.equal(store.act(profile, created.id, heal).replayed, true);
  const next = store.act(profile, created.id, { requestId: 'next', expectedRevision: 4, type: 'end-turn' });
  assert.equal(next.battle.state.player.hp.decimal, '50');
  assert.equal(next.battle.state.breakdown.player, 1);
  assert.equal(next.battle.revision, 5);
});

test('failed v2 healing transaction rolls back HP, stacks, revision and retry receipt together', async t => {
  const files = await fixture(t), profile = randomUUID(), store = new BattleStore(`${files.savePath}.status`);
  files.cleanupWith(() => store.close());
  const initial = store.create(profile, scenario(), { requestId: 'create', seed: 3 }).battle;
  store.act(profile, initial.id, { requestId: 'inflict', expectedRevision: 1, type: 'end-turn' });
  const damaged = store.act(profile, initial.id, { requestId: 'tick', expectedRevision: 2, type: 'end-turn' }).battle;
  const heal = { requestId: 'heal', expectedRevision: 3, type: 'play-card', instanceId: 'heal-1' };
  store.db.exec("CREATE TRIGGER reject_status BEFORE INSERT ON battle_commands BEGIN SELECT RAISE(ABORT, 'status save failed'); END;");
  assert.throws(() => store.act(profile, initial.id, heal), /status save failed/);
  assert.deepEqual(store.get(profile, initial.id), damaged);
  assert.equal(store.db.prepare('SELECT count(*) AS n FROM battle_commands WHERE command_id=?').get('heal').n, 0);
  store.db.exec('DROP TRIGGER reject_status');
  const recovered = store.act(profile, initial.id, heal);
  assert.equal(recovered.battle.state.breakdown.player, 1);
  assert.equal(recovered.battle.state.player.hp.decimal, '70');
});
