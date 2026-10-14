import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createPiles, drawCards, finishHandRound, movePlayedCard } from '../src/piles.js';

const state = (changes = {}) => ({ hand: [], draw: [], discard: [], exhausted: [], powerUsed: [], removed: [], ...changes });
const ids = piles => Object.values(piles).flat().sort();

test('draw, refill, play and round end conserve instances across a complete synthetic pile cycle', () => {
  const initial = createPiles(state({ draw: ['a', 'b'], discard: ['c', 'd'], exhausted: ['e'], powerUsed: ['p'], removed: ['r'] }));
  const drawn = drawCards(initial, 3, { handLimit: 10, recycleOrder: ['d', 'c'] });
  assert.deepEqual(drawn.piles.hand, ['a', 'b', 'd']);
  assert.deepEqual(drawn.events.map(x => x.type), ['CardDrawn', 'CardDrawn', 'DiscardRecycled', 'CardDrawn']);
  const played = movePlayedCard(drawn.piles, 'a', 'discard');
  const ended = finishHandRound(played.piles, [{ cardId: 'd', destination: 'exhausted' }, { cardId: 'b', destination: 'hand' }]);
  assert.deepEqual(ended.piles, state({ hand: ['b'], draw: ['c'], discard: ['a'], exhausted: ['e', 'd'], powerUsed: ['p'], removed: ['r'] }));
  assert.deepEqual(ids(ended.piles), ids(initial));
  assert.deepEqual(initial, state({ draw: ['a', 'b'], discard: ['c', 'd'], exhausted: ['e'], powerUsed: ['p'], removed: ['r'] }));
});

test('normal refill never returns exhausted, power-used or removed cards', () => {
  const input = state({ exhausted: ['e'], powerUsed: ['p'], removed: ['r'] });
  const out = drawCards(input, 6, { handLimit: 10 });
  assert.equal(out.drawn, 0); assert.deepEqual(out.piles, input);
});

test('hand limit interrupts before shuffle; an already over-limit hand is not truncated', () => {
  const input = state({ hand: ['a', 'b'], discard: ['c'] });
  assert.equal(drawCards(input, 6, { handLimit: 2 }).recycled, false);
  assert.deepEqual(drawCards(input, 6, { handLimit: 1 }).piles, input);
});

test('missing or invalid refill permutation fails atomically even after an available first draw', () => {
  const input = state({ draw: ['a'], discard: ['b', 'c'] });
  const original = structuredClone(input);
  for (const recycleOrder of [undefined, ['b'], ['b', 'b'], ['b', 'unknown']]) {
    assert.throws(() => drawCards(input, 3, { handLimit: 10, recycleOrder }), /permutation/);
    assert.deepEqual(input, original);
  }
});

test('a sparse refill permutation cannot lose a card or emit undefined after a first draw', () => {
  const input = state({ draw: ['first'], discard: ['a', 'b'] });
  const original = structuredClone(input), recycleOrder = ['a', ,];
  assert.throws(() => drawCards(input, 3, { handLimit: 10, recycleOrder }), /sparse/);
  assert.deepEqual(input, original);
  assert.equal(recycleOrder.length, 2);
  assert.equal(Object.hasOwn(recycleOrder, 1), false);
  // The same valid request still works after the failed attempt.
  const fixed = drawCards(input, 3, { handLimit: 10, recycleOrder: ['a', 'b'] });
  assert.deepEqual(fixed.piles.hand, ['first', 'a', 'b']);
  assert.deepEqual(ids(fixed.piles), ids(input));
});

test('refill does not invoke custom iterators or indexed accessors during validation or use', () => {
  const input = state({ draw: ['first'], discard: ['a', 'b'] });
  const original = structuredClone(input);
  let calls = 0;
  const customIterator = ['a', 'b'];
  customIterator[Symbol.iterator] = function* () { ++calls; yield 'a'; yield 'unknown'; };
  const accessor = ['a', 'b'];
  Object.defineProperty(accessor, 1, { get() { ++calls; return calls === 1 ? 'b' : 'unknown'; } });
  class CustomArray extends Array { *[Symbol.iterator]() { ++calls; yield 'a'; yield 'b'; } }
  for (const recycleOrder of [customIterator, accessor, new CustomArray('a', 'b')]) {
    assert.throws(() => drawCards(input, 3, { handLimit: 10, recycleOrder }), TypeError);
    assert.deepEqual(input, original);
  }
  assert.equal(calls, 0);
  const valid = Object.freeze(['b', 'a']);
  const result = drawCards(input, 3, { handLimit: 10, recycleOrder: valid });
  assert.deepEqual(result.piles.hand, ['first', 'b', 'a']);
  assert.deepEqual(result.events.find(event => event.type === 'DiscardRecycled').cardIds, valid);
});

