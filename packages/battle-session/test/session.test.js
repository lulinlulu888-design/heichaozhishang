import test from 'node:test';
import assert from 'node:assert/strict';
import { int, float, toTagged, fromTagged, compare } from '../../battle-core/src/index.js';
import { createBattle, playCard, endTurn, validateState, validateDefinition, LIMITS } from '../src/index.js';
const I = n => toTagged(int(n)), F = n => toTagged(float(n));
const damage = (amount, target = 'opponent') => ({ type: 'damage', target, amount });
const shield = (amount, target = 'self') => ({ type: 'shield', target, amount });
const copy = value => JSON.parse(JSON.stringify(value));
const decimal = value => value.decimal;
// Synthetic data only. Names/values below are not original game definitions.
function definition(overrides = {}) {
  return {
    id: 'synthetic-v1', player: { id: 'p', name: 'Player', maxHp: I(100) }, enemy: { id: 'e', name: 'Enemy', maxHp: I(12) },
    deck: [{ instanceId: 'i1', cardId: 'attack' }, { instanceId: 'i2', cardId: 'guard' },
      { instanceId: 'i3', cardId: 'attack' }, { instanceId: 'i4', cardId: 'cycle' }],
    cards: { attack: { name: 'Attack', cost: 1, effects: [damage('6')] }, guard: { name: 'Guard', cost: 1, effects: [shield('5')] },
      cycle: { name: 'Cycle', cost: 0, effects: [{ type: 'draw', count: 2 }] } },
    enemySkills: { hit: { effects: [damage('7')] }, wait: { effects: [] } }, enemyIntents: [['hit']], enemyFallback: ['hit'],
    initialDraw: 3, roundDraw: 3, energyPerRound: 2, handLimit: 3, maxRounds: 5,
    ...overrides,
  };
}
function assertFinal(result, def) {
  assert.deepEqual(result.events.at(-1), { type: 'StateUpdated', state: result.state });
  assert.deepEqual(validateState(def, copy(result.state)), result.state);
}

test('create draws the provided deck in order without consuming random state and freezes output', () => {
  const def = definition(), result = createBattle(def, 0);
  assert.deepEqual(result.state.piles.hand, ['i1', 'i2', 'i3']);
  assert.deepEqual(result.state.piles.draw, ['i4']);
  assert.equal(result.state.rng.state, 0); assert.equal(result.state.round, 1);
  assert.equal(result.state.energy, 2); assert.equal(result.state.actionIndex, 0);
  assert.equal(result.events[0].type, 'BattleStarted');
  assert.throws(() => result.state.piles.hand.push('bad'), TypeError);
  assert.throws(() => { result.state.player.hp.decimal = '0'; }, TypeError);
  def.deck[0].instanceId = 'changed';
  assert.equal(result.state.cards[0].instanceId, 'i1');
});

test('two legal attacks win, conserve instances, and reject all terminal operations', () => {
  const def = definition(), initial = createBattle(def, 12).state;
  const first = playCard(def, initial, 'i1');
  assert.equal(decimal(first.state.enemy.hp), '6'); assert.equal(first.state.energy, 1);
  const won = playCard(def, first.state, 'i3');
  assert.equal(won.state.status, 'won'); assert.equal(won.state.outcomeReason, 'enemy-defeated');
  assert.equal(decimal(won.state.enemy.hp), '0'); assert.equal(won.state.energy, 0);
  assert.deepEqual(won.state.piles.discard, ['i1', 'i3']);
  assert.equal(won.events.filter(e => e.type === 'BattleEnded').length, 1);
  assert.throws(() => endTurn(def, won.state), /terminal/);
  assert.throws(() => playCard(def, won.state, 'i2'), /terminal/);
  assert.equal(initial.energy, 2); assert.equal(decimal(initial.enemy.hp), '12');
  assertFinal(won, def);
});

