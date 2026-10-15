// A normal preserved stop may be discarded without resuming an empty UI run.
// No port/database/URI override is accepted; ownership comes from this exact
// tool-generated manifest, live startup journal, stop receipt and Mongo claim.
import { readFile,writeFile,realpath } from 'node:fs/promises';
import { resolve,dirname,basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import mongoose from '../../server/node_modules/mongoose/index.js';
import { validateMongoUri,validateResumeManifest,validateDatabaseIdentity,validateOwnedDatabaseForDrop,REQUIRED_COLLECTIONS,within } from './isolated_session_manifest.mjs';
import { assertProductionMetadata } from './isolated_session_lifecycle.mjs';

const {values}=parseArgs({options:{manifest:{type:'string'}}});
if(!values.manifest)throw Error('Pass the exact stopped empty run --manifest=<server.json>');
const root=fileURLToPath(new URL('../../',import.meta.url)),allowedRoot=await realpath(resolve(root,'analysis/unreal/session-test'));
const manifestPath=await realpath(resolve(values.manifest)),directory=dirname(manifestPath);
if(basename(manifestPath)!=='server.json'||!within(allowedRoot,directory))throw Error('Use only an exact isolated-run server.json');
const localJson=async name=>{const path=await realpath(resolve(directory,name));if(dirname(path)!==directory)throw Error('Lifecycle evidence escapes this exact run');return JSON.parse(await readFile(path,'utf8'));};
const manifestText=await readFile(manifestPath,'utf8'),manifest=JSON.parse(manifestText),stopped=await localJson('stopped.json');
const uri='mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true';validateMongoUri(uri);
const {hash}=validateResumeManifest({manifest,manifestText,manifestPath,allowedRoot,stopped,mongoUri:uri});
if(manifest.processIndex!==0)throw Error('Empty-run cleanup is restricted to the initial normally stopped process');
const startup=await localJson('startup-process-0.json');
if(startup.schemaVersion!==1||startup.mode!=='isolated-session-startup-ownership'||startup.phase!=='stopped'||startup.databaseClaimed!==true
  ||startup.databaseDropped!==false||startup.checkpointPreserved!==true||startup.manifestSha256!==hash
  ||startup.processIndex!==0||startup.resumed!==false||startup.pid!==manifest.pid||startup.port!==manifest.port||startup.runId!==manifest.runId||startup.databaseIdentity!==manifest.databaseIdentity
  ||startup.processIdentity!==manifest.processIdentity||startup.mongoDatabase!==manifest.mongoDatabase||startup.recordDirectory!==manifest.recordDirectory
  ||startup.mongoUriSha256!==manifest.mongoUriSha256||startup.mongoEndpoint!==manifest.mongoEndpoint
  ||!startup.phases?.some(p=>p.phase==='running'&&p.databaseClaimed===true)
  ||startup.phases.at(-1)?.phase!=='stopped')throw Error('The normally stopped run lacks its exact live ownership journal');
const connection=mongoose.createConnection(uri,{dbName:manifest.mongoDatabase,serverSelectionTimeoutMS:5000});connection.on('error',()=>{});
try {
  await connection.asPromise();
  const identity=await connection.db.collection('hczs_ue_test_identity').findOne({_id:'identity'});
  validateDatabaseIdentity(identity,manifest,hash);
  validateOwnedDatabaseForDrop(identity,{databaseName:connection.name,runId:manifest.runId,databaseIdentity:manifest.databaseIdentity,processIdentity:manifest.processIdentity});
  assertProductionMetadata(await connection.db.collection('hczs_metadata').findOne({_id:'schema'}));
  const names=(await connection.db.listCollections({}, {nameOnly:true}).toArray()).map(row=>row.name);
  if(names.some(name=>!REQUIRED_COLLECTIONS.includes(name)))throw Error('Unrecognized collections in the empty test run; refusing cleanup');
  const emptyCollections=['profiles','hczs_battles','hczs_battle_creations','hczs_battle_commands','hall_states','hall_requests','hczs_admin_requests','hczs_admin_logs'];
  const counts=Object.fromEntries(await Promise.all(emptyCollections.map(async name=>[name,await connection.db.collection(name).countDocuments()])));
  if(Object.values(counts).some(count=>count!==0))throw Error('Only a test run with zero profiles, battles, creations and player/operator commands may be discarded');
  // Re-read the claim directly before the delete. A resumed/changed owner is
  // never deleted, even if a stale filesystem receipt still looks valid.
  const current=await connection.db.collection('hczs_ue_test_identity').findOne({_id:'identity'});
  validateDatabaseIdentity(current,manifest,hash);
  validateOwnedDatabaseForDrop(current,{databaseName:connection.name,runId:manifest.runId,databaseIdentity:manifest.databaseIdentity,processIdentity:manifest.processIdentity});
  await connection.dropDatabase();
  const result={schemaVersion:1,mode:'owned-empty-isolated-session-cleanup',passed:true,databaseDropped:true,mongoDatabase:manifest.mongoDatabase,
    runId:manifest.runId,databaseIdentity:manifest.databaseIdentity,processIdentity:manifest.processIdentity,manifestSha256:hash,counts,time:Date.now()};
  await writeFile(resolve(directory,'empty-cleanup.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
} finally {await connection.close().catch(()=>{});}
