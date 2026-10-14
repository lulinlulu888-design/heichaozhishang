import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import {
  createProjection, receiveBatch, playNext, inspectProjection,
  integerValue as int, binary64Value as float, LIMITS,
} from '../src/index.js';

// Entirely synthetic fixtures. No captured original server messages are available.
const piles = () => ({ handPile: [], drawPile: [], discardPile: [], exhaustedPile: [], powerUsedPile: [] });
const entity = (id = 'elsa', hp = '100', shield = '20') => ({ id, hp: int(hp), shield: int(shield) });
const snapshot = (snapshotId = 'initial', entities = [entity()], teams = []) => ({ snapshotId, entities, teams });
const change = (type = 'HpChange', final = '80', delta = '-20', targetId = 'elsa') =>
  ({ type, targetId, finalValue: int(final), deltaValue: int(delta) });
const sync = value => ({ type: 'SyncSnapshot', snapshot: value });
const group = (id, actions, kind = 'SkillUse') => ({ type: 'Group', kind, id, actions });
const batch = (actions, batchId = 'batch-1') => ({ batchId, actions });
const view = inspectProjection;
const start = () => createProjection(snapshot());
const accept = (projection, actions, batchId) => receiveBatch(projection, batch(actions, batchId)).projection;
const playAll = projection => playNext(projection, view(projection).pendingCount);
const team = () => ({ id: 'team1', cards: [
  { id: 'card-1', cardTypeId: '410101', charId: 'elsa' },
  { id: 'card-2', cardTypeId: '410101', charId: 'elsa' },
  { id: 'unassigned', cardTypeId: '410102', charId: 'elsa' },
], piles: { ...piles(), handPile: ['card-1'], drawPile: ['card-2'] } });

test('initial state is cloned, immutable, and separate from caller ownership', () => {
  const input = snapshot('initial', [entity()], [team()]);
  const projection = createProjection(input);
  input.entities[0].hp = int('999'); input.teams[0].piles.handPile.length = 0;
  assert.equal(view(projection).visibleState.entities[0].hp.decimal, '100');
  assert.deepEqual(view(projection).visibleState.teams[0].piles.handPile, ['card-1']);
  assert.throws(() => { view(projection).visibleState.entities[0].hp.decimal = '0'; }, TypeError);
  assert.throws(() => view(projection).visibleState.teams[0].cards.push({}), TypeError);
  assert.throws(() => inspectProjection({ type: 'BattlePresentationProjection' }), TypeError);
});

test('HP uses finalValue; delta is retained even when it does not sum to final', () => {
  const initial = start();
  const accepted = accept(initial, [change('HpChange', '80', '-999')]);
  assert.equal(view(accepted).visibleState.entities[0].hp.decimal, '100');
  assert.equal(view(accepted).receivedSnapshot.entities[0].hp.decimal, '100');
  const played = playNext(accepted);
  assert.equal(view(played.projection).visibleState.entities[0].hp.decimal, '80');
  assert.equal(view(played.projection).visibleState.entities[0].shield.decimal, '20');
  assert.equal(played.events[0].previousValue.decimal, '100');
  assert.equal(played.events[0].deltaValue.decimal, '-999');
  assert.equal(played.events[0].finalValue.decimal, '80');
  assert.equal(view(played.projection).receivedSnapshot.entities[0].hp.decimal, '100');
  assert.equal(view(initial).pendingCount, 0);
  assert.equal(view(accepted).pendingCount, 1);
});

test('shield is assigned directly; negative HP is not silently clamped or absorbed', () => {
  const played = playAll(accept(start(), [change('ShieldChange', '500', '-10'), change('HpChange', '-5', '-1')]));
  const result = view(played.projection).visibleState.entities[0];
  assert.equal(result.shield.decimal, '500'); assert.equal(result.hp.decimal, '-5');
  assert.deepEqual(played.events.map(e => e.type), ['ShieldChange', 'HpChange']);
});

