import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import { createBattle, endTurn, playCard } from '../packages/battle-session/src/index.js';

const source = await readFile(new URL('./templates/cocos-enemy-turn-presentation.ts',import.meta.url),'utf8');
assert.equal(source,await readFile(new URL('../clients/cocos-poc/assets/EnemyTurnPresentation.ts',import.meta.url),'utf8'));
const { beforeEnemyAction, actionSegments } = await import('data:text/javascript;base64,'+Buffer.from(stripTypeScriptTypes(source)).toString('base64'));
const hp = decimal => ({numeric_type:'integer',decimal});
// Synthetic fixture; exercise the actual session event producer, not a copied event list.
const definition = {id:'timing-test', player:{id:'p',name:'p',maxHp:hp('100')},enemy:{id:'e',name:'e',maxHp:hp('100')},
    deck:[{instanceId:'a',cardId:'hit'},{instanceId:'b',cardId:'hit'}],
    cards:{hit:{name:'hit',cost:1,effects:[{type:'damage',target:'opponent',amount:'1'}]}},
    enemySkills:{hit:{effects:[{type:'damage',target:'opponent',amount:'7'}]}},enemyIntents:[['hit']],enemyFallback:['hit'],
    initialDraw:2,roundDraw:2,energyPerRound:3,handLimit:3,maxRounds:5};
const previous = createBattle(definition,42).state;
const original = JSON.stringify(previous);
const next = endTurn(definition,previous);
const visible = beforeEnemyAction(previous,next.events);
assert.equal(visible.round,1); assert.equal(next.state.round,2);
assert.deepEqual(visible.piles.hand,[]); assert.equal(next.state.piles.hand.length,2);
assert.deepEqual(visible.piles.discard,['a','b']);
assert.equal(visible.player.hp.decimal,'100'); assert.equal(next.state.player.hp.decimal,'93');
assert.equal(JSON.stringify(previous),original);
assert.equal(beforeEnemyAction(previous,[]),previous);
assert.equal(beforeEnemyAction(previous,[{type:'TurnStarted',round:99}]),previous);
assert.equal(beforeEnemyAction(previous,[{type:'CardMoved',instanceId:'missing',from:'hand',to:'discard'}]),previous);
const multi = {...definition, enemySkills:{...definition.enemySkills,guard:{effects:[{type:'shield',target:'self',amount:'9'}]}},
    enemyIntents:[['hit','guard','hit']]};
const multiResult=endTurn(multi,previous);
const segments=actionSegments(multiResult.events);
assert.deepEqual(segments.map(s=>s.action.skillId),['hit','guard','hit']);
assert.deepEqual(segments.map(s=>s.events.filter(e=>e.type==='DamageApplied').length),[1,0,1]);
assert.deepEqual(segments.map(s=>s.events.filter(e=>e.type==='ShieldAdded').length),[0,1,0]);
assert.equal(segments[0].events.find(e=>e.type==='DamageApplied').finalHp.decimal,'93');
assert.equal(segments[2].events.find(e=>e.type==='DamageApplied').previousHp.decimal,'93');
assert.equal(segments[2].events.find(e=>e.type==='DamageApplied').finalHp.decimal,'86');
assert.deepEqual(actionSegments([]),[]);
const status = JSON.parse(JSON.stringify(definition));
status.statusRules = {policy:'breakdown-reconstruction-v1',attack:{player:hp('100'),enemy:hp('100')}};
status.cards.hit.effects = [{type:'breakdown',target:'opponent',stacks:2}];
status.enemySkills.apply = {effects:[{type:'breakdown',target:'opponent',stacks:2}]};
status.enemyIntents = [['apply','hit']];
const applied = playCard(status,createBattle(status,42).state,'a');
const statusRound = endTurn(status,applied.state);
const statusEnd = endTurn(status,statusRound.state);
const statusSegments = actionSegments(statusEnd.events);
assert.deepEqual(statusSegments.map(s=>s.action.type),['BreakdownTriggered','EnemySkillUsed','BreakdownTriggered']);
assert.deepEqual(statusSegments.map(s=>s.events.filter(e=>e.type==='DamageApplied').map(e=>e.target)),[['player'],['player'],['enemy']]);
assert.deepEqual(statusSegments.map(s=>s.events.find(e=>e.type==='DamageApplied').amount),['40','7','40']);
const statusPrefix = beforeEnemyAction(statusRound.state,statusEnd.events);
assert.equal(statusPrefix.player.hp.decimal,'53'); // tick settled; enemy hit still pending
assert.equal(statusEnd.state.player.hp.decimal,'46');
assert.equal(statusRound.state.player.hp.decimal,'93');
const lethal = JSON.parse(JSON.stringify(status)); lethal.statusRules.attack.enemy=hp('1000');
const lethalEnd=endTurn(lethal,statusRound.state);
assert.equal(lethalEnd.state.status,'lost');
assert.deepEqual(actionSegments(lethalEnd.events).map(s=>s.action.type),['BreakdownTriggered']);
assert.ok(actionSegments(lethalEnd.events)[0].events.some(e=>e.type==='BattleEnded'));
console.log('Enemy animation prefix: previous round, discarded hand, deferred damage/draw, immutable source and invalid-prefix fallback passed.');
console.log('Actual three-skill session events retain order and isolate damage/shield effects per animation.');
console.log('Status ticks isolate owner-end damage from enemy attack; lethal status remains a standalone segment.');