test('victory stops later effects immediately but the played card still reaches discard', () => {
  const def = definition();
  def.cards.attack.effects = [damage('12'), damage('999', 'self'), { type: 'draw', count: 2 }];
  const result = playCard(def, createBattle(def, 0).state, 'i1');
  assert.equal(result.state.status, 'won'); assert.equal(decimal(result.state.player.hp), '100');
  assert.equal(result.events.filter(e => e.type === 'DamageApplied').length, 1);
  assert.equal(result.events.filter(e => e.type === 'CardDrawn').length, 0);
  assert.deepEqual(result.state.piles.discard, ['i1']);
  assertFinal(result, def);
});

test('shield absorbs ordered multi-hit damage before HP, then old player shield clears', () => {
  const def = definition(); def.enemySkills.hit.effects = [damage('4'), damage('4')];
  const guarded = playCard(def, createBattle(def, 0).state, 'i2');
  const next = endTurn(def, guarded.state), hits = next.events.filter(e => e.type === 'DamageApplied');
  assert.deepEqual(hits.map(e => [decimal(e.absorbed), decimal(e.hpLost), decimal(e.finalShield), decimal(e.finalHp)]),
    [['4', '0', '1', '100'], ['1', '3', '0', '97']]);
  assert.equal(decimal(next.state.player.shield), '0'); assert.equal(next.state.energy, 2);
  assert.equal(next.state.round, 2); assertFinal(next, def);
});

test('endTurn discards hand, clears enemy old shield, uses intent, then resets surviving player', () => {
  const def = definition();
  def.cards.guard.effects = [shield('5'), shield('20', 'opponent')];
  def.enemySkills.hit.effects = [shield('8'), damage('1')];
  const guarded = playCard(def, createBattle(def, 2).state, 'i2');
  const next = endTurn(def, guarded.state);
  assert.equal(decimal(next.state.enemy.shield), '8');
  assert.equal(decimal(next.state.player.hp), '100'); assert.equal(decimal(next.state.player.shield), '0');
  const names = next.events.map(e => e.type);
  assert.deepEqual(names.slice(0, 4), ['CardMoved', 'CardMoved', 'ShieldCleared', 'EnemySkillUsed']);
  assert.ok(names.indexOf('EnergyChanged') > names.indexOf('DamageApplied'));
  assert.ok(names.indexOf('TurnStarted') > names.indexOf('EnergyChanged'));
});

test('lethal enemy damage loses with zero HP; later enemy effects and skills do not run', () => {
  const def = definition(); def.enemySkills.hit.effects = [damage('101'), shield('10')];
  def.enemyIntents = [['hit', 'hit']];
  const lost = endTurn(def, createBattle(def, 0).state);
  assert.equal(lost.state.status, 'lost'); assert.equal(lost.state.outcomeReason, 'player-defeated');
  assert.equal(decimal(lost.state.player.hp), '0'); assert.equal(lost.state.round, 1);
  assert.equal(lost.events.filter(e => e.type === 'EnemySkillUsed').length, 1);
  assert.equal(lost.events.filter(e => e.type === 'ShieldAdded').length, 0);
  assert.equal(lost.events.filter(e => e.type === 'TurnStarted').length, 0);
  assert.throws(() => endTurn(def, lost.state), /terminal/); assertFinal(lost, def);
});

test('self damage obeys terminal rules for either actor, including enemy suicide at round limit', () => {
  const def = definition(); def.cards.attack.effects = [damage('100', 'self'), damage('12')];
  const lost = playCard(def, createBattle(def, 0).state, 'i1');
  assert.equal(lost.state.status, 'lost'); assert.equal(decimal(lost.state.enemy.hp), '12');
  assertFinal(lost, def);
  def.maxRounds = 1; def.enemySkills.hit.effects = [damage('12', 'self'), damage('100')];
  const won = endTurn(def, createBattle(def, 0).state);
  assert.equal(won.state.status, 'won'); assert.equal(decimal(won.state.player.hp), '100');
  assertFinal(won, def);
});

