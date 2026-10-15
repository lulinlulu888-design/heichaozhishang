// Explicit reconstruction rules. No original server compatibility, Node API,
// wall clock, global random generator, or execution of APK code.
import { int, fromTagged, toTagged, compare, add, subtract, multiply, rpgPropertyPercent } from '../../battle-core/src/index.js';
export const FORMAT = 'hczs-battle-session-v1';
export const STATUS_FORMAT = 'hczs-battle-session-v2';
export const ULTIMATE_FORMAT = 'hczs-battle-session-v3';
export const LIMITS = Object.freeze({ cards: 64, cardDefinitions: 256, enemySkills: 128,
  effects: 32, skillsPerTurn: 16, rounds: 1000, energy: 1000000, actions: 1000000,
  amountDigits: 64, healthDigits: 128 });
const ZERO = int(0);
const ZONES = ['hand', 'draw', 'discard', 'exhausted', 'powerUsed', 'removed'];
const DEF_KEYS = ['id', 'player', 'enemy', 'deck', 'cards', 'enemySkills', 'enemyIntents', 'enemyFallback',
  'initialDraw', 'roundDraw', 'energyPerRound', 'handLimit', 'maxRounds'];
const STATE_KEYS = ['format', 'definitionId', 'round', 'status', 'outcomeReason', 'energy', 'player', 'enemy',
  'cards', 'piles', 'rng', 'actionIndex'];
