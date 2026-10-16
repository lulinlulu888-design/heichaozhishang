import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID, createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import mongoose from 'mongoose';
import { fixture, request } from './helpers.js';
import { loadMainline, mainlineContentId } from '../src/mainline.js';
import { MongoProfileStore } from '../src/database/mongo-profiles.js';
import { MongoBattleStore } from '../src/database/mongo-battles.js';
import { MongoMainlineStore } from '../src/database/mongo-mainline.js';

const uri=process.env.HCZS_TEST_MONGODB_URI;
const enabled={skip:!uri && 'Set HCZS_TEST_MONGODB_URI to an independent test replica set'};
async function start(options) {
  const code=`import {createApp} from ${JSON.stringify(new URL('../src/app.js',import.meta.url).href)};
    try { const app=await createApp(JSON.parse(process.env.HCZS_PROGRESS_TEST_OPTIONS));
      process.on('message',async v=>{if(v==='close'){await app.close();process.disconnect();}});process.send({address:app.address});
    } catch(e){process.send({error:e.message});process.disconnect();process.exitCode=1;}`;
  const child=spawn(process.execPath,['--input-type=module','-e',code],{windowsHide:true,stdio:['ignore','ignore','pipe','ipc'],
    env:{...process.env,HCZS_PROGRESS_TEST_OPTIONS:JSON.stringify(options)}});
  let stderr='';child.stderr.on('data',b=>{stderr=(stderr+b).slice(-2000);});
  const exited=new Promise(resolve=>child.once('exit',code=>resolve(code)));
  let ready;
  try {
    ready=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Progress server startup timed out')),20000);
      child.once('message',v=>{clearTimeout(timer);resolve(v);});child.once('error',e=>{clearTimeout(timer);reject(e);});
      child.once('exit',c=>{clearTimeout(timer);reject(Error('Progress server exited '+c+': '+stderr));});});
    if(ready.error)throw Error(ready.error);
  }catch(e){child.kill();await exited;throw e;}
  let stopped=false;
  return {address:ready.address,async close(){if(stopped)return;stopped=true;child.send('close');
    const timer=setTimeout(()=>child.kill(),5000);try{assert.equal(await exited,0,stderr);}finally{clearTimeout(timer);}}};
}

