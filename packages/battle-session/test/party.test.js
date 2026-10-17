import test from 'node:test';
import assert from 'node:assert/strict';
import { createBattle, playCard, endTurn, validateState, validateDefinition, PARTY_FORMAT } from '../src/index.js';

const tagged = value => ({ numeric_type: 'integer', decimal: String(value) });
function definition(overrides = {}) {
  return {
    id: 'party-test', player: { id: 'party', name: '队伍' },
    party: [{ id: 'a', name: 'A', maxHp: tagged(300), attack: tagged(100) }, { id: 'b', name: 'B', maxHp: tagged(500), attack: tagged(200) }],
    enemy: { id: 'boss', name: 'Boss', maxHp: tagged(5000), attack: tagged(100) },
    deck: [
      { instanceId: 'c1', cardId: 'hit', ownerId: 'a' }, { instanceId: 'c2', cardId: 'hit', ownerId: 'b' },
      { instanceId: 'c3', cardId: 'wall', ownerId: 'b' }, { instanceId: 'c4', cardId: 'cheer', ownerId: 'a' },
    ],
    cards: {
      hit: { name: '斩击', cost: 1, effects: [{ type: 'damage', target: 'opponent', factor: 100 }] },
      wall: { name: '群体护盾', cost: 1, effects: [{ type: 'shield', target: 'party', factor: 50 }] },
      cheer: { name: '友情之力', cost: 1, effects: [{ type: 'attackBuff', target: 'party', stacks: 1 }] },
    },
    enemySkills: {
      flurry: { effects: [{ type: 'damage', target: 'first-mid-last', factor: 100, times: 4 }] },
      rage: { effects: [{ type: 'attackBuff', target: 'self', stacks: 5 }] },
    },
    enemyIntents: [['flurry'], ['rage']], enemyFallback: ['flurry'],
    initialDraw: 4, roundDraw: 4, energyPerRound: 5, handLimit: 10, maxRounds: 3,
    partyRules: { policy: 'prologue-party-reconstruction-v1', buffId: '1001', attackPercentPerStack: 6, maxStacks: 999, enemyTargeting: 'first-living-in-formation' },
    ...overrides,
  };
}

test('owner attack and attack-buff stacks drive card damage; party shields and buffs reach every member', () => {
  const d = definition();
  let { state } = createBattle(d, 1);
  assert.equal(state.format, PARTY_FORMAT);
  assert.deepEqual(state.piles.hand, ['c1', 'c2', 'c3', 'c4']);
  let result = playCard(d, state, 'c4');
  assert.deepEqual(result.state.party.map(m => m.attackBuff), [1, 1]);
  result = playCard(d, result.state, 'c2');
  // B: 200 attack * 100% * (1 + 0.06) = 212.
  assert.equal(result.events.find(e => e.type === 'DamageApplied').amount, '212');
  result = playCard(d, result.state, 'c3');
  assert.deepEqual(result.state.party.map(m => m.shield.decimal), ['100', '100']);
  assert.equal(result.state.enemy.hp.decimal, '4788');
});

test('first-mid-last hits the first living member, passes remaining hits on, and removes the defeated owner cards', () => {
  const d = definition({ party: [{ id: 'a', name: 'A', maxHp: tagged(150), attack: tagged(100) }, { id: 'b', name: 'B', maxHp: tagged(500), attack: tagged(200) }] });
  let { state } = createBattle(d, 1);
  const { state: next, events } = endTurn(d, state);
  const hits = events.filter(e => e.type === 'DamageApplied');
  assert.deepEqual(hits.map(e => [e.memberIndex, e.hpLost.decimal]), [[0, '100'], [0, '50'], [1, '100'], [1, '100']]);
  assert.deepEqual(events.filter(e => e.type === 'MemberDefeated').map(e => e.memberId), ['a']);
  assert.deepEqual([...next.piles.removed].sort(), ['c1', 'c4']);
  assert.ok(next.piles.hand.every(id => !['c1', 'c4'].includes(id)));
  assert.equal(next.status, 'player-turn');
  // The boss buff raises its later damage by 6% per stack.
  const after = endTurn(d, endTurn(d, next).state);
  assert.equal(after.events.find(e => e.type === 'DamageApplied').amount, '130');
});

test('the party loses only when every member is defeated, and at the round limit', () => {
  const weak = definition({ party: [{ id: 'a', name: 'A', maxHp: tagged(100), attack: tagged(1) }, { id: 'b', name: 'B', maxHp: tagged(100), attack: tagged(1) }] });
  const lost = endTurn(weak, createBattle(weak, 1).state).state;
  assert.deepEqual([lost.status, lost.outcomeReason], ['lost', 'party-defeated']);
  const d = definition({ enemySkills: { flurry: { effects: [{ type: 'attackBuff', target: 'self', stacks: 1 }] }, rage: { effects: [{ type: 'attackBuff', target: 'self', stacks: 1 }] } } });
  let state = createBattle(d, 1).state;
  for (let round = 0; round < 3; ++round) state = endTurn(d, state).state;
  assert.deepEqual([state.status, state.outcomeReason, state.round], ['lost', 'round-limit', 3]);
  assert.throws(() => endTurn(d, state), /terminal/);
});

test('party definitions and states reject unknown owners, unlabelled policies and tampered removal', () => {
  assert.throws(() => validateDefinition(definition({ deck: [{ instanceId: 'x', cardId: 'hit', ownerId: 'zz' }] })), /owner/);
  assert.throws(() => validateDefinition(definition({ partyRules: { ...definition().partyRules, attackPercentPerStack: 10 } })), /policy/);
  const d = definition(), { state } = createBattle(d, 1);
  assert.deepEqual(validateState(d, state), state);
  const tampered = structuredClone(state);
  tampered.piles.removed = [tampered.piles.hand.pop()];
  assert.throws(() => validateState(d, tampered), /removed/);
  const dead = structuredClone(state);
  dead.party[0].hp = tagged(0);
  assert.throws(() => validateState(d, dead), /removed/);
});
