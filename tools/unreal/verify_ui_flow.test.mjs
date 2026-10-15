import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyUIFlow } from './verify_ui_flow.mjs';
import { fixture } from './ui_flow_fixture.mjs';

test('actual UI/wire/persistence evidence can agree',()=>assert.equal(verifyUIFlow(fixture()).passed,true));
test('direct GI/API or non-hit controls cannot pass as UI input',()=>{
  for(const modification of [a=>a.inputSource='direct-gi',a=>a.controlHit=false,a=>a.paint.controls[0].enabled=false]){
    const f=fixture();modification(f.initial.actions.find(a=>a.action==='play-card'));assert.equal(verifyUIFlow(f).checks.onlyRoutedUIInputs,false);
  }
});
test('pending mutation and duplicate creation are rejected',()=>{
  const f=fixture();f.initial.actions.find(a=>a.action==='new-battle').pendingIntent=true;assert.equal(verifyUIFlow(f).checks.noCommandsWhilePending,false);
  f.initial.actions.find(a=>a.action==='new-battle').pendingIntent=false;f.events.push({...f.events[1]});assert.equal(verifyUIFlow(f).checks.noDuplicateProfileOrBattleCreation,false);
});
test('resource loading without six actual HD draws is insufficient',()=>{
  const f=fixture();for(const r of [f.initial,f.resume])for(const s of r.screenshots)delete s.paint.actualPaintedSprites['shield-icon'];
  assert.equal(verifyUIFlow(f).checks.allSixHDIconsActuallyDrawn,false);
});
test('wrong map, hidden actor or another shape cannot pass screenshot scene checks',()=>{
  const f=fixture();f.initial.screenshots.find(s=>s.stage==='battle-first').worldMap='L_ElsaHallFxPreview';assert.equal(verifyUIFlow(f).checks.hallAndBattleWorldsActuallyPainted,false);
  const g=fixture();g.initial.screenshots.find(s=>s.stage==='battle-first').scene.enemyMesh='/Engine/BasicShapes/Cube.Cube';assert.equal(verifyUIFlow(g).checks.sourceSceneMatchesBattle,false);
  const h=fixture();h.initial.screenshots.find(s=>s.stage==='battle-first').scene.playerVisible=false;assert.equal(verifyUIFlow(h).checks.sourceSceneMatchesBattle,false);
});
test('resume requires explicit same UUID and exact unrounded checkpoint',()=>{
  const f=fixture();f.resume.actions[0].value='another-profile';assert.equal(verifyUIFlow(f).checks.resumeExplicitProfileAndBattle,false);
  const g=fixture();g.resume.checkpointObserved.enemyHp='94';assert.equal(verifyUIFlow(g).checks.exactResumeCheckpoint,false);
});
test('server persistence must equal final UI rather than a locally forged outcome',()=>{
  const f=fixture();f.resume.finalBattle.enemyHp='1';assert.equal(verifyUIFlow(f).checks.finalUIEqualsPersistedBattle,false);
  const g=fixture();g.persisted.battle.state.actionIndex=99;assert.equal(verifyUIFlow(g).checks.finalUIEqualsPersistedBattle,false);
  const h=fixture();h.manifest.port=7460;assert.equal(verifyUIFlow(h).checks.isolatedIdentity,false);
});
test('missing native pointer observation cannot pass as a routed UI click',()=>{
  const f=fixture();delete f.initial.actions.find(a=>a.action==='play-card').pointerObservation;assert.equal(verifyUIFlow(f).checks.onlyRoutedUIInputs,false);
});
test('the initial UI checkpoint must also match an independent pre-restart server read',()=>{
  const f=fixture();f.checkpointPersisted.battle.enemyHp='1';assert.equal(verifyUIFlow(f).checks.checkpointEqualsIndependentPersistedRead,false);
  const g=fixture();delete g.checkpointPersisted;assert.equal(verifyUIFlow(g).checks.checkpointEqualsIndependentPersistedRead,false);
});
test('Node restart requires a changed process and matching preserved database identity chain',()=>{
  const f=fixture();f.manifest.pid=f.manifest.previousPid;assert.equal(verifyUIFlow(f).checks.nodeProcessRestartSameDatabase,false);
  const g=fixture();g.events.find(e=>e.phase==='test-server-stopped').preservedDatabase=false;assert.equal(verifyUIFlow(g).checks.nodeProcessRestartSameDatabase,false);
  const h=fixture();h.checkpointPersisted.databaseIdentity='another';assert.equal(verifyUIFlow(h).checks.nodeProcessRestartSameDatabase,false);
});
test('both runs require the real Hall worldline click then source-page frame then adapter click',()=>{
  for(const edit of [f=>f.initial.actions=f.initial.actions.filter(a=>a.action!=='worldline'),
    f=>f.resume.actions=f.resume.actions.filter(a=>a.action!=='local-battle-preview'),
    f=>{const a=f.initial.actions;[a[2],a[3]]=[a[3],a[2]];},
    f=>f.resume.screenshots=f.resume.screenshots.filter(s=>s.stage!=='worldline-resume'),
    f=>f.initial.screenshots.find(s=>s.stage==='worldline-first').actionCount=9]){
    const f=fixture();edit(f);assert.equal(verifyUIFlow(f).checks.originalWorldlinePageActuallyClickedAndPainted,false);
  }
});
test('static source page rejects readonly inspection, invented progress and wrong assets',()=>{
  for(const edit of [p=>p.readOnlySourceInspection=true,p=>p.progressAvailable=true,p=>p.chapterInstances=19,
    p=>p.sourceLayoutSha256='e'.repeat(64),p=>p.actualPaintedSprites=p.actualPaintedSprites.slice(1),
    p=>p.paintResources[p.actualPaintedSprites[0]]='/Engine/BasicShapes/Fake.Fake',p=>p.renderedTexts=['placeholder']]){
    const f=fixture();edit(f.initial.screenshots.find(s=>s.stage==='worldline-first').paint);
    assert.equal(verifyUIFlow(f).checks.originalWorldlinePageActuallyClickedAndPainted,false);
  }
});
test('worldline travel/adapter clicks cannot be accepted while an intent is pending',()=>{
  const f=fixture();f.resume.actions.find(a=>a.action==='local-battle-preview').pendingIntent=true;
  assert.equal(verifyUIFlow(f).checks.noCommandsWhilePending,false);
});
test('two filenames cannot substitute for two actual UE process identities and time intervals',()=>{
  for(const edit of [f=>f.resume.ueProcessId=f.initial.ueProcessId,f=>f.resume.runId=f.initial.runId,
    f=>delete f.resume.startedAtUtc,f=>f.initial.finishedAtUnixMs=150]){
    const f=fixture();edit(f);assert.equal(verifyUIFlow(f).checks.twoDistinctUEProcesses,false);
  }
  const f=fixture();f.checkpoint.initialRunId=f.resume.runId;assert.equal(verifyUIFlow(f).checks.checkpointBelongsToInitialUEProcess,false);
});
test('wire commands must match each run, request revision and the actual clicked card',()=>{
  for(const edit of [e=>e.processIdentity='wrong-process',e=>e.expectedRevision=99,e=>e.revision=99,e=>e.instanceId='another-card',e=>e.time=300]){
    const f=fixture();edit(f.events.find(e=>e.type==='play-card'));assert.equal(verifyUIFlow(f).checks.eachUIRunMatchesItsNodeWireIntents,false);
  }
  const f=fixture(),commands=f.events.filter(e=>e.type==='play-card');commands[1].requestId=commands[0].requestId;
  assert.equal(verifyUIFlow(f).checks.eachUIRunMatchesItsNodeWireIntents,false);
});
test('Node resume also requires matching persisted full state/scenario hashes',()=>{
  const f=fixture();f.checkpointPersisted.stateSha256='e'.repeat(64);assert.equal(verifyUIFlow(f).checks.nodeProcessRestartSameDatabase,false);
  const g=fixture();g.manifest.resumeCheckpoint.scenarioSha256='e'.repeat(64);assert.equal(verifyUIFlow(g).checks.nodeProcessRestartSameDatabase,false);
});
test('a disk manifest cannot replace the authenticated actual Node/database read identity',()=>{
  for(const edit of [s=>s.pid++,s=>s.databaseIdentity='another',s=>s.manifestSha256='e'.repeat(64),s=>s.databaseLifecycle='stopped']){
    const f=fixture();edit(f.persisted.testServer);assert.equal(verifyUIFlow(f).checks.liveReadIdentityMatchesResumedNode,false);
  }
});
test('final lifecycle gate accepts only the matching resumed generated database drop receipt',()=>{
  const f=fixture();assert.equal(verifyUIFlow({...f,requireCleanup:true}).passed,true);
  for(const edit of [s=>s.databaseDropped=false,s=>s.mongoDatabase='hczs',s=>s.processIdentity='wrong',s=>s.manifestSha256='e'.repeat(64)]){
    const f=fixture();edit(f.stopped);assert.equal(verifyUIFlow({...f,requireCleanup:true}).checks.ownedGeneratedDatabaseCleanup,false);
  }
  const g=fixture();delete g.stopped;assert.equal(verifyUIFlow({...g,requireCleanup:true}).checks.ownedGeneratedDatabaseCleanup,false);
  const report=verifyUIFlow(fixture());assert.equal(report.scope.originalApkExecuted,false);assert.equal(report.scope.originalApkPlayableVerified,false);
  assert.equal(report.scope.originalChapterProgressVerified,false);assert.equal(report.scope.mongoDaemonRestartVerified,false);
});
