import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { loadTutorialScenario } from '../src/tutorial.js';
import { loadCityScenario } from '../src/city-scenario.js';
import { BattleStore } from '../src/battles.js';
import { createApp } from '../src/app.js';
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
  assert.equal(battle.state.status,'won'); assert.equal(battle.state.round,3);
  assert.equal(battle.state.enemy.hp.decimal,'0.0');
  store.close(); store = new BattleStore(files.savePath);
  assert.deepEqual(store.get(profile,battle.id),battle);
  assert.throws(() => store.act(profile,battle.id,{requestId:'after-win',expectedRevision:battle.revision,type:'end-turn'}));
});
