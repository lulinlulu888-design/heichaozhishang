// New-client normalized DTO projection. Not an original wire decoder, damage
// calculator, action scheduler, or engine renderer. No Node or BigInt dependency.
export const LIMITS = Object.freeze({ entities: 1024, teams: 16, cards: 8192,
  batchActions: 4096, groupDepth: 32, pendingEvents: 16384, batches: 4096, integerDigits: 4096 });
export const PILE_NAMES = Object.freeze(['handPile', 'drawPile', 'discardPile', 'exhaustedPile', 'powerUsedPile']);
const states = new WeakMap();
const freeze = Object.freeze;
const fail = (message) => { throw new TypeError(message); };

function record(value, keys, label) {
  if (!value || typeof value !== 'object' ||
      (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) fail(`${label}: plain DTO object required`);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.length !== keys.length || actual.some(k => !keys.includes(k))) fail(`${label}: missing or unsupported field`);
  for (const key of keys) if (!descriptors[key] || !('value' in descriptors[key])) fail(`${label}.${key}: accessors are unsupported`);
  return value;
}
function array(value, limit, label) {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > limit) fail(`${label}: bounded plain array required`);
  const own = Reflect.ownKeys(value);
  if (own.length !== value.length + 1) fail(`${label}: sparse/custom arrays unsupported`);
  for (let i = 0; i < value.length; ++i) {
    const d = Object.getOwnPropertyDescriptor(value, String(i));
    if (!d || !('value' in d)) fail(`${label}: sparse/accessor arrays unsupported`);
  }
  return value;
}
function id(value, label) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) fail(`${label}: normalized string ID required`);
  return value;
}
function numericHex(number) {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, number, false);
  const high = view.getUint32(0), low = view.getUint32(4);
  const sign = high >>> 31 ? '-' : '', exponent = (high >>> 20) & 0x7ff;
  const fraction = (high & 0xfffff).toString(16).padStart(5, '0') + low.toString(16).padStart(8, '0');
  if (!exponent && !(high & 0xfffff) && !low) return `${sign}0x0.0p+0`;
  const power = exponent ? exponent - 1023 : -1022;
  return `${sign}0x${exponent ? 1 : 0}.${fraction}p${power < 0 ? '' : '+'}${power}`;
}
function valueCopy(value, label) {
  // Inspect discriminants as data properties, never invoke a DTO getter.
  if (!value || typeof value !== 'object') fail(`${label}: tagged numeric value required`);
  const tag = Object.getOwnPropertyDescriptor(value, 'numeric_type');
  if (!tag || !('value' in tag)) fail(`${label}: numeric_type data field required`);
  if (tag.value === 'integer') {
    record(value, ['numeric_type', 'decimal'], label);
    if (typeof value.decimal !== 'string' || value.decimal.length > LIMITS.integerDigits ||
        !/^(?:0|-?[1-9][0-9]*)$/.test(value.decimal)) fail(`${label}: canonical integer decimal required`);
    return freeze({ numeric_type: 'integer', decimal: value.decimal });
  }
  if (tag.value !== 'binary64') fail(`${label}: unsupported numeric type`);
  record(value, ['numeric_type', 'decimal', 'hex'], label);
  if (typeof value.decimal !== 'string' || value.decimal.length > 64 ||
      !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(value.decimal)) fail(`${label}: finite binary64 decimal required`);
  const number = Number(value.decimal);
  if (!Number.isFinite(number) || numericHex(number) !== value.hex) fail(`${label}: invalid or inconsistent binary64`);
  return freeze({ numeric_type: 'binary64', decimal: value.decimal, hex: value.hex });
}
export function integerValue(decimal) {
  return valueCopy({ numeric_type: 'integer', decimal }, 'integerValue');
}
export function binary64Value(number) {
  if (typeof number !== 'number' || !Number.isFinite(number)) fail('binary64Value: finite Number required');
  let decimal = Object.is(number, -0) ? '-0.0' : String(number);
  if (!/[.eE]/.test(decimal)) decimal += '.0';
  return valueCopy({ numeric_type: 'binary64', decimal, hex: numericHex(number) }, 'binary64Value');
}

