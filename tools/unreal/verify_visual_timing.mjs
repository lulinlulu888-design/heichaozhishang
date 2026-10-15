// Read-only acceptance of native per-hit logs against source timing and HTTP receipts.
import { readFile, writeFile, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs, isDeepStrictEqual } from 'node:util';
import { createHash } from 'node:crypto';

const rows = value => Array.isArray(value) ? value : [];
const integer = value => Number.isSafeInteger(value) && value >= 0;
const sha = raw => createHash('sha256').update(raw).digest('hex');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const markers = new Map([
  ['card intent dispatched','dispatched'], ['card intent windup','windup'],
  ['windup impact position','impact'], ['source impact held for authority','held'],
  ['visual receipt accepted','accepted'], ['confirmed reaction released','reaction'],
  ['visual intent cleared','cleared'],
]);

export function parseVisualLog(log) {
  const events = [], problems = [];
  String(log).split(/\r?\n/).forEach((line,index) => {
    if (/\b(?:Error|Fatal):.*HCZS/.test(line) || line.includes('HCZS local windup stopped before its final pose'))
      problems.push(`Native presentation error at line ${index+1}`);
    const marker = [...markers].find(([text]) => line.includes(`HCZS ${text}:`));
    if (!marker) return;
    const fields = Object.fromEntries([...line.matchAll(/\b([A-Za-z]+)=([^\s;]+)/g)].map(m=>[m[1],m[2]]));
    for (const key of ['revision','actionIndex','atUnixMs','ordinal','progress','sourceRatio','confirmed','abortedPending']) {
      if (Object.hasOwn(fields,key)) fields[key] = /^\d+(?:\.\d+)?$/.test(fields[key]) ? Number(fields[key]) : NaN;
    }
    const event = {kind:marker[1],line:index+1,...fields};
    const needed = {dispatched:['revision'],windup:['revision'],impact:['ordinal','clip','progress','sourceRatio','confirmed'],
      held:['ordinal'],accepted:['revision','actionIndex'],reaction:['actionIndex','ordinal','clip'],cleared:['abortedPending']}[event.kind];
    if (!event.request || !integer(event.atUnixMs) || event.atUnixMs===0 || needed.some(k=>
      k==='clip' ? typeof event[k]!=='string'||!event[k] : !Number.isFinite(event[k])) ||
      ['ordinal','revision','actionIndex','confirmed'].some(k=>Object.hasOwn(event,k)&&!integer(event[k]))) {
      problems.push(`Malformed ${event.kind} log at line ${index+1}`);
    }
    events.push(event);
  });
  return {events,problems};
}

export function validateHitManifest(manifest,sourceAudit) {
  if (manifest?.schema!=='hczs-battle-hit-events-v1' || !manifest.card_animation_queues || !manifest.player_hit_events ||
      sourceAudit?.mode!=='elsa-authored-hit-timing-static-audit' || sourceAudit.auditPassed!==true ||
      sourceAudit.originalEventTrackSource?.sha256!==manifest.event_track_sha256) throw Error('Invalid source timing manifest/audit');
  for (const [clip,event] of Object.entries(manifest.player_hit_events)) {
    const source=sourceAudit.clips?.[clip],hits=rows(source?.events).filter(e=>e.name==='attack');
    if (hits.length!==1 || event.event_name!=='attack' || !Number.isFinite(event.progress) || event.progress<=0 || event.progress>=1 ||
        event.progress!==hits[0].normalizedClipProgress || event.ratio_literal!==hits[0].ratioLiteral ||
        event.duration_seconds!==source.durationSeconds || !isDeepStrictEqual(event.xml_byte_span,hits[0].xmlByteSpan))
      throw Error(`Manifest differs from source attack event: ${clip}`);
  }
  for (const [card,clips] of Object.entries(manifest.card_animation_queues)) {
    const skill=rows(sourceAudit.skills).filter(s=>String(s.skillId)===card);
    if (!Array.isArray(clips)||!clips.length||skill.length!==1||clips.some(c=>!manifest.player_hit_events[c])||
        !isDeepStrictEqual(clips,rows(skill[0].hitEventsForConfiguredClips).map(e=>e.clip)))
      throw Error(`Manifest differs from source card stages: ${card}`);
  }
  if (!isDeepStrictEqual(Object.keys(manifest.card_animation_queues).sort(),rows(sourceAudit.skills).map(s=>String(s.skillId)).sort()))
    throw Error('Source card coverage differs from manifest');
}

/** Request IDs are joined through their run's actual Node identity and battle path.
 * An ordinal is exactly one impact/reaction pair, never a whole-card dedupe key. */