const error = message => { throw new TypeError(message); };
function record(value, keys, label) {
  if (!value || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) error(`${label}: plain record required`);
  const own = Reflect.ownKeys(value);
  if (keys && (own.length !== keys.length || own.some(key => !keys.includes(key)))) error(`${label}: missing/unknown field`);
  for (const key of own) {
    if (typeof key !== 'string' || !('value' in Object.getOwnPropertyDescriptor(value, key))) error(`${label}: data fields required`);
  }
  return value;
}
function list(value, limit, label) {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > limit) error(`${label}: bounded plain array required`);
  if (Reflect.ownKeys(value).length !== value.length + 1) error(`${label}: sparse/custom array rejected`);
  const result = [];
  for (let index = 0; index < value.length; ++index) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !('value' in descriptor)) error(`${label}: dense data indices required`);
    result.push(descriptor.value);
  }
  return result;
}
function id(value, label) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) error(`${label}: normalized string ID required`);
  return value;
}
function name(value) {
  if (typeof value !== 'string' || value.length < 1 || value.length > 128 || /[\x00-\x1f\x7f]/.test(value)) error('name: bounded readable string required');
  return value;
}
function integer(value, max, label, min = 0) {
  if (!Number.isSafeInteger(value) || value < min || value > max) error(`${label}: integer outside bounds`);
  return value === 0 ? 0 : value; // Canonicalize numeric -0 for JSON-stable counters.
}
function decimal(value, digits = LIMITS.amountDigits) {
  if (typeof value !== 'string' || value.length > digits || !/^(?:0|[1-9][0-9]*)$/.test(value)) error('canonical nonnegative decimal string required');
  return value;
}
function health(value) {
  record(value, null, 'health');
  if (value.numeric_type === 'integer') {
    record(value, ['numeric_type', 'decimal'], 'integer health');
    decimal(value.decimal, LIMITS.healthDigits);
  } else if (value.numeric_type === 'binary64') {
    record(value, ['numeric_type', 'decimal', 'hex'], 'binary64 health');
    if (typeof value.decimal !== 'string' || value.decimal.length > 64) error('binary64 health decimal outside bounds');
  } else error('unknown health numeric type');
  const scalar = fromTagged(value);
  if (compare(scalar, ZERO) < 0) error('health cannot be negative');
  return toTagged(scalar);
}
const zero = value => compare(fromTagged(value), ZERO) === 0;
const min = (a, b) => compare(a, b) < 0 ? a : b;
function freeze(value) {
  if (value && typeof value === 'object') {
    for (const key of Object.keys(value)) freeze(value[key]);
    Object.freeze(value);
  }
  return value;
}
function effects(input, enemy, statusRules) {
  return list(input, LIMITS.effects, 'effects').map(effect => {
    record(effect, null, 'effect');
    if (effect.type === 'breakdown' && statusRules) {
      record(effect, ['type', 'target', 'stacks'], 'breakdown effect');
      if (effect.target !== 'opponent') error('breakdown reconstruction requires opponent target');
      return { type: 'breakdown', target: 'opponent', stacks: integer(effect.stacks, 999, 'stacks', 1) };
    }
    if (effect.type === 'heal' && statusRules) {
      record(effect, ['type', 'target', 'amount'], 'heal effect');
      if (!['self', 'opponent'].includes(effect.target)) error('unsupported heal target');
      return { type: 'heal', target: effect.target, amount: decimal(effect.amount) };
    }
    if (effect.type === 'damage' || effect.type === 'shield') {
      record(effect, ['type', 'target', 'amount'], 'effect');
      if (!['self', 'opponent'].includes(effect.target)) error('unsupported effect target');
      return { type: effect.type, target: effect.target, amount: decimal(effect.amount) };
    }
    if (effect.type === 'draw' && !enemy) {
      record(effect, ['type', 'count'], 'draw effect');
      return { type: 'draw', count: integer(effect.count, LIMITS.cards, 'draw count') };
    }
    error('unsupported effect (enemy draw has no defined pile semantics)');
  });
}
function definitionCopy(input) {
  record(input, null, 'definition');
  const usesStatuses = Object.prototype.hasOwnProperty.call(input, 'statusRules');
  const usesUltimates = Object.prototype.hasOwnProperty.call(input, 'ultimateRules');
  record(input, [...DEF_KEYS, ...(usesStatuses ? ['statusRules'] : []), ...(usesUltimates ? ['ultimateRules'] : [])], 'definition');
  const result = { id: id(input.id, 'definition.id') };
  if (usesUltimates) {
    const rules = record(input.ultimateRules, ['policy', 'ownerId', 'cardId', 'pointsRequired', 'maxPerRound'], 'ultimateRules');
    if (rules.policy !== 'elsa-combo-reconstruction-v1' || rules.ownerId !== '1' || rules.cardId !== '410104' ||
        rules.pointsRequired !== 3 || rules.maxPerRound !== 3) error('unsupported ultimate policy');
    result.ultimateRules = { ...rules };
  }
  if (usesStatuses) {
    record(input.statusRules, ['policy', 'attack'], 'statusRules');
    if (input.statusRules.policy !== 'breakdown-reconstruction-v1') error('unknown status policy');
    record(input.statusRules.attack, ['player', 'enemy'], 'status attack');
    result.statusRules = { policy: input.statusRules.policy,
      attack: { player: health(input.statusRules.attack.player), enemy: health(input.statusRules.attack.enemy) } };
  }
  for (const side of ['player', 'enemy']) {
    record(input[side], ['id', 'name', 'maxHp'], side);
    const maxHp = health(input[side].maxHp);
    if (zero(maxHp)) error('maxHp must be positive');
    result[side] = { id: id(input[side].id, `${side}.id`), name: name(input[side].name), maxHp };
  }
  if (result.player.id === result.enemy.id) error('combatant IDs must differ');
  for (const field of ['cards', 'enemySkills']) {
    const map = record(input[field], null, field), keys = Reflect.ownKeys(map);
    if (!keys.length || keys.length > (field === 'cards' ? LIMITS.cardDefinitions : LIMITS.enemySkills)) error(`${field}: definition count outside bounds`);
    const out = Object.create(null);
    for (const key of keys) {
      id(key, field);
      const entry = map[key], enemy = field === 'enemySkills';
      record(entry, enemy ? ['effects'] : ['name', 'cost', 'effects',
        ...(usesUltimates ? ['ownerId', 'cardType', 'specialPoints', 'removeOnLeaveHand'] : [])], `${field}.${key}`);
      out[key] = enemy ? { effects: effects(entry.effects, true, usesStatuses) } : {
        name: name(entry.name), cost: integer(entry.cost, LIMITS.energy, 'card cost'), effects: effects(entry.effects, false, usesStatuses),
      };
      if (!enemy && usesUltimates) {
        const ultimate = key === result.ultimateRules.cardId;
        if (entry.ownerId !== result.ultimateRules.ownerId ||
            ![0, 1, 2, 3, 6, 7].includes(entry.cardType) || (entry.cardType === 7) !== ultimate ||
            entry.specialPoints !== (ultimate ? 0 : 1) || entry.removeOnLeaveHand !== ultimate ||
            (ultimate && entry.cost !== 0)) error('unsupported ultimate card metadata');
        Object.assign(out[key], { ownerId: entry.ownerId, cardType: entry.cardType,
          specialPoints: entry.specialPoints, removeOnLeaveHand: entry.removeOnLeaveHand });
      }
    }
    result[field] = out;
  }
  if (usesUltimates && !Object.hasOwn(result.cards, result.ultimateRules.cardId)) error('missing ultimate card definition');
  const instances = new Set();
  result.deck = list(input.deck, LIMITS.cards, 'deck').map(card => {
    record(card, ['instanceId', 'cardId'], 'deck card');
    id(card.instanceId, 'instanceId'); id(card.cardId, 'cardId');
    if (instances.has(card.instanceId) || !Object.prototype.hasOwnProperty.call(result.cards, card.cardId)) error('duplicate instance or unknown card ID');
    if (usesUltimates && (card.instanceId.startsWith('ultimate:') || card.cardId === result.ultimateRules.cardId)) error('ultimate instances must be generated');
    instances.add(card.instanceId);
    return { instanceId: card.instanceId, cardId: card.cardId };
  });
  if (!result.deck.length) error('deck must contain at least one instance');
  function intent(input) {
    const order = list(input, LIMITS.skillsPerTurn, 'enemy intent');
    if (!order.length) error('enemy intent must explicitly contain at least one skill');
    for (const key of order) if (typeof key !== 'string' || !Object.prototype.hasOwnProperty.call(result.enemySkills, key)) error('unknown enemy skill ID');
    return order;
  }
  result.enemyIntents = list(input.enemyIntents, LIMITS.rounds, 'enemyIntents').map(intent);
  result.enemyFallback = intent(input.enemyFallback);
  for (const key of ['initialDraw', 'roundDraw', 'handLimit']) result[key] = integer(input[key], LIMITS.cards, key);
  result.energyPerRound = integer(input.energyPerRound, LIMITS.energy, 'energyPerRound');
  result.maxRounds = integer(input.maxRounds, LIMITS.rounds, 'maxRounds', 1);
  return result;
}
/** Validates and copies the public definition, without inferring any gameplay data. */
export function validateDefinition(definition) { return freeze(definitionCopy(definition)); }
function stateCopy(definition, input) {
  const format = definition.ultimateRules ? ULTIMATE_FORMAT : definition.statusRules ? STATUS_FORMAT : FORMAT;
  record(input, [...STATE_KEYS, ...(definition.statusRules ? ['breakdown'] : []),
    ...(definition.ultimateRules ? ['ultimate'] : [])], 'state');
  if (input.format !== format || input.definitionId !== definition.id) error('state format/definition mismatch');
  const out = { format, definitionId: definition.id,
    round: integer(input.round, definition.maxRounds, 'round', 1),
    status: input.status, outcomeReason: input.outcomeReason,
    energy: integer(input.energy, definition.energyPerRound, 'energy'),
    actionIndex: integer(input.actionIndex, LIMITS.actions, 'actionIndex') };
  if (definition.ultimateRules) {
    const rules = definition.ultimateRules;
    record(input.ultimate, ['chainOwnerId', 'points', 'generatedThisRound', 'generatedTotal'], 'ultimate');
    const points = integer(input.ultimate.points, rules.pointsRequired - 1, 'combo points');
    if (input.ultimate.chainOwnerId !== (points ? rules.ownerId : null)) error('invalid combo owner');
    const generatedThisRound = integer(input.ultimate.generatedThisRound, rules.maxPerRound, 'round ultimate count');
    const generatedTotal = integer(input.ultimate.generatedTotal, out.round * rules.maxPerRound, 'total ultimate count');
    if (generatedThisRound > generatedTotal || generatedTotal - generatedThisRound > (out.round - 1) * rules.maxPerRound ||
        (generatedThisRound === rules.maxPerRound && points)) error('invalid ultimate counters');
    out.ultimate = { chainOwnerId: input.ultimate.chainOwnerId, points, generatedThisRound, generatedTotal };
  }
  if (definition.statusRules) {
    record(input.breakdown, ['player', 'enemy'], 'breakdown');
    out.breakdown = { player: integer(input.breakdown.player, 999, 'player stacks'),
      enemy: integer(input.breakdown.enemy, 999, 'enemy stacks') };
  }
  for (const side of ['player', 'enemy']) {
    record(input[side], ['hp', 'shield'], `state.${side}`);
    out[side] = { hp: health(input[side].hp), shield: health(input[side].shield) };
    if (compare(fromTagged(out[side].hp), fromTagged(definition[side].maxHp)) > 0) error('HP exceeds definition maxHp');
  }
  if (out.status === 'player-turn') {
    if (out.outcomeReason !== null || zero(out.player.hp) || zero(out.enemy.hp)) error('invalid active state');
  } else if (out.status === 'won') {
    if (out.outcomeReason !== 'enemy-defeated' || !zero(out.enemy.hp) || zero(out.player.hp)) error('invalid won state');
  } else if (out.status === 'lost') {
    if (zero(out.enemy.hp) || !((out.outcomeReason === 'player-defeated' && zero(out.player.hp)) ||
        (out.outcomeReason === 'round-limit' && !zero(out.player.hp) && out.round === definition.maxRounds))) error('invalid lost state');
  } else error('unknown battle status');
  const generated = out.ultimate?.generatedTotal ?? 0;
  const registryLimit = definition.deck.length + (definition.ultimateRules ? definition.maxRounds * definition.ultimateRules.maxPerRound : 0);
  const registry = list(input.cards, registryLimit, 'state.cards');
  if (registry.length !== definition.deck.length + generated) error('card registry does not match definition');
  out.cards = registry.map((card, index) => {
    record(card, ['instanceId', 'cardId'], 'registry card');
    const expected = definition.deck[index] ?? { instanceId: `ultimate:${index - definition.deck.length + 1}`, cardId: definition.ultimateRules.cardId };
    if (card.instanceId !== expected.instanceId || card.cardId !== expected.cardId) error('card registry does not match definition');
    return { instanceId: card.instanceId, cardId: card.cardId };
  });
  record(input.piles, ZONES, 'piles');
  const ids = new Set(out.cards.map(card => card.instanceId)), seen = new Set();
  out.piles = {};
  for (const zone of ZONES) {
    const members = list(input.piles[zone], zone === 'removed' ? registryLimit : LIMITS.cards, zone);
    if (['exhausted', 'powerUsed'].includes(zone) && members.length || (!definition.ultimateRules && zone === 'removed' && members.length)) error('terminal pile zones are unsupported in this rules version');
    for (const value of members) {
      if (!ids.has(value) || seen.has(value)) error('unknown or duplicate pile instance');
      if (definition.ultimateRules && (value.startsWith('ultimate:') ? !['hand', 'removed'].includes(zone) : zone === 'removed')) error('invalid ultimate pile');
      seen.add(value);
    }
    out.piles[zone] = members;
  }
  if (seen.size !== ids.size) error('every instance must occupy exactly one pile');
  if (out.piles.hand.length > definition.handLimit) error('hand exceeds definition handLimit');
  record(input.rng, ['algorithm', 'state'], 'rng');
  if (input.rng.algorithm !== 'mulberry32-v1') error('unknown PRNG algorithm');
  out.rng = { algorithm: 'mulberry32-v1', state: integer(input.rng.state, 0xffffffff, 'PRNG state') };
  return out;
}
/** Structural validation only; does not authenticate the save or its gameplay history. */
export function validateState(definition, state) { return freeze(stateCopy(definitionCopy(definition), state)); }
function nextRandom(rng) {
  rng.state = (rng.state + 0x6d2b79f5) >>> 0;
  let value = rng.state;
  value = Math.imul(value ^ value >>> 15, value | 1);
  value ^= value + Math.imul(value ^ value >>> 7, value | 61);
  return (value ^ value >>> 14) >>> 0;
}
function randomBelow(rng, limit) {
  const threshold = 0x100000000 - (0x100000000 % limit);
  let value;
  do { value = nextRandom(rng); } while (value >= threshold);
  return value % limit;
}
function draw(definition, state, count, events) {
  let cursor = 0;
  for (let n = 0; n < count && state.piles.hand.length < definition.handLimit; ++n) {
    if (cursor === state.piles.draw.length) {
      if (!state.piles.discard.length) break;
      const deck = state.piles.discard.slice(), before = state.rng.state;
      for (let i = deck.length - 1; i > 0; --i) {
        const j = randomBelow(state.rng, i + 1);
        [deck[i], deck[j]] = [deck[j], deck[i]];
      }
      state.piles.draw = deck; state.piles.discard = []; cursor = 0;
      events.push({ type: 'DiscardRecycled', order: deck.slice(), rngBefore: before, rngAfter: state.rng.state });
    }
    const instanceId = state.piles.draw[cursor++];
    state.piles.hand.push(instanceId);
    events.push({ type: 'CardDrawn', instanceId });
  }
  state.piles.draw = state.piles.draw.slice(cursor);
}
function outcome(state, status, reason, events) {
  state.status = status; state.outcomeReason = reason;
  events.push({ type: 'BattleEnded', status, reason, round: state.round });
}
function applyEffects(state, actor, effects, definition, events) {
  for (let effectIndex = 0; effectIndex < effects.length && state.status === 'player-turn'; ++effectIndex) {
    const effect = effects[effectIndex];
    if (effect.type === 'draw') { draw(definition, state, effect.count, events); continue; }
    const target = effect.target === 'self' ? actor : actor === 'player' ? 'enemy' : 'player';
    const entity = state[target], previousHp = entity.hp, previousShield = entity.shield;
    if (effect.type === 'breakdown') {
      const previousStacks = state.breakdown[target];
      state.breakdown[target] = Math.min(999, previousStacks + effect.stacks);
      events.push({ type: 'BreakdownChanged', actor, target, previousStacks,
        finalStacks: state.breakdown[target], reason: 'applied' });
    } else if (effect.type === 'heal') {
      const restored = min(int(effect.amount), subtract(fromTagged(definition[target].maxHp), fromTagged(entity.hp)));
      entity.hp = toTagged(add(fromTagged(entity.hp), restored));
      events.push({ type: 'HealthRestored', actor, target, effectIndex, amount: effect.amount, restored: toTagged(restored),
        previousHp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
      // Explicit reconstruction: only positive actual recovery removes one stack.
      if (compare(restored, ZERO) > 0 && state.breakdown[target] > 0) {
        const previousStacks = state.breakdown[target]--;
        events.push({ type: 'BreakdownChanged', actor, target, previousStacks,
          finalStacks: state.breakdown[target], reason: 'healed' });
      }
    } else if (effect.type === 'shield') {
      entity.shield = toTagged(add(fromTagged(entity.shield), int(effect.amount)));
      events.push({ type: 'ShieldAdded', actor, target, effectIndex, amount: effect.amount,
        previousHp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
    } else {
      const amount = int(effect.amount), shield = fromTagged(entity.shield), hp = fromTagged(entity.hp);
      const absorbed = min(shield, amount), remainder = subtract(amount, absorbed);
      const hpLost = min(hp, remainder);
      entity.shield = toTagged(subtract(shield, absorbed)); entity.hp = toTagged(subtract(hp, hpLost));
      events.push({ type: 'DamageApplied', actor, target, effectIndex, amount: effect.amount, absorbed: toTagged(absorbed), hpLost: toTagged(hpLost),
        previousHp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
      if (zero(state.enemy.hp)) outcome(state, 'won', 'enemy-defeated', events);
      else if (zero(state.player.hp)) outcome(state, 'lost', 'player-defeated', events);
    }
  }
}
function tickBreakdown(definition, state, target, events) {
  if (!definition.statusRules || !state.breakdown[target] || state.status !== 'player-turn') return;
  const actor = target === 'player' ? 'enemy' : 'player';
  const amount = rpgPropertyPercent({ property: fromTagged(definition.statusRules.attack[actor]),
    percent: multiply(int(state.breakdown[target]), int(20)), method: 0 }).value.toString();
  events.push({ type: 'BreakdownTriggered', actor, target, stacks: state.breakdown[target], amount });
  // Reconstruction settlement: reuse shield/HP damage; original extraDamage pipeline is unresolved.
  applyEffects(state, actor, [{ type: 'damage', target: 'opponent', amount }], definition, events);
}
function energy(state, finalValue, events) {
  const previousValue = state.energy; state.energy = finalValue;
  events.push({ type: 'EnergyChanged', previousValue, finalValue });
}
function clearShield(state, target, events) {
  const entity = state[target], previousShield = entity.shield; entity.shield = toTagged(ZERO);
  events.push({ type: 'ShieldCleared', target, previousHp: entity.hp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
}
function finish(definition, state, events) {
  const checked = freeze(stateCopy(definition, state));
  events.push({ type: 'StateUpdated', state: checked });
  return freeze({ state: checked, events });
}
function active(definition, input) {
  const state = stateCopy(definition, input);
  if (state.status !== 'player-turn') error('terminal battle rejects further operations');
  state.actionIndex = integer(state.actionIndex + 1, LIMITS.actions, 'actionIndex');
  return state;
}
// Source establishes three consecutive same-owner points and three creations per round.
// Local edge policies: settle effects first; no creation after lethal; consume a full-hand
// trigger without queuing it; zero-point ultimate cards leave an existing chain unchanged.
function gainUltimate(definition, state, card, events) {
  const rules = definition.ultimateRules, combo = state.ultimate;
  if (!rules || !card.specialPoints || state.status !== 'player-turn' || combo.generatedThisRound >= rules.maxPerRound) return;
  combo.points = (combo.chainOwnerId === card.ownerId ? combo.points : 0) + card.specialPoints;
  combo.chainOwnerId = card.ownerId;
  if (combo.points < rules.pointsRequired) return;
  combo.points = 0; combo.chainOwnerId = null;
  if (state.piles.hand.length >= definition.handLimit) return;
  combo.generatedThisRound += 1; combo.generatedTotal += 1;
  const instanceId = `ultimate:${combo.generatedTotal}`;
  state.cards.push({ instanceId, cardId: rules.cardId });
  state.piles.hand.push(instanceId);
  events.push({ type: 'CardDrawn', instanceId, generated: true });
}
function leaveHand(definition, state, instanceId, from, events) {
  const cardId = state.cards.find(card => card.instanceId === instanceId).cardId;
  const to = definition.ultimateRules && definition.cards[cardId].removeOnLeaveHand ? 'removed' : 'discard';
  state.piles[to].push(instanceId);
  events.push({ type: 'CardMoved', instanceId, from, to });
}
export function createBattle(input, seed) {
  const definition = definitionCopy(input);
  seed = integer(seed, 0xffffffff, 'seed');
  const state = { format: definition.ultimateRules ? ULTIMATE_FORMAT : definition.statusRules ? STATUS_FORMAT : FORMAT, definitionId: definition.id, round: 1, status: 'player-turn', outcomeReason: null,
    energy: definition.energyPerRound, player: { hp: definition.player.maxHp, shield: toTagged(ZERO) },
    enemy: { hp: definition.enemy.maxHp, shield: toTagged(ZERO) }, cards: definition.deck.map(card => ({ ...card })),
    piles: { hand: [], draw: definition.deck.map(card => card.instanceId), discard: [], exhausted: [], powerUsed: [], removed: [] },
    rng: { algorithm: 'mulberry32-v1', state: seed }, actionIndex: 0 };
  if (definition.statusRules) state.breakdown = { player: 0, enemy: 0 };
  if (definition.ultimateRules) state.ultimate = { chainOwnerId: null, points: 0, generatedThisRound: 0, generatedTotal: 0 };
  const events = [{ type: 'BattleStarted', definitionId: definition.id, seed }, { type: 'TurnStarted', round: 1 }];
  draw(definition, state, definition.initialDraw, events);
  return finish(definition, state, events);
}
export function playCard(input, original, instanceId) {
  const definition = definitionCopy(input), state = active(definition, original);
  id(instanceId, 'instanceId');
  const position = state.piles.hand.indexOf(instanceId);
  if (position < 0) error('card instance is not in hand');
  const cardId = state.cards.find(card => card.instanceId === instanceId).cardId, card = definition.cards[cardId];
  if (card.cost > state.energy) error('insufficient energy');
  const events = [{ type: 'CardPlayed', instanceId, cardId, cost: card.cost }];
  energy(state, state.energy - card.cost, events);
  state.piles.hand.splice(position, 1); // In flight: never included in same-card draw effects.
  applyEffects(state, 'player', card.effects, definition, events);
  leaveHand(definition, state, instanceId, 'in-flight', events);
  gainUltimate(definition, state, card, events);
  return finish(definition, state, events);
}
export function endTurn(input, original) {
  const definition = definitionCopy(input), state = active(definition, original), events = [];
  tickBreakdown(definition, state, 'player', events);
  if (state.status !== 'player-turn') return finish(definition, state, events);
  for (const instanceId of state.piles.hand) {
    leaveHand(definition, state, instanceId, 'hand', events);
  }
  state.piles.hand = [];
  if (state.ultimate) { state.ultimate.points = 0; state.ultimate.chainOwnerId = null; }
  clearShield(state, 'enemy', events);
  const intent = definition.enemyIntents[state.round - 1] || definition.enemyFallback;
  for (const skillId of intent) {
    if (state.status !== 'player-turn') break;
    events.push({ type: 'EnemySkillUsed', skillId, round: state.round });
    applyEffects(state, 'enemy', definition.enemySkills[skillId].effects, definition, events);
  }
  tickBreakdown(definition, state, 'enemy', events);
  if (state.status === 'player-turn') {
    if (state.round === definition.maxRounds) outcome(state, 'lost', 'round-limit', events);
    else {
      state.round += 1;
      if (state.ultimate) state.ultimate.generatedThisRound = 0;
      clearShield(state, 'player', events);
      energy(state, definition.energyPerRound, events);
      events.push({ type: 'TurnStarted', round: state.round });
      draw(definition, state, definition.roundDraw, events);
    }
  }
  return finish(definition, state, events);
}