function snapshotCopy(input, label) {
  record(input, ['snapshotId', 'entities', 'teams'], label);
  const snapshotId = id(input.snapshotId, `${label}.snapshotId`);
  const entityIds = new Set();
  const entities = array(input.entities, LIMITS.entities, `${label}.entities`).map((e, index) => {
    const loc = `${label}.entities[${index}]`;
    record(e, ['id', 'hp', 'shield'], loc); id(e.id, `${loc}.id`);
    if (entityIds.has(e.id)) fail(`${loc}: duplicate entity ID`);
    entityIds.add(e.id);
    return freeze({ id: e.id, hp: valueCopy(e.hp, `${loc}.hp`), shield: valueCopy(e.shield, `${loc}.shield`) });
  });
  const teamIds = new Set(), allCards = new Set();
  const teams = array(input.teams, LIMITS.teams, `${label}.teams`).map((team, index) => {
    const loc = `${label}.teams[${index}]`;
    record(team, ['id', 'cards', 'piles'], loc); id(team.id, `${loc}.id`);
    if (teamIds.has(team.id)) fail(`${loc}: duplicate team ID`);
    teamIds.add(team.id);
    const cardIds = new Set();
    const cards = array(team.cards, LIMITS.cards, `${loc}.cards`).map((card, index) => {
      const at = `${loc}.cards[${index}]`;
      record(card, ['id', 'cardTypeId', 'charId'], at);
      for (const field of ['id', 'cardTypeId', 'charId']) id(card[field], `${at}.${field}`);
      if (allCards.has(card.id)) fail(`${at}: duplicate card ID`);
      cardIds.add(card.id); allCards.add(card.id);
      if (allCards.size > LIMITS.cards) fail(`${label}: total card budget exceeded`);
      return freeze({ id: card.id, cardTypeId: card.cardTypeId, charId: card.charId });
    });
    record(team.piles, PILE_NAMES, `${loc}.piles`);
    const piles = {}, assignedCards = new Set();
    for (const name of PILE_NAMES) {
      const members = array(team.piles[name], LIMITS.cards, `${loc}.piles.${name}`);
      const seen = new Set();
      piles[name] = freeze(members.map(value => {
        id(value, `${loc}.piles.${name}`);
        if (!cardIds.has(value)) fail(`${loc}.piles.${name}: unknown card`);
        if (seen.has(value)) fail(`${loc}.piles.${name}: duplicate card`);
        if (assignedCards.has(value)) fail(`${loc}.piles.${name}: card assigned to multiple piles`);
        seen.add(value); assignedCards.add(value); return value;
      }));
    }
    // Cross-pile exclusivity is a NEW normalized-state invariant, not a claim
    // that the original synchronizer performed this check. Unassigned cards OK.
    return freeze({ id: team.id, cards: freeze(cards), piles: freeze(piles) });
  });
  return freeze({ snapshotId, entities: freeze(entities), teams: freeze(teams) });
}

function flattenBatch(batch) {
  record(batch, ['batchId', 'actions'], 'batch');
  id(batch.batchId, 'batch.batchId');
  const tokens = [], groupIds = new Set(), active = new Set();
  let count = 0;
  function walk(actions, parentPath, depth) {
    if (depth > LIMITS.groupDepth) fail('group nesting budget exceeded');
    array(actions, LIMITS.batchActions, 'actions');
    if (active.has(actions)) fail('cyclic action group');
    active.add(actions);
    for (let i = 0; i < actions.length; ++i) {
      if (++count > LIMITS.batchActions) fail('batch action budget exceeded');
      const action = actions[i], actionPath = freeze(parentPath.concat(i));
      const descriptor = action && typeof action === 'object' && Object.getOwnPropertyDescriptor(action, 'type');
      if (!descriptor || !('value' in descriptor)) fail('action.type data field required');
      const base = { batchId: batch.batchId, actionPath };
      if (descriptor.value === 'Group') {
        record(action, ['type', 'kind', 'id', 'actions'], 'Group');
        id(action.id, 'Group.id');
        if (!['SkillUse', 'SkillEachState', 'Target'].includes(action.kind)) fail('unsupported group kind');
        if (groupIds.has(action.id)) fail('duplicate group ID within batch');
        groupIds.add(action.id);
        const group = freeze({ ...base, id: action.id, kind: action.kind });
        tokens.push(freeze({ ...base, type: 'GroupBegin', group }));
        walk(action.actions, actionPath, depth + 1);
        tokens.push(freeze({ ...base, type: 'GroupEnd', group }));
      } else if (descriptor.value === 'SyncSnapshot') {
        record(action, ['type', 'snapshot'], 'SyncSnapshot');
        tokens.push(freeze({ ...base, type: 'SyncSnapshot', snapshot: snapshotCopy(action.snapshot, 'SyncSnapshot.snapshot') }));
      } else if (descriptor.value === 'HpChange' || descriptor.value === 'ShieldChange') {
        record(action, ['type', 'targetId', 'deltaValue', 'finalValue'], descriptor.value);
        tokens.push(freeze({ ...base, type: action.type, targetId: id(action.targetId, 'targetId'),
          deltaValue: valueCopy(action.deltaValue, 'deltaValue'), finalValue: valueCopy(action.finalValue, 'finalValue') }));
      } else fail('unsupported action type');
    }
    active.delete(actions);
  }
  walk(batch.actions, [], 0);
  return freeze(tokens);
}

