import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { verifyVisualTiming, validateHitManifest, parseVisualLog } from './verify_visual_timing.mjs';
import { projectVisualTimingReceipt } from './visual_timing_receipt.mjs';

const hitManifest=JSON.parse(readFileSync(new URL('../../analysis/unreal/battle-hit-timing/manifest.json',import.meta.url)));
const sourceAudit=JSON.parse(readFileSync(new URL('../../'+hitManifest.source_audit,import.meta.url)));
const ids=['00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000004'];
function fixture() {
  const f={manifest:{mode:'isolated-native-session-test',faults:false,previousProcessIdentity:ids[0],processIdentity:ids[1],cardResponseDelayMs:1500},
    hitManifest:structuredClone(hitManifest),sourceAudit:structuredClone(sourceAudit),uiVerification:{passed:true},runs:[],events:[]};
  for(const [i,kind] of ['initial','resume'].entries()) {
    const base=i*6000,cardId=i===0?'410101':'110001',requestId=`request-${i}`,instanceId=`card-${i}`,revision=i+1;
    const processIdentity=ids[i],profileId=ids[2],battleId=ids[3],path=`/api/rebuild/v1/profiles/${profileId}/battles/${battleId}`;
    const clips=hitManifest.card_animation_queues[cardId];
    const report={runKind:kind,passed:true,profileId,battleId,startedAtUnixMs:base+1000,finishedAtUnixMs:base+5000,actions:[
      {action:'play-card',inputSource:'slate-drag',revision,value:instanceId,pointerObservation:{lastGesture:{outcome:'submitted',battleId,
        cardId,cardInstanceId:instanceId,events:[{kind:'release',atUnixMs:base+1100}]}}}]};
    const command={phase:'ue-request',processIdentity,method:'POST',path:path+'/actions',type:'play-card',requestId,expectedRevision:revision,
      revision:revision+1,instanceId,status:200,replayed:false,profileId,battleId,receivedAtUnixMs:base+1103,upstreamCompletedAtUnixMs:base+1120,
      battleStatus:'player-turn',receiptEvents:[{type:'CardPlayed',cardId,instanceId},...clips.map((_,effectIndex)=>({type:'DamageApplied',actor:'player',target:'enemy',effectIndex}))]};
    f.events.push(command,{phase:'ue-response-delayed',processIdentity,requestId,path:path+'/actions',delayMs:1500,delayStartedAtUnixMs:base+1121},
      {phase:'ue-response-delivered',processIdentity,requestId,path:path+'/actions',type:'play-card',status:200,battleId,revision:revision+1,
        delayMs:1500,deliveredAtUnixMs:base+2621,time:base+2621},
      {phase:'ue-request',processIdentity,method:'GET',path,status:200,profileId,battleId,revision:revision+1,receivedAtUnixMs:base+2630,time:base+2635});
    const line=(name,fields)=>`LogTemp: Display: HCZS ${name}: request=${requestId} ${Object.entries(fields).map(([k,v])=>`${k}=${v}`).join(' ')}`;
    const impact=(ordinal,time,confirmed)=>line('windup impact position',{ordinal,clip:clips[ordinal],progress:hitManifest.player_hit_events[clips[ordinal]].progress+0.01,
      sourceRatio:hitManifest.player_hit_events[clips[ordinal]].progress,confirmed,atUnixMs:base+time});
    const reaction=(ordinal,time)=>line('confirmed reaction released',{actionIndex:revision,ordinal,clip:clips[ordinal],atUnixMs:base+time});
    const logs=[line('card intent dispatched',{revision,atUnixMs:base+1101}),line('card intent windup',{revision,atUnixMs:base+1102}),
      impact(0,1500,0),line('source impact held for authority',{ordinal:0,atUnixMs:base+1500}),
      line('visual receipt accepted',{revision:revision+1,actionIndex:revision,atUnixMs:base+2640}),reaction(0,2640)];
    if(clips.length===2)logs.push(impact(1,3400,1),reaction(1,3400));
    f.runs.push({kind,report,log:logs.join('\n')});
  }
  return f;
}
const replaceLog=(f,before,after)=>{f.runs[0].log=f.runs[0].log.replace(before,after);};
const reject=(edit)=>{const f=fixture();edit(f);const result=verifyVisualTiming(f);assert.equal(result.passed,false,JSON.stringify(result));};

