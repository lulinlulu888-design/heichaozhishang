import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { loadTutorialScenario } from '../src/tutorial.js';
import { loadCityScenario } from '../src/city-scenario.js';
import { BattleStore } from '../src/battles.js';
import { createApp } from '../src/app.js';
import { createBattle, playCard } from '../../packages/battle-session/src/index.js';
import { fixture, request } from './helpers.js';

test('pinned city skills preserve double hit, shield, decomposition and explicit policy', async () => {
  const base = await loadTutorialScenario(), city = await loadCityScenario(base), d = city.definition;
  assert.equal(d.enemy.maxHp.decimal, '6041.0');
  assert.equal(city.provenance.monsterAttack.decimal, '422.0');
  assert.equal(city.provenance.originalScenarioRecovered, false);
  assert.deepEqual(d.enemySkills['66051'].effects, Array.from({length:2}, () => ({type:'damage',target:'opponent',amount:'379'})));
  assert.deepEqual(d.enemySkills['66052'].effects, [{type:'damage',target:'opponent',amount:'253'}]);
  assert.deepEqual(d.enemySkills['66053'].effects, [{type:'shield',target:'self',amount:'906'}]);
  assert.deepEqual(d.enemySkills['66054'].effects, [{type:'breakdown',target:'opponent',stacks:2}]);
  assert.deepEqual(d.enemyIntents.slice(0,5), [['66054'],['66053'],['66051'],['66054'],['66051']]);
  assert.deepEqual(city.policies.enemySelection.pool, [
    {skillId:'66051',weight:45},{skillId:'66052',weight:35},{skillId:'66053',weight:20}]);
  assert.equal(base.definition.enemy.id, '991');
  assert.equal(base.definition.ultimateRules, undefined, 'tutorial 5000 retains its source DisableSpecialSkill gate');
  assert.equal(d.ultimateRules.policy, 'elsa-combo-reconstruction-v1');
  assert.deepEqual(d.cards['410104'].effects.map(effect => effect.amount), ['72','72','144','144','144','289','289','289']);
  assert.deepEqual(city.provenance.ultimate.calculations.slice(0,8).map(row => row.percentage), [15,15,30,30,30,60,60,60]);
  assert.deepEqual(city.provenance.ultimate.calculations[8], {stateId:379,operation:'energyadd',amount:0,disposition:'no-op'});
  assert.equal(city.provenance.ultimate.originalServerRecovered, false);
  assert.equal((await loadCityScenario(base)).definition.id, d.id);
});

test('real city state applies breakdown then double hit, and survives SQLite reopening/retry', async t => {
  const files = await fixture(t), profile = randomUUID();
  const scenario = await loadCityScenario(await loadTutorialScenario());
  let store = new BattleStore(files.savePath); files.cleanupWith(() => store.close());
  const initial = store.create(profile, scenario, {requestId:'city-start',seed:2}).battle;
  const first = store.act(profile, initial.id, {requestId:'turn1',expectedRevision:1,type:'end-turn'});
  assert.equal(first.battle.state.breakdown.player, 2);
  const command = {requestId:'turn2',expectedRevision:2,type:'end-turn'};
  const second = store.act(profile, initial.id, command);
  assert.deepEqual(second.events.filter(e => e.type === 'DamageApplied').map(e => e.amount), ['168','379','379']);
  store.close(); store = new BattleStore(files.savePath);
  assert.deepEqual(store.get(profile, initial.id), second.battle);
  const replay = store.act(profile, initial.id, command);
  assert.equal(replay.replayed,true);
  assert.deepEqual(replay.events,second.events);
});

test('city HTTP opt-in exposes its own scenario and rejects conflicting modes', async t => {
  const files = await fixture(t), tutorialDirectory = fileURLToPath(new URL('../../analysis/first-encounter/',import.meta.url));
  const options = {...files,tutorialDirectory,cityPreview:true,port:0,log:()=>{}};
  const app = await createApp(options); files.cleanupWith(() => app.close());
  const response = await request(app.address,'/tutorial');
  assert.equal(response.status,200); assert.equal(response.body.definition.enemy.id,'6605');
  assert.equal(response.body.policies.level,40);
  await assert.rejects(createApp({...options,customScenarioPath:'unused.json'}),/cannot combine/);
});

