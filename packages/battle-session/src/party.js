// Explicit party reconstruction rules (prologue battle 1703). Source tables give
// the party, deck owners, card factors, state target enums and boss skills; the
// resolver code for those enums, buff timing and member defeat handling were not
// recovered, so the choices below are labelled local policy, not original rules.
import {
  int, float, fromTagged, toTagged, compare, add, subtract, multiply, classicDivide,
  calcDamage, calcBlock, attackFactorValue,
} from '../../battle-core/src/index.js';

export const PARTY_FORMAT = 'hczs-battle-session-party-v1';
export const PARTY_POLICY = 'prologue-party-reconstruction-v1';
const LIMITS = Object.freeze({ members: 3, cards: 64, cardDefinitions: 256, enemySkills: 128, effects: 32,
  skillsPerTurn: 16, rounds: 1000, energy: 1000000, actions: 1000000, hits: 16, stacks: 999, factor: 100000, amountDigits: 64 });
const ZERO = int(0);
const ZONES = ['hand', 'draw', 'discard', 'removed'];
const DEF_KEYS = ['id', 'player', 'party', 'enemy', 'deck', 'cards', 'enemySkills', 'enemyIntents', 'enemyFallback',
  'initialDraw', 'roundDraw', 'energyPerRound', 'handLimit', 'maxRounds', 'partyRules'];
const STATE_KEYS = ['format', 'definitionId', 'round', 'status', 'outcomeReason', 'energy', 'party', 'enemy',
  'cards', 'piles', 'rng', 'actionIndex'];
// Neutral values for every unrecovered calcDamage/calcBlock dependency.
const NEUTRAL_DAMAGE = Object.freeze({ rpgAttackType: int(1), addAttackValue: ZERO, combatCounterRatioValue: int(1),
  dstEntityDefenseValue: int(1), attackedFactorValue: ZERO, criticalRatioValue: int(1), propDamageIncValue: ZERO,
  propDamageReduceValue: ZERO, propAtkDamageIncValue: ZERO, propAtkDamageReduceValue: ZERO, propMgcDamageIncValue: ZERO,
  propMgcDamageReduceValue: ZERO, overwhelmRatio: int(1), extraAttackValue: ZERO, extraAttackedValue: ZERO,
  extraDamage: ZERO, isPVP: false, pvpAtkRatio: int(1), isDamageSkillPreview: false, slowHp: ZERO });
const NEUTRAL_SHIELD_SOURCE = Object.freeze({ propAddTargetShield: ZERO, shieldFactor: ZERO });
const NEUTRAL_SHIELD_TARGET = Object.freeze({ propBeAddShield: ZERO, shieldFactor: ZERO, isPVP: false, pvpShieldRatio: int(1) });

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
  return Array.from({ length: value.length }, (_, index) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !('value' in descriptor)) error(`${label}: dense data indices required`);
    return descriptor.value;
  });
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
  return value === 0 ? 0 : value;
}
function scalar(value, label) {
  record(value, null, label);
  if (value.numeric_type === 'integer') {
    record(value, ['numeric_type', 'decimal'], label);
    if (typeof value.decimal !== 'string' || value.decimal.length > 128 || !/^(?:0|[1-9][0-9]*)$/.test(value.decimal)) error(`${label}: canonical decimal required`);
  } else if (value.numeric_type === 'binary64') {
    record(value, ['numeric_type', 'decimal', 'hex'], label);
    if (typeof value.decimal !== 'string' || value.decimal.length > 64) error(`${label}: binary64 decimal outside bounds`);
  } else error(`${label}: unknown numeric type`);
  const parsed = fromTagged(value);
  if (compare(parsed, ZERO) < 0) error(`${label}: cannot be negative`);
  return toTagged(parsed);
}
function positive(value, label) {
  const result = scalar(value, label);
  if (zero(result)) error(`${label}: must be positive`);
  return result;
}
const zero = value => compare(fromTagged(value), ZERO) === 0;
const min = (a, b) => compare(a, b) < 0 ? a : b;
function freeze(value) {
  if (value && typeof value === 'object') { for (const key of Object.keys(value)) freeze(value[key]); Object.freeze(value); }
  return value;
}

