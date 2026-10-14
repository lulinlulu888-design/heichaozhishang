// Pure controller + real session integration. Transport is synthetic, not HTTP/UI.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createBattle, endTurn, playCard } from '../packages/battle-session/src/index.js';
import { int, toTagged } from '../packages/battle-core/src/index.js';
import { readCocosTestBuild } from './load_cocos_test_module.mjs';
const source = await readFile(new URL('../clients/cocos-poc/assets/TutorialBattleController.ts', import.meta.url), 'utf8');
assert.equal(source, await readFile(new URL('./templates/cocos-tutorial-battle-controller.ts', import.meta.url), 'utf8'));
const ts = createRequire(import.meta.url)('../.tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/typescript.js');
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } });
const useCreator = process.argv.includes('--compiled');
let TutorialBattleController;
if (useCreator) {
  const build = await readCocosTestBuild();
  ({ TutorialBattleController } = build.load('TutorialBattleController.ts', { cclegacy: { _RF: { push() {}, pop() {} } } }));
} else {
  ({ TutorialBattleController } = await import('data:text/javascript;base64,' + Buffer.from(compiled.outputText).toString('base64')));
}
const hp = n => toTagged(int(n)), clone = x => JSON.parse(JSON.stringify(x));
const definition = {
  id: 'status-client-test', player: { id: 'p', name: 'P', maxHp: hp(100) }, enemy: { id: 'e', name: 'E', maxHp: hp(100) },
  statusRules: { policy: 'breakdown-reconstruction-v1', attack: { player: hp(101), enemy: hp(101) } },
  deck: [{ instanceId: 'h', cardId: 'h' }], cards: { h: { name: 'Heal', cost: 0, effects: [{ type: 'heal', target: 'self', amount: '10' }] } },
  enemySkills: { apply: { effects: [{ type: 'breakdown', target: 'opponent', stacks: 2 }] }, wait: { effects: [] } },
  enemyIntents: [['apply']], enemyFallback: ['wait'], initialDraw: 1, roundDraw: 1, energyPerRound: 1, handLimit: 1, maxRounds: 10,
};
const profileId = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa', id = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb';
const initial = { id, profileId, revision: 1, createdAt: 1, updatedAt: 1,
  scenario: { title: 'Synthetic', notice: 'Reconstruction test', definition }, state: createBattle(definition, 1).state };
let record = clone(initial), corrupt = null, badEvent = false, sequence = 0;
const controller = new TutorialBattleController(async (method, path, body) => {
  if (method === 'GET') {
    if (path.endsWith('/battles')) return { battles: [{ ...record, status: record.state.status }] };
    const copy = clone(record); if (corrupt) corrupt(copy); return { battle: copy };
  }
  const result = body.type === 'end-turn' ? endTurn(definition, record.state) : playCard(definition, record.state, body.instanceId);
  record = { ...record, revision: record.revision + 1, state: result.state };
  const events = clone(result.events);
  if (badEvent) events.unshift({ type: 'BreakdownChanged', actor: 'enemy', target: 'player', previousStacks: 2, finalStacks: 1000, reason: 'applied' });
  return { battle: record, events, replayed: false };
}, () => {}, () => `test-${++sequence}`);
await controller.open(profileId); assert.equal(controller.snapshot.phase, 'ready');
await controller.endTurn(); assert.equal(controller.snapshot.battle.state.breakdown.player, 2);
assert.ok(controller.snapshot.events.some(e => e.type === 'BreakdownChanged'));
await controller.endTurn(); assert.equal(controller.snapshot.battle.state.player.hp.decimal, '60');
assert.ok(controller.snapshot.events.some(e => e.type === 'BreakdownTriggered'));
await controller.play('h'); assert.equal(controller.snapshot.phase, 'ready');
assert.equal(controller.snapshot.battle.state.player.hp.decimal, '70');
assert.equal(controller.snapshot.battle.state.breakdown.player, 1);
assert.ok(controller.snapshot.events.some(e => e.type === 'HealthRestored'));
const stable = controller.snapshot.battle;
const mutations = [
  b => { b.state.breakdown.player = 1000; }, b => { delete b.state.breakdown; },
  b => { b.state.format = 'hczs-battle-session-v1'; },
  b => { b.scenario.definition.statusRules.policy = 'original'; },
  b => { b.scenario.definition.statusRules.attack.enemy.decimal = '-1'; },
  b => { b.scenario.definition.enemySkills.apply.effects[0].target = 'self'; },
];
for (const mutate of mutations) {
  corrupt = mutate; await controller.refresh();
  assert.equal(controller.snapshot.phase, 'error'); assert.deepEqual(controller.snapshot.battle, stable);
}
corrupt = null; await controller.refresh(); assert.equal(controller.snapshot.phase, 'ready');
badEvent = true; await controller.endTurn();
assert.equal(controller.snapshot.phase, 'uncertain'); assert.deepEqual(controller.snapshot.battle, stable);
controller.dispose();
const report = { evidence: `${useCreator ? 'Actual Creator Web module' : 'Transpiled TS controller'} + real session with synthetic transport; not HTTP, browser or native`,
  controllerSha256: createHash('sha256').update(source).digest('hex'),
  checks: ['v2 read', 'status application', 'tick', 'healing and decrement', 'invalid read retention (6)', 'invalid committed event remains uncertain'],
  passed: true, uiVerified: false };
const out = new URL('../analysis/test/status-client/', import.meta.url);
await mkdir(out, { recursive: true }); await writeFile(new URL(useCreator ? 'creator-evidence.json' : 'evidence.json', out), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report));