test('receiving snapshots advances data immediately but card piles wait for playback', () => {
  const before = team(), after = team();
  after.piles.handPile = ['card-2']; after.piles.drawPile = []; after.piles.discardPile = ['card-1'];
  const initial = createProjection(snapshot('initial', [entity()], [before]));
  const incoming = snapshot('settled', [entity('elsa', '70')], [after]);
  const accepted = receiveBatch(initial, batch([change('HpChange', '80'), sync(incoming)]));
  assert.deepEqual(accepted.receipts, [{ type: 'SnapshotReceived', batchId: 'batch-1', actionPath: [1], previousSnapshotId: 'initial', snapshotId: 'settled' }]);
  assert.equal(view(accepted.projection).receivedSnapshot.entities[0].hp.decimal, '70');
  assert.deepEqual(view(accepted.projection).receivedSnapshot.teams[0].piles.handPile, ['card-2']);
  assert.deepEqual(view(accepted.projection).visibleState.teams[0].piles.handPile, ['card-1']);
  incoming.entities.length = 0; after.piles.discardPile.length = 0;
  const first = playNext(accepted.projection);
  assert.equal(view(first.projection).visibleState.entities[0].hp.decimal, '80');
  assert.equal(view(first.projection).receivedSnapshot.entities[0].hp.decimal, '70');
  const second = playNext(first.projection);
  assert.equal(second.events[0].type, 'SnapshotApplied');
  assert.deepEqual(view(second.projection).visibleState.teams[0].piles.discardPile, ['card-1']);
});

test('multiple queued snapshots retain the latest received state while older one plays', () => {
  const first = accept(start(), [sync(snapshot('A', [entity('elsa', '80')]))], 'A');
  const second = accept(first, [sync(snapshot('B', [entity('elsa', '70')]))], 'B');
  const played = playNext(second);
  assert.equal(view(played.projection).visibleState.snapshotId, 'A');
  assert.equal(view(played.projection).receivedSnapshot.snapshotId, 'B');
  const last = playNext(played.projection);
  assert.equal(view(last.projection).visibleState.snapshotId, 'B');
});

test('nested groups preserve boundaries, action paths, order and in-progress group state', () => {
  const received = accept(start(), [group('skill', [change(), group('state', [group('target', [
    change('ShieldChange', '10'),
  ], 'Target')], 'SkillEachState')]), group('empty', [])]);
  assert.equal(view(received).pendingCount, 10);
  const first = playNext(received, 3);
  assert.deepEqual(view(first.projection).activeGroups.map(g => g.id), ['skill', 'state']);
  const last = playAll(first.projection);
  const events = first.events.concat(last.events);
  assert.deepEqual(events.map(e => e.type), ['GroupBegin','HpChange','GroupBegin','GroupBegin','ShieldChange','GroupEnd','GroupEnd','GroupEnd','GroupBegin','GroupEnd']);
  assert.deepEqual(events.map(e => e.actionPath), [[0],[0,0],[0,1],[0,1,0],[0,1,0,0],[0,1,0],[0,1],[0],[1],[1]]);
  assert.deepEqual(events.filter(e => e.group).map(e => e.depth), [1,2,3,3,2,1,1,1]);
  assert.deepEqual(events.map(e => e.sequence), [1,2,3,4,5,6,7,8,9,10]);
  assert.deepEqual(view(last.projection).activeGroups, []);
  assert.throws(() => events[0].actionPath.push(1), TypeError);
});

test('invalid later action cannot partially commit an earlier snapshot or delta', () => {
  const original = start(), before = view(original);
  assert.throws(() => accept(original, [sync(snapshot('settled')), change(), change('HpChange', '1', '-1', 'missing')]), /unknown target/);
  assert.deepEqual(view(original), before);
  const corrected = accept(original, [sync(snapshot('settled')), change()]);
  assert.equal(view(corrected).receivedBatchCount, 1);
  assert.equal(view(corrected).receivedSnapshot.snapshotId, 'settled');
});

test('target validity follows the queued tail, not current visible or newest received state alone', () => {
  const pending = accept(start(), [sync(snapshot('removed', []))], 'remove');
  assert.equal(view(pending).visibleState.entities[0].id, 'elsa');
  assert.throws(() => accept(pending, [change()], 'bad'), /unknown target/);
  const newEntity = snapshot('new', [entity('monster')]);
  assert.throws(() => accept(start(), [change('HpChange', '1', '-1', 'monster'), sync(newEntity)]), /unknown target/);
  const good = accept(start(), [sync(newEntity), change('HpChange', '1', '-1', 'monster')]);
  assert.equal(view(playAll(good).projection).visibleState.entities[0].hp.decimal, '1');
});