export function verifyVisualTiming({manifest,runs,events,hitManifest,sourceAudit,uiVerification}) {
  const problems=[],intents=[];
  try { validateHitManifest(hitManifest,sourceAudit); } catch(error) { problems.push(error.message); }
  if (uiVerification?.passed!==true) problems.push('Independent UI/wire/persistence verification did not pass');
  if (manifest?.mode!=='isolated-native-session-test'||manifest.faults!==false) problems.push('An isolated no-fault run is required');
  const contexts=rows(runs);
  if (contexts.length!==2||contexts[0]?.kind!=='initial'||contexts[1]?.kind!=='resume') problems.push('Initial and resume logs are required');
  const seenKeys=new Set(),usedWire=new Set();
  for (const [runIndex,run] of contexts.entries()) {
    const report=run.report,processIdentity=runIndex===0?manifest?.previousProcessIdentity:manifest?.processIdentity;
    const parsed=parseVisualLog(run.log);problems.push(...parsed.problems.map(p=>`${run.kind}: ${p}`));
    if (report?.runKind!==run.kind||report?.passed!==true||!UUID.test(report?.battleId)||!UUID.test(report?.profileId)||!UUID.test(processIdentity))
      problems.push(`${run.kind}: invalid report/process identity`);
    const path=`/api/rebuild/v1/profiles/${report?.profileId}/battles/${report?.battleId}`;
    const actions=rows(report?.actions).filter(a=>a.action==='play-card');
    const requestIds=new Set();
    for (const action of actions) {
      const failed=[];const check=(name,condition)=>{if(!condition)failed.push(name);};
      const wire=rows(events).filter(e=>e.phase==='ue-request'&&e.processIdentity===processIdentity&&e.method==='POST'&&
        e.path===path+'/actions'&&e.type==='play-card'&&e.expectedRevision===action.revision&&e.instanceId===action.value);
      check('oneAuthoritativeCommand',wire.length===1&&wire[0].status===200&&wire[0].replayed===false);
      const command=wire[0]??{},requestId=command.requestId,key=`${report?.battleId}/${requestId}`;
      check('uniqueBattleRequest',typeof requestId==='string'&&requestId.length>0&&!seenKeys.has(key));seenKeys.add(key);requestIds.add(requestId);
      wire.forEach(w=>usedWire.add(w));
      const log=parsed.events.filter(e=>e.request===requestId),of=kind=>log.filter(e=>e.kind===kind);
      const singles={};for(const kind of ['dispatched','windup','accepted']){const matches=of(kind);check(`one_${kind}`,matches.length===1);singles[kind]=matches[0]??{};}
      const {dispatched,windup,accepted}=singles;
      check('noAbortedPresentation',of('cleared').length===0);
      const gesture=action.pointerObservation?.lastGesture,release=rows(gesture?.events).at(-1),cardId=gesture?.cardId;
      const clips=hitManifest?.card_animation_queues?.[cardId];
      check('physicalReleaseIdentity',action.inputSource==='slate-drag'&&gesture?.outcome==='submitted'&&gesture?.battleId===report?.battleId&&
        gesture.cardInstanceId===action.value&&release?.kind==='release'&&integer(release.atUnixMs));
      check('sourceCardMapping',Array.isArray(clips)&&clips.length>0);
      const receipt=rows(command.receiptEvents),played=receipt.filter(e=>e.type==='CardPlayed'),damage=receipt.filter(e=>e.type==='DamageApplied');
      check('authoritativeReceiptEvents',Array.isArray(command.receiptEvents)&&played.length===1&&played[0].cardId===cardId&&played[0].instanceId===action.value&&
        ['player-turn','won','lost'].includes(command.battleStatus)&&damage.length>0&&damage.every((e,i)=>e.actor==='player'&&e.target==='enemy'&&
          integer(e.effectIndex)&&(i===0||e.effectIndex>damage[i-1].effectIndex))&&damage.length<=rows(clips).length&&
        !receipt.some(e=>e.type==='EnemySkillUsed'));
      check('onlyTerminalAuthorityMayOmitStage',damage.length===rows(clips).length||command.battleStatus==='won'&&
        receipt.some(e=>e.type==='BattleEnded'&&e.status==='won'&&e.reason==='enemy-defeated'));
      check('authorityRevisionAndIdentity',command.battleId===report?.battleId&&command.profileId===report?.profileId&&
        command.revision===action.revision+1&&dispatched.revision===action.revision&&windup.revision===action.revision&&
        accepted.revision===command.revision&&accepted.actionIndex===action.revision);
      const delivered=rows(events).filter(e=>e.phase==='ue-response-delivered'&&e.processIdentity===processIdentity&&
        e.requestId===requestId&&e.path===path+'/actions');
      check('oneActualResponseFinish',delivered.length===1);
      const finish=delivered[0]??{},finishedAt=finish.deliveredAtUnixMs;
      check('responseFinishIdentity',finish.status===200&&finish.type==='play-card'&&finish.battleId===report?.battleId&&
        finish.revision===command.revision&&integer(finishedAt)&&integer(finish.time)&&finish.time>=finishedAt);
      check('releaseDispatchWindupBeforeResponse',release?.atUnixMs<=dispatched.atUnixMs&&dispatched.atUnixMs<=windup.atUnixMs&&
        dispatched.line<windup.line&&dispatched.atUnixMs<=command.receivedAtUnixMs&&command.receivedAtUnixMs<=command.upstreamCompletedAtUnixMs&&
        command.upstreamCompletedAtUnixMs<=finishedAt&&windup.atUnixMs<finishedAt&&finishedAt<=accepted.atUnixMs&&windup.line<accepted.line);
      const latest=rows(events).filter(e=>e.phase==='ue-request'&&e.processIdentity===processIdentity&&e.method==='GET'&&e.path===path&&
        e.status===200&&e.battleId===report?.battleId&&e.profileId===report?.profileId&&e.revision===command.revision&&
        e.receivedAtUnixMs>=finishedAt&&e.time>=e.receivedAtUnixMs&&e.time<=accepted.atUnixMs);
      check('independentLatestReadBeforeAcceptance',latest.length>0);
      const delays=rows(events).filter(e=>e.phase==='ue-response-delayed'&&e.processIdentity===processIdentity&&e.requestId===requestId&&e.path===path+'/actions');
      check('configuredDelayActuallyObserved',integer(manifest?.cardResponseDelayMs)&&manifest.cardResponseDelayMs>0&&delays.length===1&&
        delays[0].delayMs===manifest.cardResponseDelayMs&&finish.delayMs===manifest.cardResponseDelayMs&&
        finishedAt-delays[0].delayStartedAtUnixMs>=manifest.cardResponseDelayMs);
      const impacts=of('impact'),reactions=of('reaction'),holds=of('held'),stages=[];
      check('oneImpactAndReactionPerAuthoritativeOrdinal',impacts.length===damage.length&&reactions.length===damage.length);
      check('ordinalRange', [...impacts,...reactions,...holds].every(e=>integer(e.ordinal)&&e.ordinal<damage.length));
      for(let ordinal=0;ordinal<damage.length;ordinal++) {
        const impactRows=impacts.filter(e=>e.ordinal===ordinal),reactionRows=reactions.filter(e=>e.ordinal===ordinal),heldRows=holds.filter(e=>e.ordinal===ordinal);
        const impact=impactRows[0]??{},reaction=reactionRows[0]??{},clip=clips?.[ordinal],source=hitManifest?.player_hit_events?.[clip];
        check(`ordinal_${ordinal}_exactlyOnce`,impactRows.length===1&&reactionRows.length===1);
        check(`ordinal_${ordinal}_sourceRatio`,impact.clip===clip&&reaction.clip===clip&&source&&
          impact.sourceRatio===Number(source.progress.toFixed(6))&&Number.isFinite(impact.progress)&&impact.progress+0.000001>=source.progress&&impact.progress<=1.000001);
        check(`ordinal_${ordinal}_afterImpactAndAuthority`,impact.line>windup.line&&impact.atUnixMs>=windup.atUnixMs&&reaction.line>impact.line&&
          reaction.line>accepted.line&&reaction.atUnixMs>=impact.atUnixMs&&reaction.atUnixMs>=accepted.atUnixMs&&reaction.actionIndex===accepted.actionIndex);
        const alreadyConfirmed=impact.line>accepted.line;
        check(`ordinal_${ordinal}_confirmationFlag`,impact.confirmed===(alreadyConfirmed?1:0)&&
          (alreadyConfirmed?impact.atUnixMs>=accepted.atUnixMs:impact.atUnixMs<=accepted.atUnixMs));
        check(`ordinal_${ordinal}_authorityHold`,alreadyConfirmed?heldRows.length===0:heldRows.length===1&&
          heldRows[0].line>impact.line&&heldRows[0].line<accepted.line&&heldRows[0].atUnixMs>=impact.atUnixMs&&heldRows[0].atUnixMs<=accepted.atUnixMs);
        if(ordinal>0) {
          const previous=stages[ordinal-1];
          check(`ordinal_${ordinal}_ordered`,impact.line>previous.reactionLine&&impact.atUnixMs>=previous.reactionAtUnixMs&&
            reaction.line>previous.reactionLine&&reaction.atUnixMs>=previous.reactionAtUnixMs);
        }
        stages.push({ordinal,clip,sourceRatio:impact.sourceRatio,impactProgress:impact.progress,impactAtUnixMs:impact.atUnixMs,
          reactionAtUnixMs:reaction.atUnixMs,impactLine:impact.line,reactionLine:reaction.line});
      }
      check('eventsWithinActualUERun',log.every(e=>integer(e.atUnixMs)&&e.atUnixMs>=report.startedAtUnixMs&&e.atUnixMs<=report.finishedAtUnixMs));
      intents.push({battleId:report?.battleId,requestId,run:run.kind,cardId,instanceId:action.value,expectedRevision:action.revision,
        confirmedRevision:command.revision,authoritativeDamageCount:damage.length,battleStatus:command.battleStatus,
        responseFinishedAtUnixMs:finishedAt,acceptedAtUnixMs:accepted.atUnixMs,stages,passed:failed.length===0,failed});
    }
    if (!actions.length) problems.push(`${run.kind}: no physical card play`);
    for(const event of parsed.events)if(!requestIds.has(event.request))problems.push(`${run.kind}: orphan ${event.kind} at line ${event.line}`);
  }
  const commands=rows(events).filter(e=>e.phase==='ue-request'&&e.method==='POST'&&e.type==='play-card');
  if(commands.some(c=>!usedWire.has(c)))problems.push('An action command has no matching physical UI intent');
  const multiHit=intents.filter(i=>i.cardId==='410101'&&i.authoritativeDamageCount===2&&i.battleStatus==='player-turn'&&i.passed);
  if(!multiHit.length)problems.push('Missing a successful real nonterminal 410101 two-hit case');
  return {schema:'hczs-visual-timing-verification-v2',mode:'actual-ue-ordinal-logs-and-authoritative-http-receipts',
    passed:problems.length===0&&intents.length>0&&intents.every(i=>i.passed),problems,intents,
    summary:{playIntents:intents.length,validatedOrdinals:intents.reduce((n,i)=>n+i.stages.length,0),nonterminalTwoHitCases:multiHit.length},
    scope:{originalApkExecuted:false,sourceRatiosMatched:problems.length===0&&intents.length>0&&intents.every(i=>!i.failed.some(f=>f.includes('sourceRatio')||f==='sourceCardMapping')),
      originalFullTimingEquivalence:false,hpOrOutcomePredictionClaimed:false,
      dbMutatedByThisVerifier:false,unrealLaunchedByThisVerifier:false}};
}

