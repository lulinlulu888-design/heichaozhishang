import { createPiles, drawCards, movePlayedCard, finishHandRound, PileState } from '../src/piles.js';
const initial: PileState = createPiles({ hand: ['a'], draw: [], discard: [], exhausted: [], powerUsed: [], removed: [] });
const next = drawCards(initial, 1, { handLimit: 10, recycleOrder: [] });
movePlayedCard(next.piles, 'a', 'draw', { drawIndex: 0 });
movePlayedCard(next.piles, 'a', 'removed');
movePlayedCard(next.piles, 'a', 'discard', {});
finishHandRound(next.piles, [{ cardId: 'a', destination: 'hand' }]);
// @ts-expect-error A return into draw requires explicit position.
movePlayedCard(initial, 'a', 'draw');
// @ts-expect-error Every zone must be explicit.
createPiles({ hand: [] });
// @ts-expect-error Snapshots cannot be mutated in place.
initial.hand.push('b');
// @ts-expect-error Non-draw options must be a record, not a primitive.
movePlayedCard(initial, 'a', 'discard', 42);
// @ts-expect-error Insertion positions are valid only for draw.
movePlayedCard(initial, 'a', 'discard', { drawIndex: 1 });
// @ts-expect-error Non-draw destinations have no supported option fields.
movePlayedCard(initial, 'a', 'discard', { unsupported: true });