test('invalid playback counts and duplicate batch IDs leave accepted state usable', () => {
  const accepted = accept(start(), [change()]), before = view(accepted);
  for (const count of [0, -1, 2, 0.5, NaN, Infinity, '1']) assert.throws(() => playNext(accepted, count), TypeError);
  assert.throws(() => accept(accepted, [change()]), /already received/);
  assert.deepEqual(view(accepted), before);
  assert.equal(view(playNext(accepted).projection).playedCount, 1);
  assert.throws(() => playNext(start()), TypeError);
});

test('empty batches are explicit deduplicated no-ops; group IDs are unique per batch', () => {
  const empty = receiveBatch(start(), batch([]));
  assert.deepEqual(empty.receipts, []); assert.equal(view(empty.projection).pendingCount, 0);
  assert.equal(view(empty.projection).receivedBatchCount, 1);
  assert.throws(() => accept(empty.projection, []), /already received/);
  assert.throws(() => accept(start(), [group('g', []), group('g', [])]), /duplicate group/);
  const first = accept(start(), [group('g', [])], 'A');
  assert.equal(view(accept(first, [group('g', [])], 'B')).pendingCount, 4);
});

test('raw original actions, unknown actions, missing and extra fields are rejected', () => {
  const invalid = [
    ['HpChange', { target: 'elsa', deltaValue: -1, finalValue: 99 }],
    { type: 'RoundBegin' }, { ...change(), skillInfo: {} },
    { type: 'HpChange', targetId: 'elsa', finalValue: int('1') },
    group('g', [], 'MadeUpKind'),
    sync({ ...snapshot(), propertiesInfo: {} }),
  ];
  for (const action of invalid) assert.throws(() => accept(start(), [action]), TypeError);
  const type = { toString() { throw Error('must not stringify untrusted value'); } };
  assert.throws(() => accept(start(), [{ type }]), /unsupported action type/);
});

test('normalized card instances are unique across piles and teams; card types may repeat', () => {
  const valid = snapshot('cards', [entity()], [team()]);
  assert.equal(view(createProjection(valid)).visibleState.teams[0].cards.length, 3);
  const crossPile = team(); crossPile.piles.discardPile = ['card-1'];
  assert.throws(() => createProjection(snapshot('bad', [], [crossPile])), /multiple piles/);
  const withinPile = team(); withinPile.piles.handPile.push('card-1');
  assert.throws(() => createProjection(snapshot('bad', [], [withinPile])), /duplicate card/);
  const otherTeam = { ...team(), id: 'team2' };
  assert.throws(() => createProjection(snapshot('bad', [], [team(), otherTeam])), /duplicate card ID/);
  const unknown = team(); unknown.piles.drawPile.push('unknown');
  assert.throws(() => createProjection(snapshot('bad', [], [unknown])), /unknown card/);
  // History need not be retained; registry may contain currently unassigned cards.
  const removed = snapshot('removed', [], [{ id: 'team1', cards: [], piles: piles() }]);
  assert.equal(view(accept(createProjection(valid), [sync(removed)])).receivedSnapshot.teams[0].cards.length, 0);
});

test('duplicate entity IDs, team IDs and non-normalized IDs are rejected', () => {
  assert.throws(() => createProjection(snapshot('bad', [entity(), entity()])), /duplicate entity/);
  const a = { id: 'same', cards: [], piles: piles() };
  assert.throws(() => createProjection(snapshot('bad', [], [a,a])), /duplicate team/);
  for (const id of ['', ' space', 'with/slash', 1, 'x'.repeat(129)]) {
    assert.throws(() => createProjection(snapshot(id)), TypeError);
    assert.throws(() => accept(start(), [change()], id), TypeError);
  }
});

test('integer payloads preserve values above 2^53 without Number or BigInt arithmetic', () => {
  const huge = '9'.repeat(300), final = '-' + huge;
  const initial = createProjection(snapshot('large', [entity('elsa', huge)]));
  const played = playNext(accept(initial, [change('HpChange', final, '1')]));
  assert.equal(played.events[0].previousValue.decimal, huge);
  assert.equal(played.events[0].finalValue.decimal, final);
  assert.deepEqual(JSON.parse(JSON.stringify(view(played.projection))), view(played.projection));
  for (const invalid of [1, 9007199254740992, '+1', '-0', '01', '1.0', '1e3', '', '1'.repeat(LIMITS.integerDigits + 1)]) {
    assert.throws(() => int(invalid), TypeError);
  }
});

