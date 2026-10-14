// Independent controller/HTTP/SQLite checks. No Cocos engine, UI, or preview process.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { DatabaseSync } from 'node:sqlite';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, relative, join, dirname, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { createApp } from '../server/src/app.js';
import { readCocosTestBuild } from './load_cocos_test_module.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const { values } = parseArgs({ options: { report: { type: 'string', default: 'analysis/test/tutorial-client/evidence.json' }, compiled: { type: 'boolean', default: false } } });
if(values.compiled && values.report==='analysis/test/tutorial-client/evidence.json') values.report='analysis/test/tutorial-client/creator-evidence.json';
const reportPath = resolve(root, values.report);
const evidenceRoot = resolve(root, 'analysis/test');
const reportRelative = relative(evidenceRoot, reportPath);
assert.ok(reportRelative && !reportRelative.startsWith(`..${sep}`) && reportRelative !== '..' && !/^[A-Za-z]:/.test(reportRelative), 'report must stay inside analysis/test');
const controllerPath = resolve(root, 'clients/cocos-poc/assets/TutorialBattleController.ts');
const compilerPath = resolve(root, '.tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/typescript.js');
const hash = value => createHash('sha256').update(value).digest('hex');
const clone = value => JSON.parse(JSON.stringify(value));
const evidence = {
  kind: 'tutorial-controller-http-sqlite-verification', startedAt: new Date().toISOString(),
  node: process.version, compilerVersion: null, controllerSourceSha256: null,
  scope: 'Single TS module transpilation; controller state machine in Node; actual loopback HTTP and independent read-only SQLite connections.',
  uiVerified: false, browserVerified: false, nativeRuntimeVerified: false,
  originalGameFidelityVerified: false, tests: [], ownedServices: [], cleanupComplete: false,
};
const temporaryPaths = new Set();
const pendingGates = new Set();
let TutorialBattleController, BattleRequestError;
let nextRequestId = 0;