test('round limit loses only after the final enemy turn and finite intents fall back explicitly', () => {
  const def = definition({ maxRounds: 2, enemyIntents: [['wait']], enemyFallback: ['hit'] });
  const r2 = endTurn(def, createBattle(def, 0).state);
  assert.equal(r2.state.round, 2); assert.equal(decimal(r2.state.player.hp), '100');
  const lost = endTurn(def, r2.state);
  assert.equal(lost.state.status, 'lost'); assert.equal(lost.state.outcomeReason, 'round-limit');
  assert.equal(decimal(lost.state.player.hp), '93'); assert.equal(lost.state.round, 2);
  assert.equal(lost.events.find(e => e.type === 'EnemySkillUsed').skillId, 'hit');
  assert.equal(lost.events.filter(e => e.type === 'TurnStarted').length, 0); assertFinal(lost, def);
});

test('a draw card is held outside piles until all its effects finish and cannot draw itself', () => {
  const def = definition({ deck: [{ instanceId: 'only', cardId: 'cycle' }], initialDraw: 1, roundDraw: 1,
    enemyIntents: [], enemyFallback: ['wait'] });
  const played = playCard(def, createBattle(def, 0).state, 'only');
  assert.deepEqual(played.state.piles.hand, []); assert.deepEqual(played.state.piles.discard, ['only']);
  assert.equal(played.events.filter(e => e.type === 'CardDrawn').length, 0);
  const next = endTurn(def, played.state);
  assert.deepEqual(next.state.piles.hand, ['only']); assertFinal(next, def);
});

test('draw effects refill only prior discarded cards and respect hand limit', () => {
  const def = definition({ initialDraw: 4 });
  def.handLimit = 4;
  const initial = createBattle(def, 77).state;
  const attack = playCard(def, initial, 'i1');
  const drawn = playCard(def, attack.state, 'i4');
  assert.deepEqual(drawn.state.piles.hand, ['i2', 'i3', 'i1']);
  assert.deepEqual(drawn.state.piles.discard, ['i4']);
  assert.equal(drawn.events.filter(e => e.type === 'CardDrawn').length, 1);
  const limit = definition({ handLimit: 1, initialDraw: 64 });
  assert.deepEqual(createBattle(limit, 0).state.piles.hand, ['i1']);
});

test('same seed and command history reproduce shuffle and JSON-resumed future exactly', () => {
  const def = definition({ enemyIntents: [], enemyFallback: ['wait'], roundDraw: 4, initialDraw: 4, handLimit: 4 });
  const initial = createBattle(def, 123456789).state;
  const one = endTurn(def, initial), repeat = endTurn(def, createBattle(def, 123456789).state);
  assert.deepEqual(one, repeat);
  const loaded = validateState(def, copy(one.state));
  assert.deepEqual(endTurn(def, loaded), endTurn(def, one.state));
  const other = endTurn(def, createBattle(def, 42).state);
  assert.notDeepEqual(one.state.rng, other.state.rng);
  assertFinal(one, def);
});

test('mulberry32-v1 and descending Fisher-Yates lock a two-turn golden sequence', () => {
  // Independently evaluated with unsigned 32-bit Python arithmetic. First six
  // PRNG outputs for seed 0: 1144304738,1416247,958946056,627933444,2007157716,2340967985.
  const def = definition({ enemyIntents: [], enemyFallback: ['wait'], roundDraw: 4, initialDraw: 4, handLimit: 4 });
  const first = endTurn(def, createBattle(def, 0).state);
  assert.deepEqual(first.state.piles.hand, ['i4', 'i1', 'i2', 'i3']);
  assert.equal(first.state.rng.state, 1199730143);
  assert.deepEqual(first.events.find(e => e.type === 'DiscardRecycled'), {
    type: 'DiscardRecycled', order: ['i4', 'i1', 'i2', 'i3'], rngBefore: 0, rngAfter: 1199730143,
  });
  const second = endTurn(def, first.state);
  assert.deepEqual(second.state.piles.hand, ['i2', 'i1', 'i3', 'i4']);
  assert.equal(second.state.rng.state, 2399460286);
});

