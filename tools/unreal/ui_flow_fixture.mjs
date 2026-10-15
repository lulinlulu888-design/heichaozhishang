// Synthetic validator contract fixture; this is not runtime or image evidence.
import { projectServerBattle } from './verify_ui_flow.mjs';

function baseFixture() {
  const p='11111111-1111-1111-1111-111111111111',b='22222222-2222-2222-2222-222222222222';
  const firstId='33333333-3333-3333-3333-333333333333',secondId='44444444-4444-4444-4444-444444444444',dbId='55555555-5555-5555-5555-555555555555';
  const hash='a'.repeat(64),secondHash='b'.repeat(64),stateHash='c'.repeat(64),scenarioHash='d'.repeat(64),database='hczs_test_ue_'+'a'.repeat(32);
  const tag=value=>({numeric_type:'integer',decimal:value});
  const definition={id:'tutorial-5000-test',player:{id:'1',name:'艾尔莎',maxHp:tag('100')},enemy:{id:'991',name:'幻眼魔方',maxHp:tag('100')},
    deck:[{instanceId:'card-1',cardId:'110001'}],cards:{'110001':{name:'斩击',cost:1,effects:[{type:'damage',target:'opponent',amount:'5'}]}},
    enemySkills:{'990':{effects:[{type:'damage',target:'opponent',amount:'2'}]}},enemyIntents:[['990']],enemyFallback:['990'],initialDraw:1,roundDraw:1,energyPerRound:1,handLimit:10,maxRounds:30};
  const battle={id:b,profileId:p,revision:5,scenario:{definition,encounterId:'tutorial-5000'},state:{format:'hczs-battle-session-v1',definitionId:definition.id,
    round:3,status:'won',outcomeReason:'enemy-defeated',energy:0,actionIndex:4,player:{hp:tag('80'),shield:tag('0')},enemy:{hp:tag('0'),shield:tag('0')},
    cards:definition.deck,piles:{hand:[],draw:[],discard:['card-1'],exhausted:[],powerUsed:[],removed:[]},rng:{algorithm:'mulberry32-v1',state:7}}};
  const final=projectServerBattle(battle),saved=structuredClone(final);
  Object.assign(saved,{revision:3,status:'player-turn',round:2,energy:1,enemyHp:'95',playerHp:'90',discardCount:0,hand:[{instanceId:'card-1',cardId:'110001',cost:1,name:'斩击'}]});
  const icons=['energy-icon','end-icon-normal','end-icon-active','shield-icon','deck-icon','card-cost'];
  const sprites=Object.fromEntries([...icons,'player-hp-bg','enemy-hp-bg'].map(key=>[key,icons.includes(key)?`/Game/Recovered/Battle/UI/AI/T_${key}`:`/Game/Recovered/Battle/UI/T_${key}`]));
  const paint=(map='L_TutorialBattle')=>({mode:'actual-nativepaint-and-slate-pointer-observation',map,paintSerial:4,sourceChineseFont:true,
    renderedTexts:['艾尔莎','幻眼魔方'],battleScene:map==='L_TutorialBattle',phase:map==='L_TutorialBattle'?3:2,profileId:p,battleId:b,pending:false,
    actualPaintedSprites:sprites,paintResources:sprites,hdIconVariant:true,hdIconsWithOriginalFootprint:6,sceneProblem:'',handCount:1,visible:true,serverPlayerHp:'90',serverEnemyHp:'95',controls:[],pointerEventSerial:0});
  const sourceIds=['standalone_d39d38f1ca5d191311abf53a','standalone_eb7f8c6b04784e4565579e7b','standalone_2f76a1a1318fd9d9d0c334e3',
    'd7319d96886bbe4d58eb4524','80c8b62820653c892c6f4104','a479406985055a836d73d810','8f96dcd8fa42d39c21e9a396','standalone_ac06da80916e1b49cf2bb923',
    'd6492d6903eb707e6b4ee8f9','1a3385b920e937f28cfba72a','a2d0a1bae517808aba3d2034','208e7c0ec0a8420948f63153'];
  const sourcePaint=()=>({...paint('L_ElsaHallFxPreview'),originalSourcePage:true,sourceReady:true,progressAvailable:false,chapterInstances:0,readOnlySourceInspection:false,
    sourceLayoutSha256:'8afc937db8a3cc13ddde0bc771995734895b590828b70454444d7b9e282007ef',renderedTexts:['世界线','本地战斗预览'],
    actualPaintedSprites:[...sourceIds],paintResources:Object.fromEntries(sourceIds.map(id=>[id,`/Game/Recovered/Worldline/UI/Sprites/T_${id}.T_${id}`])),controls:[{action:'local-battle-preview',value:'',enabled:true}]});
  const action=(action,value='',map='L_TutorialBattle',revision=0)=>({action,value,map,revision,surface:action==='local-battle-preview'?'worldline':action==='worldline'?'hall':'session',phase:map==='L_TutorialBattle'?3:2,inputSource:'slate-pointer',input:'mouse',controlHit:true,
    requestInFlight:false,pendingIntent:false,paint:{...(action==='local-battle-preview'?sourcePaint():paint(map)),controls:[{action,value,enabled:true}]},
    pointerObservation:{lastPointerAction:action,lastPointerValue:value,lastPointerTouch:false,pointerEventSerial:1}});
  const scene={ready:true,canPresentBattle:true,playerId:'1',enemyId:'991',playerMesh:'/Game/Recovered/Battle/Elsa/elsa.elsa',expectedPlayerMesh:'/Game/Recovered/Battle/Elsa/elsa.elsa',
    enemyMesh:'/Game/Recovered/Battle/Cube/cube.cube',expectedEnemyMesh:'/Game/Recovered/Battle/Cube/cube.cube',cameraTag:'HCZSBattleCamera',cameraReady:true,playerVisible:true,enemyVisible:true,
    playerLeftEnemyRight:true,playerScreenX:400,enemyScreenX:1200};
  const shot=(stage,map)=>({stage,path:`${stage}.png`,width:1600,height:900,worldMap:map,playerId:'1',enemyId:'991',paint:paint(map),scene});
  const worldlineShot=(stage,actionCount)=>({...shot(stage,'L_ElsaHallFxPreview'),actionCount,surface:'worldline',paint:sourcePaint(),scene:{ready:false}});
  const times=(start,end)=>({startedAtUnixMs:start,finishedAtUnixMs:end,startedAtUtc:new Date(start).toISOString(),finishedAtUtc:new Date(end).toISOString()});
  const initial={schemaVersion:1,mode:'ue-slate-ui-flow',runKind:'initial',passed:true,port:7465,profileId:p,battleId:b,ueProcessId:7001,runId:'77777777-7777-7777-7777-777777777777',...times(10,90),
    actions:[action('confirm-new-profile','','L_ElsaHallFxPreview'),action('create-profile','','L_ElsaHallFxPreview'),action('worldline','','L_ElsaHallFxPreview'),
      action('local-battle-preview','','L_ElsaHallFxPreview'),action('select-encounter','tutorial-5000','L_ElsaHallFxPreview'),
      action('new-battle','','L_ElsaHallFxPreview'),action('play-card','card-1','L_TutorialBattle',1),action('end-turn','','L_TutorialBattle',2),action('hall')],
    screenshots:[shot('hall-first','L_ElsaHallFxPreview'),worldlineShot('worldline-first',3),shot('battle-first','L_TutorialBattle')],finalBattle:saved};
  const resume={schemaVersion:1,mode:'ue-slate-ui-flow',runKind:'resume',passed:true,port:7465,profileId:p,battleId:b,checkpointObserved:structuredClone(saved),finalBattle:final,
    ueProcessId:7002,runId:'88888888-8888-8888-8888-888888888888',...times(120,200),
    actions:[action('select-profile',p,'L_ElsaHallFxPreview'),action('worldline','','L_ElsaHallFxPreview'),action('local-battle-preview','','L_ElsaHallFxPreview'),
      action('continue-battle',b,'L_ElsaHallFxPreview'),action('play-card','card-1','L_TutorialBattle',3),action('end-turn','','L_TutorialBattle',4),action('hall')],
    screenshots:[worldlineShot('worldline-resume',2),shot('battle-resume','L_TutorialBattle'),shot('hall-last','L_ElsaHallFxPreview')]};
  const events=[{phase:'ue-request',method:'POST',path:'/api/rebuild/v1/profiles',status:201,profileId:p,processIdentity:firstId,time:20},
    {phase:'ue-request',method:'POST',path:`/api/rebuild/v1/profiles/${p}/battles`,status:201,replayed:false,battleId:b,encounterId:'tutorial-5000',processIdentity:firstId,time:21},
    ...['play-card','end-turn','play-card','end-turn'].map((type,i)=>({phase:'ue-request',method:'POST',path:`/api/rebuild/v1/profiles/${p}/battles/${b}/actions`,status:200,replayed:false,type,
      ...(type==='play-card'?{instanceId:'card-1'}:{}),requestId:`ue-0000000${i+1}-0000-0000-0000-000000000000`,expectedRevision:i+1,revision:i+2,processIdentity:i<2?firstId:secondId,time:i<2?22+i:130+i}))];
  const images=Object.fromEntries([...initial.screenshots,...resume.screenshots].map(s=>[s.path,{width:1600,height:900,nonBlackRatio:0.7}]));
  const resumeCheckpoint={profileId:p,battleId:b,revision:saved.revision,actionIndex:saved.revision-1,stateSha256:stateHash,scenarioSha256:scenarioHash};
  events.push({phase:'test-server-ready',processIdentity:firstId,processIndex:0,pid:1234,time:1,resumed:false,databaseIdentity:dbId,mongoDatabase:database,manifestSha256:hash},
    {phase:'test-server-stopped',processIdentity:firstId,time:100,preservedDatabase:true,manifestSha256:hash},
    {phase:'test-server-ready',processIdentity:secondId,processIndex:1,pid:5678,time:110,resumed:true,databaseIdentity:dbId,mongoDatabase:database,manifestSha256:secondHash,previousManifestSha256:hash,resumeCheckpoint},
    {phase:'test-server-stopped',processIdentity:secondId,time:210,preservedDatabase:false,manifestSha256:secondHash});
  const testServer={schemaVersion:1,mode:'isolated-native-session-test-identity',readOnly:true,databaseLifecycle:'running',pid:5678,port:7465,runId:p,
    processIdentity:secondId,processIndex:1,databaseIdentity:dbId,mongoDatabase:database,mongoEndpoint:'127.0.0.1:27027',manifestSha256:secondHash};
  return {manifest:{schemaVersion:2,mode:'isolated-native-session-test',faults:false,mongoDatabase:database,port:7465,
    runId:p,databaseIdentity:dbId,processIdentity:secondId,previousProcessIdentity:firstId,processIndex:1,pid:5678,previousPid:1234,previousManifestSha256:hash,resumeCheckpoint},initial,resume,
    checkpoint:{mode:'ue-slate-ui-checkpoint',port:7465,profileId:p,battleId:b,battle:saved,initialRunId:initial.runId,initialUEProcessId:initial.ueProcessId},events,images,
    checkpointPersisted:{mode:'readonly-checkpoint-persisted-v1',port:7465,profileId:p,battleId:b,battle:structuredClone(saved),
      processIdentity:firstId,nodePid:1234,databaseIdentity:dbId,manifestSha256:hash,stateSha256:stateHash,scenarioSha256:scenarioHash},
    persisted:{bootstrap:{service:'hczs-rebuild',apiVersion:1,storage:'mongodb',profiles:[{id:p}]},profile:{id:p},hall:{profileId:p},battles:[{id:b}],battle,testServer},
    stopped:{stopped:true,databaseDropped:true,mongoDatabase:database,runId:p,databaseIdentity:dbId,processIdentity:secondId,processIndex:1,manifestSha256:secondHash,time:220}};
}

