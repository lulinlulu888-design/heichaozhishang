/** Deterministic rebuilt pile operations. This is not the missing server turn/RNG implementation. */
const ZONES = Object.freeze(['hand', 'draw', 'discard', 'exhausted', 'powerUsed', 'removed']);
const ROUND_DESTINATIONS = new Set(['hand', 'discard', 'exhausted', 'removed']);
const PLAY_DESTINATIONS = new Set(['draw', 'discard', 'exhausted', 'powerUsed', 'removed']);
const MAX_CARDS = 100000;
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

function integer(value, name, maximum = MAX_CARDS) {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum) throw new TypeError(`${name} must be an integer in [0, ${maximum}]`);
  return value;
}
function id(value) {
  if (typeof value !== 'string' || !value.length || value.length > 128) throw new TypeError('card instance ID must be a nonempty string of at most 128 characters');
  return value;
}
function plain(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) throw new TypeError(`${name} must be a plain record`);
  for (const key of Reflect.ownKeys(value)) {
    if (!('value' in Object.getOwnPropertyDescriptor(value, key))) throw new TypeError(`${name} must contain data properties, not accessors`);
  }
  return value;
}
// Accept ordinary DTO arrays only. Read each own index once without invoking
// getters/iterators, then validate and use the same private dense copy.
function denseArray(value, name) {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > MAX_CARDS) {
    throw new TypeError(`${name} must be a bounded plain array`);
  }
  if (Reflect.ownKeys(value).length !== value.length + 1) throw new TypeError(`${name} must not be sparse or have custom properties`);
  const copy = [];
  for (let index = 0; index < value.length; ++index) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !('value' in descriptor)) throw new TypeError(`${name} must contain dense data indices, not accessors`);
    copy.push(descriptor.value);
  }
  return copy;
}
function checkedState(input) {
  plain(input, 'piles');
  if (Reflect.ownKeys(input).length !== ZONES.length || ZONES.some(zone => !own(input, zone))) {
    throw new TypeError('all six pile zones must be explicit');
  }
  const seen = new Set(), result = {};
  for (const zone of ZONES) {
    const cards = denseArray(input[zone], `${zone} pile`);
    for (const value of cards) {
      id(value);
      if (seen.has(value)) throw new TypeError(`card instance occurs more than once: ${value}`);
      seen.add(value);
      if (seen.size > MAX_CARDS) throw new RangeError('pile instance budget exceeded');
    }
    result[zone] = cards;
  }
  return result;
}
function frozenState(state) {
  for (const zone of ZONES) Object.freeze(state[zone]);
  return Object.freeze(state);
}
function result(state, events, details = {}) {
  return Object.freeze({ piles: frozenState(state), events: Object.freeze(events.map(event => {
    if (event.cardIds) Object.freeze(event.cardIds);
    return Object.freeze(event);
  })), ...details });
}

/** Copies and validates a complete state; removed is a local terminal zone, not exhausted. */
export function createPiles(state) {
  return frozenState(checkedState(state));
}

/** Draws from an explicitly ordered deck. A refill permutation is required only if a refill happens. */
export function drawCards(input, count, options) {
  const state = checkedState(input);
  integer(count, 'draw count');
  plain(options, 'draw options');
  const limit = integer(options.handLimit, 'hand limit');
  if (Reflect.ownKeys(options).some(key => !['handLimit', 'recycleOrder'].includes(key))) throw new TypeError('unknown draw option');
  const events = [];
  let drawn = 0, recycled = false, drawIndex = 0;
  const drawCount = Math.min(count, Math.max(0, limit - state.hand.length));
  while (drawn < drawCount) {
    if (drawIndex === state.draw.length) {
      if (state.discard.length === 0) break;
      const order = denseArray(options.recycleOrder, 'refill permutation');
      const discardIds = new Set(state.discard);
      if (order.length !== state.discard.length ||
          new Set(order).size !== order.length || order.some(value => !discardIds.has(value))) {
        throw new TypeError('refill requires an explicit permutation of the discard pile');
      }
      state.draw = order; state.discard = []; recycled = true; drawIndex = 0;
      events.push({ type: 'DiscardRecycled', cardIds: order.slice() });
    }
    const cardId = state.draw[drawIndex++];
    state.hand.push(cardId); drawn += 1;
    events.push({ type: 'CardDrawn', cardId });
  }
  state.draw = state.draw.slice(drawIndex);
  return result(state, events, { drawn, recycled });
}

/** Caller resolves card effects/keywords before selecting a destination. No energy/legality inference. */
export function movePlayedCard(input, cardId, destination, options = {}) {
  const state = checkedState(input);
  id(cardId); plain(options, 'play options');
  if (!PLAY_DESTINATIONS.has(destination)) throw new TypeError('unsupported played-card destination');
  const index = state.hand.indexOf(cardId);
  if (index === -1) throw new TypeError('played card is not in hand');
  if (Reflect.ownKeys(options).some(key => key !== 'drawIndex') || (destination !== 'draw' && own(options, 'drawIndex'))) {
    throw new TypeError('drawIndex is only valid for the draw destination');
  }
  const drawIndex = destination === 'draw' ? integer(options.drawIndex, 'draw insertion index', state.draw.length) : null;
  state.hand.splice(index, 1);
  if (destination === 'draw') state.draw.splice(drawIndex, 0, cardId);
  else state[destination].push(cardId);
  return result(state, [{ type: 'PlayedCardMoved', cardId, destination, ...(drawIndex === null ? {} : { drawIndex }) }]);
}

/** Complete resolved routing for current hand; overlapping keyword precedence is deliberately external. */
export function finishHandRound(input, dispositions) {
  const state = checkedState(input);
  const items = denseArray(dispositions, 'round dispositions');
  if (items.length !== state.hand.length) {
    throw new TypeError('round end needs exactly one disposition for each hand instance');
  }
  const routes = new Map(), handIds = new Set(state.hand);
  for (const item of items) {
    plain(item, 'disposition'); id(item.cardId);
    if (Reflect.ownKeys(item).length !== 2 || !own(item, 'cardId') || !own(item, 'destination') ||
        !ROUND_DESTINATIONS.has(item.destination) || routes.has(item.cardId) || !handIds.has(item.cardId)) {
      throw new TypeError('invalid, duplicate or unknown round disposition');
    }
    routes.set(item.cardId, item.destination);
  }
  const hand = state.hand; state.hand = [];
  const events = [];
  // Stable current-hand order is a reconstruction choice, not recovered trigger ordering.
  for (const cardId of hand) {
    const destination = routes.get(cardId);
    state[destination].push(cardId);
    events.push({ type: destination === 'hand' ? 'CardRetained' : 'RoundEndCardMoved', cardId, destination });
  }
  return result(state, events);
}