function playerEffects(input) {
  return list(input, LIMITS.effects, 'effects').map(effect => {
    record(effect, null, 'effect');
    if (effect.type === 'damage') {
      record(effect, ['type', 'target', 'factor'], 'damage effect');
      if (effect.target !== 'opponent') error('player damage requires opponent target');
      return { type: 'damage', target: 'opponent', factor: integer(effect.factor, LIMITS.factor, 'factor') };
    }
    if (effect.type === 'shield') {
      record(effect, ['type', 'target', 'factor'], 'shield effect');
      if (!['self', 'party'].includes(effect.target)) error('unsupported shield target');
      return { type: 'shield', target: effect.target, factor: integer(effect.factor, LIMITS.factor, 'factor') };
    }
    if (effect.type === 'attackBuff') {
      record(effect, ['type', 'target', 'stacks'], 'buff effect');
      if (!['self', 'party'].includes(effect.target)) error('unsupported buff target');
      return { type: 'attackBuff', target: effect.target, stacks: integer(effect.stacks, LIMITS.stacks, 'stacks', 1) };
    }
    if (effect.type === 'draw') {
      record(effect, ['type', 'count'], 'draw effect');
      return { type: 'draw', count: integer(effect.count, LIMITS.cards, 'draw count') };
    }
    error('unsupported party card effect');
  });
}
function enemyEffects(input) {
  return list(input, LIMITS.effects, 'effects').map(effect => {
    record(effect, null, 'effect');
    if (effect.type === 'damage') {
      record(effect, ['type', 'target', 'factor', 'times'], 'enemy damage effect');
      if (effect.target !== 'first-mid-last') error('enemy damage requires first-mid-last target');
      return { type: 'damage', target: 'first-mid-last', factor: integer(effect.factor, LIMITS.factor, 'factor'),
        times: integer(effect.times, LIMITS.hits, 'times', 1) };
    }
    if (effect.type === 'attackBuff') {
      record(effect, ['type', 'target', 'stacks'], 'enemy buff effect');
      if (effect.target !== 'self') error('enemy buff requires self target');
      return { type: 'attackBuff', target: 'self', stacks: integer(effect.stacks, LIMITS.stacks, 'stacks', 1) };
    }
    error('unsupported party enemy effect');
  });
}

export function isPartyDefinition(input) {
  return Boolean(input) && typeof input === 'object' && Object.prototype.hasOwnProperty.call(input, 'partyRules');
}

