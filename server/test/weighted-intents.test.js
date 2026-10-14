import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { weightedIntents, materializeEnemySelection } from '../src/weighted-intents.js';
import { BattleStore } from '../src/battles.js';
import { loadCityScenario } from '../src/city-scenario.js';
import { loadTutorialScenario } from '../src/tutorial.js';
import { fixture } from './helpers.js';

const policy = { algorithm:'sha256-weighted-intents-v1', divisor:3,remainder:1,fixedSkill:'66054',
  pool:[{skillId:'66051',weight:45},{skillId:'66052',weight:35},{skillId:'66053',weight:20}] };
test('seeded weighted schedule respects source branches and varies between battles', () => {
  assert.deepEqual(weightedIntents(policy,2,8).flat(), ['66054','66051','66052','66054','66052','66051','66054','66052']);
  const seen = new Set();
  for (let seed=0;seed<100;seed++) {
    const schedule = weightedIntents(policy,seed,30);
    assert.deepEqual(schedule,weightedIntents(policy,seed,30));
    schedule.forEach(([id],i) => { if (i%3===0) assert.equal(id,'66054'); else seen.add(id); });
  }
  assert.deepEqual([...seen].sort(), ['66051','66052','66053']);
  for (const invalid of [[], [{skillId:'66051',weight:0}], [{skillId:'66051',weight:1.5}],
    [{skillId:'66051',weight:1},{skillId:'66051',weight:2}], [{skillId:'66051',weight:0x100000001}]]) {
    assert.throws(() => weightedIntents({...policy,pool:invalid},0,30));
  }
});
test('materializing intents preserves deck PRNG inputs and original templates', async () => {
  const base=await loadTutorialScenario(), template=await loadCityScenario(base), before=JSON.stringify(template);
  const a=materializeEnemySelection(template,2), b=materializeEnemySelection(template,3);
  assert.notEqual(a.definition.id,b.definition.id);
  assert.deepEqual(a.definition.deck,b.definition.deck);
  assert.deepEqual(a,materializeEnemySelection(template,2));
  assert.equal(JSON.stringify(template),before);
  assert.equal(materializeEnemySelection(base,2),base);
});
test('random-seed creation retry and SQLite reopen retain the exact schedule; legacy schedules stay fixed', async t => {
  const files=await fixture(t), profile=randomUUID(), template=await loadCityScenario(await loadTutorialScenario());
  let store=new BattleStore(files.savePath); files.cleanupWith(()=>store.close());
  const command={requestId:'random-city'};
  const initial=store.create(profile,template,command);
  assert.ok(Number.isInteger(initial.battle.scenario.provenance.enemySelection.seed));
  const saved=structuredClone(initial.battle.scenario);
  const changed=structuredClone(template); changed.policies.enemySelection.pool=[{skillId:'66053',weight:100}];
  assert.deepEqual(store.create(profile,changed,command).battle,initial.battle);
  store.close(); store=new BattleStore(files.savePath);
  assert.deepEqual(store.get(profile,initial.battle.id).scenario,saved);
  assert.deepEqual(store.create(profile,changed,command).battle,initial.battle);
  assert.equal(store.create(profile,changed,command).replayed,true);
  const legacy=structuredClone(template); delete legacy.policies.enemySelection;
  const fixed=store.create(profile,legacy,{requestId:'legacy',seed:2}).battle;
  assert.deepEqual(fixed.scenario,legacy);
  assert.deepEqual(fixed.state.rng,{algorithm:'mulberry32-v1',state:2});
});