test('current source ratios and two independent hit ordinals pass',()=>{
  const result=verifyVisualTiming(fixture());assert.equal(result.passed,true,JSON.stringify(result));
  assert.equal(result.summary.validatedOrdinals,3);assert.equal(result.summary.nonterminalTwoHitCases,1);
});
test('old halfway single-event logs cannot pass the new source timing contract',()=>reject(f=>{
  replaceLog(f,/ordinal=0 clip=fire_1_1 progress=[\d.]+ sourceRatio=[\d.]+/,'progress=0.502328');
}));
test('each ordinal rejects a missing impact or reaction and a repeated first hit',()=>{
  for(const marker of ['windup impact position','confirmed reaction released'])reject(f=>{
    f.runs[0].log=f.runs[0].log.split('\n').filter(l=>!(l.includes(marker)&&l.includes('ordinal=1'))).join('\n');
  });
  reject(f=>{f.runs[0].log+='\n'+f.runs[0].log.split('\n').find(l=>l.includes('confirmed reaction released')&&l.includes('ordinal=0'));});
  reject(f=>replaceLog(f,'ordinal=1 clip=fire_1_3','ordinal=0 clip=fire_1_3'));
});
test('reaction cannot precede its impact, authority acceptance, or prior ordinal',()=>{
  reject(f=>{const lines=f.runs[0].log.split('\n');[lines[6],lines[7]]=[lines[7],lines[6]];f.runs[0].log=lines.join('\n');});
  reject(f=>replaceLog(f,'ordinal=0 clip=fire_1_1 atUnixMs=2640','ordinal=0 clip=fire_1_1 atUnixMs=2639'));
  reject(f=>{const lines=f.runs[0].log.split('\n');[lines[5],lines[7]]=[lines[7],lines[5]];f.runs[0].log=lines.join('\n');});
});
test('rejects wrong clip, halfway source ratio and early actual clip progress',()=>{
  reject(f=>replaceLog(f,'ordinal=1 clip=fire_1_3','ordinal=1 clip=fire_1_1'));
  reject(f=>replaceLog(f,'sourceRatio=0.350154','sourceRatio=0.5'));
  reject(f=>replaceLog(f,/progress=[\d.]+/,'progress=0.1'));
});
test('manifest edits cannot redefine the source timing expected by the checker',()=>{
  reject(f=>{f.hitManifest.player_hit_events.fire_1_1.progress=0.5;});
  reject(f=>{f.hitManifest.card_animation_queues['410101']=['fire_1_1'];});
  assert.doesNotThrow(()=>validateHitManifest(hitManifest,sourceAudit));
});
test('authority evidence requires response finish and a subsequent independent latest GET',()=>{
  reject(f=>{f.events=f.events.filter(e=>e.phase!=='ue-response-delivered');});
  reject(f=>{f.events.find(e=>e.method==='GET').receivedAtUnixMs=2620;});
  reject(f=>{f.events.find(e=>e.phase==='ue-response-delivered').deliveredAtUnixMs=2700;});
  reject(f=>{f.events.find(e=>e.phase==='ue-response-delayed').delayMs=0;});
});
test('cross-battle, cross-request, cross-process, and orphan logs are rejected',()=>{
  reject(f=>{f.events[0].battleId=ids[0];});
  reject(f=>{f.events[0].processIdentity=ids[1];});
  reject(f=>replaceLog(f,'request=request-0','request=other'));
  reject(f=>{f.runs[0].log+='\nHCZS confirmed reaction released: request=other actionIndex=1 ordinal=0 clip=fire_1 atUnixMs=3500';});
});
test('missing or duplicated authority damage cannot substitute for two source stages',()=>{
  reject(f=>{delete f.events[0].receiptEvents;});
  reject(f=>{f.events[0].receiptEvents.pop();});
  reject(f=>{f.events[0].receiptEvents[2].effectIndex=0;});
  reject(f=>{f.events[0].receiptEvents[1].target='player';});
});
test('late authority requires an actual hold and consistent confirmed flag',()=>{
  reject(f=>{f.runs[0].log=f.runs[0].log.split('\n').filter(l=>!l.includes('held for authority')).join('\n');});
  reject(f=>replaceLog(f,'confirmed=0','confirmed=1'));
});
test('terminal first hit may omit second only with real terminal authority, but does not satisfy two-hit coverage',()=>{
  const f=fixture();
  // Preserve the first nonterminal two-hit case and make resume a one-hit terminal 410101.
  const run=f.runs[1],command=f.events.find(e=>e.type==='play-card'&&e.method==='POST'&&e.processIdentity===ids[1]);
  run.report.actions[0].pointerObservation.lastGesture.cardId='410101';command.receiptEvents[0].cardId='410101';command.battleStatus='won';
  command.receiptEvents.push({type:'BattleEnded',status:'won',reason:'enemy-defeated'});
  run.log=run.log.replaceAll('clip=fire_1 ','clip=fire_1_1 ').replace('sourceRatio=0.2307','sourceRatio=0.350154').replace(/progress=[\d.]+/,'progress=0.36');
  assert.equal(verifyVisualTiming(f).passed,true);
  command.battleStatus='player-turn';assert.equal(verifyVisualTiming(f).passed,false);
});
test('a terminal-only two-stage card does not fulfill nonterminal two-hit coverage',()=>reject(f=>{
  f.events[0].battleStatus='won';
}));
test('aborted or errored presentation is rejected even if hit counts look complete',()=>{
  reject(f=>{f.runs[0].log+='\nHCZS visual intent cleared: request=request-0 abortedPending=0 atUnixMs=3500';});
  reject(f=>{f.runs[0].log+='\nLogTemp: Error: HCZS authored hit event missing/incompatible: fire_1_1';});
});
test('receipt projection retains only required event fields and no arbitrary secrets',()=>{
  const result=projectVisualTimingReceipt({token:'secret',battle:{state:{status:'player-turn'},profile:{token:'secret'}},events:[
    {type:'CardPlayed',cardId:'410101',instanceId:'card',authorization:'secret'},
    {type:'DamageApplied',actor:'player',target:'enemy',effectIndex:0,unknown:{token:'secret'}},
    {type:'OtherEvent',token:'secret'}]});
  assert.deepEqual(result,{battleStatus:'player-turn',receiptEvents:[{type:'CardPlayed',cardId:'410101',instanceId:'card'},
    {type:'DamageApplied',actor:'player',target:'enemy',effectIndex:0}]});
  assert.throws(()=>projectVisualTimingReceipt({battle:{state:{status:'bad'}},events:[]}));
});
test('malformed ordinal is rejected, not silently ignored',()=>{
  assert.equal(parseVisualLog('HCZS windup impact position: request=x ordinal=NaN clip=fire_1 progress=0.4 sourceRatio=0.3 confirmed=0 atUnixMs=1000').problems.length,1);
});
