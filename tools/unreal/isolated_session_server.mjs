// Independent generated Mongo database + loopback proxy for actual UE native HTTP tests.
// Never opens a user-selected database; faults are deterministic test transport behavior.
import { createServer } from 'node:http';
import { randomUUID, randomBytes } from 'node:crypto';
import { mkdir, writeFile, appendFile, access, readFile, realpath, rename } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { setTimeout as waitForResponseDelay } from 'node:timers/promises';
import { createApp } from '../../server/src/app.js';
import mongoose from '../../server/node_modules/mongoose/index.js';
import { IDENTITY_COLLECTION, digest, isTestPort, isGeneratedDatabase, within, validateMongoUri,
  validateResumeManifest, validateDatabaseIdentity, validateResumeCollections, validateOwnedDatabaseForDrop, resolveMainlineOption, resolveMainlineFaultOption } from './isolated_session_manifest.mjs';
import { MainlineFaultSequence } from './isolated_mainline_faults.mjs';
import { MongoProfileStore } from '../../server/src/database/mongo-profiles.js';
import { MongoBattleStore } from '../../server/src/database/mongo-battles.js';
import { initializeFreshTestDatabase, assertProductionMetadata } from './isolated_session_lifecycle.mjs';
import { projectVisualTimingReceipt } from './visual_timing_receipt.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const { values } = parseArgs({ options: { port: { type: 'string' },
  'record-directory': { type: 'string' }, faults: { type: 'boolean', default: false },
  'card-response-delay-ms': { type: 'string' },
  'reject-first-play': { type: 'boolean', default: false },
  mainline: { type: 'boolean' },
  'mainline-faults': { type: 'boolean', default: false },
  'preserve-database': { type: 'boolean', default: false }, 'resume-manifest': { type: 'string' } } });
function parseCardResponseDelayMs(value) {
  if (!/^\d+$/.test(String(value)) || !Number.isSafeInteger(Number(value)) || Number(value) > 5000)
    throw Error('--card-response-delay-ms must be an integer from 0 to 5000');
  return Number(value);
}
const requestedCardResponseDelayMs = parseCardResponseDelayMs(values['card-response-delay-ms'] ?? '0');
const rejectFirstPlay = values['reject-first-play'] === true;
if (rejectFirstPlay && values.faults) throw Error('--reject-first-play cannot be combined with --faults');
const resumeMode = Boolean(values['resume-manifest']);
const mainlineFaults = resolveMainlineFaultOption(values['mainline-faults'], {mainlineEnabled:values.mainline===true,faults:values.faults,resume:resumeMode});
if(resumeMode && (values.port || values['record-directory'] || values.faults || values['reject-first-play'] || values['card-response-delay-ms'] !== undefined || values.mainline !== undefined))throw Error('Resume inherits its test port, directory, response delay and mainline mode; overrides and faults are forbidden');
const allowedRoot = resolve(root, 'analysis/unreal/session-test');
const previousManifestPath = resumeMode ? resolve(values['resume-manifest']) : null;
const recordDirectory = resumeMode ? dirname(previousManifestPath) : resolve(values['record-directory'] ?? resolve(allowedRoot, randomUUID()));
if (!within(allowedRoot, recordDirectory)) throw Error('Use a child folder inside analysis/unreal/session-test');
await mkdir(recordDirectory, { recursive: true });
if(!within(await realpath(allowedRoot), await realpath(recordDirectory)))throw Error('Test directory resolves outside the isolated run root');
if(!resumeMode)await access(resolve(recordDirectory, 'server.json')).then(() => { throw Error('Do not overwrite an existing test-run manifest'); }, error => { if (error.code !== 'ENOENT') throw error; });
const mongoUri = process.env.HCZS_TEST_MONGODB_URI ?? 'mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true';
const mongoUriSha256 = validateMongoUri(mongoUri);
let previousManifest, previousManifestText, previousManifestHash, previousCheckpoint;
if(resumeMode) {
  previousManifestText=await readFile(previousManifestPath,'utf8'); previousManifest=JSON.parse(previousManifestText);
  const stopped=JSON.parse(await readFile(resolve(recordDirectory,'stopped.json'),'utf8'));
  previousManifestHash=validateResumeManifest({manifest:previousManifest,manifestText:previousManifestText,manifestPath:previousManifestPath,allowedRoot,stopped,mongoUri}).hash;
}
const port = resumeMode ? previousManifest.port : Number(values.port ?? '7464');
if(!isTestPort(port))throw Error('Choose a dedicated test port');
const cardResponseDelayMs = resumeMode ? parseCardResponseDelayMs(previousManifest.cardResponseDelayMs ?? 0) : requestedCardResponseDelayMs;
const mainlineEnabled = resolveMainlineOption(values.mainline, previousManifest);
const mongoDatabase = resumeMode ? previousManifest.mongoDatabase : `hczs_test_ue_${randomUUID().replaceAll('-', '')}`;
const runId=resumeMode ? previousManifest.runId : randomUUID();
const databaseIdentity=resumeMode ? previousManifest.databaseIdentity : randomUUID();
const processIdentity=randomUUID(), processIndex=resumeMode ? previousManifest.processIndex+1 : 0;
const controlToken = randomBytes(24).toString('hex');
const tracePath = resolve(recordDirectory, 'http-trace.jsonl');
const manifestPath = resolve(recordDirectory, 'server.json');
let app, proxy, closing = false, identityClaimed=false, manifestHash;
const startupPath=resolve(recordDirectory,resumeMode?`startup-process-${processIndex}-${processIdentity}.json`:'startup-process-0.json');
let startupPhase='allocated';
const startupJournal={schemaVersion:1,mode:'isolated-session-startup-ownership',pid:process.pid,port,runId,databaseIdentity,
  processIdentity,processIndex,mongoDatabase,mongoEndpoint:'127.0.0.1:27027',mongoUriSha256,recordDirectory,
  preserveDatabase:values['preserve-database'],mainlineEnabled,mainlineFaults,resumed:resumeMode,allocatedAt:Date.now(),phase:startupPhase,databaseClaimed:false,
  phases:[{phase:startupPhase,time:Date.now(),databaseClaimed:false}]};
