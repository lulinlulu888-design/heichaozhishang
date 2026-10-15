import { readFile, writeFile, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';
import { inflateSync } from 'node:zlib';
import { isDeepStrictEqual } from 'node:util';
import { validateState } from '../../packages/battle-session/src/index.js';
import { isGeneratedDatabase, isTestPort, validateUIRunningManifest, validateLiveTestIdentity, digest } from './isolated_session_manifest.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const HALL = 'L_ElsaHallFxPreview', BATTLE = 'L_TutorialBattle';
const HD_KEYS = ['energy-icon','end-icon-normal','end-icon-active','shield-icon','deck-icon','card-cost'];
const WORLDLINE_LAYOUT_SHA = '8afc937db8a3cc13ddde0bc771995734895b590828b70454444d7b9e282007ef';
const WORLDLINE_SOURCE_IDS = ['standalone_d39d38f1ca5d191311abf53a','standalone_eb7f8c6b04784e4565579e7b','standalone_2f76a1a1318fd9d9d0c334e3',
  'd7319d96886bbe4d58eb4524','80c8b62820653c892c6f4104','a479406985055a836d73d810','8f96dcd8fa42d39c21e9a396',
  'standalone_ac06da80916e1b49cf2bb923','d6492d6903eb707e6b4ee8f9','1a3385b920e937f28cfba72a','a2d0a1bae517808aba3d2034','208e7c0ec0a8420948f63153'];
const guardedActions = new Set(['create-profile','new-battle','challenge-again','play-card','end-turn','hall','worldline',
  'local-battle-preview','back','select-profile','select-encounter','continue-battle','refresh-battle',
  'tap-card','invalid-target-card-drag','outside-card-drag','cancel-card-drag']);
const NEGATIVE_DRAGS = {'tap-card':'tap','invalid-target-card-drag':'invalid-target','outside-card-drag':'outside','cancel-card-drag':'cancel'};
const SHA = /^[0-9a-f]{64}$/;
const shortMap = value => typeof value === 'string' ? value.split('/').at(-1).replace(/^UEDPIE_\d+_/, '') : '';
const records = value => Array.isArray(value) ? value : [];
const integers = (value, min = 0) => Number.isSafeInteger(value) && value >= min;
const same = (a,b) => isDeepStrictEqual(a,b);

/** Authoritative server GET projection, preserving tagged decimal text and hand order. */
export function projectServerBattle(battle) {
  if (!battle || !UUID.test(battle.id) || !UUID.test(battle.profileId) || !integers(battle.revision,1)) throw Error('Invalid persisted battle identity');
  const definition = battle.scenario?.definition, state = validateState(definition, battle.state);
  if (!same(state, battle.state) || state.actionIndex + 1 !== battle.revision) throw Error('Invalid persisted revision/state relation');
  const registry = new Map(state.cards.map(card => [card.instanceId, card.cardId]));
  return { id:battle.id, profileId:battle.profileId, revision:battle.revision, definitionId:state.definitionId,
    encounterId:battle.scenario.encounterId ?? '',status:state.status,round:state.round,energy:state.energy,
    playerHp:state.player.hp.decimal,enemyHp:state.enemy.hp.decimal,playerShield:state.player.shield.decimal,enemyShield:state.enemy.shield.decimal,
    drawCount:state.piles.draw.length,discardCount:state.piles.discard.length,
    hand:state.piles.hand.map(instanceId => { const cardId=registry.get(instanceId), card=definition.cards[cardId]; return {instanceId,cardId,cost:card.cost,name:card.name}; }) };
}
const projectionKeys = ['id','profileId','revision','definitionId','encounterId','status','round','energy','playerHp','enemyHp','playerShield','enemyShield','drawCount','discardCount','hand'];
function projected(value) { return value && typeof value === 'object' && !Array.isArray(value) ? Object.fromEntries(projectionKeys.map(key => [key,value[key]])) : null; }
function paintedSprites(paint) {
  const source = paint?.actualPaintedSprites;
  if (Array.isArray(source)) return source.map(row => typeof row === 'string' ? {key:row,asset:paint.paintResources?.[row]} : {key:row.key ?? row.id,asset:row.asset ?? row.resource});
  if (source && typeof source === 'object') return Object.entries(source).map(([key,asset]) => ({key,asset:typeof asset === 'string' ? asset : asset?.asset ?? asset?.resource}));
  return [];
}
function paintValid(paint, map) {
  return paint?.mode === 'actual-nativepaint-and-slate-pointer-observation' && integers(paint.paintSerial,1)
    && shortMap(paint.map) === map && paint.sourceChineseFont === true && Array.isArray(paint.renderedTexts);
}
function worldlinePaintValid(paint) {
  const sprites=paintedSprites(paint),keys=sprites.map(row=>row.key);
  return paintValid(paint,HALL) && paint.phase===2 && paint.battleScene===false && paint.originalSourcePage===true
    && paint.sourceReady===true && paint.visible===true && paint.pending===false
    && paint.progressAvailable===false && paint.chapterInstances===0 && paint.readOnlySourceInspection===false
    && paint.sourceLayoutSha256===WORLDLINE_LAYOUT_SHA && records(paint.renderedTexts).includes('世界线')
    && records(paint.renderedTexts).includes('本地战斗预览') && keys.length===12 && new Set(keys).size===12
    && WORLDLINE_SOURCE_IDS.every(id=>sprites.some(row=>row.key===id && row.asset===`/Game/Recovered/Worldline/UI/Sprites/T_${id}.T_${id}`));
}
function worldlineRouteValid(report, stage, afterAction) {
  const actions=records(report?.actions),shots=records(report?.screenshots).filter(s=>s.stage===stage);
  const entries=actions.map((a,i)=>({a,i})).filter(({a})=>a.action==='worldline');
  const previews=actions.map((a,i)=>({a,i})).filter(({a})=>a.action==='local-battle-preview');
  if(entries.length!==1||previews.length!==1||shots.length!==1)return false;
  const {a:entry,i:entryIndex}=entries[0],{a:preview,i:previewIndex}=previews[0],shot=shots[0];
  const adapterIndex=actions.findIndex(a=>a.action===afterAction);
  const selectionIndex=actions.findIndex(a=>a.action===(afterAction==='select-encounter'?'create-profile':'select-profile'));
  const battleCreateIndex=actions.findIndex(a=>a.action==='new-battle');
  return selectionIndex>=0 && selectionIndex<entryIndex && entryIndex<previewIndex && previewIndex<adapterIndex
    && (afterAction!=='select-encounter'||adapterIndex<battleCreateIndex) && entry.value==='' && preview.value===''
    && entry.surface==='hall' && shortMap(entry.map)===HALL && entry.phase===2 && entry.paint?.originalSourcePage!==true
    && preview.surface==='worldline' && shortMap(preview.map)===HALL && preview.phase===2 && worldlinePaintValid(preview.paint)
    && shot.surface==='worldline' && shortMap(shot.worldMap)===HALL && shot.actionCount===previewIndex
    && worldlinePaintValid(shot.paint) && shot.paint.paintSerial<=preview.paint.paintSerial
    && entry.paint.profileId===report.profileId && preview.paint.profileId===report.profileId && shot.paint.profileId===report.profileId;
}
function sceneValid(shot) {
  const s = shot.scene ?? shot.paint?.scene;
  return s?.ready === true && s.canPresentBattle === true && s.playerId === '1' && s.enemyId === '991'
    && typeof s.playerMesh === 'string' && s.playerMesh.startsWith('/Game/Recovered/Battle/Elsa/')
    && typeof s.enemyMesh === 'string' && s.enemyMesh.startsWith('/Game/Recovered/Battle/Cube/')
    && s.playerMesh === s.expectedPlayerMesh && s.enemyMesh === s.expectedEnemyMesh && s.cameraTag === 'HCZSBattleCamera' && s.cameraReady === true
    && s.playerLeftEnemyRight === true && Number.isFinite(s.playerScreenX) && Number.isFinite(s.enemyScreenX) && s.playerScreenX < s.enemyScreenX
    && (Number(shot.paint?.serverPlayerHp) === 0 || s.playerVisible === true) && (Number(shot.paint?.serverEnemyHp) === 0 || s.enemyVisible === true);
}

const pointValid=p=>Array.isArray(p)&&p.length===2&&p.every(v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<1000000);
const rectValid=r=>Array.isArray(r)&&r.length===4&&r.every(v=>typeof v==='number'&&Number.isFinite(v))&&r[0]<r[2]&&r[1]<r[3];
const insideRect=(p,r)=>pointValid(p)&&rectValid(r)&&p[0]>=r[0]&&p[0]<=r[2]&&p[1]>=r[1]&&p[1]<=r[3];
const insideCanvas=p=>pointValid(p)&&p[0]>=0&&p[0]<=1280&&p[1]>=0&&p[1]<=720;
function gestureTraceValid(row,cardIds,battleId) {
  const g=row?.pointerObservation?.lastGesture,events=records(g?.events);
  const before=row?.paint?.lastGesture;
  if(row?.inputSource!=='slate-drag'||row.surface!=='session'||shortMap(row.map)!==BATTLE||row.phase!==3||row.controlHit!==true
    ||!['mouse','touch'].includes(row.input)||!integers(row.revision,1)||!integers(row.startedAtUnixMs,1)||!integers(row.finishedAtUnixMs,row.startedAtUnixMs)
    ||!integers(g?.serial,1)||!integers(before?.serial)||g.serial<=before.serial||g.cardInstanceId!==row.value
    ||g.cardId!==cardIds.get(row.value)||typeof g.cardId!=='string'||g.battleId!==battleId||g.startRevision!==row.revision
    ||g.isTouch!==(row.input==='touch')||!integers(g.pointerIndex)||![5,30].includes(g.threshold)||g.active!==false||typeof g.lostCapture!=='boolean'
    ||events.length<2||events.length>256||events[0]?.kind!=='start')return false;
  const start=events[0].point;
  return insideCanvas(start)&&events.every((e,i)=>['start','move','release','cancel'].includes(e?.kind)&&pointValid(e.point)
    &&typeof e.targetHit==='boolean'&&typeof e.upwardDelta==='number'&&Number.isFinite(e.upwardDelta)
    &&Math.abs(e.upwardDelta-(start[1]-e.point[1]))<0.001&&integers(e.atUnixMs,row.startedAtUnixMs)&&e.atUnixMs<=row.finishedAtUnixMs
    &&(i===0||e.atUnixMs>=events[i-1].atUnixMs)&& (i===0?e.kind==='start':e.kind!=='start'))
    &&events.slice(1,-1).every(e=>e.kind==='move');
}
function completeProjection(value) {
  const p=projected(value),decimal=v=>typeof v==='string'&&/^\d+(?:\.\d+)?$/.test(v);
  return p&&UUID.test(p.id)&&UUID.test(p.profileId)&&integers(p.revision,1)&&typeof p.definitionId==='string'&&p.definitionId.length>0
    &&p.encounterId==='tutorial-5000'&&['player-turn','won','lost'].includes(p.status)&&integers(p.round,1)&&integers(p.energy)
    &&decimal(p.playerHp)&&decimal(p.enemyHp)&&decimal(p.playerShield)&&decimal(p.enemyShield)&&integers(p.drawCount)&&integers(p.discardCount)
    &&Array.isArray(p.hand)&&p.hand.every(c=>c&&typeof c.instanceId==='string'&&typeof c.cardId==='string'&&integers(c.cost)&&typeof c.name==='string');
}
function targetProjectionValid(g,expectedEnemyMesh) {
  const p=g?.targetProjection;
  return p?.valid===true&&p.source==='native-bounds-eight-corners'&&p.actorTag==='HCZSBattleEnemy'&&p.actorId==='991'
    &&typeof expectedEnemyMesh==='string'&&expectedEnemyMesh.startsWith('/Game/Recovered/Battle/Cube/')&&p.mesh===expectedEnemyMesh&&rectValid(p.bounds);
}

/** Native gesture evidence plus independent authoritative GET/arrival trace.
 * This validates the fixed one-enemy new-domain adapter, never a legacy tID. */
export function verifyBattleDragFlow({reports,events,battle,profileId,battleId,nodeProcessIdentities,expectedEnemyMesh}) {
  const contexts=records(reports).flatMap((report,index)=>records(report?.actions).map(row=>({row,report,processIdentity:nodeProcessIdentities?.[index]})));
  const successes=contexts.filter(({row})=>row?.action==='play-card'),negative=contexts.filter(({row})=>Object.hasOwn(NEGATIVE_DRAGS,row?.action));
  const cardIds=new Map(records(battle?.state?.cards).filter(c=>c&&typeof c.instanceId==='string'&&typeof c.cardId==='string').map(c=>[c.instanceId,c.cardId]));
  const path=`/api/rebuild/v1/profiles/${profileId}/battles/${battleId}`,requests=records(events).filter(e=>e.phase==='ue-request');
  const checks={};
  checks.successfulCardsUsePhysicalSlatedrag=successes.length>=2&&successes.every(({row})=>gestureTraceValid(row,cardIds,battleId));
  checks.successfulDragsHaveValidReleaseAndRealTarget=successes.length>=2&&successes.every(({row})=>{
    const g=row.pointerObservation?.lastGesture,trace=records(g?.events),release=trace.at(-1);
    return gestureTraceValid(row,cardIds,battleId)&&g.outcome==='submitted'&&g.reason===''&&g.lostCapture===false&&g.targetId==='991'
      &&trace.some(e=>e.kind==='move'&&e.upwardDelta>=g.threshold)&&release?.kind==='release'&&release.targetHit===true
      &&release.upwardDelta>=g.threshold&&insideCanvas(release.point)&&720-release.point[1]>100
      &&targetProjectionValid(g,expectedEnemyMesh)&&insideRect(release.point,g.targetProjection.bounds);
  });
  checks.mouseAndTouchEachSubmitNativeDrag=successes.some(({row})=>row.input==='mouse')&&successes.some(({row})=>row.input==='touch');
  checks.postArrivalIsAfterPhysicalRelease=successes.length>=2&&successes.every(({row,processIdentity,report})=>{
    const release=records(row.pointerObservation?.lastGesture?.events).at(-1);
    const commands=requests.filter(e=>e.method==='POST'&&e.path===path+'/actions'&&e.type==='play-card'&&e.processIdentity===processIdentity
      &&e.expectedRevision===row.revision&&e.instanceId===row.value);
    return release?.kind==='release'&&commands.length===1&&commands[0].status===200&&integers(commands[0].receivedAtUnixMs,release.atUnixMs)
      &&commands[0].receivedAtUnixMs<=report.finishedAtUnixMs&&integers(commands[0].time,commands[0].receivedAtUnixMs);
  });
  checks.allFourNativeCancellationProbesObserved=Object.values(NEGATIVE_DRAGS).every(kind=>negative.some(({row})=>row.probe?.kind===kind))
    &&negative.every(({row})=>row.probe?.kind===NEGATIVE_DRAGS[row.action]);
  checks.tapWrongTargetOutsideAndCancelNeverSubmit=negative.length>=4&&negative.every(({row})=>{
    if(!gestureTraceValid(row,cardIds,battleId))return false;
    const g=row.pointerObservation.lastGesture,e=g.events.at(-1),kind=row.probe?.kind;
    if(g.targetId!=='')return false;
    if(kind==='cancel')return g.outcome==='cancelled'&&e.kind==='cancel'&&g.lostCapture===true&&typeof g.reason==='string'&&g.reason.includes('capture');
    if(g.lostCapture!==false||e.kind!=='release')return false;
    if(kind==='tap')return g.outcome==='tap'&&g.reason==='below-drag-threshold'&&insideCanvas(e.point)&&e.upwardDelta<g.threshold;
    if(kind==='outside')return g.outcome==='rejected'&&g.reason==='outside'&&!insideCanvas(e.point);
    return kind==='invalid-target'&&g.outcome==='rejected'&&g.reason==='invalid-target'&&e.targetHit===false&&insideCanvas(e.point)
      &&e.upwardDelta>=g.threshold&&720-e.point[1]>100&&targetProjectionValid(g,expectedEnemyMesh)&&!insideRect(e.point,g.targetProjection.bounds);
  });
  checks.cancellationProbesKeepAuthoritativeRevisionAndWireUnchanged=negative.length>=4&&negative.every(({row,report,processIdentity})=>{
    const probe=row.probe,g=row.pointerObservation?.lastGesture,first=records(g?.events)[0],last=records(g?.events).at(-1);
    const actions=records(report.actions),index=actions.indexOf(row),refreshes=[actions[index-1],actions[index+1]];
    if(!probe||!first||!last||!integers(probe.startedAtUnixMs,1)||!integers(probe.finishedAtUnixMs,probe.startedAtUnixMs)
      ||probe.startedAtUnixMs>row.startedAtUnixMs||probe.finishedAtUnixMs<row.finishedAtUnixMs
      ||probe.beforeServerRevision!==row.revision||probe.afterServerRevision!==row.revision
      ||!completeProjection(probe.beforeBattle)||!completeProjection(probe.afterBattle)||!same(projected(probe.beforeBattle),projected(probe.afterBattle))
      ||probe.beforeBattle?.id!==battleId||probe.beforeBattle?.profileId!==profileId||probe.beforeBattle?.revision!==row.revision
      ||refreshes.some(a=>a?.action!=='refresh-battle'||a.inputSource!=='slate-pointer'||a.controlHit!==true||shortMap(a.map)!==BATTLE||a.phase!==3))return false;
    const reads=requests.filter(e=>e.processIdentity===processIdentity&&e.method==='GET'&&e.path===path&&e.status===200&&e.revision===row.revision);
    const before=reads.some(e=>integers(e.receivedAtUnixMs,probe.startedAtUnixMs)&&integers(e.time,e.receivedAtUnixMs)&&e.time<=first.atUnixMs);
    const after=reads.some(e=>integers(e.receivedAtUnixMs,last.atUnixMs)&&integers(e.time,e.receivedAtUnixMs)&&e.time<=probe.finishedAtUnixMs);
    const unobservedArrival=requests.some(e=>e.method==='POST'&&e.processIdentity===processIdentity&&!integers(e.receivedAtUnixMs,1));
    const wrote=requests.some(e=>e.method==='POST'&&e.processIdentity===processIdentity&&e.receivedAtUnixMs>=probe.startedAtUnixMs&&e.receivedAtUnixMs<=probe.finishedAtUnixMs);
    return before&&after&&!wrote&&!unobservedArrival;
  });
  checks.mouseAndTouchNativeDragPreviewFrames=records(reports).length===2&&records(reports).every((report,index)=>{
    const stage=index===0?'card-drag-preview':'resumed-card-drag-preview',shots=records(report?.screenshots).filter(s=>s.stage===stage);
    if(shots.length!==1)return false;
    const shot=shots[0],g=shot.paint?.lastGesture,trace=records(g?.events);
    const context=successes.find(c=>c.report===report&&c.row.pointerObservation?.lastGesture?.serial===g?.serial);
    return context&&shot.surface==='session'&&shortMap(shot.worldMap)===BATTLE&&shot.paint?.phase===3&&shot.paint.pending===false
      &&shot.paint.dragPreviewPainted===true&&g.active===true&&g.outcome==='tracking'&&g.lostCapture===false
      &&g.cardInstanceId===context.row.value&&g.cardId===cardIds.get(context.row.value)&&g.battleId===battleId
      &&g.isTouch===(index===1)&&shot.actionCount===records(report.actions).indexOf(context.row)
      &&trace.length>=2&&trace[0].kind==='start'&&trace.slice(1).every(e=>e.kind==='move')
      &&trace.at(-1).upwardDelta>=g.threshold&&targetProjectionValid(g,expectedEnemyMesh)
      &&same(trace,records(context.row.pointerObservation.lastGesture.events).slice(0,trace.length));
  });
  for(const name of Object.keys(checks))checks[name]=checks[name]===true;
  return {checks,passed:Object.values(checks).every(Boolean)};
}

export function verifyUIFlow({manifest,initial,resume,checkpoint,checkpointPersisted,persisted,events,images = {},stopped,requireCleanup=false}) {
  const checks = {}, requests = records(events).filter(e => e.phase === 'ue-request');
  const reports = [initial,resume], actions = reports.flatMap(r => records(r?.actions)), shots = reports.flatMap(r => records(r?.screenshots));
  const profileId = checkpoint?.profileId, battleId = checkpoint?.battleId;
  const p = `/api/rebuild/v1/profiles/${profileId}`, b = `${p}/battles/${battleId}`;
  checks.isolatedIdentity = manifest?.mode === 'isolated-native-session-test' && manifest.faults === false
    && isGeneratedDatabase(manifest.mongoDatabase) && isTestPort(manifest.port)
    && UUID.test(profileId) && UUID.test(battleId) && reports.every(r => r?.port === manifest.port) && checkpoint?.port === manifest.port;
  checks.nativeUIReports = reports.every(r => r?.schemaVersion === 1 && r.mode === 'ue-slate-ui-flow' && r.passed === true)
    && initial?.runKind === 'initial' && resume?.runKind === 'resume' && checkpoint?.mode === 'ue-slate-ui-checkpoint';
  checks.twoDistinctUEProcesses = reports.every(r=>integers(r?.ueProcessId,1) && UUID.test(r.runId)
    && integers(r.startedAtUnixMs,1) && integers(r.finishedAtUnixMs,r.startedAtUnixMs)
    && Math.abs(Date.parse(r.startedAtUtc)-r.startedAtUnixMs)<1000 && Math.abs(Date.parse(r.finishedAtUtc)-r.finishedAtUnixMs)<1000)
    && initial?.ueProcessId!==resume?.ueProcessId && initial?.runId!==resume?.runId
    && initial?.finishedAtUnixMs<resume?.startedAtUnixMs;
  checks.sameProfileAndBattleAcrossRuns = reports.every(r => r?.profileId === profileId && r.battleId === battleId)
    && checkpoint?.battle?.id === battleId && checkpoint?.battle?.profileId === profileId;
  checks.checkpointBelongsToInitialUEProcess = checkpoint?.initialRunId===initial?.runId && UUID.test(checkpoint?.initialRunId??'')
    && integers(checkpoint?.initialUEProcessId,1) && checkpoint.initialUEProcessId===initial?.ueProcessId;
  checks.onlyRoutedUIInputs = actions.length >= 8 && actions.every(a => {
    const drag=a?.action==='play-card'||Object.hasOwn(NEGATIVE_DRAGS,a?.action);
    return a?.inputSource===(drag?'slate-drag':'slate-pointer')&&['mouse','touch'].includes(a.input)
      &&a.controlHit===true&&paintValid(a.paint,shortMap(a.map))&&integers(a.phase)&&a.phase===a.paint.phase
      &&records(a.paint.controls).some(c=>c.action===(drag?'play-card':a.action)&&c.value===(a.value??'')&&c.enabled===true)
      &&(drag?a.pointerObservation?.lastGesture?.cardInstanceId===a.value
        :a.pointerObservation?.lastPointerAction===a.action&&a.pointerObservation.lastPointerValue===(a.value??'')&&a.pointerObservation.lastPointerTouch===(a.input==='touch'))
      &&integers(a.paint.pointerEventSerial)&&integers(a.pointerObservation?.pointerEventSerial,1)&&a.pointerObservation.pointerEventSerial>a.paint.pointerEventSerial;
  });
  checks.noCommandsWhilePending = actions.filter(a => guardedActions.has(a.action)).every(a => a.requestInFlight === false && a.pendingIntent === false && a.paint?.pending === false);
  checks.originalWorldlinePageActuallyClickedAndPainted = worldlineRouteValid(initial,'worldline-first','select-encounter')
    && worldlineRouteValid(resume,'worldline-resume','continue-battle');
  checks.initialExplicitCreationAndEncounter = records(initial?.actions).some(a => a.action === 'confirm-new-profile' && a.controlHit === true)
    && records(initial?.actions).some(a => a.action === 'create-profile' && a.controlHit === true)
    && records(initial?.actions).some(a => a.action === 'select-encounter' && a.value === 'tutorial-5000' && a.controlHit === true)
    && records(initial?.actions).some(a => a.action === 'new-battle' && a.controlHit === true);
  checks.resumeExplicitProfileAndBattle = records(resume?.actions).some(a => a.action === 'select-profile' && a.value === profileId && a.controlHit === true)
    && records(resume?.actions).some(a => a.action === 'continue-battle' && a.value === battleId && a.controlHit === true)
    && !records(resume?.actions).some(a => ['create-profile','new-battle','challenge-again'].includes(a.action));
  const checkpointObserved = resume?.checkpointObserved?.battle ?? resume?.checkpointObserved;
  checks.exactResumeCheckpoint = same(projected(checkpointObserved),projected(checkpoint?.battle)) && projected(checkpointObserved) !== null;
  checks.checkpointEqualsIndependentPersistedRead = checkpointPersisted?.mode === 'readonly-checkpoint-persisted-v1'
    && checkpointPersisted.port === manifest?.port && checkpointPersisted.profileId === profileId && checkpointPersisted.battleId === battleId
    && projected(checkpointPersisted.battle) !== null && same(projected(checkpointPersisted.battle),projected(checkpoint?.battle));
  const ready=records(events).filter(e=>e.phase==='test-server-ready'),stops=records(events).filter(e=>e.phase==='test-server-stopped');
  const first=ready.find(e=>e.processIdentity===manifest?.previousProcessIdentity),second=ready.find(e=>e.processIdentity===manifest?.processIdentity);
  const firstStop=stops.find(e=>e.processIdentity===manifest?.previousProcessIdentity);
  checks.nodeProcessRestartSameDatabase = manifest?.schemaVersion===2 && manifest.processIndex===1 && UUID.test(manifest.runId) && UUID.test(manifest.databaseIdentity)
    && UUID.test(manifest.processIdentity) && UUID.test(manifest.previousProcessIdentity) && manifest.processIdentity!==manifest.previousProcessIdentity
    && integers(manifest.pid,1) && integers(manifest.previousPid,1) && manifest.pid!==manifest.previousPid
    && first?.pid===manifest.previousPid && first.processIndex===0 && first.resumed===false && first.databaseIdentity===manifest.databaseIdentity && first.mongoDatabase===manifest.mongoDatabase
    && second?.pid===manifest.pid && second.processIndex===1 && second.resumed===true && second.databaseIdentity===manifest.databaseIdentity && second.mongoDatabase===manifest.mongoDatabase
    && first.manifestSha256===manifest.previousManifestSha256 && second.previousManifestSha256===first.manifestSha256
    && firstStop?.preservedDatabase===true && firstStop.manifestSha256===first.manifestSha256 && first.time<firstStop.time && firstStop.time<second.time
    && checkpointPersisted?.processIdentity===manifest.previousProcessIdentity && checkpointPersisted.nodePid===manifest.previousPid
    && checkpointPersisted.databaseIdentity===manifest.databaseIdentity && checkpointPersisted.manifestSha256===manifest.previousManifestSha256
    && manifest.resumeCheckpoint?.profileId===profileId && manifest.resumeCheckpoint.battleId===battleId
    && manifest.resumeCheckpoint.revision===checkpoint?.battle?.revision && second.resumeCheckpoint?.revision===checkpoint?.battle?.revision
    && manifest.resumeCheckpoint.actionIndex===checkpoint?.battle?.revision-1 && second.resumeCheckpoint?.actionIndex===manifest.resumeCheckpoint.actionIndex
    && SHA.test(checkpointPersisted?.stateSha256??'') && SHA.test(checkpointPersisted?.scenarioSha256??'')
    && manifest.resumeCheckpoint.stateSha256===checkpointPersisted.stateSha256 && second.resumeCheckpoint?.stateSha256===checkpointPersisted.stateSha256
    && manifest.resumeCheckpoint.scenarioSha256===checkpointPersisted.scenarioSha256 && second.resumeCheckpoint?.scenarioSha256===checkpointPersisted.scenarioSha256
    && first.time<=initial?.startedAtUnixMs && initial?.finishedAtUnixMs<firstStop.time
    && second.time<=resume?.startedAtUnixMs;
  checks.liveReadIdentityMatchesResumedNode = persisted?.testServer?.mode==='isolated-native-session-test-identity'
    && persisted.testServer.readOnly===true && persisted.testServer.databaseLifecycle==='running'
    && persisted.testServer.pid===manifest?.pid && persisted.testServer.processIdentity===manifest?.processIdentity
    && persisted.testServer.databaseIdentity===manifest?.databaseIdentity && persisted.testServer.runId===manifest?.runId
    && persisted.testServer.mongoDatabase===manifest?.mongoDatabase && persisted.testServer.port===manifest?.port
    && persisted.testServer.manifestSha256===second?.manifestSha256;
  checks.realScreenshots = shots.length >= 6 && shots.every(s => {
    const image=images[s.path]; return image && image.width === s.width && image.height === s.height && image.width >= 1280 && image.height >= 720
      && Math.abs(image.width/image.height - 16/9) < 0.03 && image.nonBlackRatio > 0.02 && paintValid(s.paint,shortMap(s.worldMap));
  });
  const battleShots = shots.filter(s => shortMap(s.worldMap) === BATTLE);
  const hallShots = shots.filter(s => shortMap(s.worldMap) === HALL && s.paint?.originalSourcePage!==true);
  checks.hallAndBattleWorldsActuallyPainted = battleShots.length >= 2 && hallShots.length >= 2
    && battleShots.every(s => s.playerId === '1' && s.enemyId === '991' && s.paint?.battleScene === true && s.paint?.phase === 3 && s.paint?.profileId === profileId && s.paint?.battleId === battleId)
    && hallShots.every(s => s.paint?.battleScene === false);
  checks.sourceSceneMatchesBattle = battleShots.length >= 2 && battleShots.every(sceneValid);
  checks.frameHasRealBattleHUD = battleShots.some(s => {
    const keys=new Set(paintedSprites(s.paint).map(r => r.key));
    return s.paint?.sceneProblem === '' && s.paint?.handCount > 0 && s.paint?.visible === true && keys.has('player-hp-bg') && keys.has('enemy-hp-bg')
      && keys.has('energy-icon') && keys.has('card-cost') && keys.has('deck-icon') && records(s.paint.renderedTexts).some(t => /艾尔莎/.test(t))
      && records(s.paint.renderedTexts).some(t => /幻眼魔方/.test(t));
  });
  const hdDraws = new Map();
  for (const s of battleShots) for (const row of paintedSprites(s.paint)) if (HD_KEYS.includes(row.key) && typeof row.asset === 'string' && row.asset.startsWith('/Game/Recovered/Battle/UI/AI/')) hdDraws.set(row.key,row.asset);
  checks.allSixHDIconsActuallyDrawn = HD_KEYS.every(key => hdDraws.has(key)) && battleShots.some(s => s.paint?.hdIconVariant === true && s.paint?.hdIconsWithOriginalFootprint === 6);
  const newProfiles=requests.filter(e => e.method==='POST' && e.path === '/api/rebuild/v1/profiles' && e.status === 201);
  const newBattles=requests.filter(e => e.method==='POST' && e.path === p+'/battles' && e.status === 201);
  checks.noDuplicateProfileOrBattleCreation = newProfiles.length === 1 && newProfiles[0].profileId===profileId && newBattles.length === 1 && newBattles[0].replayed === false
    && UUID.test(newBattles[0].battleId) && newBattles[0].battleId === battleId && newBattles[0].encounterId==='tutorial-5000';
  const profileWrites=actions.filter(a => a.action==='create-profile'), battleWrites=actions.filter(a => a.action==='new-battle');
  const cardWrites=actions.filter(a => a.action==='play-card'), turnWrites=actions.filter(a => a.action==='end-turn');
  checks.uiActionsMatchWireCommands = profileWrites.length === newProfiles.length && battleWrites.length === newBattles.length
    && cardWrites.length >= 1 && turnWrites.length >= 1
    && cardWrites.length === requests.filter(e => e.path===b+'/actions' && e.type==='play-card' && e.status===200).length
    && turnWrites.length === requests.filter(e => e.path===b+'/actions' && e.type==='end-turn' && e.status===200).length;
  const allCommands=requests.filter(e=>e.method==='POST' && e.path===b+'/actions');
  checks.eachUIRunMatchesItsNodeWireIntents = reports.every((report,index)=>{
    const processIdentity=index===0?manifest?.previousProcessIdentity:manifest?.processIdentity;
    const ui=records(report?.actions).filter(a=>['play-card','end-turn'].includes(a.action));
    const wire=allCommands.filter(e=>e.processIdentity===processIdentity);
    return ui.length===wire.length && ui.length>=1 && ui.every((a,i)=>{
      const event=wire[i];
      return event.status===200 && event.replayed===false && event.type===a.action && integers(a.revision,1)
        && integers(event.expectedRevision,1) && integers(event.revision,2) && event.expectedRevision===a.revision && event.revision===a.revision+1
        && typeof event.requestId==='string' && event.requestId.startsWith('ue-') && UUID.test(event.requestId.slice(3))
        && event.time>=report.startedAtUnixMs && event.time<=report.finishedAtUnixMs
        && (a.action==='play-card'?event.instanceId===a.value:event.instanceId===undefined);
    });
  }) && new Set(allCommands.map(e=>e.requestId)).size===allCommands.length
    && newProfiles.every(e=>e.processIdentity===manifest.previousProcessIdentity) && newBattles.every(e=>e.processIdentity===manifest.previousProcessIdentity);
  checks.persistedServiceIdentity = persisted?.bootstrap?.service === 'hczs-rebuild' && persisted.bootstrap.apiVersion === 1 && persisted.bootstrap.storage === 'mongodb';
  let finalProjection;
  try { finalProjection=projectServerBattle(persisted?.battle); } catch {}
  checks.persistedOnlyTestProfileAndBattle = records(persisted?.bootstrap?.profiles).length === 1 && persisted?.profile?.id === profileId
    && records(persisted?.battles).length === 1 && persisted.battles[0].id === battleId && persisted?.hall?.profileId === profileId;
  checks.finalUIEqualsPersistedBattle = finalProjection !== undefined && same(projected(resume?.finalBattle),finalProjection)
    && finalProjection.id === battleId && finalProjection.profileId === profileId && finalProjection.encounterId === 'tutorial-5000'
    && finalProjection.definitionId === checkpoint?.battle?.definitionId && finalProjection.revision > checkpoint?.battle?.revision
    && ['won','lost'].includes(finalProjection.status);
  const cleanupVerified=stopped?.stopped===true && stopped.databaseDropped===true && stopped.mongoDatabase===manifest?.mongoDatabase
    && stopped.runId===manifest?.runId && stopped.databaseIdentity===manifest?.databaseIdentity && stopped.processIdentity===manifest?.processIdentity
    && stopped.processIndex===1 && stopped.manifestSha256===second?.manifestSha256 && integers(stopped.time,1)
    && stopped.time>=resume?.finishedAtUnixMs && stops.some(e=>e.processIdentity===manifest?.processIdentity && e.preservedDatabase===false
      && e.manifestSha256===stopped.manifestSha256 && e.time<=stopped.time);
  checks.ownedGeneratedDatabaseCleanup = !requireCleanup || cleanupVerified;
  const expectedEnemyMesh=shots.filter(sceneValid).map(s=>(s.scene??s.paint?.scene)?.enemyMesh)[0];
  const drag=verifyBattleDragFlow({reports,events,battle:persisted?.battle,profileId,battleId,
    nodeProcessIdentities:[manifest?.previousProcessIdentity,manifest?.processIdentity],expectedEnemyMesh});
  Object.assign(checks,drag.checks);
  for(const name of Object.keys(checks))checks[name]=checks[name]===true;
  const failed=Object.entries(checks).filter(([,value]) => !value).map(([name]) => name);
  return {passed:failed.length===0,mode:'actual-ui-plus-wire-plus-persisted-state',checks,failed,hdDraws:Object.fromEntries(hdDraws),
    scope:{originalApkExecuted:false,originalApkPlayableVerified:false,originalChapterProgressVerified:false,humanVisualReviewVerified:false,
      worldlineStaticSourcePageVerified:checks.originalWorldlinePageActuallyClickedAndPainted,localBattlePreviewAdapter:true,
      nativeDragGestureVerified:drag.passed,oneEnemyNewDomainTargetAdapter:true,legacyEntityTargetIdCompatible:false,originalTexturedDragArrowVerified:false,
      mongoDatabasePersistenceVerified:checks.nodeProcessRestartSameDatabase,mongoDaemonRestartVerified:false,cleanupVerified}};
}

/** Read-only image inspection; this never edits an image or creates replacement pixels. */
export function inspectPng(bytes) {
  if (bytes.length < 100 || !bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) throw Error('Not a PNG screenshot');
  let width,height,depth,color,interlace; const data=[];
  for(let offset=8;offset+12<=bytes.length;) {
    const length=bytes.readUInt32BE(offset),type=bytes.toString('ascii',offset+4,offset+8);
    if(length>32*1024*1024 || offset+length+12>bytes.length) throw Error('PNG chunk outside bounds');
    const body=bytes.subarray(offset+8,offset+8+length);
    if(type==='IHDR') { width=body.readUInt32BE(0);height=body.readUInt32BE(4);depth=body[8];color=body[9];interlace=body[12]; }
    if(type==='IDAT') data.push(body);offset+=length+12;if(type==='IEND')break;
  }
  if(!integers(width,1)||!integers(height,1)||width>8192||height>8192||depth!==8||![2,6].includes(color)||interlace!==0)throw Error('Unsupported screenshot pixel format/size');
  const channels=color===6?4:3,stride=width*channels,raw=inflateSync(Buffer.concat(data),{maxOutputLength:64*1024*1024});
  if(raw.length!==(stride+1)*height)throw Error('Incomplete screenshot pixels');
  let previous=Buffer.alloc(stride),nonBlack=0;
  const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
  for(let y=0;y<height;y++) {
    const filter=raw[y*(stride+1)],row=Buffer.from(raw.subarray(y*(stride+1)+1,(y+1)*(stride+1)));
    if(filter>4)throw Error('Invalid screenshot filter');
    for(let x=0;x<stride;x++){const a=x>=channels?row[x-channels]:0,b=previous[x],c=x>=channels?previous[x-channels]:0;row[x]=(row[x]+(filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):filter===4?paeth(a,b,c):0))&255;}
    for(let x=0;x<stride;x+=channels)if(row[x]+row[x+1]+row[x+2]>30)nonBlack++;
    previous=row;
  }
  return {width,height,nonBlackRatio:nonBlack/(width*height),sha256:createHash('sha256').update(bytes).digest('hex')};
}