test('Authoritative win settlement is atomic, concurrent/retry safe, profile scoped and survives Node restart',enabled,async t=>{
  const files=await fixture(t),database='hczs_test_progress_'+randomUUID().replaceAll('-','');
  const connection=await mongoose.createConnection(uri,{dbName:database,serverSelectionTimeoutMS:5000}).asPromise();
  assert.deepEqual(await connection.db.listCollections().toArray(),[],'Only a newly allocated empty test database may be used');
  const children=[];
  files.cleanupWith(async()=>{try{for(const child of children)await child.close();}
    finally{try{assert.match(database,/^hczs_test_progress_[0-9a-f]{32}$/);assert.equal(connection.name,database);
      const identity=await connection.db.collection('hczs_metadata').findOne({_id:'schema'});
      assert.equal(identity?.project,'hczs-rebuild');await connection.dropDatabase();}finally{await connection.close();}}});
  const options={storage:'mongodb',mongoUri:uri,mongoDatabase:database,port:0,dataDirectory:files.dataDirectory,
    tutorialDirectory:fileURLToPath(new URL('../../analysis/first-encounter',import.meta.url)),
    mainlineDirectory:fileURLToPath(new URL('../../analysis/mainline-progression',import.meta.url))};
  let server=await start(options);children.push(server);
  const bootstrap=await request(server.address,'/bootstrap');
  assert.ok(bootstrap.body.capabilities.includes('mainline-progression'));
  const create=await request(server.address,'/profiles','POST',{displayName:'主线验收'});
  const id=create.body.profile.id,path='/profiles/'+id+'/mainline';
  const initial=(await request(server.address,path)).body.campaign;
  assert.equal(initial.revision,0);assert.equal(initial.challenges[1].status,'locked');
  const command={requestId:'settle-1',expectedRevision:0,contentId:initial.contentId};
  let b=(await request(server.address,'/profiles/'+id+'/battles','POST',{requestId:'battle-1',encounterId:'tutorial-5000',seed:123})).body.battle;
  assert.ok(b?.id);
  assert.equal((await request(server.address,path+'/settlements','POST',{...command,battleId:b.id})).body.error.code,'BATTLE_NOT_WON');
  assert.equal((await request(server.address,path)).body.campaign.revision,0);
  for(let i=0;b.state.status==='player-turn'&&i<100;i++){
    const instanceId=b.state.piles.hand.find(id=>{const c=b.state.cards.find(c=>c.instanceId===id);return b.scenario.definition.cards[c.cardId].cost<=b.state.energy;});
    const response=await request(server.address,'/profiles/'+id+'/battles/'+b.id+'/actions','POST',{
      requestId:'action-'+i,expectedRevision:b.revision,...(instanceId?{type:'play-card',instanceId}:{type:'end-turn'})});
    assert.equal(response.status,200);b=response.body.battle;
  }
  assert.equal(b.state.status,'won','Test uses actual battle commands, never injected terminal save data');
  const other=(await request(server.address,'/profiles','POST',{displayName:'另一档案'})).body.profile;
  assert.equal((await request(server.address,'/profiles/'+other.id+'/mainline/settlements','POST',{...command,battleId:b.id})).status,404);
  const input={...command,battleId:b.id};
  const responses=await Promise.all([request(server.address,path+'/settlements','POST',input),request(server.address,path+'/settlements','POST',input)]);
  assert.deepEqual(responses.map(r=>r.status),[200,200]);
  assert.deepEqual(responses.map(r=>r.body.replayed).sort(),[false,true]);
  const receipt=responses.find(r=>!r.body.replayed).body;
  assert.deepEqual(receipt.rewards,[]);assert.equal(receipt.campaign.revision,1);
  assert.deepEqual(receipt.campaign.challenges.map(n=>[n.id,n.status]),[[3997,'passed'],[3998,'available']]);
  assert.equal(receipt.campaign.challenges[1].executable,false);
  assert.equal((await request(server.address,path+'/settlements','POST',{...input,battleId:randomUUID()})).body.error.code,'REQUEST_ID_CONFLICT');
  assert.equal((await request(server.address,path+'/settlements','POST',{...input,requestId:'different',expectedRevision:0})).body.error.code,'REVISION_CONFLICT');
  assert.equal((await request(server.address,path+'/settlements','POST',{...input,requestId:'duplicate-battle',expectedRevision:1})).body.error.code,'CHALLENGE_ALREADY_COMPLETED');
  assert.equal(await connection.db.collection('mainline_states').countDocuments(),1);
  assert.equal(await connection.db.collection('mainline_requests').countDocuments(),1);
  await server.close();server=await start(options);children.push(server);
  assert.deepEqual((await request(server.address,path)).body.campaign,receipt.campaign);
  const retry=await request(server.address,path+'/settlements','POST',input);
  assert.equal(retry.body.replayed,true);assert.deepEqual(retry.body.campaign,receipt.campaign);
  assert.equal((await request(server.address,'/profiles/'+id+'/battles/'+b.id)).body.battle.state.status,'won');
  await server.close();

  // Keep using this test's generated, owned database and real victorious battle.
  // Availability changes are simulated definitions, never production enablement.
  const definition=await loadMainline(options.mainlineDirectory,{resolve:()=>({})});
  const profiles=new MongoProfileStore(connection),battles=new MongoBattleStore(connection);
  const original=new MongoMainlineStore(connection,definition,profiles,battles);
  const states=connection.db.collection('mainline_states'),requests=connection.db.collection('mainline_requests');
  const stateKey=JSON.stringify([id,2]),requestKey=JSON.stringify([id,input.requestId]);
  const stateRow=await states.findOne({_id:stateKey}),requestRow=await requests.findOne({_id:requestKey});
  assert.equal(stateRow.schemaVersion,2);assert.equal(requestRow.schemaVersion,2);
  const restore=async()=>{await states.replaceOne({_id:stateKey},stateRow,{upsert:true});
    await requests.replaceOne({_id:requestKey},requestRow,{upsert:true});};

  const upgraded=structuredClone(definition);
  upgraded.nodes[1].encounterId='prologue-boss-1703';upgraded.contentId=mainlineContentId(upgraded);
  const next=new MongoMainlineStore(connection,upgraded,profiles,battles);
  const view=await next.get(id);
  assert.equal(view.revision,1);assert.equal(view.challenges[1].executable,true);
  assert.deepEqual((await next.settle(id,input)).campaign,receipt.campaign,'Historical retry keeps its original definition');

  // The first deployed format had no frozen definition. It must remain readable
  // after adding a new binding, without fabricating a new chapter or receipt.
  await states.updateOne({_id:stateKey},{$set:{schemaVersion:1},$unset:{definitionJson:''}});
  await requests.updateOne({_id:requestKey},{$set:{schemaVersion:1},$unset:{definitionJson:''}});
  assert.equal((await next.get(id)).revision,1);
  assert.deepEqual((await next.settle(id,input)).campaign,receipt.campaign);
  const changedPolicy=structuredClone(upgraded);changedPolicy.policy='future-incompatible-policy';
  changedPolicy.contentId=mainlineContentId(changedPolicy);
  const incompatible=new MongoMainlineStore(connection,changedPolicy,profiles,battles);
  await assert.rejects(()=>incompatible.get(id),{code:'MAINLINE_CONTENT_CHANGED',status:409});
  await restore();
  await assert.rejects(()=>incompatible.get(id),{code:'MAINLINE_CONTENT_CHANGED',status:409});
  assert.deepEqual(await states.findOne({_id:stateKey}),stateRow,'Incompatible definitions cannot reset persisted progress');

  // A receipt without its atomically committed state is data loss, not rev0.
  await states.deleteOne({_id:stateKey});
  await assert.rejects(()=>original.get(id),{code:'SAVE_CORRUPT'});
  await assert.rejects(()=>original.settle(id,input),{code:'SAVE_CORRUPT'});
  await assert.rejects(()=>original.settle(id,{...input,requestId:'missing-state'}),{code:'SAVE_CORRUPT'});
  await restore();

  // Deterministic GET/first-commit interleaving: its first state read observed
  // null, then the transaction became visible before the receipt read.
  const findById=original.states.findById;
  let first=true;
  original.states.findById=function(...args){if(first){first=false;return {lean:async()=>null};}
    return findById.apply(this,args);};
  try { assert.equal((await original.get(id)).revision,1); }
  finally { original.states.findById=findById; }

  // Even a correctly hashed forged receipt may not mark an unimplemented boss
  // completed, nor may GET quietly accept that impossible saved state.
  const forgedDone={challengeId:3998,battleId:randomUUID(),battleRevision:1,completedAt:stateRow.updatedAt};
  await states.updateOne({_id:stateKey},{$set:{revision:2,completed:[...stateRow.completed,forgedDone]}});
  await assert.rejects(()=>original.get(id),{code:'SAVE_CORRUPT'});
  const forgedResult=structuredClone(receipt);
  forgedResult.campaign.completed.push(forgedDone);forgedResult.campaign.revision=2;
  forgedResult.campaign.challenges[1].status='passed';forgedResult.campaign.challenges[1].recordPresent=true;forgedResult.campaign.challenges[1].successTime=1;
  forgedResult.settlement=forgedDone;
  const forgedText=JSON.stringify(forgedResult),forgedInput={...input,requestId:'forged',expectedRevision:1,battleId:forgedDone.battleId};
  await requests.insertOne({...requestRow,_id:JSON.stringify([id,'forged']),requestId:'forged',
    payload:JSON.stringify({expectedRevision:1,contentId:input.contentId,battleId:forgedDone.battleId}),
    result:forgedText,resultHash:createHash('sha256').update(forgedText).digest('hex')});
  await assert.rejects(()=>original.settle(id,forgedInput),{code:'SAVE_CORRUPT'});
  await requests.deleteOne({_id:JSON.stringify([id,'forged'])});await restore();

  const disabled=structuredClone(upgraded);disabled.nodes[0].encounterId=null;disabled.contentId=mainlineContentId(disabled);
  const invalidMigration=new MongoMainlineStore(connection,disabled,profiles,battles);
  await assert.rejects(()=>invalidMigration.settle(id,{...input,requestId:'disabled-previous',expectedRevision:1,contentId:disabled.contentId}),
    {code:'MAINLINE_CONTENT_CHANGED',status:409});
  assert.deepEqual(await states.findOne({_id:stateKey}),stateRow);
  assert.equal(await requests.countDocuments(),1);
});