test('binary64 tags preserve signed zero and check decimal/hex agreement', () => {
  assert.deepEqual(float(-0), { numeric_type: 'binary64', decimal: '-0.0', hex: '-0x0.0p+0' });
  const initial = snapshot(); initial.entities[0].hp = float(1.5);
  const action = { ...change(), finalValue: float(-0), deltaValue: float(-1.5) };
  const played = playNext(accept(createProjection(initial), [action]));
  assert.equal(played.events[0].finalValue.hex, '-0x0.0p+0');
  for (const n of [0, -0, Number.MIN_VALUE, Number.MAX_VALUE, 0.1, -1.25]) {
    const e = entity(); e.hp = float(n);
    assert.deepEqual(view(createProjection(snapshot('float', [e]))).visibleState.entities[0].hp, float(n));
  }
  for (const n of [NaN, Infinity, -Infinity, '1']) assert.throws(() => float(n), TypeError);
  const invalid = { numeric_type: 'binary64', decimal: '1.0', hex: '0x0.0p+0' };
  assert.throws(() => accept(start(), [{ ...change(), finalValue: invalid }]), /inconsistent/);
  assert.throws(() => accept(start(), [{ ...change(), finalValue: 1 }]), /tagged/);
});

test('sparse, custom, accessor and cyclic DTOs are rejected without calling accessors', () => {
  let calls = 0;
  const action = change(); Object.defineProperty(action, 'finalValue', { get() { ++calls; return int('0'); } });
  assert.throws(() => accept(start(), [action]), /accessors/);
  const numbers = { decimal: '1', get numeric_type() { ++calls; return 'integer'; } };
  assert.throws(() => accept(start(), [{ ...change(), finalValue: numbers }]), /data field/);
  const sparse = new Array(1); assert.throws(() => accept(start(), sparse), /sparse/);
  const getterArray = [change()]; Object.defineProperty(getterArray, '0', { get() { ++calls; return change(); } });
  assert.throws(() => accept(start(), getterArray), /accessor/);
  class CustomArray extends Array { map() { ++calls; return []; } }
  assert.throws(() => accept(start(), new CustomArray()), /plain array/);
  const actions = []; actions.push(group('cycle', actions));
  assert.throws(() => accept(start(), actions), /cyclic/);
  assert.equal(calls, 0);
});

test('explicit nesting and action budgets reject oversize batches atomically', () => {
  let actions = [];
  for (let n = 0; n <= LIMITS.groupDepth; ++n) actions = [group('g' + n, actions)];
  assert.throws(() => accept(start(), actions), /nesting budget/);
  assert.throws(() => accept(start(), Array.from({ length: LIMITS.batchActions + 1 }, () => change())), /bounded/);
  const nestedCount = [group('g', Array.from({ length: LIMITS.batchActions }, () => change()))];
  assert.throws(() => accept(start(), nestedCount), /action budget/);
});

test('playback chunking is deterministic and snapshot receive inside a group stays separate', () => {
  const received = receiveBatch(start(), batch([group('g', [change(), sync(snapshot('settled')), change('ShieldChange', '7')])]));
  assert.deepEqual(received.receipts[0].actionPath, [0,1]);
  assert.equal(view(received.projection).receivedSnapshot.snapshotId, 'settled');
  assert.equal(view(received.projection).visibleState.snapshotId, 'initial');
  const full = playAll(received.projection);
  let current = received.projection; const events = [];
  while (view(current).pendingCount) {
    const next = playNext(current); events.push(...next.events); current = next.projection;
  }
  assert.deepEqual(events, full.events);
  assert.deepEqual(view(current), view(full.projection));
});

test('runtime has no Node or BigInt requirement for projection, including huge integer tags', () => {
  const code = readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
  // Trusted local module source evaluated in an isolated test realm, never APK code.
  const script = code.replace(/^export /gm, '') + `
    const p = createProjection({ snapshotId: 's', entities: [{ id: 'e', hp: integerValue('9007199254740993'), shield: binary64Value(-0) }], teams: [] });
    const q = receiveBatch(p, { batchId: 'b', actions: [{ type: 'HpChange', targetId: 'e', deltaValue: integerValue('-1'), finalValue: integerValue('9007199254740992') }] });
    inspectProjection(playNext(q.projection).projection).visibleState.entities[0].hp.decimal;
  `;
  assert.equal(vm.runInNewContext(script, { BigInt: undefined }, { timeout: 1000 }), '9007199254740992');
});