test('fractional HP survives creation and exact typed storage; mixed damage is never pre-truncated', () => {
  const def = definition(); def.player.maxHp = F(1768.8); def.enemy.maxHp = F(12.5);
  const initial = createBattle(def, 0);
  assert.deepEqual(initial.state.player.hp, F(1768.8));
  const played = playCard(def, initial.state, 'i1');
  assert.deepEqual(played.state.enemy.hp, F(6.5));
  const next = endTurn(def, played.state);
  assert.deepEqual(next.state.player.hp, F(1761.8));
  assertFinal(next, def);
});

test('integer HP and damage above 2^53 preserve exactness and fractional shield absorbs correctly', () => {
  const def = definition(); def.enemy.maxHp = I('9007199254740993');
  def.cards.attack.effects = [damage('9007199254740992')];
  const hit = playCard(def, createBattle(def, 0).state, 'i1');
  assert.deepEqual(hit.state.enemy.hp, I(1));
  const loaded = copy(createBattle(def, 0).state); loaded.enemy.shield = F(0.5);
  def.cards.attack.effects = [damage('1')];
  // Use a representable small HP to make the fractional remainder observable.
  loaded.enemy.hp = F(10.5);
  const fraction = playCard(def, loaded, 'i1');
  assert.deepEqual(fraction.state.enemy.hp, F(10));
  const event = fraction.events.find(e => e.type === 'DamageApplied');
  assert.deepEqual(event.absorbed, F(0.5)); assert.deepEqual(event.hpLost, F(0.5));
});

test('illegal plays and failures are atomic, with no energy, PRNG or pile mutation', () => {
  const def = definition(), initial = createBattle(def, 2).state;
  const saved = JSON.stringify(initial);
  for (const instanceId of ['i4', 'unknown', '', 2]) assert.throws(() => playCard(def, initial, instanceId), TypeError);
  def.cards.attack.cost = 3;
  assert.throws(() => playCard(def, initial, 'i1'), /energy/);
  assert.equal(JSON.stringify(initial), saved);
  def.cards.attack.cost = 1;
  const corrected = playCard(def, initial, 'i1');
  assert.equal(corrected.state.actionIndex, 1); assert.equal(corrected.state.energy, 1);
});

test('save validation rejects forged structures, inconsistent outcomes and unknown or duplicated instances', () => {
  const def = definition(), initial = createBattle(def, 0).state;
  const mutations = [
    s => { s.format = 'future'; }, s => { s.definitionId = 'other'; }, s => { s.round = 0; },
    s => { s.energy = 3; }, s => { s.player.hp = I(101); }, s => { s.player.hp = I(0); },
    s => { s.enemy.hp = { numeric_type: 'integer', decimal: '-1' }; },
    s => { s.status = 'won'; s.outcomeReason = 'enemy-defeated'; },
    s => { s.status = 'lost'; s.outcomeReason = 'round-limit'; },
    s => { s.cards[0].cardId = 'guard'; }, s => { s.cards.reverse(); },
    s => { s.piles.hand.push(s.piles.draw.pop()); },
    s => { s.piles.discard.push('i1'); }, s => { s.piles.hand.pop(); },
    s => { s.piles.hand[0] = 'forged'; }, s => { s.piles.removed.push(s.piles.hand.pop()); },
    s => { s.rng.state = -1; }, s => { s.rng.algorithm = 'Math.random'; },
    s => { s.actionIndex = LIMITS.actions + 1; }, s => { s.unrecognized = 1; },
    s => { s.player.shield = { numeric_type: 'binary64', decimal: '1.0', hex: '0x0.0p+0' }; },
  ];
  for (const mutate of mutations) {
    const state = copy(initial); mutate(state);
    assert.throws(() => validateState(def, state), TypeError);
  }
  assert.deepEqual(validateState(def, copy(initial)), initial);
});