test('pile records, routing records and options reject accessors without invoking them', () => {
  let calls = 0;
  const getter = () => { ++calls; return []; };
  const input = state({ hand: ['a'] });
  const pileGetter = state();
  Object.defineProperty(pileGetter, 'hand', { enumerable: true, get: getter });
  assert.throws(() => createPiles(pileGetter), /accessors/);
  assert.throws(() => createPiles(state({ hand: ['a', ,] })), /sparse/);
  const changingOptions = { handLimit: 10 };
  Object.defineProperty(changingOptions, 'recycleOrder', { enumerable: true, get: getter });
  assert.throws(() => drawCards(input, 1, changingOptions), /accessors/);
  const route = { cardId: 'a' };
  Object.defineProperty(route, 'destination', { enumerable: true, get: getter });
  assert.throws(() => finishHandRound(input, [route]), /accessors/);
  const routes = [{ cardId: 'a', destination: 'discard' }];
  routes[Symbol.iterator] = function* () { ++calls; };
  assert.throws(() => finishHandRound(input, routes), /custom/);
  const playOptions = {};
  Object.defineProperty(playOptions, 'drawIndex', { enumerable: true, get: getter });
  assert.throws(() => movePlayedCard(input, 'a', 'draw', playOptions), /accessors/);
  assert.equal(calls, 0);
  assert.deepEqual(input, state({ hand: ['a'] }));
});

test('caller-controlled recycle order changes draw order without a hidden RNG', () => {
  const input = state({ discard: ['a', 'b', 'c'] });
  assert.deepEqual(drawCards(input, 2, { handLimit: 10, recycleOrder: ['b', 'c', 'a'] }).piles.hand, ['b', 'c']);
  assert.deepEqual(drawCards(input, 2, { handLimit: 10, recycleOrder: ['c', 'a', 'b'] }).piles.hand, ['c', 'a']);
});

test('round routing is complete, disjoint, and cannot silently resolve keyword conflicts', () => {
  const input = state({ hand: ['a', 'b', 'c', 'd'] });
  const out = finishHandRound(input, [
    { cardId: 'd', destination: 'removed' }, { cardId: 'b', destination: 'exhausted' },
    { cardId: 'a', destination: 'discard' }, { cardId: 'c', destination: 'hand' },
  ]);
  assert.deepEqual(out.piles, state({ discard: ['a'], exhausted: ['b'], hand: ['c'], removed: ['d'] }));
  assert.deepEqual(out.events.map(e => e.cardId), ['a', 'b', 'c', 'd']);
  for (const routes of [[], Array(4).fill({ cardId: 'a', destination: 'discard' }),
    ['a', 'b', 'c', 'unknown'].map(cardId => ({ cardId, destination: 'discard' }))]) {
    assert.throws(() => finishHandRound(input, routes));
  }
  assert.deepEqual(input.hand, ['a', 'b', 'c', 'd']);
});

test('played return to draw requires an explicit valid insertion index', () => {
  const input = state({ hand: ['a'], draw: ['b', 'c'] });
  assert.deepEqual(movePlayedCard(input, 'a', 'draw', { drawIndex: 1 }).piles.draw, ['b', 'a', 'c']);
  for (const options of [{}, { drawIndex: -1 }, { drawIndex: 3 }]) assert.throws(() => movePlayedCard(input, 'a', 'draw', options));
  assert.throws(() => movePlayedCard(input, 'b', 'discard'), /not in hand/);
  assert.throws(() => movePlayedCard(input, 'a', 'hand'), /destination/);
});

test('instance identity is unique across zones; records and results are isolated', () => {
  assert.throws(() => createPiles(state({ hand: ['same'], draw: ['same'] })), /more than once/);
  assert.throws(() => createPiles(state({ hand: [1] })), /instance ID/);
  assert.throws(() => createPiles({ hand: [] }), /all six/);
  const source = state({ hand: ['__proto__', 'a'] });
  const copy = createPiles(source);
  source.hand.length = 0;
  assert.deepEqual(copy.hand, ['__proto__', 'a']);
  assert.throws(() => copy.hand.push('b'), TypeError);
  const out = drawCards(state({ discard: ['a'] }), 1, { handLimit: 1, recycleOrder: ['a'] });
  assert.throws(() => out.events[0].cardIds.push('b'), TypeError);
});

test('draw counts and effective limits must be supplied finite nonnegative integers', () => {
  for (const count of [-1, .5, NaN, Infinity, '1', 100001]) assert.throws(() => drawCards(state(), count, { handLimit: 10 }));
  for (const options of [undefined, {}, { handLimit: NaN }, { handLimit: 10, unknown: 1 }]) assert.throws(() => drawCards(state(), 1, options));
});
