import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyUIFlow, verifyBattleDragFlow } from './verify_ui_flow.mjs';
import { fixture } from './ui_flow_fixture.mjs';

const card=f=>f.initial.actions.find(a=>a.action==='play-card');
const gesture=f=>card(f).pointerObservation.lastGesture;
const post=f=>f.events.find(e=>e.type==='play-card');
const probe=f=>f.initial.actions.find(a=>a.action==='invalid-target-card-drag');
const drag=f=>verifyBattleDragFlow({reports:[f.initial,f.resume],events:f.events,battle:f.persisted.battle,
  profileId:f.checkpoint.profileId,battleId:f.checkpoint.battleId,
  nodeProcessIdentities:[f.manifest.previousProcessIdentity,f.manifest.processIdentity],
  expectedEnemyMesh:'/Game/Recovered/Battle/Cube/cube.cube'});

test('synthetic native drag evidence integrates with the full UI/restart validator',()=>{
  const result=verifyUIFlow(fixture());assert.deepEqual(result.failed,[]);assert.equal(result.passed,true);
  assert.equal(result.scope.nativeDragGestureVerified,true);
  assert.equal(result.scope.legacyEntityTargetIdCompatible,false);
  assert.equal(result.scope.originalApkPlayableVerified,false);
});

test('a routed click cannot impersonate physical dragging',()=>{
  const f=fixture();card(f).inputSource='slate-pointer';
  assert.equal(drag(f).checks.successfulCardsUsePhysicalSlatedrag,false);
  assert.equal(verifyUIFlow(f).checks.onlyRoutedUIInputs,false);
});

test('physical drag requires a new gesture, real move and terminal release',()=>{
  for(const edit of [g=>g.events.splice(1,1),g=>g.events.at(-1).kind='move',g=>g.events.at(-1).kind='cancel',
    g=>g.serial=4,g=>g.events[1].atUnixMs=g.events[0].atUnixMs-1,g=>g.events[1].upwardDelta=0]){
    const f=fixture();edit(gesture(f));assert.equal(drag(f).checks.successfulDragsHaveValidReleaseAndRealTarget,false);
  }
});

test('capture loss, cancellation and obsolete revision cannot be accepted as submitted',()=>{
  for(const edit of [g=>g.lostCapture=true,g=>g.outcome='cancelled',g=>g.reason='obsolete-state',g=>g.startRevision=99,g=>g.active=true]){
    const f=fixture();edit(gesture(f));assert.equal(drag(f).checks.successfulDragsHaveValidReleaseAndRealTarget,false);
  }
});

test('successful target requires the actual enemy bounds, source mesh and new-domain ID',()=>{
  for(const edit of [g=>g.targetId='legacy-tID',g=>g.targetProjection.actorId='1',g=>g.targetProjection.valid=false,
    g=>g.targetProjection.source='invented-screen-region',g=>g.targetProjection.mesh='/Engine/BasicShapes/Cube.Cube',
    g=>g.targetProjection.bounds=[0,0,100,100],g=>g.events.at(-1).targetHit=false]){
    const f=fixture();edit(gesture(f));assert.equal(drag(f).checks.successfulDragsHaveValidReleaseAndRealTarget,false);
  }
});

test('valid target alone cannot override viewport and source release-zone thresholds',()=>{
  for(const point of [[1040,620],[-1,300],[1281,300]]){
    const f=fixture(),g=gesture(f);g.targetProjection.bounds=[-10,0,1300,700];
    for(const e of g.events.slice(1)){e.point=[...point];e.upwardDelta=650-point[1];}
    assert.equal(drag(f).checks.successfulDragsHaveValidReleaseAndRealTarget,false);
  }
});

test('request arrival must follow physical release, independent of the later receipt time',()=>{
  for(const edit of [e=>delete e.receivedAtUnixMs,e=>e.receivedAtUnixMs=21979,e=>e.receivedAtUnixMs=90001]){
    const f=fixture();edit(post(f));assert.equal(drag(f).checks.postArrivalIsAfterPhysicalRelease,false);
  }
  const f=fixture();f.events.push({...post(f)});assert.equal(drag(f).checks.postArrivalIsAfterPhysicalRelease,false);
});