test('definition validation rejects unsupported effects, missing choices and unsafe quantities', () => {
  const mutations = [
    d => { d.player.maxHp = I(0); }, d => { d.player.maxHp = '100'; },
    d => { delete d.energyPerRound; }, d => { d.initialDraw = 65; }, d => { d.energyPerRound = .5; },
    d => { d.maxRounds = 0; }, d => { d.deck = []; }, d => { d.deck[1].instanceId = 'i1'; },
    d => { d.deck[0].cardId = 'missing'; }, d => { d.cards.attack.cost = -1; },
    d => { d.cards.attack.effects = [{ type: 'heal', amount: '1', target: 'self' }]; },
    d => { d.cards.attack.effects = [damage('01')]; }, d => { d.cards.attack.effects = [damage('1.5')]; },
    d => { d.cards.attack.effects = [damage('1', 'all')]; },
    d => { d.cards.attack.effects = Array(33).fill(damage('1')); },
    d => { d.enemySkills.hit.effects = [{ type: 'draw', count: 1 }]; },
    d => { d.enemyFallback = []; }, d => { d.enemyIntents = [['unknown']]; },
    d => { d.enemy.id = d.player.id; }, d => { d.cards.attack.name = ''; },
  ];
  for (const mutate of mutations) {
    const def = definition(); mutate(def);
    assert.throws(() => createBattle(def, 0), TypeError);
  }
  for (const seed of [-1, 0x100000000, .5, NaN, '0']) assert.throws(() => createBattle(definition(), seed), TypeError);
  assert.equal(validateDefinition(definition()).deck.length, 4);
});

test('records/arrays reject getters, sparse arrays and custom iterators without invoking them', () => {
  let calls = 0;
  const def = definition(); Object.defineProperty(def.player, 'maxHp', { get() { ++calls; return I(100); } });
  assert.throws(() => createBattle(def, 0), /data fields/);
  const sparse = definition(); delete sparse.deck[1];
  assert.throws(() => createBattle(sparse, 0), /sparse/);
  const custom = definition(); custom.deck[Symbol.iterator] = function* () { ++calls; };
  assert.throws(() => createBattle(custom, 0), /custom/);
  const good = definition(), save = copy(createBattle(good, 0).state);
  Object.defineProperty(save.piles.hand, 0, { get() { ++calls; return 'i1'; } });
  assert.throws(() => validateState(good, save), /data indices/);
  assert.equal(calls, 0);
});

test('zero-cost effects, zero draws and zero hand limit are explicit valid choices', () => {
  const def = definition({ energyPerRound: 0, initialDraw: 0, roundDraw: 0, handLimit: 0, maxRounds: 1,
    enemyIntents: [], enemyFallback: ['wait'] });
  const result = endTurn(def, createBattle(def, 0).state);
  assert.equal(result.state.status, 'lost'); assert.equal(result.state.outcomeReason, 'round-limit');
  assert.deepEqual(result.state.piles.hand, []); assert.equal(result.state.rng.state, 0);
  const canonicalZero = createBattle({ ...def, energyPerRound: -0 }, -0).state;
  assert.equal(Object.is(canonicalZero.rng.state, -0), false);
  assert.equal(Object.is(canonicalZero.energy, -0), false);
  assert.deepEqual(validateState(def, copy(canonicalZero)), canonicalZero);
  const zero = definition(); zero.cards.guard = { name: 'Zero', cost: 0, effects: [shield('0'), damage('0'), { type: 'draw', count: 0 }] };
  const played = playCard(zero, createBattle(zero, 0).state, 'i2');
  assert.equal(played.state.energy, 2); assert.equal(compare(fromTagged(played.state.enemy.hp), int(12)), 0);
});