export function fixture() {
  const f=baseFixture(),p=f.checkpoint.profileId,b=f.checkpoint.battleId,mesh='/Game/Recovered/Battle/Cube/cube.cube';
  for(const r of [f.initial,f.resume]){r.startedAtUnixMs*=1000;r.finishedAtUnixMs*=1000;r.startedAtUtc=new Date(r.startedAtUnixMs).toISOString();r.finishedAtUtc=new Date(r.finishedAtUnixMs).toISOString();}
  for(const e of f.events){e.time*=1000;if(e.phase==='ue-request')e.receivedAtUnixMs=e.time-1;}
  f.stopped.time*=1000;
  const projection={actorTag:'HCZSBattleEnemy',actorId:'991',source:'native-bounds-eight-corners',valid:true,bounds:[900,180,1220,450],mesh};
  const trace=(serial,start,end,isTouch,outcome='submitted',reason='',point=[1040,300],threshold=5)=>({serial,cardInstanceId:'card-1',cardId:'110001',battleId:b,startRevision:isTouch?3:1,
    isTouch,pointerIndex:0,threshold,active:false,lostCapture:outcome==='cancelled',outcome,reason,targetId:outcome==='submitted'?'991':'',targetProjection:structuredClone(projection),events:[
      {kind:'start',point:[640,650],targetHit:false,upwardDelta:0,atUnixMs:start+10},
      {kind:'move',point:[...point],targetHit:outcome==='submitted',upwardDelta:650-point[1],atUnixMs:start+40},
      {kind:outcome==='cancelled'?'cancel':'release',point:[...point],targetHit:outcome==='submitted',upwardDelta:650-point[1],atUnixMs:end-10}]});
  const apply=(row,g,start,end)=>{row.inputSource='slate-drag';row.surface='session';row.input=g.isTouch?'touch':'mouse';row.startedAtUnixMs=start;row.finishedAtUnixMs=end;
    row.paint.lastGesture={serial:g.serial-1};row.pointerObservation.lastGesture=g;row.pointerObservation.lastPointerTouch=g.isTouch;};
  const initialCard=f.initial.actions.find(a=>a.action==='play-card'),resumeCard=f.resume.actions.find(a=>a.action==='play-card');
  apply(initialCard,trace(5,21900,21990,false),21900,21990);apply(resumeCard,trace(1,131900,131990,true),131900,131990);
  const playWire=f.events.filter(e=>e.type==='play-card');playWire[0].receivedAtUnixMs=21985;playWire[1].receivedAtUnixMs=131985;
  const refresh=()=>{const a=structuredClone(f.initial.actions.find(a=>a.action==='end-turn'));a.action='refresh-battle';a.value='';a.revision=1;
    a.paint.controls=[{action:a.action,value:'',enabled:true}];a.pointerObservation.lastPointerAction=a.action;a.pointerObservation.lastPointerValue='';return a;};
  const saved={...structuredClone(f.checkpoint.battle),revision:1,round:1,playerHp:'100',enemyHp:'100'};
  const negativeRows=[];
  const cases=[['tap-card','tap','tap','below-drag-threshold',[641,649],5],['invalid-target-card-drag','invalid-target','rejected','invalid-target',[280,330],30],
    ['outside-card-drag','outside','rejected','outside',[-20,320],5],['cancel-card-drag','cancel','cancelled','mouse-capture-lost',[750,440],5]];
  for(let i=0;i<cases.length;i++){
    const [action,kind,outcome,reason,point,threshold]=cases[i],base=21100+i*200;
    const row=structuredClone(initialCard);row.action=action;row.revision=1;row.paint.controls=[{action:'play-card',value:row.value,enabled:true}];
    apply(row,trace(i+1,base+30,base+90,false,outcome,reason,point,threshold),base+30,base+90);
    row.probe={kind,beforeServerRevision:1,afterServerRevision:1,startedAtUnixMs:base,finishedAtUnixMs:base+160,beforeBattle:structuredClone(saved),afterBattle:structuredClone(saved)};
    negativeRows.push(refresh(),row,refresh());
    for(const [receivedAtUnixMs,time]of[[base+5,base+10],[base+110,base+120]])f.events.push({phase:'ue-request',processIdentity:f.manifest.previousProcessIdentity,method:'GET',path:`/api/rebuild/v1/profiles/${p}/battles/${b}`,status:200,revision:1,receivedAtUnixMs,time});
  }
  f.initial.actions.splice(f.initial.actions.indexOf(initialCard),0,...negativeRows);
  for(const [r,row,stage]of[[f.initial,initialCard,'card-drag-preview'],[f.resume,resumeCard,'resumed-card-drag-preview']]){
    const template=r.screenshots.find(s=>s.worldMap==='L_TutorialBattle'),shot=structuredClone(template),g=structuredClone(row.pointerObservation.lastGesture);
    g.active=true;g.outcome='tracking';g.targetId='';g.events.pop();shot.stage=stage;shot.path=stage+'.png';shot.surface='session';shot.actionCount=r.actions.indexOf(row);
    shot.paint.lastGesture=g;shot.paint.dragPreviewPainted=true;r.screenshots.push(shot);f.images[shot.path]={width:1600,height:900,nonBlackRatio:0.7};
  }
  return f;
}
