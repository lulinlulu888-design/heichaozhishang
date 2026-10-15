import test from 'node:test';
import assert from 'node:assert/strict';
import { int, toTagged } from '../../battle-core/src/index.js';
import { createBattle, playCard, endTurn, validateDefinition, validateState, ULTIMATE_FORMAT } from '../src/index.js';

const hp = amount => toTagged(int(amount));
// Synthetic combat values; source percentages and city enablement are tested in server tests.
function definition(count = 3) {
  return { id: 'synthetic-ultimate-v3', player: { id: '1', name: 'Player', maxHp: hp(100) },
    enemy: { id: 'enemy', name: 'Enemy', maxHp: hp(100000) },
    deck: Array.from({ length: count }, (_, i) => ({ instanceId: `normal:${i}`, cardId: 'attack' })),
    cards: {
      attack: { name: 'Normal', cost: 1, effects: [], ownerId: '1', cardType: 0, specialPoints: 1, removeOnLeaveHand: false },
      '410104': { name: 'Ultimate', cost: 0, effects: Array.from({ length: 8 }, () => ({ type: 'damage', target: 'opponent', amount: '1' })),
        ownerId: '1', cardType: 7, specialPoints: 0, removeOnLeaveHand: true },
    }, enemySkills: { wait: { effects: [] } }, enemyIntents: [], enemyFallback: ['wait'],
    initialDraw: count, roundDraw: count, energyPerRound: 3, handLimit: 64, maxRounds: 30,
    ultimateRules: { policy: 'elsa-combo-reconstruction-v1', ownerId: '1', cardId: '410104', pointsRequired: 3, maxPerRound: 3 } };
}
function triple(d, state) {
  let result;
  for (const instanceId of state.piles.hand.filter(id => !id.startsWith('ultimate:')).slice(0, 3)) {
    result = playCard(d, state, instanceId); state = result.state;
  }
  return result;
}

test('three ordinary cards create one unique ultimate; zero energy permits eight hits and removes it', () => {
  const d = definition(); let state = createBattle(d, 10).state;
  assert.equal(state.format, ULTIMATE_FORMAT);
  for (let i = 0; i < 2; i++) {
    state = playCard(d, state, `normal:${i}`).state;
    assert.equal(state.ultimate.points, i + 1);
    assert.equal(state.cards.length, 3);
  }
  const third = playCard(d, state, 'normal:2');
  assert.equal(third.state.energy, 0);
  assert.deepEqual(third.state.ultimate, { chainOwnerId: null, points: 0, generatedThisRound: 1, generatedTotal: 1 });
  assert.deepEqual(third.state.piles.hand, ['ultimate:1']);
  assert.deepEqual(third.events.filter(e => e.generated), [{ type: 'CardDrawn', instanceId: 'ultimate:1', generated: true }]);
  const used = playCard(d, third.state, 'ultimate:1');
  assert.equal(used.state.energy, 0);
  assert.equal(used.events.filter(e => e.type === 'DamageApplied').length, 8);
  assert.deepEqual(used.state.piles.removed, ['ultimate:1']);
  assert.ok(!used.state.piles.discard.includes('ultimate:1'));
  assert.deepEqual(used.state.ultimate, third.state.ultimate);
  assert.throws(() => playCard(d, used.state, 'ultimate:1'), /not in hand/);
  assert.deepEqual(validateState(d, JSON.parse(JSON.stringify(used.state))), used.state);
});

test('per-round cap is three; ending the round removes held ultimates and resets only round counters', () => {
  const d = definition(12); d.cards.attack.cost = 0;
  let state = createBattle(d, 0).state;
  for (const { instanceId } of d.deck) state = playCard(d, state, instanceId).state;
  assert.equal(state.ultimate.generatedThisRound, 3);
  assert.equal(state.ultimate.points, 0);
  assert.deepEqual(state.piles.hand, ['ultimate:1', 'ultimate:2', 'ultimate:3']);
  const next = endTurn(d, state);
  assert.deepEqual(next.state.piles.removed, state.piles.hand);
  assert.deepEqual(next.state.ultimate, { chainOwnerId: null, points: 0, generatedThisRound: 0, generatedTotal: 3 });
  const generated = triple(d, next.state);
  assert.equal(generated.state.ultimate.generatedTotal, 4);
  assert.ok(generated.state.piles.hand.includes('ultimate:4'));
  assert.equal(new Set(generated.state.cards.map(c => c.instanceId)).size, generated.state.cards.length);
  const partial = playCard(d, next.state, next.state.piles.hand[0]).state;
  assert.equal(endTurn(d, partial).state.ultimate.points, 0);
});