test('both mouse and touch must successfully submit native drags',()=>{
  const f=fixture();f.resume.actions.find(a=>a.action==='play-card').input='mouse';
  assert.equal(drag(f).checks.mouseAndTouchEachSubmitNativeDrag,false);
});

test('tap, wrong-target, outside and capture-loss probes are all mandatory',()=>{
  for(const action of ['tap-card','invalid-target-card-drag','outside-card-drag','cancel-card-drag']){
    const f=fixture();f.initial.actions=f.initial.actions.filter(a=>a.action!==action);
    assert.equal(drag(f).checks.allFourNativeCancellationProbesObserved,false);
  }
});

test('negative gestures must demonstrate their actual rejection condition',()=>{
  for(const edit of [f=>probe(f).pointerObservation.lastGesture.targetId='991',
    f=>probe(f).pointerObservation.lastGesture.events.at(-1).targetHit=true,
    f=>f.initial.actions.find(a=>a.action==='cancel-card-drag').pointerObservation.lastGesture.lostCapture=false,
    f=>f.initial.actions.find(a=>a.action==='tap-card').pointerObservation.lastGesture.outcome='submitted']){
    const f=fixture();edit(f);assert.equal(drag(f).checks.tapWrongTargetOutsideAndCancelNeverSubmit,false);
  }
});

test('negative probes compare full authoritative projection, including decimal text and hand',()=>{
  for(const edit of [p=>p.afterServerRevision++,p=>p.afterBattle.enemyHp='99',p=>p.afterBattle.playerHp='100.0',
    p=>p.afterBattle.hand=[],p=>delete p.beforeBattle,p=>p.beforeBattle.profileId='another-profile']){
    const f=fixture();edit(probe(f).probe);assert.equal(drag(f).checks.cancellationProbesKeepAuthoritativeRevisionAndWireUnchanged,false);
  }
});

test('negative probes require GUI refreshes and independently timed GETs on both sides',()=>{
  for(const edit of [f=>f.initial.actions[f.initial.actions.indexOf(probe(f))-1].inputSource='direct-api',
    f=>f.events=f.events.filter(e=>!(e.method==='GET'&&e.receivedAtUnixMs===21305)),
    f=>f.events.find(e=>e.method==='GET'&&e.receivedAtUnixMs===21410).revision=2]){
    const f=fixture();edit(f);assert.equal(drag(f).checks.cancellationProbesKeepAuthoritativeRevisionAndWireUnchanged,false);
  }
});

test('any POST arrival in a negative probe interval invalidates the no-write proof',()=>{
  const f=fixture(),p=probe(f).probe;f.events.push({...post(f),receivedAtUnixMs:p.startedAtUnixMs+1,time:p.finishedAtUnixMs+100});
  assert.equal(drag(f).checks.cancellationProbesKeepAuthoritativeRevisionAndWireUnchanged,false);
});

test('missing POST arrival timestamps cannot be replaced by response log times',()=>{
  const f=fixture();delete post(f).receivedAtUnixMs;
  assert.equal(drag(f).checks.cancellationProbesKeepAuthoritativeRevisionAndWireUnchanged,false);
});

test('mid-drag screenshots must show actual painted cue while held, before submission',()=>{
  for(const edit of [s=>s.paint.dragPreviewPainted=false,s=>s.paint.lastGesture.active=false,
    s=>s.paint.lastGesture.events.push({kind:'release'}),s=>s.paint.pending=true,s=>s.actionCount++,
    s=>s.paint.lastGesture.events[1].point[0]++,s=>s.surface='hall']){
    const f=fixture();edit(f.initial.screenshots.find(s=>s.stage==='card-drag-preview'));
    assert.equal(drag(f).checks.mouseAndTouchNativeDragPreviewFrames,false);
  }
});

test('two held preview frames cannot substitute one mouse capture for the resumed touch',()=>{
  const f=fixture();f.resume.screenshots.find(s=>s.stage==='resumed-card-drag-preview').paint.lastGesture.isTouch=false;
  assert.equal(drag(f).checks.mouseAndTouchNativeDragPreviewFrames,false);
});
