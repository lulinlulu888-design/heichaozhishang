// Explicit real-Mongo integration gate. This launches only this tool's hidden
// Node children and allocates new generated databases on project loopback27027.
// It never launches UE, touches a main-service port, or enumerates databases.
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdir,readFile,writeFile,access } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs,isDeepStrictEqual } from 'node:util';
import mongoose from '../../server/node_modules/mongoose/index.js';
import { connectDatabase } from '../../server/src/database/connection.js';
import { initializeFreshTestDatabase } from './isolated_session_lifecycle.mjs';
import { digest,isGeneratedDatabase,isTestPort,validateMongoUri,validateLiveTestIdentity,validateOwnedDatabaseForDrop } from './isolated_session_manifest.mjs';

const {values}=parseArgs({options:{run:{type:'boolean',default:false},port:{type:'string'}}});
if(!values.run)throw Error('Pass --run to execute real isolated Mongo/Node lifecycle integration');
const port=Number(values.port??7468);if(!isTestPort(port))throw Error('Use a dedicated integration port');
const root=fileURLToPath(new URL('../../',import.meta.url)),uri='mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true';
validateMongoUri(uri);
const directory=resolve(root,'analysis/unreal/session-test','lifecycle-'+randomUUID());await mkdir(directory,{recursive:true});
const connectionPath=resolve(root,'server/src/database/connection.js'),beforeSource=digest(await readFile(connectionPath));
const checks={},processes=[],owned=[],failures=[],failedDatabases=[];
const resultPath=resolve(directory,'integration-result.json');
const pause=ms=>new Promise(done=>setTimeout(done,ms));
async function bounded(promise,ms,message){let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(message)),ms);})]);}finally{clearTimeout(timer);}}
const json=async p=>JSON.parse(await readFile(p,'utf8'));
async function raw(name) {
  if(!isGeneratedDatabase(name))throw Error('Unexpected non-generated database');
  const c=mongoose.createConnection(uri,{dbName:name,serverSelectionTimeoutMS:5000});c.on('error',()=>{});
  try{return await c.asPromise();}catch(error){await c.close().catch(()=>{});throw error;}
}
async function empty(name){const c=await raw(name);try{return (await c.db.listCollections({}, {nameOnly:true}).toArray()).length===0;}finally{await c.close();}}
function child(args,record,label) {
  const spawned=spawn(process.execPath,[resolve(root,'tools/unreal/isolated_session_server.mjs'),...args],{
    cwd:root,env:{...process.env,HCZS_TEST_MONGODB_URI:uri},stdio:['ignore','pipe','pipe'],windowsHide:true});
  const item={spawned,record,label,exited:false,out:'',err:''};processes.push(item);
  spawned.stdout.on('data',b=>{item.out+=(b.toString('utf8'));});spawned.stderr.on('data',b=>{item.err+=(b.toString('utf8'));});
  item.completion=new Promise(done=>{
    spawned.once('error',error=>{item.error=error.message;});
    spawned.once('close',(code,signal)=>{item.exited=true;item.code=code;item.signal=signal;done(item);});
  });return item;
}
async function waitReady(item) {
  const path=resolve(item.record,'server.json'),deadline=Date.now()+30000;
  while(Date.now()<deadline){
    if(item.exited)throw Error(`${item.label} exited before publishing its manifest: ${item.err.slice(-600)}`);
    try {const text=await readFile(path,'utf8'),manifest=JSON.parse(text);
      if(manifest.pid===item.spawned.pid){item.manifest=manifest;item.manifestText=text;owned.push(manifest);return manifest;}
    } catch(error) {if(!['ENOENT',undefined].includes(error.code))throw error;}
    await pause(100);
  }throw Error('Isolated Node readiness timed out');
}
async function identity(item) {
  const m=item.manifest,response=await fetch(m.address+'/__hczs_test_control/identity',{headers:{authorization:'Bearer '+m.controlToken},signal:AbortSignal.timeout(5000)});
  if(response.status!==200)throw Error('Isolated live identity probe failed');
  return validateLiveTestIdentity(await response.json(),m,item.manifestText);
}
async function stop(item) {
  if(item.exited)return;
  const m=item.manifest,response=await fetch(m.address+'/__hczs_test_control/stop',{method:'POST',headers:{authorization:'Bearer '+m.controlToken},signal:AbortSignal.timeout(5000)});
  if(response.status!==200)throw Error('Isolated normal stop failed');await response.text();
  await bounded(item.completion,15000,'Isolated Node stop timed out');
  if(item.code!==0)throw Error('Isolated Node stop exited with failure');
}
async function request(m,path,input) {
  const response=await fetch(m.address+'/api/rebuild/v1'+path,{method:input?'POST':'GET',headers:input?{'content-type':'application/json'}:{},
    ...(input?{body:JSON.stringify(input)}:{}),signal:AbortSignal.timeout(10000)});
  const value=await response.json();if(!response.ok)throw Error('Isolated API fixture request failed: '+response.status);return value;
}
let blocker,negative;
try {
  const record=resolve(directory,'normal');await mkdir(record);
  const first=child([`--port=${port}`,`--record-directory=${record}`,'--preserve-database'],record,'first');await waitReady(first);await identity(first);
  const c=await raw(first.manifest.mongoDatabase);
  try {
    const schema=await c.db.collection('hczs_metadata').findOne({_id:'schema'}),claim=await c.db.collection('hczs_ue_test_identity').findOne({_id:'identity'});
    checks.productionInitializedBeforeTestClaim=schema?.project==='hczs-rebuild'&&schema.version===1&&claim?.runId===first.manifest.runId;
  }finally{await c.close();}
  const startup=await json(resolve(record,'startup-process-0.json'));
  const phaseNames=startup.phases?.map(row=>row.phase)??[];
  checks.initialStartupPublished=startup.phase==='running'&&startup.databaseClaimed===true
    &&phaseNames.indexOf('preflight-empty')>=0&&phaseNames.indexOf('preflight-empty')<phaseNames.indexOf('production-metadata-initialized')
    &&phaseNames.indexOf('production-metadata-initialized')<phaseNames.indexOf('identity-claimed')
    &&startup.phases.find(row=>row.phase==='production-metadata-initialized')?.databaseClaimed===false;
  const profile=(await request(first.manifest,'/profiles',{displayName:'隔离生命周期测试'})).profile;
  const created=(await request(first.manifest,`/profiles/${profile.id}/battles`,{requestId:'lifecycle-'+randomUUID(),encounterId:'tutorial-5000'})).battle;
  const saved=(await request(first.manifest,`/profiles/${profile.id}/battles/${created.id}`)).battle;
  await stop(first);
  const preserved=await json(resolve(record,'stopped.json'));
  checks.preserveStopRetainsOnlyItsGeneratedDatabase=preserved.databaseDropped===false&&preserved.mongoDatabase===first.manifest.mongoDatabase&&!await empty(preserved.mongoDatabase);
  const second=child([`--resume-manifest=${resolve(record,'server.json')}`],record,'resume');await waitReady(second);await identity(second);
  const restored=(await request(second.manifest,`/profiles/${profile.id}/battles/${created.id}`)).battle;
  checks.realNodeRestartRestoresExactStateAndScenario=second.manifest.pid!==first.manifest.pid&&second.manifest.processIdentity!==first.manifest.processIdentity
    &&second.manifest.mongoDatabase===first.manifest.mongoDatabase&&second.manifest.databaseIdentity===first.manifest.databaseIdentity
    &&isDeepStrictEqual(restored,saved)&&second.manifest.resumeCheckpoint.stateSha256===digest(JSON.stringify(saved.state))
    &&second.manifest.resumeCheckpoint.scenarioSha256===digest(JSON.stringify(saved.scenario));
  await stop(second);const dropped=await json(resolve(record,'stopped.json'));
  checks.finalStopDropsOnlyOwnedGeneratedDatabase=dropped.databaseDropped===true&&dropped.processIdentity===second.manifest.processIdentity&&await empty(dropped.mongoDatabase);

  // A dedicated, self-generated negative fixture proves production refusal is
  // intact. Its unique sentinel authorizes only this harness's exact cleanup.
  negative={name:'hczs_test_ue_'+randomUUID().replaceAll('-',''),nonce:randomUUID()};
  const n=await raw(negative.name);
  try {
    if((await n.db.listCollections({}, {nameOnly:true}).toArray()).length!==0)throw Error('Negative fixture namespace already exists');
    await n.db.collection('isolated_lifecycle_negative').insertOne({_id:'sentinel',mode:'isolated-lifecycle-negative-test',nonce:negative.nonce});
    const before=await n.db.collection('isolated_lifecycle_negative').findOne({_id:'sentinel'});
    let productionRejected=false,toolRejected=false;
    try {const unexpected=await connectDatabase({uri,database:negative.name});await unexpected.close();}
    catch(error){productionRejected=error.message.startsWith('Refusing to adopt a non-empty MongoDB database');}
    try {await initializeFreshTestDatabase({mongoUri:uri,identity:{_id:'identity',schemaVersion:1,mode:'isolated-native-session-test',runId:randomUUID(),databaseIdentity:randomUUID(),processIdentity:randomUUID(),processIndex:0,
      lifecycle:'starting',mongoDatabase:negative.name,mongoUriSha256:validateMongoUri(uri)}});}catch(error){toolRejected=error.message.includes('already contains collections');}
    const after=await n.db.collection('isolated_lifecycle_negative').findOne({_id:'sentinel'}),names=(await n.db.listCollections({}, {nameOnly:true}).toArray()).map(r=>r.name);
    checks.nonemptyProductionAndToolRefuseWithoutAdoption=productionRejected&&toolRejected&&isDeepStrictEqual(before,after)&&names.length===1&&names[0]==='isolated_lifecycle_negative';
    if(after?.mode!=='isolated-lifecycle-negative-test'||after.nonce!==negative.nonce||!isGeneratedDatabase(n.name))throw Error('Negative fixture ownership changed; refusing cleanup');
    await n.dropDatabase();negative.cleaned=true;
  }finally{await n.close();}
  checks.negativeFixtureOwnNonceCleanup=await empty(negative.name);

  // An occupied test port causes a real startup failure after valid schema and
  // claim. Even --preserve-database must clean this unpublished initial run.
  blocker=createServer((req,res)=>res.writeHead(503).end());await new Promise((ok,fail)=>{blocker.once('error',fail);blocker.listen(port,'127.0.0.1',ok);});
  const failedRecord=resolve(directory,'occupied-port');await mkdir(failedRecord);
  const failed=child([`--port=${port}`,`--record-directory=${failedRecord}`,'--preserve-database'],failedRecord,'occupied-port');
  await bounded(failed.completion,30000,'Occupied-port negative startup did not terminate');
  const failedJournal=await json(resolve(failedRecord,'startup-process-0.json'));
  failedDatabases.push(failedJournal.mongoDatabase);
  checks.failedInitialStartupRecordsExactOwnedIdentity=failed.code===1&&failedJournal.phase==='failed'&&failedJournal.failure.phase==='proxy-listening'
    &&failedJournal.databaseClaimed===true&&failedJournal.cleanup.databaseDropped===true&&isGeneratedDatabase(failedJournal.mongoDatabase)
    &&failedJournal.pid===failed.spawned.pid;
  checks.failedPreserveStartupLeavesNoGeneratedDatabase=await empty(failedJournal.mongoDatabase);
  checks.failedStartupNeverPublishesReadyManifest=await access(resolve(failedRecord,'server.json')).then(()=>false,error=>error.code==='ENOENT');
  await new Promise(ok=>blocker.close(ok));blocker=null;
} catch(error){failures.push(String(error.message).slice(0,1000));}
finally {
  if(blocker)await new Promise(ok=>blocker.close(ok));
  for(const item of processes){
    if(!item.exited){try{if(item.manifest)await stop(item);else throw Error('No published manifest');}catch(error){item.spawned.kill();await item.completion;failures.push('Emergency stop of owned integration child: '+item.label);}}
    await writeFile(resolve(directory,item.label+'.stdout.txt'),item.out);await writeFile(resolve(directory,item.label+'.stderr.txt'),item.err);
  }
  // Only exact identities retained from our own children may be cleaned here.
  for(const m of owned){
    const c=await raw(m.mongoDatabase);
    try {
      const names=await c.db.listCollections({}, {nameOnly:true}).toArray();if(!names.length)continue;
      const current=await c.db.collection('hczs_ue_test_identity').findOne({_id:'identity'});
      const matching=owned.find(x=>x.mongoDatabase===m.mongoDatabase&&x.processIdentity===current?.processIdentity);
      if(!matching)throw Error('Integration database no longer belongs to an owned child');
      validateOwnedDatabaseForDrop(current,{databaseName:c.name,runId:matching.runId,databaseIdentity:matching.databaseIdentity,processIdentity:matching.processIdentity});
      await c.dropDatabase();failures.push('Emergency cleanup required for '+m.mongoDatabase);
    }catch(error){failures.push(String(error.message));}finally{await c.close();}
  }
  if(negative&&!negative.cleaned){const c=await raw(negative.name);try{const row=await c.db.collection('isolated_lifecycle_negative').findOne({_id:'sentinel'});
    if(row?.mode==='isolated-lifecycle-negative-test'&&row.nonce===negative.nonce){await c.dropDatabase();negative.cleaned=true;}}
    finally{await c.close();}}
}
checks.productionConnectionSourceUnchanged=digest(await readFile(connectionPath))===beforeSource;
const result={schemaVersion:1,mode:'isolated-real-mongo-node-lifecycle-integration-not-ui',passed:failures.length===0&&Object.values(checks).every(v=>v===true),
  checks,failures,directory,port,mongoEndpoint:'127.0.0.1:27027',productionConnectionSha256:beforeSource,
  scope:{generatedDatabasesOnly:true,databaseEnumeration:false,mainServiceTouched:false,unrealStarted:false,originalApkExecuted:false,mongoDaemonRestarted:false},
  generatedDatabaseIdentities:[...new Set([...owned.map(m=>m.mongoDatabase),...(negative?[negative.name]:[]),...failedDatabases])]};
await writeFile(resultPath,JSON.stringify(result,null,2));console.log(JSON.stringify({...result,resultPath},null,2));if(!result.passed)process.exitCode=1;
