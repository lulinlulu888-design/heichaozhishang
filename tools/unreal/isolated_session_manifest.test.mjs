import test from 'node:test';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {digest,validateResumeManifest,validateDatabaseIdentity,validateResumeCollections,REQUIRED_COLLECTIONS,validateMongoUri,
  validateLiveTestIdentity,validateOwnedDatabaseForDrop} from './isolated_session_manifest.mjs';
const uri='mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true';
function fixture() {
  const allowedRoot=resolve('analysis/unreal/session-test'),directory=resolve(allowedRoot,'fixture-run');
  const manifest={schemaVersion:2,mode:'isolated-native-session-test',pid:1234,address:'http://127.0.0.1:7465',port:7465,
    mongoDatabase:'hczs_test_ue_'+'a'.repeat(32),mongoEndpoint:'127.0.0.1:27027',mongoUriSha256:digest(uri),
    runId:'11111111-1111-1111-1111-111111111111',databaseIdentity:'22222222-2222-2222-2222-222222222222',
    processIdentity:'33333333-3333-3333-3333-333333333333',processIndex:0,recordDirectory:directory,tracePath:resolve(directory,'http-trace.jsonl'),
    preserveDatabase:true,faults:false,controlToken:'a'.repeat(48)};
  const manifestText=JSON.stringify(manifest),hash=digest(manifestText);
  const stopped={stopped:true,databaseDropped:false,mongoDatabase:manifest.mongoDatabase,runId:manifest.runId,databaseIdentity:manifest.databaseIdentity,
    processIdentity:manifest.processIdentity,processIndex:0,manifestSha256:hash,time:1234};
  const identity={_id:'identity',schemaVersion:1,mode:manifest.mode,runId:manifest.runId,databaseIdentity:manifest.databaseIdentity,
    mongoDatabase:manifest.mongoDatabase,recordDirectory:directory,mongoUriSha256:digest(uri),activeManifestSha256:hash,firstManifestSha256:hash,
    processIdentity:manifest.processIdentity,processIndex:0,lifecycle:'stopped'};
  return {manifest,manifestText,manifestPath:resolve(directory,'server.json'),allowedRoot,stopped,mongoUri:uri,identity,hash};
}
test('a preserved generated test run can be authenticated for resume',()=>{const f=fixture();assert.equal(validateResumeManifest(f).hash,f.hash);assert.doesNotThrow(()=>validateDatabaseIdentity(f.identity,f.manifest,f.hash));});
test('arbitrary databases, primary ports and changed endpoints are rejected before connection',()=>{
  for(const edit of [m=>m.mongoDatabase='hczs',m=>m.port=7460,m=>m.mongoEndpoint='localhost:27017',m=>m.schemaVersion=1,m=>m.faults=true]){
    const f=fixture();edit(f.manifest);assert.throws(()=>validateResumeManifest(f));
  }
  for(const value of ['mongodb://localhost:27027/?replicaSet=hczs-local&directConnection=true','mongodb://127.0.0.1:27027/hczs?replicaSet=hczs-local&directConnection=true',
    uri+'&readPreference=secondary','mongodb://user:password@127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true'])assert.throws(()=>validateMongoUri(value));
});
test('a copied or edited manifest and missing preserved stop cannot reopen a database',()=>{
  for(const edit of [f=>f.manifestText+=' ',f=>f.stopped.databaseDropped=true,f=>f.stopped.processIdentity=f.manifest.runId,
    f=>f.manifest.preserveDatabase=false,f=>f.manifestPath=resolve(f.allowedRoot,'another','server.json'),f=>f.manifestPath=resolve('server.json')]){
    const f=fixture();edit(f);assert.throws(()=>validateResumeManifest(f));
  }
});
test('database identity, exact manifest hash and stopped lifecycle all have to agree',()=>{
  for(const edit of [i=>i.runId='another',i=>i.databaseIdentity='another',i=>i.activeManifestSha256='b'.repeat(64),i=>i.lifecycle='running',i=>i.processIndex=1]){
    const f=fixture();edit(f.identity);assert.throws(()=>validateDatabaseIdentity(f.identity,f.manifest,f.hash));
  }
});
test('the UI resume requires initialized schemas and exactly one matching profile and battle',()=>{
  const f=fixture(),p=f.manifest.runId,b=f.manifest.databaseIdentity;
  const input={names:REQUIRED_COLLECTIONS,profile:{_id:p,schemaVersion:1,revision:1},battle:{id:b,profile_id:p,schemaVersion:1,revision:3},
    config:{_id:'config',schemaVersion:1,revision:1},release:{_id:0,schemaVersion:1},profileCount:1,battleCount:1,creationCount:1};
  assert.deepEqual(validateResumeCollections(input),{profileId:p,battleId:b,revision:3});
  for(const edit of [v=>v.names=['profiles'],v=>v.profileCount=2,v=>v.battleCount=0,v=>v.creationCount=2,v=>v.battle.profile_id=b,v=>v.release._id=1]){
    const modified=structuredClone(input);edit(modified);assert.throws(()=>validateResumeCollections(modified));
  }
});
test('actual live Node/database identity must match the manifest before persisted reads',()=>{
  const f=fixture(),identity={schemaVersion:1,mode:'isolated-native-session-test-identity',readOnly:true,databaseLifecycle:'running',
    ...Object.fromEntries(['pid','port','mongoDatabase','mongoEndpoint','runId','databaseIdentity','processIdentity','processIndex'].map(k=>[k,f.manifest[k]])),manifestSha256:f.hash};
  assert.equal(validateLiveTestIdentity(identity,f.manifest,f.manifestText),identity);
  for(const edit of [i=>i.pid++,i=>i.databaseIdentity=f.manifest.runId,i=>i.processIdentity=f.manifest.runId,
    i=>i.manifestSha256='b'.repeat(64),i=>i.databaseLifecycle='stopped',i=>i.readOnly=false,i=>i.mongoDatabase='hczs']){
    const changed=structuredClone(identity);edit(changed);assert.throws(()=>validateLiveTestIdentity(changed,f.manifest,f.manifestText));
  }
  const main={...f.manifest,port:7460,address:'http://127.0.0.1:7460'};
  assert.throws(()=>validateLiveTestIdentity({...identity,port:7460},main,JSON.stringify(main)));
});
test('cleanup can only drop the current owned generated test database',()=>{
  const f=fixture(),ownership={databaseName:f.manifest.mongoDatabase,runId:f.manifest.runId,databaseIdentity:f.manifest.databaseIdentity,processIdentity:f.manifest.processIdentity};
  assert.doesNotThrow(()=>validateOwnedDatabaseForDrop(f.identity,ownership));
  for(const edit of [v=>v.databaseName='hczs',v=>v.runId='another',v=>v.databaseIdentity=f.manifest.runId,v=>v.processIdentity=f.manifest.runId]){
    const changed={...ownership};edit(changed);assert.throws(()=>validateOwnedDatabaseForDrop(f.identity,changed));
  }
  for(const edit of [v=>v.mode='production',v=>v.schemaVersion=0,v=>v.mongoDatabase='hczs']){
    const changed={...f.identity};edit(changed);assert.throws(()=>validateOwnedDatabaseForDrop(changed,ownership));
  }
});