test('removed generated instances stay bounded by rounds, independent of the 64-card initial-deck limit', () => {
  const d = definition(9); d.cards.attack.cost = 0;
  let state = createBattle(d, 0).state;
  for (let round = 1; round <= 23; round++) {
    for (const instanceId of state.piles.hand.slice()) state = playCard(d, state, instanceId).state;
    state = endTurn(d, state).state;
  }
  assert.equal(state.piles.removed.length, 69);
  assert.equal(state.cards.length, 78);
  assert.equal(state.piles.draw.some(id => id.startsWith('ultimate:')), false);
  assert.deepEqual(validateState(d, state), state);
});

test('local full-hand and lethal policies do not queue or fabricate a generated card', () => {
  const full = definition(6); full.initialDraw = 3; full.handLimit = 3;
  full.cards.attack.effects = [{ type: 'draw', count: 1 }];
  const result = triple(full, createBattle(full, 0).state);
  assert.equal(result.state.piles.hand.length, 3);
  assert.deepEqual(result.state.ultimate, { chainOwnerId: null, points: 0, generatedThisRound: 0, generatedTotal: 0 });
  const lethal = definition(); lethal.enemy.maxHp = hp(3);
  lethal.cards.attack.effects = [{ type: 'damage', target: 'opponent', amount: '1' }];
  const won = triple(lethal, createBattle(lethal, 0).state);
  assert.equal(won.state.status, 'won'); assert.equal(won.state.ultimate.generatedTotal, 0);
  assert.equal(won.events.some(e => e.generated), false);
});

test('generated registries, card metadata and counters reject corruption', () => {
  const d = definition(), state = triple(d, createBattle(d, 0).state).state;
  for (const mutate of [
    s => { s.cards.at(-1).cardId = 'attack'; },
    s => { s.cards.at(-1).instanceId = 'ultimate:9'; },
    s => { s.ultimate.generatedTotal++; },
    s => { s.ultimate.generatedThisRound = 2; },
    s => { s.piles.discard.push(s.piles.hand.pop()); },
    s => { s.ultimate.points = 1; },
  ]) { const copy = structuredClone(state); mutate(copy); assert.throws(() => validateState(d, copy)); }
  for (const mutate of [
    x => { x.deck[0].instanceId = 'ultimate:1'; },
    x => { x.cards.attack.ownerId = '2'; },
    x => { x.cards['410104'].specialPoints = 1; },
    x => { x.ultimateRules.maxPerRound = 4; },
  ]) { const copy = structuredClone(d); mutate(copy); assert.throws(() => validateDefinition(copy)); }
});

test('v1 and v2 definitions remain opt-in-free and reject injected generated cards', () => {
  for (const statusRules of [undefined, { policy: 'breakdown-reconstruction-v1', attack: { player: hp(1), enemy: hp(1) } }]) {
    const old = definition(); delete old.ultimateRules; delete old.cards['410104'];
    for (const key of ['ownerId', 'cardType', 'specialPoints', 'removeOnLeaveHand']) delete old.cards.attack[key];
    if (statusRules) old.statusRules = statusRules;
    const state = triple(old, createBattle(old, 0).state).state;
    assert.equal(state.format, statusRules ? 'hczs-battle-session-v2' : 'hczs-battle-session-v1');
    assert.equal(state.ultimate, undefined); assert.equal(state.cards.length, 3);
    assert.deepEqual(validateState(old, JSON.parse(JSON.stringify(state))), state);
    const corrupt = structuredClone(state); corrupt.cards.push({ instanceId: 'ultimate:1', cardId: 'attack' });
    assert.throws(() => validateState(old, corrupt));
  }
});