async function json(path){return JSON.parse(await readFile(path,'utf8'));}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const {values}=parseArgs({options:{'record-directory':{type:'string'},'initial-report':{type:'string'},'resume-report':{type:'string'},checkpoint:{type:'string'},'persisted-snapshot':{type:'string'},'capture-checkpoint-persisted':{type:'boolean',default:false},'require-cleanup':{type:'boolean',default:false}}});
  if(!values['record-directory'])throw Error('Pass --record-directory <isolated UI run>');
  const root=fileURLToPath(new URL('../../',import.meta.url)),allowed=await realpath(resolve(root,'analysis/unreal/session-test')),directory=await realpath(resolve(values['record-directory']));
  const contained=path=>{const r=relative(directory,path);return Boolean(r)&&!r.startsWith('..')&&!isAbsolute(r);};
  const runRelative=relative(allowed,directory);
  if(!runRelative||runRelative.startsWith('..')||isAbsolute(runRelative))throw Error('UI run directory must be a child of analysis/unreal/session-test');
  const localPath=async(value,fallback)=>{const path=await realpath(resolve(value??resolve(directory,fallback)));if(!contained(path))throw Error('Report outside this isolated UI run');return path;};
  const manifestPath=await localPath(undefined,'server.json'),manifestText=await readFile(manifestPath,'utf8');
  const manifest=JSON.parse(manifestText),checkpoint=await json(await localPath(values.checkpoint,'ui-checkpoint.json'));
  validateUIRunningManifest(manifest);
  if(manifest.mode!=='isolated-native-session-test'||!isTestPort(manifest.port)||!isGeneratedDatabase(manifest.mongoDatabase)
    ||resolve(manifest.recordDirectory??'')!==directory||resolve(manifest.tracePath??'')!==resolve(directory,'http-trace.jsonl')
    ||!UUID.test(checkpoint.profileId)||!UUID.test(checkpoint.battleId)||checkpoint.port!==manifest.port)throw Error('Refusing to read an unrecognized/production service');
  const base=`http://127.0.0.1:${manifest.port}/api/rebuild/v1`,p=`/profiles/${checkpoint.profileId}`;
  const get=async path=>{const response=await fetch(base+path,{signal:AbortSignal.timeout(5000)});if(response.status!==200)throw Error('Read-only persisted inspection failed');return response.json();};
  let liveIdentity;
  if(!values['persisted-snapshot']) {
    const response=await fetch(`http://127.0.0.1:${manifest.port}/__hczs_test_control/identity`,{headers:{authorization:`Bearer ${manifest.controlToken}`},signal:AbortSignal.timeout(5000)});
    if(response.status!==200)throw Error('Actual isolated Node/database identity probe failed');
    liveIdentity=validateLiveTestIdentity(await response.json(),manifest,manifestText);
  }
  if(values['capture-checkpoint-persisted']) {
    if(values['persisted-snapshot']||values['require-cleanup']||manifest.processIndex!==0)throw Error('Checkpoint capture requires the first running isolated Node process');
    const [bootstrap,battle]=await Promise.all([get('/bootstrap'),get(p+'/battles/'+checkpoint.battleId)]);
    if(bootstrap.service!=='hczs-rebuild'||bootstrap.apiVersion!==1||bootstrap.storage!=='mongodb'||records(bootstrap.profiles).length!==1||bootstrap.profiles[0].id!==checkpoint.profileId)throw Error('Checkpoint server identity/profile mismatch');
    const projectedBattle=projectServerBattle(battle.battle);
    if(projectedBattle.id!==checkpoint.battleId||projectedBattle.profileId!==checkpoint.profileId||!same(projectedBattle,projected(checkpoint.battle)))throw Error('Checkpoint persisted identity/state mismatch');
    const snapshot={mode:'readonly-checkpoint-persisted-v1',port:manifest.port,profileId:checkpoint.profileId,battleId:checkpoint.battleId,battle:projectedBattle,
      processIdentity:liveIdentity.processIdentity,nodePid:liveIdentity.pid,databaseIdentity:liveIdentity.databaseIdentity,
      manifestSha256:liveIdentity.manifestSha256,stateSha256:digest(JSON.stringify(battle.battle.state)),scenarioSha256:digest(JSON.stringify(battle.battle.scenario)),
      serverBattleSha256:digest(JSON.stringify(battle.battle)),testServer:liveIdentity};
    await writeFile(resolve(directory,'ui-checkpoint-persisted.json'),JSON.stringify(snapshot,null,2));
    console.log(JSON.stringify({captured:true,profileId:checkpoint.profileId,battleId:checkpoint.battleId,revision:projectedBattle.revision}));
  } else {
  const [initial,resume,checkpointPersisted,trace]=await Promise.all([
    localPath(values['initial-report'],'ui-initial.json').then(json),localPath(values['resume-report'],'ui-resume.json').then(json),
    localPath(undefined,'ui-checkpoint-persisted.json').then(json),localPath(undefined,'http-trace.jsonl').then(path=>readFile(path,'utf8'))]);
  let persisted;
  if(values['persisted-snapshot']){
    persisted=await json(await localPath(values['persisted-snapshot']));
    validateLiveTestIdentity(persisted.testServer,manifest,manifestText);
  }
  else {
    const [bootstrap,profile,hall,battles,battle]=await Promise.all([get('/bootstrap'),get(p),get(p+'/hall'),get(p+'/battles'),get(p+'/battles/'+checkpoint.battleId)]);
    persisted={bootstrap,profile:profile.profile,hall:hall.hall,battles:battles.battles,battle:battle.battle,testServer:liveIdentity};
    await writeFile(resolve(directory,'ui-persisted.json'),JSON.stringify(persisted,null,2));
  }
  const images={};
  for(const shot of [...records(initial.screenshots),...records(resume.screenshots)]){
    const path=await localPath(shot.path);images[shot.path]=inspectPng(await readFile(path));
  }
  const stopped=values['require-cleanup']?await json(await localPath(undefined,'stopped.json')):undefined;
  const result=verifyUIFlow({manifest,initial,resume,checkpoint,checkpointPersisted,persisted,images,stopped,requireCleanup:values['require-cleanup'],events:trace.trim().split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line))});
  await writeFile(resolve(directory,'ui-flow-verification.json'),JSON.stringify({...result,images},null,2));console.log(JSON.stringify(result,null,2));if(!result.passed)process.exitCode=1;
  }
}
