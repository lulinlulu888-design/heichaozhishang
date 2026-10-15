import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import mongoose from 'mongoose';
import { fixture, request } from './helpers.js';

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
});