function applyVisible(snapshot, token) {
  if (token.type === 'SyncSnapshot') return token.snapshot;
  if (token.type !== 'HpChange' && token.type !== 'ShieldChange') return snapshot;
  const target = snapshot.entities.find(e => e.id === token.targetId);
  if (!target) fail(`unknown target at playback position: ${token.targetId}`);
  const field = token.type === 'HpChange' ? 'hp' : 'shield';
  const replacement = freeze({ ...target, [field]: token.finalValue });
  return freeze({ ...snapshot, entities: freeze(snapshot.entities.map(e => e === target ? replacement : e)) });
}
function state(projection) {
  const value = projection && states.get(projection);
  if (!value) fail('projection must be created by this module');
  return value;
}
function handle(value) {
  const result = freeze({ type: 'BattlePresentationProjection' });
  states.set(result, value); return result;
}
export function createProjection(initialSnapshot) {
  const initial = snapshotCopy(initialSnapshot, 'initialSnapshot');
  return handle({ received: initial, visible: initial, future: initial, pending: freeze([]),
    groups: freeze([]), batches: new Set(), played: 0 });
}

export function receiveBatch(projection, batch) {
  const previous = state(projection);
  const tokens = flattenBatch(batch); // Deep-copy and validate the entire DTO first.
  if (previous.batches.has(batch.batchId)) fail('batch ID already received');
  if (previous.batches.size >= LIMITS.batches) fail('projection lifetime batch budget exceeded');
  if (previous.pending.length + tokens.length > LIMITS.pendingEvents) fail('pending event budget exceeded');
  let future = previous.future, received = previous.received;
  const receipts = [];
  for (const token of tokens) {
    // Validate against the tail of ALL accepted actions, not newest received
    // snapshot or currently visible entities. All work remains local on error.
    future = applyVisible(future, token);
    if (token.type === 'SyncSnapshot') {
      receipts.push(freeze({ type: 'SnapshotReceived', batchId: token.batchId,
        actionPath: token.actionPath, previousSnapshotId: received.snapshotId, snapshotId: token.snapshot.snapshotId }));
      received = token.snapshot;
    }
  }
  const batches = new Set(previous.batches); batches.add(batch.batchId);
  return freeze({ projection: handle({ ...previous, received, future, batches,
    pending: freeze(previous.pending.concat(tokens)) }), receipts: freeze(receipts) });
}

export function playNext(projection, count = 1) {
  const previous = state(projection);
  if (!Number.isSafeInteger(count) || count < 1 || count > previous.pending.length ||
      !Number.isSafeInteger(previous.played + count)) fail('invalid playback event count');
  let visible = previous.visible;
  const groups = previous.groups.slice(), events = [];
  for (let i = 0; i < count; ++i) {
    const token = previous.pending[i];
    const base = { batchId: token.batchId, actionPath: token.actionPath, sequence: previous.played + i + 1 };
    if (token.type === 'GroupBegin') {
      groups.push(token.group);
      events.push(freeze({ ...base, type: token.type, group: token.group, depth: groups.length }));
    } else if (token.type === 'GroupEnd') {
      if (groups[groups.length - 1] !== token.group) fail('internal group boundary mismatch');
      events.push(freeze({ ...base, type: token.type, group: token.group, depth: groups.length }));
      groups.pop();
    } else if (token.type === 'SyncSnapshot') {
      visible = token.snapshot;
      events.push(freeze({ ...base, type: 'SnapshotApplied', snapshot: token.snapshot }));
    } else {
      const old = visible.entities.find(e => e.id === token.targetId);
      if (!old) fail('internal target validation mismatch');
      visible = applyVisible(visible, token);
      events.push(freeze({ ...base, type: token.type, targetId: token.targetId,
        previousValue: token.type === 'HpChange' ? old.hp : old.shield,
        deltaValue: token.deltaValue, finalValue: token.finalValue }));
    }
  }
  return freeze({ projection: handle({ ...previous, visible, groups: freeze(groups),
    pending: freeze(previous.pending.slice(count)), played: previous.played + count }), events: freeze(events) });
}

export function inspectProjection(projection) {
  const s = state(projection);
  return freeze({ receivedSnapshot: s.received, visibleState: s.visible,
    pendingCount: s.pending.length, playedCount: s.played, receivedBatchCount: s.batches.size, activeGroups: s.groups });
}