async function temporary(prefix) {
  const path = await mkdtemp(join(tmpdir(), prefix));
  const parent = resolve(tmpdir());
  assert.ok(resolve(path).startsWith(parent + sep), 'temporary directory escaped OS temp');
  temporaryPaths.add(path);
  return path;
}
async function removeTemporary(path) {
  assert.ok(temporaryPaths.has(path), 'only owned temporary paths may be removed');
  assert.ok(resolve(path).startsWith(resolve(tmpdir()) + sep), 'cleanup target escaped OS temp');
  await rm(path, { recursive: true, force: true });
  temporaryPaths.delete(path);
}
function deferred() {
  let resolvePromise, reject;
  const promise = new Promise((yes, no) => { resolvePromise = yes; reject = no; });
  const gate = { promise, resolve(value) { pendingGates.delete(gate); resolvePromise(value); }, reject };
  pendingGates.add(gate);
  return gate;
}
async function bounded(promise, label, milliseconds = 10000) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out: ${label}`)), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}
function compactBattle(battle) {
  if (!battle) return null;
  return clone({ id: battle.id, profileId: battle.profileId, definitionId: battle.state.definitionId, revision: battle.revision, status: battle.state.status,
    round: battle.state.round, energy: battle.state.energy, playerHp: battle.state.player.hp,
    enemyHp: battle.state.enemy.hp, hand: battle.state.piles.hand, actionIndex: battle.state.actionIndex,
    stateSha256: hash(JSON.stringify(battle.state)) });
}
function playable(battle) {
  return battle.state.piles.hand.map(instanceId => {
    const entry = battle.state.cards.find(card => card.instanceId === instanceId);
    const card = battle.scenario.definition.cards[entry.cardId];
    return { instanceId, cost: card.cost, damage: card.effects.filter(effect => effect.type === 'damage').reduce((sum, effect) => sum + Number(effect.amount), 0) };
  }).filter(card => card.cost <= battle.state.energy).sort((a, b) => b.damage / Math.max(1, b.cost) - a.damage / Math.max(1, a.cost))[0]?.instanceId;
}
function assertMatchesSqlite(rig, battle) {
  const db = new DatabaseSync(rig.battleSavePath, { readOnly: true });
  try {
    const row = db.prepare('SELECT revision, state_json FROM battles WHERE id = ? AND profile_id = ?').get(battle.id, battle.profileId);
    assert.ok(row, 'battle exists in the independent SQLite connection');
    assert.equal(battle.revision, row.revision);
    assert.deepEqual(battle.state, JSON.parse(row.state_json));
    return {
      ...compactBattle(battle),
      commandCount: db.prepare('SELECT count(*) AS n FROM battle_commands WHERE battle_id = ?').get(battle.id).n,
      creationCount: db.prepare('SELECT count(*) AS n FROM battle_creations WHERE profile_id = ?').get(battle.profileId).n,
      battleCount: db.prepare('SELECT count(*) AS n FROM battles WHERE profile_id = ?').get(battle.profileId).n,
    };
  } finally { db.close(); }
}

async function withRig(operation) {
  const directory = await temporary('hczs-controller-test-');
  const controllers = [], calls = [], serviceErrors = [];
  const savePath = join(directory, 'profiles.sqlite'), battleSavePath = join(directory, 'battles.sqlite');
  const options = { port: 0, savePath, battleSavePath, dataDirectory: resolve(root, 'analysis/game-data'),
    tutorialDirectory: resolve(root, 'analysis/first-encounter'), log: event => serviceErrors.push(event) };
  let app;
  try {
    app = await createApp(options);
    const serviceRecord = { address: app.address, closed: false };
    evidence.ownedServices.push(serviceRecord);
    const transport = async (method, path, body) => {
      const call = { method, path, ...(body === undefined ? {} : { body: clone(body) }) };
      calls.push(call);
      const response = await fetch(app.address + '/api/rebuild/v1' + path, { method,
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(5000) });
      const result = await response.json();
      call.status = response.status;
      if (result.battle) call.result = compactBattle(result.battle);
      if (typeof result.replayed === 'boolean') call.replayed = result.replayed;
      if (!response.ok) throw new BattleRequestError(response.status, result.error?.code ?? 'HTTP_ERROR', result.error?.message ?? 'HTTP error');
      return result;
    };
    const profile = (await transport('POST', '/profiles', { displayName: '控制器独立验证' })).profile;
    const rig = {
      profile, transport, calls, battleSavePath, directory,
      controller(customTransport = transport) {
        const changes = [];
        const controller = new TutorialBattleController(customTransport, snapshot => {
          changes.push({ phase: snapshot.phase, profileId: snapshot.profileId, pending: snapshot.pending, canRetry: snapshot.canRetry,
            battle: compactBattle(snapshot.battle), message: snapshot.message });
        }, () => `controller-test-${++nextRequestId}`);
        controllers.push(controller);
        return { controller, changes };
      },
      async latest(battleId, profileId = profile.id) {
        return (await transport('GET', `/profiles/${profileId}/battles/${battleId}`)).battle;
      },
      async act(battle, action) {
        return transport('POST', `/profiles/${battle.profileId}/battles/${battle.id}/actions`, {
          requestId: `independent-${++nextRequestId}`, expectedRevision: battle.revision, ...action,
        });
      },
      async reopen() {
        await app.close(); serviceRecord.closed = true;
        app = await createApp(options);
        const record = { address: app.address, closed: false };
        evidence.ownedServices.push(record);
      },
    };
    const detail = await bounded(operation(rig), 'test operation', 30000);
    assert.deepEqual(serviceErrors, [], 'no hidden server internal errors');
    return { ...detail, httpRequests: calls.length, writes: calls.filter(call => call.method === 'POST').map(call => ({ path: call.path, body: call.body,
      status: call.status, replayed: call.replayed, result: call.result })) };
  } finally {
    for (const controller of controllers) controller.dispose();
    for (const gate of [...pendingGates]) gate.resolve();
    if (app) {
      const address = app.address;
      await app.close();
      const record = evidence.ownedServices.find(item => item.address === address && !item.closed);
      if (record) record.closed = true;
    }
    await removeTemporary(directory);
  }
}

async function check(name, operation) {
  const start = performance.now();
  try {
    const detail = await withRig(operation);
    evidence.tests.push({ name, status: 'passed', durationMs: Math.round(performance.now() - start), detail });
    console.log(`PASS ${name}`);
  } catch (error) {
    evidence.tests.push({ name, status: 'failed', durationMs: Math.round(performance.now() - start), error: String(error), stack: error.stack });
    console.error(`FAIL ${name}: ${error.message}`);
  }
}

async function openNew(rig, transport) {
  const result = rig.controller(transport);
  await result.controller.open(rig.profile.id);
  await result.controller.startNew();
  assert.equal(result.controller.snapshot.phase, 'ready');
  assert.ok(result.controller.snapshot.battle);
  return result;
}

async function tests() {
  await check('real creation, card play, turn end, controller/service restore and victory', async rig => {
    let { controller } = await openNew(rig);
    const initial = controller.snapshot.battle;
    const checkpoints = [assertMatchesSqlite(rig, initial)];
    await controller.play(playable(initial));
    assert.equal(controller.snapshot.battle.revision, initial.revision + 1);
    checkpoints.push(assertMatchesSqlite(rig, controller.snapshot.battle));
    await controller.endTurn();
    assert.equal(controller.snapshot.battle.state.round, 2);
    checkpoints.push(assertMatchesSqlite(rig, controller.snapshot.battle));
    const saved = clone(controller.snapshot.battle);
    controller.dispose();
    await rig.reopen();
    ({ controller } = rig.controller());
    await controller.open(rig.profile.id);
    assert.deepEqual(controller.snapshot.battle, saved);
    let actions = 0;
    while (controller.snapshot.battle.state.status === 'player-turn' && actions++ < 100) {
      const card = playable(controller.snapshot.battle);
      if (card) await controller.play(card); else await controller.endTurn();
      assert.equal(controller.snapshot.phase, 'ready');
      assertMatchesSqlite(rig, controller.snapshot.battle);
    }
    assert.equal(controller.snapshot.battle.state.status, 'won');
    checkpoints.push(assertMatchesSqlite(rig, controller.snapshot.battle));
    await controller.refresh();
    assert.deepEqual(controller.snapshot.battle, await rig.latest(saved.id));
    return { checkpoints, actionsAfterRestore: actions, restoreAcrossOwnedServiceReopen: true };
  });

  await check('creation committed but response lost retries identical request and creates only one battle', async rig => {
    let dropped = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (!dropped && method === 'POST' && path.endsWith('/battles')) {
        dropped = true; committed = value.battle;
        throw new BattleRequestError(0, 'NETWORK_ERROR', 'Injected response loss after SQLite commit');
      }
      return value;
    };
    const { controller } = rig.controller(transport);
    await controller.open(rig.profile.id);
    await controller.startNew();
    assert.equal(controller.snapshot.phase, 'uncertain');
    assert.equal(controller.snapshot.canRetry, true);
    const before = assertMatchesSqlite(rig, committed);
    const writes = rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/battles'));
    await controller.startNew();
    assert.equal(rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/battles')).length, 1, 'new creation is suppressed until uncertain request is resolved');
    await controller.retry();
    assert.equal(controller.snapshot.phase, 'ready');
    const sent = rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/battles'));
    assert.equal(sent.length, 2);
    assert.deepEqual(sent[1].body, writes[0].body);
    assert.equal(sent[1].replayed, true);
    assert.equal(controller.snapshot.battle.id, committed.id);
    const after = assertMatchesSqlite(rig, controller.snapshot.battle);
    assert.equal(after.battleCount, 1); assert.equal(after.creationCount, 1);
    return { before, after, sameRequestId: sent[0].body.requestId === sent[1].body.requestId };
  });

  await check('action committed but timed out remains locked and retry never charges twice', async rig => {
    let drop = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (drop && method === 'POST' && path.endsWith('/actions')) {
        drop = false; committed = value.battle;
        throw new BattleRequestError(0, 'TIMEOUT', 'Injected timeout after SQLite commit');
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    const initial = controller.snapshot.battle;
    drop = true;
    await controller.play(playable(initial));
    assert.equal(controller.snapshot.phase, 'uncertain');
    assert.equal(controller.snapshot.canRetry, true);
    const committedProof = assertMatchesSqlite(rig, committed);
    await controller.refresh();
    assert.equal(controller.snapshot.canRetry, true, 'GET state alone cannot prove the pending request receipt');
    await controller.endTurn();
    assert.equal(rig.calls.filter(call => call.path.endsWith('/actions')).length, 1);
    await controller.retry();
    assert.equal(controller.snapshot.phase, 'ready');
    assert.deepEqual(controller.snapshot.battle, committed);
    const after = assertMatchesSqlite(rig, controller.snapshot.battle);
    const writes = rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/actions'));
    assert.equal(writes.length, 2); assert.deepEqual(writes[1].body, writes[0].body);
    assert.equal(after.commandCount, 1);
    assert.equal(after.energy, committedProof.energy);
    assert.deepEqual(after.enemyHp, committedProof.enemyHp);
    return { before: compactBattle(initial), committed: committedProof, after, replayed: writes[1].replayed };
  });

  await check('409 from a second client reloads the committed revision without submitting another action', async rig => {
    const { controller } = await openNew(rig);
    const initial = controller.snapshot.battle;
    const other = (await rig.act(initial, { type: 'end-turn' })).battle;
    await controller.play(playable(initial));
    assert.ok(rig.calls.some(call => call.status === 409));
    await controller.refresh();
    assert.deepEqual(controller.snapshot.battle, other);
    const proof = assertMatchesSqlite(rig, controller.snapshot.battle);
    assert.equal(proof.commandCount, 1);
    assert.equal(controller.snapshot.canRetry, false);
    return { independentClientRevision: other.revision, refreshed: proof };
  });

  await check('uncertain writes survive leaving and reopening the profile with the original request ID', async rig => {
    let drop = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (drop && method === 'POST' && path.endsWith('/actions')) {
        drop = false; committed = value.battle;
        throw new BattleRequestError(0, 'NETWORK_ERROR', 'Uncertain write before profile switch');
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    drop = true;
    await controller.play(playable(controller.snapshot.battle));
    assert.equal(controller.snapshot.phase, 'uncertain');
    const other = (await rig.transport('POST', '/profiles', { displayName: '未知写入切换目标' })).profile;
    await controller.open(other.id);
    assert.equal(controller.snapshot.battle, null);
    await controller.open(rig.profile.id);
    assert.equal(controller.snapshot.phase, 'uncertain');
    assert.equal(controller.snapshot.canRetry, true);
    await controller.retry();
    const writes = rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/actions'));
    assert.equal(writes.length, 2); assert.deepEqual(writes[0].body, writes[1].body);
    assert.equal(writes[1].replayed, true);
    assert.equal(controller.snapshot.phase, 'ready');
    assert.deepEqual(controller.snapshot.battle, committed);
    const proof = assertMatchesSqlite(rig, committed);
    assert.equal(proof.commandCount, 1);
    return { restored: proof, requestId: writes[0].body.requestId };
  });

  await check('acknowledged write with failed confirmation GET unlocks by refreshing without another POST', async rig => {
    let breakConfirmation = false, waiting = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (breakConfirmation && method === 'POST' && path.endsWith('/actions')) {
        committed = value.battle; waiting = true;
      } else if (waiting && method === 'GET' && value.battle) {
        waiting = false; breakConfirmation = false;
        throw new BattleRequestError(0, 'TIMEOUT', 'Receipt received but confirmation GET lost');
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    breakConfirmation = true;
    await controller.play(playable(controller.snapshot.battle));
    assert.equal(controller.snapshot.phase, 'uncertain');
    assert.equal(controller.snapshot.canRetry, true);
    const callIndex = rig.calls.length;
    await controller.refresh();
    assert.equal(controller.snapshot.phase, 'ready');
    assert.equal(controller.snapshot.canRetry, false);
    assert.deepEqual(controller.snapshot.battle, committed);
    assert.ok(rig.calls.slice(callIndex).length > 0);
    assert.ok(rig.calls.slice(callIndex).every(call => call.method === 'GET'));
    assert.equal(rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/actions')).length, 1);
    const proof = assertMatchesSqlite(rig, committed);
    assert.equal(proof.commandCount, 1);
    return { reconciled: proof, reconciliationMethods: rig.calls.slice(callIndex).map(call => call.method) };
  });

  await check('an old idempotent receipt cannot roll back a newer fetched state', async rig => {
    let drop = false, receipt;
    const transport = async (method, path, body) => {
      const result = await rig.transport(method, path, body);
      if (drop && method === 'POST' && path.endsWith('/actions')) {
        drop = false; receipt = result;
        throw new BattleRequestError(0, 'NETWORK_ERROR', 'Drop old command receipt');
      }
      return result;
    };
    const { controller, changes } = await openNew(rig, transport);
    drop = true;
    await controller.play(playable(controller.snapshot.battle));
    const newer = (await rig.act(receipt.battle, { type: 'end-turn' })).battle;
    await controller.refresh();
    assert.equal(controller.snapshot.battle.revision, newer.revision);
    const index = changes.length;
    await controller.retry();
    assert.equal(controller.snapshot.phase, 'ready');
    assert.deepEqual(controller.snapshot.battle, newer);
    for (const change of changes.slice(index)) if (change.battle) assert.ok(change.battle.revision >= newer.revision, 'even transient callbacks cannot expose the old receipt revision');
    return { receiptRevision: receipt.battle.revision, final: assertMatchesSqlite(rig, controller.snapshot.battle), retryCallbacks: changes.slice(index) };
  });

  await check('duplicate play and end-turn clicks while transport is pending emit one write', async rig => {
    const gate = deferred(), entered = deferred();
    let hold = false;
    const transport = async (method, path, body) => {
      if (hold && method === 'POST' && path.endsWith('/actions')) {
        hold = false; entered.resolve(); await gate.promise;
      }
      return rig.transport(method, path, body);
    };
    const { controller } = await openNew(rig, transport);
    const card = playable(controller.snapshot.battle);
    hold = true;
    const first = controller.play(card);
    await bounded(entered.promise, 'write entered transport');
    assert.equal(controller.snapshot.pending, true);
    try { await controller.play(card); await controller.endTurn(); }
    finally { gate.resolve(); }
    await first;
    const writes = rig.calls.filter(call => call.method === 'POST' && call.path.endsWith('/actions'));
    assert.equal(writes.length, 1);
    return { committed: assertMatchesSqlite(rig, controller.snapshot.battle), writeCount: writes.length };
  });

  await check('delayed GET from a previous open cannot roll back a newer open of the same profile', async rig => {
    const gate = deferred(), entered = deferred();
    let hold = false, captured;
    const transport = async (method, path, body) => {
      const result = await rig.transport(method, path, body);
      if (hold && method === 'GET' && result.battle) {
        hold = false; captured = result.battle; entered.resolve(); await gate.promise;
      }
      return result;
    };
    const { controller, changes } = await openNew(rig, transport);
    hold = true;
    const oldRefresh = controller.refresh();
    await bounded(entered.promise, 'GET captured');
    const newer = (await rig.act(captured, { type: 'end-turn' })).battle;
    try { await controller.open(rig.profile.id); }
    finally { gate.resolve(); }
    await oldRefresh;
    assert.deepEqual(controller.snapshot.battle, newer);
    const firstNewer = changes.findIndex(change => change.battle?.revision === newer.revision);
    assert.ok(firstNewer >= 0);
    for (const change of changes.slice(firstNewer)) if (change.battle) assert.ok(change.battle.revision >= newer.revision);
    return { delayedRevision: captured.revision, final: assertMatchesSqlite(rig, controller.snapshot.battle) };
  });

  await check('profile switch fences old write response; returning can reconcile that profile', async rig => {
    const gate = deferred(), entered = deferred();
    let hold = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (hold && method === 'POST' && path.endsWith('/actions')) {
        hold = false; committed = value.battle; entered.resolve(); await gate.promise;
      }
      return value;
    };
    const { controller, changes } = await openNew(rig, transport);
    const other = (await rig.transport('POST', '/profiles', { displayName: '切换目标档案' })).profile;
    hold = true;
    const writing = controller.play(playable(controller.snapshot.battle));
    await bounded(entered.promise, 'profile-switch write committed');
    let afterSwitch;
    try { await controller.open(other.id); afterSwitch = changes.length; }
    finally { gate.resolve(); }
    await writing;
    assert.equal(controller.snapshot.profileId, other.id);
    assert.equal(controller.snapshot.battle, null);
    for (const change of changes.slice(afterSwitch)) assert.ok(!change.battle || change.battle.profileId === other.id);
    await controller.open(rig.profile.id);
    if (controller.snapshot.canRetry) await controller.retry();
    await controller.refresh();
    assert.deepEqual(controller.snapshot.battle, committed);
    return { otherProfileId: other.id, restored: assertMatchesSqlite(rig, controller.snapshot.battle) };
  });

  await check('dispose fences a delayed server response and future controller calls', async rig => {
    const gate = deferred(), entered = deferred();
    let hold = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (hold && method === 'POST' && path.endsWith('/actions')) {
        hold = false; committed = value.battle; entered.resolve(); await gate.promise;
      }
      return value;
    };
    const { controller, changes } = await openNew(rig, transport);
    hold = true;
    const writing = controller.endTurn();
    await bounded(entered.promise, 'disposed write committed');
    controller.dispose();
    const changeCount = changes.length, state = clone(controller.snapshot), callCount = rig.calls.length;
    gate.resolve(); await writing;
    await controller.refresh(); await controller.startNew(); await controller.retry();
    assert.equal(changes.length, changeCount);
    assert.deepEqual(controller.snapshot, state);
    assert.equal(rig.calls.length, callCount);
    return { callbacksAfterDispose: changes.length - changeCount, committed: assertMatchesSqlite(rig, committed) };
  });

  await check('malformed read and committed-write responses produce controlled errors and preserve known state', async rig => {
    let malformedRead = false, malformedWrite = false, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (malformedRead && method === 'GET' && value.battle) { malformedRead = false; return { battle: { id: 7 } }; }
      if (malformedWrite && method === 'POST' && path.endsWith('/actions')) {
        malformedWrite = false; committed = value.battle; return { battle: null, events: 'bad' };
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    const initial = clone(controller.snapshot.battle);
    malformedRead = true;
    await controller.refresh();
    assert.ok(['error', 'ready'].includes(controller.snapshot.phase));
    assert.ok(controller.snapshot.message.length > 0);
    assert.deepEqual(controller.snapshot.battle, initial);
    await controller.refresh();
    malformedWrite = true;
    await controller.play(playable(controller.snapshot.battle));
    assert.equal(controller.snapshot.phase, 'uncertain');
    assert.equal(controller.snapshot.canRetry, true);
    await controller.retry();
    assert.equal(controller.snapshot.phase, 'ready');
    assert.deepEqual(controller.snapshot.battle, committed);
    const proof = assertMatchesSqlite(rig, committed);
    assert.equal(proof.commandCount, 1);
    return { prior: compactBattle(initial), recovered: proof };
  });

  await check('malformed binary64 tags cannot replace a previously verified battle snapshot', async rig => {
    let mutate = null;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (mutate && method === 'GET' && value.battle) {
        const copy = clone(value); mutate(copy.battle.state.player.hp); mutate = null; return copy;
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    const expected = clone(controller.snapshot.battle);
    const mutations = [
      ['empty decimal', tag => { tag.decimal = ''; }],
      ['whitespace decimal', tag => { tag.decimal = ' '; }],
      ['negative health', tag => { tag.decimal = '-1.0'; tag.hex = '-0x1.0000000000000p+0'; }],
      ['decimal/hex mismatch', tag => { tag.decimal = '1.0'; }],
    ];
    for (const [label, change] of mutations) {
      mutate = change;
      await controller.refresh();
      assert.equal(controller.snapshot.phase, 'error', label);
      assert.deepEqual(controller.snapshot.battle, expected, label);
      assert.ok(controller.snapshot.message.length > 0);
      await controller.refresh();
      assert.equal(controller.snapshot.phase, 'ready');
    }
    return { rejectedForms: mutations.map(([label]) => label), preserved: assertMatchesSqlite(rig, expected) };
  });

  await check('malformed effect amounts, kinds and enemy intentions never reach a ready view', async rig => {
    let mutate = null;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (mutate && method === 'GET' && value.battle) {
        const copy = clone(value); mutate(copy.battle.scenario.definition); mutate = null; return copy;
      }
      return value;
    };
    const { controller } = await openNew(rig, transport);
    const expected = clone(controller.snapshot.battle);
    const mutations = [
      ['player effect amount', definition => { definition.cards['110001'].effects[0].amount = 'NaN'; }],
      ['player effect kind', definition => { definition.cards['110001'].effects[0].type = 'unknown-effect'; }],
      ['enemy effect amount', definition => { definition.enemySkills['990'].effects[0].amount = ''; }],
      ['missing intention skill', definition => { definition.enemyIntents[0] = ['unknown-skill']; }],
      ['malformed intention list', definition => { definition.enemyIntents[0] = '990'; }],
    ];
    for (const [label, change] of mutations) {
      mutate = change; await controller.refresh();
      assert.equal(controller.snapshot.phase, 'error', label);
      assert.deepEqual(controller.snapshot.battle, expected, label);
      await controller.refresh();
      assert.equal(controller.snapshot.phase, 'ready');
    }
    return { rejectedForms: mutations.map(([label]) => label), preserved: assertMatchesSqlite(rig, expected) };
  });

  await check('malformed presentation events after real commit remain retryable without duplicate effects', async rig => {
    let replacement = null, committed;
    const transport = async (method, path, body) => {
      const value = await rig.transport(method, path, body);
      if (replacement && method === 'POST' && path.endsWith('/actions')) {
        committed = value.battle;
        const copy = clone(value); copy.events = [replacement]; replacement = null; return copy;
      }
      return value;
    };
    const { controller } = rig.controller(transport);
    await controller.open(rig.profile.id);
    const invalidEvents = [
      { type: 'EnergyChanged', previousValue: 5, finalValue: 'bad' },
      { type: 'CardPlayed', instanceId: 'tutorial-card-1', cardId: '410101', cost: -1 },
      { type: 'TurnStarted', round: 'two' },
      { type: 'UnknownEvent' },
    ];
    const checks = [];
    for (const event of invalidEvents) {
      const profile = (await rig.transport('POST', '/profiles', { displayName: `事件校验 ${event.type}` })).profile;
      await controller.open(profile.id);
      await controller.startNew();
      const initial = clone(controller.snapshot.battle);
      replacement = event;
      await controller.play(playable(initial));
      assert.equal(controller.snapshot.phase, 'uncertain', event.type);
      assert.equal(controller.snapshot.canRetry, true, event.type);
      assert.deepEqual(controller.snapshot.battle, initial, event.type);
      await controller.retry();
      assert.equal(controller.snapshot.phase, 'ready', event.type);
      assert.deepEqual(controller.snapshot.battle, committed, event.type);
      const proof = assertMatchesSqlite(rig, committed);
      assert.equal(proof.commandCount, 1, event.type);
      checks.push({ rejectedEventType: event.type, result: proof });
    }
    return { cases: checks };
  });
}

try {
  const ts = createRequire(import.meta.url)(compilerPath);
  assert.equal(ts.version, '5.8.2', 'use the inspected Creator TypeScript compiler');
  evidence.compilerVersion = ts.version;
  evidence.sourceHashes = {};
  for (const file of ['tools/test_tutorial_client.mjs', 'tools/load_cocos_test_module.mjs', 'server/src/app.js', 'server/src/battles.js', 'server/src/tutorial.js', 'server/data/tutorial-policy.json']) {
    evidence.sourceHashes[file] = hash(await readFile(resolve(root, file)));
  }
  const source = await readFile(controllerPath, 'utf8');
  evidence.controllerSourceSha256 = hash(source);
  const template = await readFile(resolve(root, 'tools/templates/cocos-tutorial-battle-controller.ts'), 'utf8');
  evidence.templateSourceSha256 = hash(template);
  assert.equal(template, source, 'reproducible template and tested controller must match');
  if(values.compiled) {
    const build=await readCocosTestBuild();
    evidence.buildInputs=build.buildInputs;
    evidence.scope='Actual Creator Web System.register module in Node; mock cc registration only; actual loopback HTTP and independent SQLite reads. Not browser/native execution.';
    evidence.kind='creator-controller-http-sqlite-verification';
    ({TutorialBattleController,BattleRequestError}=build.load('TutorialBattleController.ts',{cclegacy:{_RF:{push(){},pop(){}}}}));
  } else {
  const compiled = ts.transpileModule(source, { fileName: controllerPath, reportDiagnostics: true, compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022, isolatedModules: true, strict: true,
  } });
  const errors = (compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(errors.map(item => ts.flattenDiagnosticMessageText(item.messageText, '\n')), [], 'transpile diagnostics');
  const directory = await temporary('hczs-controller-module-');
  const path = join(directory, 'TutorialBattleController.mjs');
  await writeFile(path, compiled.outputText);
  evidence.compiledModuleSha256 = hash(compiled.outputText);
  ({ TutorialBattleController, BattleRequestError } = await import(pathToFileURL(path).href));
  }
  assert.equal(typeof TutorialBattleController, 'function');
  assert.equal(typeof BattleRequestError, 'function');
  await tests();
  assert.equal(hash(await readFile(controllerPath)), evidence.controllerSourceSha256, 'controller changed during the test run; rerun the final source');
  for (const [file, expected] of Object.entries(evidence.sourceHashes)) {
    assert.equal(hash(await readFile(resolve(root, file))), expected, `${file} changed during the test run; rerun final sources`);
  }
} catch (error) {
  evidence.tests.push({ name: 'test bootstrap', status: 'failed', error: String(error), stack: error.stack });
  console.error(error.stack);
} finally {
  for (const path of [...temporaryPaths]) await removeTemporary(path);
  evidence.cleanupComplete = temporaryPaths.size === 0 && evidence.ownedServices.every(item => item.closed);
  evidence.finishedAt = new Date().toISOString();
  evidence.summary = { passed: evidence.tests.filter(item => item.status === 'passed').length,
    failed: evidence.tests.filter(item => item.status === 'failed').length, total: evidence.tests.length };
  await mkdir(dirname(reportPath), { recursive: true });
  await writeFile(reportPath, JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify({ ...evidence.summary, cleanupComplete: evidence.cleanupComplete, report: relative(root, reportPath) }));
  if (evidence.summary.failed || !evidence.cleanupComplete) process.exitCode = 1;
}
