import test from 'node:test';
import assert from 'node:assert/strict';
import { int, toTagged } from '../../battle-core/src/index.js';
import { createBattle, endTurn, playCard, validateState, validateDefinition, STATUS_FORMAT } from '../src/index.js';
const I = n => toTagged(int(n));
const clone = value => JSON.parse(JSON.stringify(value));
function fixture() {
  return {
    id: 'synthetic-status-v2', player: { id: 'p', name: 'P', maxHp: I(100) }, enemy: { id: 'e', name: 'E', maxHp: I(100) },
    statusRules: { policy: 'breakdown-reconstruction-v1', attack: { player: I(101), enemy: I(101) } },
    deck: [{ instanceId: 'h', cardId: 'heal' }, { instanceId: 'g', cardId: 'guard' }, { instanceId: 'b', cardId: 'break' }],
    cards: {
      heal: { name: 'Heal', cost: 0, effects: [{ type: 'heal', target: 'self', amount: '10' }] },
      guard: { name: 'Guard', cost: 0, effects: [{ type: 'shield', target: 'self', amount: '30' }] },
      break: { name: 'Break', cost: 0, effects: [{ type: 'breakdown', target: 'opponent', stacks: 2 }] },
    },
    enemySkills: { apply: { effects: [{ type: 'breakdown', target: 'opponent', stacks: 2 }] }, wait: { effects: [] } },
    enemyIntents: [['apply']], enemyFallback: ['wait'], initialDraw: 3, roundDraw: 3, handLimit: 3, energyPerRound: 3, maxRounds: 10,
  };
}
test('status save round-trip continues identically and ticks before hand discard', () => {
  const d = fixture(), first = endTurn(d, createBattle(d, 3).state);
  assert.equal(first.state.format, STATUS_FORMAT);
  assert.equal(first.state.player.hp.decimal, '100'); // newly inflicted on enemy turn: next owner end
  assert.equal(first.state.breakdown.player, 2);
  const restored = validateState(d, clone(first.state));
  const next = endTurn(d, restored);
  assert.deepEqual(next, endTurn(d, first.state));
  assert.equal(next.state.player.hp.decimal, '60');
  assert.equal(next.events[0].type, 'BreakdownTriggered');
  assert.deepEqual(first.state.breakdown, { player: 2, enemy: 0 });
});
test('positive recovery removes one stack; overheal and zero do not', () => {
  const d = fixture(); let s = endTurn(d, createBattle(d, 3).state).state;
  s = playCard(d, s, 'h').state; // full health
  assert.equal(s.breakdown.player, 2);
  s = endTurn(d, s).state;
  const healed = playCard(d, s, 'h');
  assert.equal(healed.state.player.hp.decimal, '70');
  assert.equal(healed.state.breakdown.player, 1);
  assert.equal(healed.events.find(e => e.type === 'HealthRestored').restored.decimal, '10');
  const zero = fixture(); zero.cards.heal.effects[0].amount = '0';
  assert.equal(playCard(zero, s, 'h').state.breakdown.player, 2);
});
test('shield absorbs status damage before clearing for the next player turn', () => {
  const d = fixture(); let s = endTurn(d, createBattle(d, 3).state).state;
  s = playCard(d, s, 'g').state;
  const next = endTurn(d, s);
  assert.equal(next.state.player.hp.decimal, '90');
  const hit = next.events.find(e => e.type === 'DamageApplied');
  assert.equal(hit.absorbed.decimal, '30'); assert.equal(hit.hpLost.decimal, '10');
});
test('lethal status stops enemy actions and next-turn draws', () => {
  const d = fixture(); d.statusRules.attack.enemy = I(1000);
  const s = endTurn(d, createBattle(d, 3).state).state;
  const next = endTurn(d, s);
  assert.equal(next.state.status, 'lost'); assert.equal(next.state.player.hp.decimal, '0');
  assert.ok(!next.events.some(e => ['EnemySkillUsed', 'TurnStarted', 'CardDrawn'].includes(e.type)));
  assert.deepEqual(next.state.piles, s.piles);
});
test('enemy owner-end tick follows enemy skills, and can win the battle', () => {
  const d = fixture(); d.statusRules.attack.player = I(1000);
  const s = playCard(d, createBattle(d, 3).state, 'b').state;
  const next = endTurn(d, s);
  assert.equal(next.state.status, 'won');
  assert.ok(next.events.findIndex(e => e.type === 'EnemySkillUsed') < next.events.findIndex(e => e.type === 'BreakdownTriggered'));
  assert.ok(!next.events.some(e => e.type === 'TurnStarted'));
});
test('stacks cap at 999; invalid saves and incompatible formats fail closed', () => {
  const d = fixture(); d.cards.break.effects = Array(2).fill({ type: 'breakdown', target: 'opponent', stacks: 999 });
  const s = playCard(d, createBattle(d, 3).state, 'b').state;
  assert.equal(s.breakdown.enemy, 999);
  for (const corrupt of [x => { delete x.breakdown; }, x => { x.breakdown.enemy = 1000; }, x => { x.format = 'hczs-battle-session-v1'; }]) {
    const bad = clone(s); corrupt(bad); assert.throws(() => validateState(d, bad), TypeError);
  }
  const old = clone(d); delete old.statusRules;
  assert.throws(() => validateDefinition(old), /unsupported effect/);
  d.statusRules.policy = 'original'; assert.throws(() => validateDefinition(d), /policy/);
});