// The persistent exclusive first journal also prevents two initial runners
// from publishing conflicting manifests into the same report directory.
await writeFile(startupPath,JSON.stringify(startupJournal,null,2),{flag:'wx'});
async function journal(phase,extra={}) {
  startupPhase=phase;Object.assign(startupJournal,extra,{phase,databaseClaimed:identityClaimed,updatedAt:Date.now()});
  startupJournal.phases.push({phase,time:Date.now(),databaseClaimed:identityClaimed});
  await writeFile(startupPath+'.tmp',JSON.stringify(startupJournal,null,2));await rename(startupPath+'.tmp',startupPath);
}
const checks = { droppedCreation: false, creationRetrySamePayload: false, historicalReceiptReadFresh: false,
  droppedConfirmedRead: false, retryConfirmedReadWithoutNewMutation: false, injectedRevisionConflict: false, rejectedFirstPlay: false };
const mainlineFaultSequence=new MainlineFaultSequence(mainlineFaults);
let firstCreation, historicalBattleId, postCreationDelivered = false, delayedReadBattle = null;
let creationMutationCount = 0;
const note = value => appendFile(tracePath, JSON.stringify({ time: Date.now(), processIdentity, processIndex, ...value }) + '\n');
async function deliverResponse(response, result, event) {
  const delayMs = event.method === 'POST' && /\/battles\/[0-9a-f-]{36}\/actions$/.test(event.path)
    && event.type === 'play-card' && result.status === 200 ? cardResponseDelayMs : 0;
  if (delayMs === 0) {
    response.writeHead(result.status, {'content-type':'application/json; charset=utf-8'}).end(result.text);
    return;
  }
  // Upstream has already returned the committed receipt. Only the wire response waits.
  const timing = { requestId: event.requestId, path: event.path, type: event.type,
    revision: event.revision, battleId: event.battleId, status: result.status,
    receivedAtUnixMs: event.receivedAtUnixMs, upstreamCompletedAtUnixMs: event.upstreamCompletedAtUnixMs,
    delayMs, delayStartedAtUnixMs: Date.now() };
  await note({phase:'ue-response-delayed', ...timing});
  await waitForResponseDelay(delayMs);
  if (response.destroyed) {
    await note({phase:'ue-response-delivery-aborted', ...timing, abortedAtUnixMs:Date.now()});
    return;
  }
  const finished = new Promise(resolveFinish => {
    response.once('finish', () => resolveFinish(true));
    response.once('close', () => resolveFinish(false));
  });
  response.writeHead(result.status, {'content-type':'application/json; charset=utf-8'}).end(result.text);
  const delivered = await finished;
  await note({phase:delivered ? 'ue-response-delivered' : 'ue-response-delivery-aborted', ...timing,
    ...(delivered ? {deliveredAtUnixMs:Date.now()} : {abortedAtUnixMs:Date.now()})});
}
async function identityConnection() {
  const connection=mongoose.createConnection(mongoUri,{dbName:mongoDatabase,serverSelectionTimeoutMS:5000});connection.on('error',()=>{});
  try{return await connection.asPromise();}catch(error){await connection.close().catch(()=>{});throw error;}
}
async function claimDatabase() {
  if(!resumeMode) {
    await initializeFreshTestDatabase({mongoUri,identity:{_id:'identity',schemaVersion:1,mode:'isolated-native-session-test',runId,databaseIdentity,mongoDatabase,
      recordDirectory,mongoUriSha256,processIdentity,processIndex,mainlineEnabled,mainlineFaults,lifecycle:'starting',createdAt:Date.now()},onPhase:async phase=>{
        if(phase==='identity-claimed')identityClaimed=true;
        await journal(phase);
      }});
    return;
  }
  const c=await identityConnection();
  try {
    const names=(await c.db.listCollections({}, {nameOnly:true}).toArray()).map(row=>row.name);
    const identities=c.db.collection(IDENTITY_COLLECTION);
    {
      validateDatabaseIdentity(await identities.findOne({_id:'identity'}),previousManifest,previousManifestHash);
      assertProductionMetadata(await c.db.collection('hczs_metadata').findOne({_id:'schema'}));
      const [profile,battle,config,release,profileCount,battleCount,creationCount]=await Promise.all([
        c.db.collection('profiles').findOne({}),c.db.collection('hczs_battles').findOne({}),c.db.collection('hczs_admin_config').findOne({_id:'config'}),
        c.db.collection('hczs_admin_releases').findOne({_id:0}),c.db.collection('profiles').countDocuments(),c.db.collection('hczs_battles').countDocuments(),c.db.collection('hczs_battle_creations').countDocuments()]);
      const checkpoint=validateResumeCollections({names,profile,battle,config,release,profileCount,battleCount,creationCount,mainlineEnabled});
      // Use the production store decoders for hashes, tagged numbers, state and identity.
      new MongoProfileStore(c).map(profile);
      const decoded=new MongoBattleStore(c).decode(battle);
      previousCheckpoint={...checkpoint,stateSha256:battle.state_hash,scenarioSha256:battle.scenario_hash,actionIndex:decoded.state.actionIndex};
      const claimed=await identities.updateOne({_id:'identity',activeManifestSha256:previousManifestHash,processIdentity:previousManifest.processIdentity,lifecycle:'stopped'},
        {$set:{lifecycle:'starting',processIdentity,processIndex}});
      if(claimed.modifiedCount!==1)throw Error('The preserved test database has already been claimed by another runner');
    }
    identityClaimed=true;
    await journal('identity-claimed');
  } finally { await c.close(); }
}
async function independentDrop({failedInitialStartup=false}={}) {
  // Preservation is for a successfully published checkpoint lifecycle. A failed
  // first startup has no UI checkpoint or resumable manifest and must not leak
  // the fresh, still-owned generated database (for example, on a port conflict).
  if (values['preserve-database'] && !failedInitialStartup) return;
  if (failedInitialStartup && resumeMode) throw Error('A failed resume must preserve its checkpoint database');
  if (!isGeneratedDatabase(mongoDatabase)||!identityClaimed) throw Error('Unexpected database identity');
  const connection = await identityConnection();
  try {
    const identity=await connection.db.collection(IDENTITY_COLLECTION).findOne({_id:'identity'});
    validateOwnedDatabaseForDrop(identity,{databaseName:connection.name,runId,databaseIdentity,processIdentity});
    await connection.dropDatabase();
  }
  finally { await connection.close(); }
}
async function close() {
  if (closing) return; closing = true;
  if (proxy) await new Promise(resolveClose => { proxy.close(resolveClose); setTimeout(() => proxy.closeAllConnections(), 1000).unref(); });
  if (app) await app.close();
  await writeFile(resolve(recordDirectory, 'fault-checks.json'), JSON.stringify({ faultMode: values.faults, checks, passed: !values.faults || Object.values(checks).every(Boolean) }, null, 2));
  if(mainlineFaults)await writeFile(resolve(recordDirectory,'mainline-fault-checks.json'),JSON.stringify(mainlineFaultSequence.snapshot(),null,2));
  const connection=await identityConnection();
  try {
    const stopped=await connection.db.collection(IDENTITY_COLLECTION).updateOne({_id:'identity',runId,databaseIdentity,processIdentity,activeManifestSha256:manifestHash},{$set:{lifecycle:'stopped',stoppedAt:Date.now()}});
    if(stopped.modifiedCount!==1)throw Error('Test database stop identity changed');
  } finally {await connection.close();}
  await note({phase:'test-server-stopped',manifestSha256:manifestHash,preservedDatabase:values['preserve-database']});
  await independentDrop();
  await journal('stopped',{databaseDropped:!values['preserve-database'],checkpointPreserved:values['preserve-database']});
  const stopped={stopped:true,databaseDropped:!values['preserve-database'],mongoDatabase,runId,databaseIdentity,processIdentity,processIndex,manifestSha256:manifestHash,time:Date.now()};
  await writeFile(resolve(recordDirectory,`stopped-process-${processIndex}.json`),JSON.stringify(stopped,null,2));
  await writeFile(resolve(recordDirectory,'stopped.json'),JSON.stringify(stopped,null,2));
  process.exitCode = 0;
}
try {
  await claimDatabase();
  await journal('app-initializing');
  app = await createApp({ port: 0, storage: 'mongodb', mongoUri, mongoDatabase,
    dataDirectory: resolve(root, 'analysis/game-data'), tutorialDirectory: resolve(root, 'analysis/first-encounter'), cityPreview: true,
    ...(mainlineEnabled ? { mainlineDirectory: resolve(root, 'analysis/mainline-progression') } : {}),
    allowedOrigins: [], log: message => note({ phase: 'backend-error', message: String(message).slice(0, 500) }) });
  async function upstream(path, method, body) {
    const result = await fetch(app.address + path, { method, headers: { accept: 'application/json', ...(body ? {'content-type':'application/json'} : {}) },
      ...(body ? { body } : {}), signal: AbortSignal.timeout(15000) });
    const text = await result.text(); let json; try { json = JSON.parse(text); } catch {}
    return { status: result.status, text, json };
  }
  proxy = createServer(async (request, response) => {
    // Capture arrival before reading any body or waiting for the backend. A
    // receipt timestamp cannot prove that a UI intent was sent after release.
    const receivedAtUnixMs=Date.now();
    try {
      if (request.url === '/__hczs_test_control/identity' && request.method === 'GET') {
        if (request.headers.authorization !== `Bearer ${controlToken}`) { response.writeHead(403).end(); return; }
        if (closing) { response.writeHead(503).end(); return; }
        const connection=await identityConnection();
        try {
          const identity=await connection.db.collection(IDENTITY_COLLECTION).findOne({_id:'identity'});
          validateOwnedDatabaseForDrop(identity,{databaseName:connection.name,runId,databaseIdentity,processIdentity});
          if(identity.lifecycle!=='running'||identity.activeManifestSha256!==manifestHash||(identity.mainlineEnabled??false)!==mainlineEnabled||
            (identity.mainlineFaults??false)!==mainlineFaults)throw Error('Live database claim differs from the published manifest');
          response.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({schemaVersion:1,mode:'isolated-native-session-test-identity',readOnly:true,
            pid:process.pid,port,mongoDatabase,mongoEndpoint:'127.0.0.1:27027',runId,databaseIdentity,processIdentity,processIndex,
            manifestSha256:manifestHash,databaseLifecycle:identity.lifecycle,mainlineEnabled,mainlineFaults}));
        } finally {await connection.close();}
        return;
      }
      if (request.url === '/__hczs_test_control/stop' && request.method === 'POST') {
        if (request.headers.authorization !== `Bearer ${controlToken}`) { response.writeHead(403).end(); return; }
        response.writeHead(200, {'content-type':'application/json'}).end('{"stopping":true}');
        setTimeout(() => close().catch(error => { console.error(error.message); process.exitCode = 1; }), 25); return;
      }
      if (closing) { response.writeHead(503).end(); return; }
      if (!request.url.startsWith('/api/rebuild/v1/')) { response.writeHead(404).end(); return; }
      const chunks = []; let count = 0;
      for await (const chunk of request) { count += chunk.length; if (count > 64 * 1024) throw Error('Test request body exceeds limit'); chunks.push(chunk); }
      const body = Buffer.concat(chunks).toString('utf8'); let input; if (body) input = JSON.parse(body);
      const isCreate = request.method === 'POST' && /^\/api\/rebuild\/v1\/profiles\/[0-9a-f-]{36}\/battles$/.test(request.url);
      const isAction = request.method === 'POST' && /\/battles\/[0-9a-f-]{36}\/actions$/.test(request.url);
      const isStateRead = request.method === 'GET' && /\/battles\/[0-9a-f-]{36}$/.test(request.url);
      if (rejectFirstPlay && isAction && input?.type === 'play-card' && !checks.rejectedFirstPlay) {
        checks.rejectedFirstPlay = true;
        const text = JSON.stringify({ error: { code: 'REVISION_CONFLICT', message: 'Isolated test rejected this play before commit' } });
        const timing = { requestId: input.requestId, path: request.url, type: 'play-card', instanceId: input.instanceId,
          receivedAtUnixMs, delayMs: cardResponseDelayMs, rejectedBeforeCommit: true };
        await note({ phase: 'ue-request', receivedAtUnixMs, method: request.method, path: request.url, status: 409,
          requestId: input.requestId, expectedRevision: input.expectedRevision, type: input.type, instanceId: input.instanceId,
          rejectedBeforeCommit: true });
        if (cardResponseDelayMs > 0) {
          await note({ phase: 'ue-response-delayed', ...timing, delayStartedAtUnixMs: Date.now() });
          await waitForResponseDelay(cardResponseDelayMs);
        }
        if (!response.destroyed) response.writeHead(409, { 'content-type': 'application/json; charset=utf-8' }).end(text);
        await note({ phase: 'ue-response-delivered', ...timing, deliveredAtUnixMs: Date.now(), status: 409 });
        return;
      }
      if (values.faults && isAction && !checks.injectedRevisionConflict) {
        const battlePath = request.url.replace(/\/actions$/, ''); const current = (await upstream(battlePath, 'GET')).json.battle;
        const playable = current.state.piles.hand.find(id => current.scenario.definition.cards[current.state.cards.find(c => c.instanceId === id).cardId].cost <= current.state.energy);
        const injected = await upstream(request.url, 'POST', JSON.stringify({ requestId: `fault-cas-${randomUUID()}`, expectedRevision: current.revision,
          type: playable ? 'play-card' : 'end-turn', ...(playable ? { instanceId: playable } : {}) }));
        if (injected.status !== 200) throw Error('Could not inject isolated CAS race');
        checks.injectedRevisionConflict = true;
        await note({ phase: 'injected-cas-race', before: current.revision, after: injected.json.battle.revision });
      }
      const result = await upstream(request.url, request.method, body);
      const event = { phase: 'ue-request', receivedAtUnixMs, upstreamCompletedAtUnixMs:Date.now(), method: request.method, path: request.url, bodySha256: digest(body),
        ...(input?.requestId ? { requestId: input.requestId, expectedRevision: input.expectedRevision, type: input.type } : {}),
        ...(typeof input?.instanceId==='string'?{instanceId:input.instanceId}:{}),
        ...(typeof input?.encounterId==='string'?{encounterId:input.encounterId}:{}),
        ...(typeof input?.contentId==='string'?{contentId:input.contentId}:{}),
        status: result.status, replayed: result.json?.replayed, revision: result.json?.battle?.revision ?? result.json?.hall?.revision ?? result.json?.campaign?.revision,
        battleId: result.json?.battle?.id ?? result.json?.settlement?.battleId,profileId:result.json?.profile?.id ?? result.json?.battle?.profileId ?? result.json?.campaign?.profileId,
        ...(isAction && result.status===200 ? projectVisualTimingReceipt(result.json) : {}) };
      const mainlineFault=mainlineFaultSequence.inspect(event);
      if(mainlineFault) {
        const completeBytes=Buffer.from(result.text,'utf8'),partialBytes=completeBytes.subarray(0,Math.min(32,completeBytes.length-1));
        await note({...event,mainlineFault,wireFailure:'truncated-http-body',declaredBytes:completeBytes.length,deliveredBytes:partialBytes.length,
          ...(mainlineFault==='truncate-commit'?{droppedAfterCommit:true}:{droppedAfterRead:true})});
        response.writeHead(200,{'content-type':'application/json; charset=utf-8','content-length':completeBytes.length,connection:'close'});
        response.write(partialBytes);setTimeout(()=>response.destroy(),25);return;
      }
      if (isCreate) creationMutationCount++;
      if (values.faults && isCreate && !checks.droppedCreation && result.status === 201) {
        firstCreation = { requestId: input.requestId, hash: digest(body) }; historicalBattleId = result.json.battle.id;
        const path = request.url + '/' + historicalBattleId + '/actions';
        const advanced = await upstream(path, 'POST', JSON.stringify({ requestId: `fault-advance-${randomUUID()}`, expectedRevision: result.json.battle.revision, type: 'end-turn' }));
        if (advanced.status !== 200) throw Error('Could not advance isolated historical receipt test');
        checks.droppedCreation = true; await note({ ...event, droppedAfterCommit: true, advancedRevision: advanced.json.battle.revision });
        response.destroy(); return;
      }
      if (values.faults && isCreate && firstCreation && result.status === 201 && result.json?.replayed === true) {
        checks.creationRetrySamePayload = firstCreation.requestId === input.requestId && firstCreation.hash === digest(body);
        postCreationDelivered = true;
      }
      if (values.faults && isStateRead && postCreationDelivered && !checks.droppedConfirmedRead && result.status === 200) {
        checks.droppedConfirmedRead = true; delayedReadBattle = { id: result.json.battle.id, count: creationMutationCount };
        const completeBytes = Buffer.from(result.text, 'utf8'); const partialBytes = completeBytes.subarray(0, Math.min(32, completeBytes.length - 1));
        await note({ ...event, droppedAfterRead: true, wireFailure: 'truncated-http-body', declaredBytes: completeBytes.length, deliveredBytes: partialBytes.length });
        // An empty disconnect is transparently retried by libcurl for GET. Send a real
        // incomplete HTTP body so the native client's confirmed-receipt retry path runs.
        response.writeHead(200, {'content-type':'application/json; charset=utf-8', 'content-length':completeBytes.length, connection:'close'});
        response.write(partialBytes);
        setTimeout(() => response.destroy(), 25); return;
      }
      if (values.faults && isStateRead && result.status === 200 && result.json.battle.id === historicalBattleId && result.json.battle.revision > 1)
        checks.historicalReceiptReadFresh = true;
      if (values.faults && isStateRead && result.status === 200 && delayedReadBattle?.id === result.json.battle.id)
        checks.retryConfirmedReadWithoutNewMutation = delayedReadBattle.count === creationMutationCount;
      await note(event); await deliverResponse(response, result, event);
    } catch (error) {
      await note({ phase: 'proxy-error', message: String(error.message).slice(0, 500) });
      if (!response.headersSent) response.writeHead(502, {'content-type':'application/json'}).end('{"error":{"code":"TEST_PROXY_FAILURE","message":"isolated test proxy failed"}}');
      else response.destroy();
    }
  });
  await journal('proxy-listening');
  await new Promise((resolveListen, reject) => { proxy.once('error', reject); proxy.listen(port, '127.0.0.1', resolveListen); });
  const manifest = { schemaVersion: 2, mode: 'isolated-native-session-test', pid: process.pid, address: `http://127.0.0.1:${port}`, port,
    mongoDatabase, mongoEndpoint: '127.0.0.1:27027', mongoUriSha256, runId, databaseIdentity, processIdentity, processIndex,
    preserveDatabase:values['preserve-database'], faults: values.faults, rejectFirstPlay, cardResponseDelayMs, mainlineEnabled, mainlineFaults, controlToken, recordDirectory, tracePath,
    ...(resumeMode?{previousManifestSha256:previousManifestHash,firstManifestSha256:previousManifest.firstManifestSha256??previousManifestHash,
      previousProcessIdentity:previousManifest.processIdentity,previousPid:previousManifest.pid,resumeCheckpoint:previousCheckpoint}: {}) };
  const manifestText=JSON.stringify(manifest,null,2);manifestHash=digest(manifestText);
  const identity=await identityConnection();
  try {
    const ready=await identity.db.collection(IDENTITY_COLLECTION).updateOne({_id:'identity',runId,databaseIdentity,processIdentity,lifecycle:'starting'},
      {$set:{lifecycle:'running',activeManifestSha256:manifestHash,firstManifestSha256:manifest.firstManifestSha256??manifestHash}});
    if(ready.modifiedCount!==1)throw Error('Test server identity changed before publication');
  } finally {await identity.close();}
  if(resumeMode)await writeFile(resolve(recordDirectory,`server-process-${previousManifest.processIndex}.json`),previousManifestText,{flag:'wx'});
  await writeFile(manifestPath+'.tmp',manifestText);await rename(manifestPath+'.tmp',manifestPath);
  await note({phase:'test-server-ready',pid:process.pid,manifestSha256:manifestHash,resumed:resumeMode,mongoDatabase,databaseIdentity,
    ...(resumeMode?{previousManifestSha256:previousManifestHash,previousProcessIdentity:previousManifest.processIdentity,resumeCheckpoint:previousCheckpoint}: {})});
  await journal('running',{manifestSha256:manifestHash});
  console.log(JSON.stringify({ ready: true, pid: process.pid, port, mongoDatabase, manifestPath, faults: values.faults,cardResponseDelayMs,mainlineEnabled,mainlineFaults,resumed:resumeMode,processIndex }));
  process.on('SIGINT', () => close().catch(error => { console.error(error.message); process.exitCode = 1; }));
  process.on('SIGTERM', () => close().catch(error => { console.error(error.message); process.exitCode = 1; }));
} catch (error) {
  const failedPhase=startupPhase;
  let cleanup={databaseDropped:false,checkpointPreserved:resumeMode,identityClaimed};
  try {
    if(proxy)await new Promise(done=>{proxy.close(done);proxy.closeAllConnections();});
    if(app)await app.close();
  } catch(closeError) {cleanup.shutdownError=String(closeError.message).slice(0,500);}
  try {if(identityClaimed) {
    if(!resumeMode) {await independentDrop({failedInitialStartup:true});cleanup.databaseDropped=true;}
    else {
      // A failed resume never deletes the saved checkpoint. Restore only our own
      // startup claim so another explicit retry can use the original manifest.
      const connection=await identityConnection();
      try {await connection.db.collection(IDENTITY_COLLECTION).updateOne({_id:'identity',processIdentity},{$set:{lifecycle:'stopped',
        processIdentity:previousManifest.processIdentity,processIndex:previousManifest.processIndex,activeManifestSha256:previousManifestHash}});}
      finally {await connection.close();}
    }
  }} catch(cleanupError) {cleanup={...cleanup,error:String(cleanupError.message).slice(0,500)};}
  await journal('failed',{failure:{phase:failedPhase,message:String(error.message).slice(0,500)},cleanup});
  await note({phase:'test-server-startup-failed',mongoDatabase,runId,databaseIdentity,failedPhase,cleanup});
  console.error(JSON.stringify({failed:true,startupPath,mongoDatabase,cleanup}));
  throw error;
}
