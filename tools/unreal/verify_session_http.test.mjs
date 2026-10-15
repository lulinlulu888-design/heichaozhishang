import test from 'node:test';
import assert from 'node:assert/strict';
import { verifySessionHttp } from './verify_session_http.mjs';

function fixture() {
  const profileId = '11111111-1111-1111-1111-111111111111', battleId = '22222222-2222-2222-2222-222222222222';
  const p = `/api/rebuild/v1/profiles/${profileId}`, b = `${p}/battles/${battleId}`;
  const get = (path, revision, extra = {}) => ({phase:'ue-request',method:'GET',path,status:200,revision,...extra});
  const act = (requestId, expectedRevision, status, type = 'play-card') => ({phase:'ue-request',method:'POST',path:b+'/actions',status,type,requestId,expectedRevision});
  const create = {phase:'ue-request',method:'POST',path:p+'/battles',status:201,requestId:'same-create-id',bodySha256:'a'.repeat(64),revision:1};
  return { manifest:{mode:'isolated-native-session-test',mongoDatabase:'hczs_test_ue_'+'a'.repeat(32),port:7465,faults:true},
    native:{passed:true,mode:'ue-native-http-session-not-ui-gameplay',port:7465,profileId,battleId,explicitProfileSelection:true,
      cardPlayed:true,turnEnded:true,newGameInstanceRestored:true,conflictReloaded:true,unconfirmedWriteRetries:1,confirmedReadRetries:1,outcome:'won',finalRevision:6},
    events:[get('/api/rebuild/v1/bootstrap'),{...create,droppedAfterCommit:true,advancedRevision:2},{...create,replayed:true},
      get(b,2,{droppedAfterRead:true,wireFailure:'truncated-http-body',declaredBytes:4000,deliveredBytes:32}),get(b,2),
      {phase:'injected-cas-race',before:2,after:3},act('stale-action-id',2,409),get(b,3),act('fresh-action-id',3,200),get(b,4),
      act('end-turn-id',4,200,'end-turn'),get(b,5),get('/api/rebuild/v1/bootstrap'),get(p),get(b,5),act('final-action-id',5,200),get(b,6)] };
}
test('wire verifier requires both native and independent transport/CAS evidence', () => {
  assert.equal(verifySessionHttp(fixture()).passed, true);
});
test('a changed creation payload or id does not count as safe retry', () => {
  for (const field of ['requestId','bodySha256']) {
    const f = fixture(); f.events[2][field] = field === 'requestId' ? 'new-id' : 'b'.repeat(64);
    assert.equal(verifySessionHttp(f).checks.sameCreationRequestAndPayload, false);
    assert.equal(verifySessionHttp(f).passed, false);
  }
});
test('confirmed read failure must be followed by read-only synchronization', () => {
  const f = fixture(); f.events.splice(4,0,{phase:'ue-request',method:'POST',path:f.events[3].path+'/actions',status:200});
  assert.equal(verifySessionHttp(f).checks.confirmedReadRetriesOnlyGet, false);
});
test('native failures, unknown profile selection and production port are never promoted', () => {
  const f = fixture(); f.native.passed = false; assert.equal(verifySessionHttp(f).passed, false);
  f.native.passed = true; f.native.explicitProfileSelection = false; assert.equal(verifySessionHttp(f).passed, false);
  f.native.explicitProfileSelection = true; f.manifest.port = 7460; f.native.port = 7460; assert.equal(verifySessionHttp(f).checks.isolatedIdentity, false);
});
test('empty-socket transparent retry does not prove the native confirmed-read retry path', () => {
  const f = fixture(); delete f.events[3].wireFailure; delete f.events[3].declaredBytes; delete f.events[3].deliveredBytes;
  f.native.confirmedReadRetries = 0;
  const result = verifySessionHttp(f);
  assert.equal(result.checks.partialReadReallyTransmitted, false);
  assert.equal(result.checks.nativeWriteAndReadRetryPaths, false);
  assert.equal(result.passed, false);
});
test('CAS recovery requires latest GET before a new id with that revision', () => {
  const f = fixture(); f.events[8].expectedRevision = 2;
  assert.equal(verifySessionHttp(f).checks.conflictReadBeforeNewIntent, false);
  f.events[8].expectedRevision = 3; f.events[8].requestId = f.events[6].requestId;
  assert.equal(verifySessionHttp(f).checks.conflictReadBeforeNewIntent, false);
});

function ultimateFixture(hits = 8) {
  const f = fixture();
  Object.assign(f.native, {ultimateGeneratedInActualHand:true, ultimateReceiptConfirmedAfterGet:true, ultimateDamageEvents:hits});
  Object.assign(f.events.at(-2), {revision:6, instanceId:'ultimate:1', receiptEvents:[
    {type:'CardPlayed',cardId:'410104',instanceId:'ultimate:1'},
    ...Array.from({length:hits}, (_, effectIndex) => ({type:'DamageApplied',actor:'player',target:'enemy',effectIndex})),
    {type:'BattleEnded',status:'won',reason:'enemy-defeated'}]});
  return f;
}

test('ultimate accepts eight hits or an authoritative early enemy death', () => {
  for (const hits of [8,5]) assert.equal(verifySessionHttp(ultimateFixture(hits)).passed, true);
});

test('ultimate rejects missing death, reordered hits and unmatched confirmation', () => {
  const f = ultimateFixture(5);
  f.events.at(-2).receiptEvents.pop();
  assert.equal(verifySessionHttp(f).checks.ultimateDamageOrder, false);
  const g = ultimateFixture();
  g.events.at(-2).receiptEvents[2].effectIndex = 0;
  assert.equal(verifySessionHttp(g).checks.ultimateDamageOrder, false);
  const h = ultimateFixture(); h.events.at(-1).revision = 7;
  assert.equal(verifySessionHttp(h).checks.ultimateReadBeforeNextWrite, false);
  const i = ultimateFixture(); i.native.ultimateDamageEvents = 7;
  assert.equal(verifySessionHttp(i).checks.ultimateNativeDamageMatchesWire, false);
});