function definitionCopy(input) {
  record(input, DEF_KEYS, 'definition');
  const rules = record(input.partyRules, ['policy', 'buffId', 'attackPercentPerStack', 'maxStacks', 'enemyTargeting'], 'partyRules');
  if (rules.policy !== PARTY_POLICY || rules.buffId !== '1001' || rules.attackPercentPerStack !== 6 ||
      rules.maxStacks !== 999 || rules.enemyTargeting !== 'first-living-in-formation') error('unsupported party policy');
  const result = { id: id(input.id, 'definition.id'), partyRules: { ...rules } };
  record(input.player, ['id', 'name'], 'player');
  result.player = { id: id(input.player.id, 'player.id'), name: name(input.player.name) };
  const members = list(input.party, LIMITS.members, 'party');
  if (!members.length) error('party requires at least one member');
  const memberIds = new Set();
  result.party = members.map((member, index) => {
    record(member, ['id', 'name', 'maxHp', 'attack'], `party[${index}]`);
    const memberId = id(member.id, 'member.id');
    if (memberIds.has(memberId)) error('duplicate party member');
    memberIds.add(memberId);
    return { id: memberId, name: name(member.name), maxHp: positive(member.maxHp, 'member.maxHp'), attack: positive(member.attack, 'member.attack') };
  });
  record(input.enemy, ['id', 'name', 'maxHp', 'attack'], 'enemy');
  result.enemy = { id: id(input.enemy.id, 'enemy.id'), name: name(input.enemy.name),
    maxHp: positive(input.enemy.maxHp, 'enemy.maxHp'), attack: positive(input.enemy.attack, 'enemy.attack') };
  if (memberIds.has(result.enemy.id)) error('combatant IDs must differ');
  for (const field of ['cards', 'enemySkills']) {
    const map = record(input[field], null, field), keys = Reflect.ownKeys(map);
    if (!keys.length || keys.length > (field === 'cards' ? LIMITS.cardDefinitions : LIMITS.enemySkills)) error(`${field}: definition count outside bounds`);
    const out = Object.create(null);
    for (const key of keys) {
      id(key, field);
      const entry = map[key];
      if (field === 'enemySkills') {
        record(entry, ['effects'], `${field}.${key}`);
        out[key] = { effects: enemyEffects(entry.effects) };
      } else {
        record(entry, ['name', 'cost', 'effects'], `${field}.${key}`);
        out[key] = { name: name(entry.name), cost: integer(entry.cost, LIMITS.energy, 'card cost'), effects: playerEffects(entry.effects) };
      }
    }
    result[field] = out;
  }
  const instances = new Set();
  result.deck = list(input.deck, LIMITS.cards, 'deck').map(card => {
    record(card, ['instanceId', 'cardId', 'ownerId'], 'deck card');
    id(card.instanceId, 'instanceId'); id(card.cardId, 'cardId');
    if (instances.has(card.instanceId) || !Object.prototype.hasOwnProperty.call(result.cards, card.cardId)) error('duplicate instance or unknown card ID');
    if (!memberIds.has(card.ownerId)) error('deck card owner is not a party member');
    instances.add(card.instanceId);
    return { instanceId: card.instanceId, cardId: card.cardId, ownerId: card.ownerId };
  });
  if (!result.deck.length) error('deck must contain at least one instance');
  const intent = value => {
    const order = list(value, LIMITS.skillsPerTurn, 'enemy intent');
    if (!order.length) error('enemy intent must explicitly contain at least one skill');
    for (const key of order) if (typeof key !== 'string' || !Object.prototype.hasOwnProperty.call(result.enemySkills, key)) error('unknown enemy skill ID');
    return order;
  };
  result.enemyIntents = list(input.enemyIntents, LIMITS.rounds, 'enemyIntents').map(intent);
  result.enemyFallback = intent(input.enemyFallback);
  for (const key of ['initialDraw', 'roundDraw', 'handLimit']) result[key] = integer(input[key], LIMITS.cards, key);
  result.energyPerRound = integer(input.energyPerRound, LIMITS.energy, 'energyPerRound');
  result.maxRounds = integer(input.maxRounds, LIMITS.rounds, 'maxRounds', 1);
  return result;
}
export function validatePartyDefinition(definition) { return freeze(definitionCopy(definition)); }