async function main() {
  const {values}=parseArgs({options:{'record-directory':{type:'string'}}});
  if(!values['record-directory'])throw Error('Pass --record-directory <isolated UI run>');
  const root=fileURLToPath(new URL('../../',import.meta.url)),allowed=await realpath(resolve(root,'analysis/unreal/session-test'));
  const directory=await realpath(resolve(values['record-directory']));
  const within=(base,path)=>{const r=relative(base,path);return Boolean(r)&&!r.startsWith('..')&&!isAbsolute(r);};
  if(!within(allowed,directory))throw Error('Not an isolated run directory');
  const sources=[];
  const read=async(base,path,json=true)=>{const real=await realpath(resolve(base,path));if(!within(base,real))throw Error('Evidence escaped its directory');
    const raw=await readFile(real);sources.push({path:relative(root,real).replaceAll('\\','/'),sha256:sha(raw)});return json?JSON.parse(raw.toString('utf8')):raw.toString('utf8');};
  const manifest=await read(directory,'server.json'),hitManifest=await read(root,'analysis/unreal/battle-hit-timing/manifest.json');
  const auditRaw=await read(root,hitManifest.source_audit,false);
  if(sha(auditRaw)!==hitManifest.source_audit_sha256)throw Error('Source timing audit hash changed');
  const sourceAudit=JSON.parse(auditRaw);
  for(const identity of rows(sourceAudit.sources)) {
    const path=await realpath(resolve(root,identity.path??identity.output));if(!within(root,path))throw Error('Source outside project');
    if(sha(await readFile(path))!==(identity.sha256??identity.decoded_sha256))throw Error(`Source file hash changed: ${path}`);
  }
  const runs=[];for(const kind of ['initial','resume'])runs.push({kind,report:await read(directory,`ui-${kind}.json`),log:await read(directory,`ue-${kind}.log`,false)});
  const events=(await read(directory,'http-trace.jsonl',false)).trim().split(/\r?\n/).filter(Boolean).map(line=>JSON.parse(line));
  const uiVerification=await read(directory,'ui-flow-verification.json');
  const result={...verifyVisualTiming({manifest,runs,events,hitManifest,sourceAudit,uiVerification}),sources};
  await writeFile(resolve(directory,'visual-timing-verification.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));if(!result.passed)process.exitCode=1;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))await main();
