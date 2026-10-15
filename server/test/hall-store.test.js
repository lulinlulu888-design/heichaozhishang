import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { DatabaseSync } from 'node:sqlite';
import { HallStore } from '../src/hall-store.js';
import { fixture } from './helpers.js';
const A='11111111-1111-4111-8111-111111111111', B='22222222-2222-4222-8222-222222222222';
const ids=new Set([33,2]);
const command=(requestId='one',expectedRevision=0,selectedHeroId=33)=>({requestId,expectedRevision,selectedHeroId});
const counts=s=>['hall_states','hall_requests'].map(t=>s.db.prepare('SELECT count(*) AS n FROM '+t).get().n);

test('hall GET is virtual; reopen replays original receipt even after later updates or catalog changes',async t=>{
 const {savePath,cleanupWith}=await fixture(t);let s=new HallStore(savePath+'.hall');
 assert.deepEqual(s.get(A),{profileId:A,revision:0,selectedHeroId:null,updatedAt:null});assert.deepEqual(counts(s),[0,0]);
 const first=s.update(A,command(),ids);assert.equal(first.hall.revision,1);assert.equal(first.replayed,false);
 s.update(A,command('two',1,null),ids);s.close();s=new HallStore(savePath+'.hall');cleanupWith(()=>s.close());
 assert.equal(s.get(A).selectedHeroId,null);assert.equal(s.get(A).revision,2);
 assert.deepEqual(s.update(A,command(),new Set()),{hall:first.hall,replayed:true});assert.deepEqual(counts(s),[1,2]);
 assert.throws(()=>s.update(A,command('one',0,2),ids),{code:'REQUEST_ID_CONFLICT',status:409});
});
test('two connections serialize revisions and isolate receipts per profile',async t=>{
 const {savePath,cleanupWith}=await fixture(t);const a=new HallStore(savePath+'.hall'),b=new HallStore(savePath+'.hall');cleanupWith(()=>{a.close();b.close();});
 a.update(A,command(),ids);assert.throws(()=>b.update(A,command('other'),ids),{code:'REVISION_CONFLICT',status:409});
 assert.equal(b.update(B,command('one',0,2),ids).hall.selectedHeroId,2);assert.deepEqual(counts(a),[2,2]);
 assert.equal(a.get(A).selectedHeroId,33);
});
test('receipt storage failure rolls back both new and existing hall state',async t=>{
 const {savePath,cleanupWith}=await fixture(t);const s=new HallStore(savePath+'.hall');cleanupWith(()=>s.close());
 s.update(A,command(),ids);const before=s.get(A);
 s.db.exec("CREATE TRIGGER reject_receipt BEFORE INSERT ON hall_requests BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END;");
 assert.throws(()=>s.update(A,command('two',1,2),ids),/injected receipt failure/);
 assert.throws(()=>s.update(B,command(),ids),/injected receipt failure/);
 assert.deepEqual(s.get(A),before);assert.equal(s.get(B).revision,0);assert.deepEqual(counts(s),[1,1]);
 s.db.exec('DROP TRIGGER reject_receipt');assert.equal(s.update(A,command('two',1,2),ids).hall.revision,2);
});
test('invalid inputs and heroes never write state or receipts',async t=>{
 const {savePath,cleanupWith}=await fixture(t);const s=new HallStore(savePath+'.hall');cleanupWith(()=>s.close());
 for(const value of [null,[],{}, {...command(),extra:1}, {...command(),requestId:'bad space'}, {...command(),requestId:'x'.repeat(129)}, {...command(),expectedRevision:-1}, {...command(),expectedRevision:1.5}])assert.throws(()=>s.update(A,value,ids),{code:'INVALID_INPUT'});
 for(const hero of [0,-1,1.2,'33',999,undefined,Number.MAX_SAFE_INTEGER+1])assert.throws(()=>s.update(A,{requestId:'hero',expectedRevision:0,selectedHeroId:hero},ids),{code:'HALL_HERO_UNAVAILABLE'});
 for(const bad of ['abc','../profile',null])assert.throws(()=>s.get(bad),{code:'INVALID_INPUT'});
 assert.deepEqual(counts(s),[0,0]);
});
test('foreign database is refused without modifying bytes or journal mode',async t=>{
 const {savePath}=await fixture(t);const db=new DatabaseSync(savePath);db.exec("CREATE TABLE unrelated(value TEXT); INSERT INTO unrelated VALUES ('keep'); PRAGMA application_id=123; PRAGMA user_version=7;");db.close();const before=await readFile(savePath);
 assert.throws(()=>new HallStore(savePath),/Unsupported hall save/);assert.deepEqual(await readFile(savePath),before);
});


test('simultaneous worker connections commit exactly one revision-zero update', async t => {
  const { Worker } = await import('node:worker_threads');
  const { savePath } = await fixture(t);
  const file = savePath + '.hall'; new HallStore(file).close();
  const gate = new SharedArrayBuffer(4), view = new Int32Array(gate);
  const code = `const { parentPort,workerData }=require('node:worker_threads');
    (async()=>{const {HallStore}=await import(workerData.module);const store=new HallStore(workerData.file);
    parentPort.postMessage({ready:true});Atomics.wait(new Int32Array(workerData.gate),0,0);
    try{parentPort.postMessage({result:store.update(workerData.id,{requestId:workerData.request,expectedRevision:0,selectedHeroId:33},new Set([33]))});}
    catch(e){parentPort.postMessage({error:e.code});}finally{store.close();}})().catch(e=>{throw e;});`;
  const workers = ['race-a','race-b'].map(request=>new Worker(code,{eval:true,workerData:{module:new URL('../src/hall-store.js',import.meta.url).href,file,id:A,request,gate}}));
  t.after(async()=>{await Promise.all(workers.map(w=>w.terminate()));});
  const ready = workers.map(w=>new Promise((resolve,reject)=>{w.once('message',m=>m.ready?resolve():reject(Error('worker not ready')));w.once('error',reject);}));
  const results = workers.map(w=>new Promise((resolve,reject)=>{w.on('message',m=>{if(!m.ready)resolve(m);});w.once('error',reject);}));
  await Promise.all(ready);Atomics.store(view,0,1);Atomics.notify(view,0,2);
  const completed=await Promise.all(results);assert.equal(completed.filter(x=>x.result).length,1);assert.equal(completed.filter(x=>x.error==='REVISION_CONFLICT').length,1);
  const check=new HallStore(file);try{assert.deepEqual(counts(check),[1,1]);assert.equal(check.get(A).revision,1);}finally{check.close();}
});