function fighter(input, maxHp, label) {
  record(input, ['hp', 'shield', 'attackBuff'], label);
  const out = { hp: scalar(input.hp, `${label}.hp`), shield: scalar(input.shield, `${label}.shield`),
    attackBuff: integer(input.attackBuff, LIMITS.stacks, `${label}.attackBuff`) };
  if (compare(fromTagged(out.hp), fromTagged(maxHp)) > 0) error('HP exceeds definition maxHp');
  return out;
}
const living = (state, index) => !zero(state.party[index].hp);
function stateCopy(definition, input) {
  record(input, STATE_KEYS, 'state');
  if (input.format !== PARTY_FORMAT || input.definitionId !== definition.id) error('state format/definition mismatch');
  const out = { format: PARTY_FORMAT, definitionId: definition.id, round: integer(input.round, definition.maxRounds, 'round', 1),
    status: input.status, outcomeReason: input.outcomeReason, energy: integer(input.energy, definition.energyPerRound, 'energy'),
    actionIndex: integer(input.actionIndex, LIMITS.actions, 'actionIndex') };
  const party = list(input.party, definition.party.length, 'state.party');
  if (party.length !== definition.party.length) error('party state does not match definition');
  out.party = party.map((member, index) => fighter(member, definition.party[index].maxHp, `state.party[${index}]`));
  out.enemy = fighter(input.enemy, definition.enemy.maxHp, 'state.enemy');
  const anyLiving = out.party.some((_, index) => living(out, index));
  if (out.status === 'player-turn') {
    if (out.outcomeReason !== null || !anyLiving || zero(out.enemy.hp)) error('invalid active state');
  } else if (out.status === 'won') {
    if (out.outcomeReason !== 'enemy-defeated' || !zero(out.enemy.hp) || !anyLiving) error('invalid won state');
  } else if (out.status === 'lost') {
    if (zero(out.enemy.hp) || !((out.outcomeReason === 'party-defeated' && !anyLiving) ||
        (out.outcomeReason === 'round-limit' && anyLiving && out.round === definition.maxRounds))) error('invalid lost state');
  } else error('unknown battle status');
  const registry = list(input.cards, definition.deck.length, 'state.cards');
  if (registry.length !== definition.deck.length) error('card registry does not match definition');
  out.cards = registry.map((card, index) => {
    record(card, ['instanceId', 'cardId', 'ownerId'], 'registry card');
    const expected = definition.deck[index];
    if (card.instanceId !== expected.instanceId || card.cardId !== expected.cardId || card.ownerId !== expected.ownerId) error('card registry does not match definition');
    return { ...expected };
  });
  record(input.piles, ZONES, 'piles');
  const owners = new Map(out.cards.map(card => [card.instanceId, card.ownerId])), seen = new Set();
  const defeated = new Set(definition.party.filter((_, index) => !living(out, index)).map(member => member.id));
  out.piles = {};
  for (const zone of ZONES) {
    const members = list(input.piles[zone], LIMITS.cards, zone);
    for (const value of members) {
      if (!owners.has(value) || seen.has(value)) error('unknown or duplicate pile instance');
      // Defeated members' cards leave play; removal is used for nothing else.
      if ((zone === 'removed') !== defeated.has(owners.get(value))) error('invalid removed pile');
      seen.add(value);
    }
    out.piles[zone] = members;
  }
  if (seen.size !== owners.size) error('every instance must occupy exactly one pile');
  if (out.piles.hand.length > definition.handLimit) error('hand exceeds definition handLimit');
  record(input.rng, ['algorithm', 'state'], 'rng');
  if (input.rng.algorithm !== 'mulberry32-v1') error('unknown PRNG algorithm');
  out.rng = { algorithm: 'mulberry32-v1', state: integer(input.rng.state, 0xffffffff, 'PRNG state') };
  return out;
}
export function validatePartyState(definition, state) { return freeze(stateCopy(definitionCopy(definition), state)); }

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
// Buff 1001 description index is "%s*6": each stack is one 6% attack factor.
function attackFactor(definition, stacks) {
  const factor = add(int(1), classicDivide(multiply(int(stacks), int(definition.partyRules.attackPercentPerStack)), float(100.0)));
  return attackFactorValue({ factors: [factor], commonFactors: [], cardFactor: ZERO, battleFactor: ZERO });
}
function base(attack, factor) { return classicDivide(multiply(fromTagged(attack), int(factor)), float(100.0)); }
function damageAmount(definition, attack, factor, stacks, dstIsPlayer) {
  return calcDamage({ ...NEUTRAL_DAMAGE, rpgBasicActionValue: base(attack, factor),
    attackFactorValue: attackFactor(definition, stacks), dstIsPlayer }).damage;
}
function shieldAmount(attack, factor) {
  return calcBlock({ basicBlock: base(attack, factor), source: NEUTRAL_SHIELD_SOURCE, card: null, target: NEUTRAL_SHIELD_TARGET }).block;
}
function hit(state, target, memberIndex, amount, details, events) {
  const entity = target === 'enemy' ? state.enemy : state.party[memberIndex];
  const previousHp = entity.hp, previousShield = entity.shield, shield = fromTagged(entity.shield), hp = fromTagged(entity.hp);
  const absorbed = min(shield, amount), hpLost = min(hp, subtract(amount, absorbed));
  entity.shield = toTagged(subtract(shield, absorbed)); entity.hp = toTagged(subtract(hp, hpLost));
  events.push({ type: 'DamageApplied', ...details, target, ...(target === 'party' ? { memberIndex } : {}),
    amount: amount.value.toString(), absorbed: toTagged(absorbed), hpLost: toTagged(hpLost),
    previousHp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
}
function buff(state, target, memberIndex, stacks, details, events) {
  const entity = target === 'enemy' ? state.enemy : state.party[memberIndex];
  const previousStacks = entity.attackBuff;
  entity.attackBuff = Math.min(LIMITS.stacks, previousStacks + stacks);
  events.push({ type: 'BuffChanged', ...details, target, ...(target === 'party' ? { memberIndex } : {}),
    buffId: '1001', previousStacks, finalStacks: entity.attackBuff });
}
function shieldMember(state, memberIndex, amount, details, events) {
  const entity = state.party[memberIndex], previousShield = entity.shield;
  entity.shield = toTagged(add(fromTagged(entity.shield), amount));
  events.push({ type: 'ShieldAdded', ...details, target: 'party', memberIndex, amount: amount.value.toString(),
    previousHp: entity.hp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
}
function defeatMember(definition, state, memberIndex, events) {
  const ownerId = definition.party[memberIndex].id;
  events.push({ type: 'MemberDefeated', memberIndex, memberId: ownerId });
  for (const zone of ['hand', 'draw', 'discard']) {
    const keep = [];
    for (const instanceId of state.piles[zone]) {
      if (state.cards.find(card => card.instanceId === instanceId).ownerId !== ownerId) keep.push(instanceId);
      else { state.piles.removed.push(instanceId); events.push({ type: 'CardMoved', instanceId, from: zone, to: 'removed' }); }
    }
    state.piles[zone] = keep;
  }
}
function settle(definition, state, events) {
  if (zero(state.enemy.hp)) return outcome(state, 'won', 'enemy-defeated', events);
  if (!state.party.some((_, index) => living(state, index))) outcome(state, 'lost', 'party-defeated', events);
}
function partyTargets(state, target, ownerIndex) {
  return target === 'self' ? [ownerIndex] : state.party.map((_, index) => index).filter(index => living(state, index));
}
function playerAct(definition, state, ownerIndex, effects, events) {
  const owner = definition.party[ownerIndex];
  for (let effectIndex = 0; effectIndex < effects.length && state.status === 'player-turn'; ++effectIndex) {
    const effect = effects[effectIndex], details = { actor: 'party', actorIndex: ownerIndex, effectIndex };
    if (effect.type === 'draw') draw(definition, state, effect.count, events);
    else if (effect.type === 'damage') {
      hit(state, 'enemy', null, damageAmount(definition, owner.attack, effect.factor, state.party[ownerIndex].attackBuff, false), details, events);
      settle(definition, state, events);
    } else if (effect.type === 'shield') {
      const amount = shieldAmount(owner.attack, effect.factor);
      for (const index of partyTargets(state, effect.target, ownerIndex)) shieldMember(state, index, amount, details, events);
    } else for (const index of partyTargets(state, effect.target, ownerIndex)) buff(state, 'party', index, effect.stacks, details, events);
  }
}
// ENUM_OPPOSITE_FIRST_MID_LAST read as a formation priority order; every hit of
// one state re-selects so a defeated member passes remaining hits on.
function enemyAct(definition, state, skillId, events) {
  for (const [effectIndex, effect] of definition.enemySkills[skillId].effects.entries()) {
    if (state.status !== 'player-turn') return;
    const details = { actor: 'enemy', skillId, effectIndex };
    if (effect.type === 'attackBuff') { buff(state, 'enemy', null, effect.stacks, details, events); continue; }
    for (let time = 0; time < effect.times && state.status === 'player-turn'; ++time) {
      const memberIndex = state.party.findIndex((_, index) => living(state, index));
      const amount = damageAmount(definition, definition.enemy.attack, effect.factor, state.enemy.attackBuff, true);
      hit(state, 'party', memberIndex, amount, { ...details, hitIndex: time }, events);
      if (!living(state, memberIndex)) defeatMember(definition, state, memberIndex, events);
      settle(definition, state, events);
    }
  }
}
function energy(state, finalValue, events) {
  const previousValue = state.energy; state.energy = finalValue;
  events.push({ type: 'EnergyChanged', previousValue, finalValue });
}
function clearShield(state, target, memberIndex, events) {
  const entity = target === 'enemy' ? state.enemy : state.party[memberIndex], previousShield = entity.shield;
  if (zero(previousShield)) return;
  entity.shield = toTagged(ZERO);
  events.push({ type: 'ShieldCleared', target, ...(target === 'party' ? { memberIndex } : {}),
    previousHp: entity.hp, finalHp: entity.hp, previousShield, finalShield: entity.shield });
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

export function createPartyBattle(input, seed) {
  const definition = definitionCopy(input);
  seed = integer(seed, 0xffffffff, 'seed');
  const fresh = maxHp => ({ hp: maxHp, shield: toTagged(ZERO), attackBuff: 0 });
  const state = { format: PARTY_FORMAT, definitionId: definition.id, round: 1, status: 'player-turn', outcomeReason: null,
    energy: definition.energyPerRound, party: definition.party.map(member => fresh(member.maxHp)), enemy: fresh(definition.enemy.maxHp),
    cards: definition.deck.map(card => ({ ...card })),
    piles: { hand: [], draw: definition.deck.map(card => card.instanceId), discard: [], removed: [] },
    rng: { algorithm: 'mulberry32-v1', state: seed }, actionIndex: 0 };
  const events = [{ type: 'BattleStarted', definitionId: definition.id, seed }, { type: 'TurnStarted', round: 1 }];
  draw(definition, state, definition.initialDraw, events);
  return finish(definition, state, events);
}
export function playPartyCard(input, original, instanceId) {
  const definition = definitionCopy(input), state = active(definition, original);
  id(instanceId, 'instanceId');
  const position = state.piles.hand.indexOf(instanceId);
  if (position < 0) error('card instance is not in hand');
  const instance = state.cards.find(card => card.instanceId === instanceId), card = definition.cards[instance.cardId];
  const ownerIndex = definition.party.findIndex(member => member.id === instance.ownerId);
  if (card.cost > state.energy) error('insufficient energy');
  const events = [{ type: 'CardPlayed', instanceId, cardId: instance.cardId, cost: card.cost, ownerIndex }];
  energy(state, state.energy - card.cost, events);
  state.piles.hand.splice(position, 1);
  playerAct(definition, state, ownerIndex, card.effects, events);
  state.piles.discard.push(instanceId);
  events.push({ type: 'CardMoved', instanceId, from: 'in-flight', to: 'discard' });
  return finish(definition, state, events);
}
export function endPartyTurn(input, original) {
  const definition = definitionCopy(input), state = active(definition, original), events = [];
  for (const instanceId of state.piles.hand) {
    state.piles.discard.push(instanceId);
    events.push({ type: 'CardMoved', instanceId, from: 'hand', to: 'discard' });
  }
  state.piles.hand = [];
  clearShield(state, 'enemy', null, events);
  const intent = definition.enemyIntents[state.round - 1] || definition.enemyFallback;
  for (const skillId of intent) {
    if (state.status !== 'player-turn') break;
    events.push({ type: 'EnemySkillUsed', skillId, round: state.round });
    enemyAct(definition, state, skillId, events);
  }
  if (state.status === 'player-turn') {
    if (state.round === definition.maxRounds) outcome(state, 'lost', 'round-limit', events);
    else {
      state.round += 1;
      state.party.forEach((_, index) => clearShield(state, 'party', index, events));
      energy(state, definition.energyPerRound, events);
      events.push({ type: 'TurnStarted', round: state.round });
      draw(definition, state, definition.roundDraw, events);
    }
  }
  return finish(definition, state, events);
}