test('city can be won using actual card commands and restores its terminal save', async t => {
  const files = await fixture(t), profile = randomUUID();
  const scenario = await loadCityScenario(await loadTutorialScenario()), d = scenario.definition;
  let store = new BattleStore(files.savePath); files.cleanupWith(() => store.close());
  let battle = store.create(profile, scenario, {requestId:'start',seed:3}).battle;
  for (let i=0;i<100 && battle.state.status === 'player-turn';i++) {
    const s = battle.state;
    const damage = card => card.effects.reduce((sum,e) => sum + (e.type === 'damage' ? Number(e.amount) : 0),0);
    const hand = s.piles.hand.map(instanceId => ({instanceId,card:d.cards[s.cards.find(c => c.instanceId === instanceId).cardId]}))
      .filter(x => x.card.cost <= s.energy).sort((a,b) => damage(b.card)-damage(a.card));
    battle = store.act(profile,battle.id,{requestId:'action-'+i,expectedRevision:battle.revision,
      ...(hand.length ? {type:'play-card',instanceId:hand[0].instanceId} : {type:'end-turn'})}).battle;
  }
  assert.equal(battle.state.status,'won'); assert.equal(battle.state.round,2);
  assert.ok(battle.state.ultimate.generatedTotal > 0);
  assert.equal(battle.state.enemy.hp.decimal,'0.0');
  store.close(); store = new BattleStore(files.savePath);
  assert.deepEqual(store.get(profile,battle.id),battle);
  assert.throws(() => store.act(profile,battle.id,{requestId:'after-win',expectedRevision:battle.revision,type:'end-turn'}));
});

test('city ultimate generation and eight-hit use survive exact command replay and SQLite restart', async t => {
  const files = await fixture(t), profile = randomUUID();
  const scenario = await loadCityScenario(await loadTutorialScenario());
  let store = new BattleStore(files.savePath); files.cleanupWith(() => store.close());
  let battle = store.create(profile, scenario, {requestId:'ultimate-start',seed:0}).battle;
  let thirdCommand, third;
  for (const instanceId of ['tutorial-card-1','tutorial-card-2','tutorial-card-3']) {
    thirdCommand = {requestId:instanceId,expectedRevision:battle.revision,type:'play-card',instanceId};
    third = store.act(profile,battle.id,thirdCommand); battle = third.battle;
  }
  assert.deepEqual(battle.state.cards.at(-1), {instanceId:'ultimate:1',cardId:'410104'});
  assert.equal(third.events.filter(e => e.generated).length,1);
  assert.deepEqual(store.act(profile,battle.id,thirdCommand), {...third,replayed:true});
  store.close(); store = new BattleStore(files.savePath);
  assert.deepEqual(store.get(profile,battle.id),battle);
  battle = store.act(profile,battle.id,{requestId:'spend-remaining-energy',expectedRevision:battle.revision,
    type:'play-card',instanceId:'tutorial-card-4'}).battle;
  assert.equal(battle.state.energy,0);
  const use = {requestId:'use-ultimate',expectedRevision:battle.revision,type:'play-card',instanceId:'ultimate:1'};
  const result = store.act(profile,battle.id,use);
  assert.deepEqual(result.events.filter(e => e.type === 'DamageApplied').map(e => e.amount), ['72','72','144','144','144','289','289','289']);
  assert.equal(result.battle.state.energy,battle.state.energy);
  assert.deepEqual(result.battle.state.piles.removed,['ultimate:1']);
  assert.deepEqual(store.act(profile,battle.id,use), {...result,replayed:true});
  assert.deepEqual(store.get(profile,battle.id),result.battle);
});

test('embedded legacy city definitions and tutorial 5000 keep original card semantics', async t => {
  const files = await fixture(t), profile = randomUUID(), base = await loadTutorialScenario();
  let state = createBattle(base.definition,0).state;
  for (const instanceId of ['tutorial-card-1','tutorial-card-2','tutorial-card-3']) state = playCard(base.definition,state,instanceId).state;
  assert.equal(state.format,'hczs-battle-session-v1'); assert.equal(state.ultimate,undefined);
  assert.equal(state.cards.length,7);
  const current = await loadCityScenario(base), legacy = structuredClone(current);
  delete legacy.definition.ultimateRules; delete legacy.definition.cards['410104'];
  delete legacy.provenance.ultimate;
  for (const card of Object.values(legacy.definition.cards)) {
    for (const field of ['ownerId','cardType','specialPoints','removeOnLeaveHand']) delete card[field];
  }
  legacy.definition.id = 'legacy-city-v2-fixture';
  let store = new BattleStore(files.savePath); files.cleanupWith(() => store.close());
  let old = store.create(profile,legacy,{requestId:'old-city',seed:0}).battle;
  const embeddedDefinition = structuredClone(old.scenario.definition);
  store.close(); store = new BattleStore(files.savePath);
  store.create(profile,current,{requestId:'new-city',seed:0});
  for (const instanceId of ['tutorial-card-1','tutorial-card-2','tutorial-card-3']) {
    old = store.act(profile,old.id,{requestId:instanceId,expectedRevision:old.revision,type:'play-card',instanceId}).battle;
  }
  assert.equal(old.state.format,'hczs-battle-session-v2'); assert.equal(old.state.ultimate,undefined);
  assert.equal(old.state.cards.length,7); assert.deepEqual(old.scenario.definition,embeddedDefinition);
});
