"""Dedicated PIE acceptance: fresh GI create -> source2133 SHOW -> continue/cancel.

Require -HczsMainlineUITest -HczsServerPort=17470
-HczsMainlineManifest=<owned server.json> -ExecCmds="py <this file>".
HTTP creates only a fresh profile; native GI creates both battles. No cards,
turns or settlements are submitted. The dedicated Editor exits on completion.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import struct
import sys
import time
import traceback
import urllib.request

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import test_mainline_ui as guard

ROOT = TOOLS.parents[1]
BATTLE = 'L_TutorialSource2133'
HALL = 'L_ElsaHallFxPreview'
SHOW = '/Game/Recovered/Battle/Entrance/elsa_entrance.elsa_entrance'
# GameStartup.initGlobals aspect classes -> ResolutionConst.BATTLE_CAMERA_FOV.
SOURCE_ASPECT_CLASSES = ((2.58333, 30.0), (2.1653, 35.65), (1.777, 35.985), (1.333, 46.75))


def source_horizontal_fov(aspect):
    """CameraBattle.__init__ vertical FOV rule, converted for UE's horizontal FOV."""
    if 1.77777 - aspect > .01 and aspect - 1.33333 > .01:
        vertical = 35.985 + (46.75 - 35.985) / .44444 * (1.77777 - aspect)
    elif aspect < 1.33333 and abs(1.33333 - aspect) > abs(aspect - 1):
        vertical = 55.0
    else:
        vertical = min(SOURCE_ASPECT_CLASSES, key=lambda row: abs(row[0] - aspect))[1]
    return math.degrees(2 * math.atan(math.tan(math.radians(vertical) / 2) * aspect))


def run():
    import unreal as u
    command = u.SystemLibrary.get_command_line()
    argument = guard.argument(command, 'HczsMainlineManifest')
    guard.check(argument, 'Require owned HczsMainlineManifest')
    path = Path(argument).resolve(); raw = path.read_bytes()
    guard.check(len(raw)<1024*1024, 'Oversized manifest')
    manifest = json.loads(raw)
    address = guard.validate_manifest(manifest, path, command)
    guard.check(manifest['port'] == 17470 and not manifest.get('mainlineFaults', False), 'Require fresh isolated17470 without faults')
    guard.check(not guard.flag(command,'HczsMainlineUIResume'), 'Fresh entrance test cannot resume a previous run')
    log_arg=guard.argument(command,'abslog') or guard.argument(command,'ABSLOG')
    guard.check(log_arg and Path(log_arg).resolve().parent==path.parent, 'Pass -abslog=<this owned run/ue-entrance.log> for native event verification')
    native_log=Path(log_arg).resolve()
    guard.check(Path(u.Paths.project_dir()).resolve() == (ROOT/'clients/unreal5 5.8').resolve()
                and u.SystemLibrary.get_engine_version().startswith('5.8.'), 'Wrong project/engine')
    editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    guard.check(not editor.get_game_world(), 'Use a dedicated Editor before PIE, never the active preview')
    start = int(time.time()*1000); prefix = 'fresh-entrance-' + str(time.time_ns())
    output = path.parent/(prefix+'.json')
    report = dict(schemaVersion=1, mode='native-gi-fresh-entrance', passed=False, nativePointerInput=False,
                  startedAtUnixMs=start, sourceSfxPlayed=False, samples=[], screenshots=[], checks=[])

    def http(route, body=None, control=False):
        guard.check(route.startswith('/api/rebuild/v1/') or control and route == '/__hczs_test_control/identity', 'Unexpected HTTP route')
        headers = {'Accept':'application/json'}
        if control: headers['Authorization'] = 'Bearer '+manifest['controlToken']
        if body is not None: headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(address+route, headers=headers, data=None if body is None else json.dumps(body).encode())
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), guard.NoRedirect()).open(request, timeout=15) as response:
            value = response.read(8*1024*1024+1)
        guard.check(len(value) <= 8*1024*1024, 'Oversized isolated response')
        return json.loads(value)

    def identity():
        guard.check(path.read_bytes() == raw, 'Manifest changed during acceptance')
        value = http('/__hczs_test_control/identity', control=True)
        guard.validate_identity(value, manifest, raw)
        return value

    report['identity'] = identity()

    def prepare():
        bootstrap = http('/api/rebuild/v1/bootstrap')
        guard.check(bootstrap.get('profiles') == [] and 'mainline-progression' in bootstrap.get('capabilities', []), 'Use an empty owned mainline run')
        profile = http('/api/rebuild/v1/profiles', {'displayName':'原入场独立验收'})['profile']['id']
        identity(); return profile

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-entrance-owned')
    future = pool.submit(prepare)
    state = dict(stage='prepare', entered=time.monotonic(), started=time.monotonic(), busy=False, done=False,
                 game=None, world=None, ids=[], shot=None, camera=None)

    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')

    def stage(name):
        state.update(stage=name, entered=time.monotonic()); report['stage']=name; save()

    def passed(name): report['checks'].append(dict(name=name, passed=True))

    def finish(error=None):
        if state['done']: return
        state['done']=True
        report.update(passed=error is None, error=error, finishedAtUnixMs=int(time.time()*1000))
        save(); u.unregister_slate_post_tick_callback(handle); pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS fresh entrance result: '+str(output))
        if error: u.log_error(error)
        u.SystemLibrary.quit_editor()

    def actor(tag):
        values = u.GameplayStatics.get_all_actors_with_tag(state['world'], tag)
        guard.check(len(values)==1, 'Actor is not unique: '+tag)
        return values[0]

    def observe(game, world):
        level = u.GameplayStatics.get_current_level_name(world, True)
        sample = dict(atUnixMs=int(time.time()*1000), worldTime=float(u.GameplayStatics.get_time_seconds(world)),
            stage=state['stage'], map=level, phase=int(game.get_editor_property('phase').value),
            locked=bool(game.is_battle_entrance_locked()), canSubmit=bool(game.can_submit_battle_intent()))
        if level == BATTLE:
            presenter = actor('HCZSBattlePresentation'); player_actor=actor('HCZSBattlePlayer')
            mesh=player_actor.get_component_by_class(u.SkeletalMeshComponent)
            camera=actor('HCZSBattleCamera'); cc=camera.get_component_by_class(u.CameraComponent)
            guard.check(u.GameplayStatics.get_player_controller(world, 0).get_view_target()==camera, 'Default battle camera is not selected')
            guard.check(abs(camera.get_actor_location().x)<.02 and abs(camera.get_actor_location().y-3000)<.02
                        and abs(camera.get_actor_location().z)<.02, 'Wrong source camera position')
            animation=mesh.get_anim_instance()
            clip=animation.get_animation_asset().get_path_name() if isinstance(animation,u.AnimSingleNodeInstance) and animation.get_animation_asset() else None
            bones={}
            for bone in ('bip001','bip001-pelvis','bip001-prop1'):
                if mesh.get_bone_index(bone)>=0:
                    value=mesh.get_socket_transform(bone,u.RelativeTransformSpace.RTS_COMPONENT)
                    bones[bone]=[value.translation.x,value.translation.y,value.translation.z,
                                 value.rotation.x,value.rotation.y,value.rotation.z,value.rotation.w]
            guard.check(len(bones)>=2 and mesh.get_num_bones()==180, 'Source battle skeleton readback missing')
            if report['entranceFx']:
                fx=json.loads(presenter.get_entrance_source_fx().development_describe())
                sample['entranceFx']=fx
                for name, low, high in (('entrance-fx-early', .08, .2), ('entrance-fx-late', .3, .5)):
                    if fx.get('playing') and low < fx['seconds'] < high and name not in state:
                        target = path.parent/(prefix+'-'+name+'.png')
                        state[name] = target
                        u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
            current=game.get_editor_property('current_battle')
            sample.update(battleId=current.get_editor_property('id'), revision=int(current.get_editor_property('revision')),
                actionIndex=int(current.get_editor_property('action_index')), playing=bool(presenter.is_entrance_playing()),
                entrancePhase=presenter.get_entrance_phase(), position=float(presenter.get_entrance_position()),
                busy=bool(presenter.is_presentation_busy()), visible=bool(mesh.get_editor_property('visible')),
                actorHidden=bool(player_actor.get_editor_property('hidden')), clip=clip,
                actualClipPosition=float(mesh.get_position()), bones=bones, camera=dict(path=camera.get_path_name(),
                    location=[camera.get_actor_location().x,camera.get_actor_location().y,camera.get_actor_location().z],
                    rotation=[cc.get_world_rotation().roll,cc.get_world_rotation().pitch,cc.get_world_rotation().yaw],
                    worldLocation=[cc.get_world_location().x,cc.get_world_location().y,cc.get_world_location().z],
                    fov=float(cc.get_editor_property('field_of_view')), aspect=float(cc.get_editor_property('aspect_ratio')),
                    constrainAspect=bool(cc.get_editor_property('constrain_aspect_ratio')),
                    viewport=[float(v) for v in (u.WidgetLayoutLibrary.get_viewport_size(world).x, u.WidgetLayoutLibrary.get_viewport_size(world).y)]))
            if report.get('roundStartDeal') or report.get('dragRetest'):
                guard.check(sample['actionIndex'] in (0, 1) and sample['revision'] == sample['actionIndex'] + 1,
                            'Acceptance changed more than one authoritative action')
            else:
                guard.check(sample['revision']==1 and sample['actionIndex']==0, 'Entrance unexpectedly changed authoritative state')
            if sample['playing']:
                guard.check(sample['locked'] and not sample['canSubmit'] and sample['busy'], 'Playing entrance did not lock intents')
                if sample['entrancePhase']=='waiting-hidden': guard.check(not sample['visible'] and sample['actorHidden'], 'Source0.5s wait did not hide player')
                if sample['entrancePhase'].startswith('show-'):
                    guard.check(clip==SHOW and math.isfinite(sample['position']) and abs(sample['position']-sample['actualClipPosition'])<.002,
                                'Entrance is not using the real source clip position')
                if sample['entrancePhase']=='show-visible': guard.check(sample['visible'] and not sample['actorHidden'], 'Source SHOW did not reveal player')
        if level == BATTLE:
            widgets = u.WidgetLibrary.get_all_widgets_of_class(world, u.load_class(None, '/Script/Hczs.HczsSessionWidget'), True)
            guard.check(len(widgets) == 1, 'Battle session widget missing/duplicated')
            ui = json.loads(widgets[0].development_describe_ui())
            sample['opening'] = {k: ui.get(k) for k in ('openingSeconds', 'openingPaintedNodes', 'openingTimelineValid', 'dealtCards', 'sourceOwnCardOriginY', 'hudIn', 'roundDeal', 'uiAudio')}
            sample['playableCards'] = len([c for c in ui.get('controls', []) if c.get('action') == 'play-card' and c.get('enabled')])
            opening = sample['opening']
            hud = opening.get('hudIn') or {}
            if 0.15 < hud.get('seconds', -1) < 0.3 and 'hudInShot' not in state:
                target = path.parent/(prefix+'-hud-in-mid.png')
                state['hudInShot'] = target
                u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
            if opening['openingSeconds'] is not None and 1.85 < opening['openingSeconds'] < 2.4:
                guard.check(opening['openingTimelineValid'] and opening['openingPaintedNodes'] > 0,
                            'Original elite opening timeline did not paint')
                if 'openingShot' not in state:
                    target = path.parent/(prefix+'-elite-opening.png')
                    state['openingShot'] = target
                    u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
            cards = opening.get('dealtCards', [])
            opening_cards = [c for c in cards if c.get('route') != 'round-start']
            if opening_cards and sample.get('entrancePhase') == 'first-deal':
                guard.check(sample['locked'] and not sample['canSubmit'] and sample['busy'], 'Dispatch allowed a gameplay command')
                guard.check(opening['sourceOwnCardOriginY'] == 720, 'Source OwnCardArea bottom-root offset changed')
                if 'centre-hold' in {c['phase'] for c in opening_cards} and 'dealShot' not in state:
                    target = path.parent/(prefix+'-first-deal-centre.png')
                    state['dealShot'] = target
                    u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
                if 'drop-to-hand' in {c['phase'] for c in opening_cards} and 'dropShot' not in state:
                    target = path.parent/(prefix+'-first-deal-drop.png')
                    state['dropShot'] = target
                    u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
        report['samples'].append(sample)
        return sample

    def capture(name):
        target=path.parent/(prefix+'-'+name+'.png')
        guard.check(not target.exists() and not any(c in target.as_posix() for c in ('"','\r','\n')), 'Unsafe capture path')
        state['shot']=dict(path=target, name=name, requested=time.monotonic())
        u.SystemLibrary.execute_console_command(state['world'],'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')

    def shot_done():
        shot=state['shot']; elapsed=time.monotonic()-shot['requested']
        guard.check(elapsed<20, 'Screenshot write timed out')
        if elapsed<1 or not shot['path'].exists(): return False
        png=shot['path'].read_bytes()
        guard.check(len(png)>1024 and png[:8]==b'\x89PNG\r\n\x1a\n', 'Actual camera PNG missing')
        width,height=struct.unpack('>II',png[16:24])
        report['screenshots'].append(dict(stage=shot['name'],path=str(shot['path']),width=width,height=height))
        return True

    def read_battle(identity_battle):
        return http('/api/rebuild/v1/profiles/'+state['profile']+'/battles/'+identity_battle)['battle']

    def final_reads():
        identity(); route='/api/rebuild/v1/profiles/'+state['profile']+'/battles'
        listed=http(route)['battles']; guard.check({b['id'] for b in listed}==set(state['ids']), 'Unexpected battle created')
        battles=[read_battle(value) for value in state['ids']]
        for value in battles:
            guard.check(value['revision']==1 and value['state']['actionIndex']==0 and value['state']['status']=='player-turn', 'Entrance/return changed business state')
        guard.check(battles[0]==state['firstAuthority'], 'Continue changed the unchanged first battle')
        rows=[json.loads(line) for line in Path(manifest['tracePath']).read_text('utf8').splitlines() if line.strip()]
        writes=[r for r in rows if r.get('phase')=='ue-request' and r.get('method') in ('POST','PATCH','DELETE') and r.get('receivedAtUnixMs',-1)>=start]
        guard.check(len(writes)==3 and [r.get('path') for r in writes]==['/api/rebuild/v1/profiles',route,route]
                    and [r.get('battleId') for r in writes[1:]]==state['ids']
                    and all(r.get('status')==201 and r.get('replayed') is False for r in writes[1:]), 'Unexpected command/replay on wire')
        log=native_log.read_text('utf8',errors='replace'); events=[]
        for index,battle_id in enumerate(state['ids']):
            def matching(prefix):
                return [line for line in log.splitlines() if prefix in line and 'battle='+battle_id in line]
            starts=matching('HCZS entrance fresh-start:'); shows=matching('HCZS entrance source SHOW:')
            cues=matching('HCZS entrance source cue:'); ends=matching('HCZS entrance finished:')
            guard.check(len(starts)==len(shows)==len(ends)==1 and len(cues)==(1 if index==0 else 0),
                        'Native entrance/cue was absent or replayed: '+battle_id)
            times=[int(re.search(r'atUnixMs=(\d+)',line)[1]) for line in (starts[0],shows[0],ends[0])]
            guard.check(times[1]-times[0]>=450, 'Native source SHOW started before the authored0.5s wait')
            guard.check(('completed=1' if index==0 else 'completed=0') in ends[0], 'Native completion/cancellation outcome differs')
            fx_starts=matching('HCZS entrance source fx started:'); fx_ends=matching('HCZS entrance source fx finished:')
            if report['entranceFx'] and index==0:
                guard.check(len(fx_starts)==1 and len(fx_ends)==1 and 'reason=complete' in fx_ends[0]
                            and 'maxActiveLayers=3' in fx_ends[0], 'Entrance source fx did not start once and complete')
            else:
                guard.check(not fx_starts, 'Entrance source fx played without the cue/opt-in')
            if index==0:
                guard.check(times[2]-times[1]>=3600 and ('effectPlayed=1' if report['entranceFx'] else 'effectPlayed=0') in cues[0]
                            and float(re.search(r'position=([0-9.]+)',cues[0])[1])>=3.7*.144595-.000002,
                            'Native actual-position completion/source event differs')
            events.append(dict(battleId=battle_id,freshStarts=1,showStarts=1,sourceCueCount=len(cues),
                completed=index==0,hiddenWaitUnixMs=times[1]-times[0],showToEndUnixMs=times[2]-times[1]))
        return dict(authoritative=[dict(id=b['id'],revision=b['revision'],actionIndex=b['state']['actionIndex'],status=b['state']['status']) for b in battles],
                    wireMutations=[{key:r.get(key) for key in ('method','path','requestId','battleId','status')} for r in writes],nativeLog=str(native_log),nativeEvents=events)

    def tick(delta):
        if state['busy'] or state['done']: return
        state['busy']=True
        try:
            guard.check(time.monotonic()-state['started']<150, 'Entrance acceptance deadline at '+state['stage'])
            world=editor.get_game_world()
            if not world: return
            state['world']=world; game=state['game']=u.GameplayStatics.get_game_instance(world)
            if not game: return
            current=state['stage']; elapsed=time.monotonic()-state['entered']; sample=observe(game,world)
            if game.get_editor_property('request_in_flight'):
                if current == 'reject-hold':
                    clip = sample.get('clip') or ''
                    if sample.get('busy') and 'idle' not in clip:
                        state['sawAttackWindup'] = clip
                return
            if not (report.get('rejectPlay') and current in ('reject-hold', 'reject-recover')):
                guard.check(not game.get_editor_property('has_pending_intent') and not game.get_editor_property('error_code'), 'Native request failed or left an unresolved intent')
            if current=='prepare' and future.done():
                state['profile']=future.result(); report['profileId']=state['profile']; game.refresh_bootstrap(); stage('profile')
            elif current=='profile': game.select_profile(state['profile']); stage('hall-first')
            elif current in ('hall-first','hall-new') and game.is_hall_scene_ready() and sample['map']==HALL:
                guard.check(game.get_editor_property('selected_profile_id')==state['profile'] and not sample['locked'], 'Wrong profile/leftover hall lock')
                game.select_encounter('tutorial-5000'); stage('scenario-first' if current=='hall-first' else 'scenario-new')
            elif current in ('scenario-first','scenario-new') and game.get_editor_property('encounter_scenario_ready'):
                game.create_selected_battle(); stage('entrance-first' if current=='scenario-first' else 'entrance-cancel')
            elif current=='entrance-first' and sample['map']==BATTLE:
                if sample['battleId'] not in state['ids']: state['ids'].append(sample['battleId'])
                if sample.get('entrancePhase')=='complete':
                    history=[r for r in report['samples'] if r.get('battleId')==sample['battleId'] and r.get('playing')]
                    hidden=[r for r in history if r['entrancePhase']=='waiting-hidden']; shown=[r for r in history if r['entrancePhase']=='show-visible']
                    guard.check(hidden and len(shown)>3 and sample['position']>=3.698 and not sample['locked'] and sample['canSubmit'] and not sample['busy'], 'Source wait/SHOW/completion/unlock was not observed')
                    guard.check(shown[-1]['position']>shown[0]['position']+.5 and shown[-1]['bones']!=shown[0]['bones'], 'Real source pose did not advance')
                    report['sampledHiddenToShowLowerBoundSeconds']=shown[0]['worldTime']-hidden[0]['worldTime']
                    opening_samples = [r['opening'] for r in history if r.get('opening', {}).get('openingSeconds', -1) > 1.85
                                       and r.get('opening', {}).get('openingSeconds', 4) < 2.4]
                    guard.check(opening_samples and all(o['openingTimelineValid'] and o['openingPaintedNodes'] > 0 for o in opening_samples),
                                'Native elite banner paint was not observed')
                    guard.check(state.get('openingShot') and state['openingShot'].exists(), 'Opening screenshot missing')
                    report['openingScreenshot'] = str(state['openingShot'])
                    passed('original-elite-banner-source-timeline-paints')
                    deal_samples = [r['opening']['dealtCards'] for r in report['samples'] if r.get('opening',{}).get('dealtCards')]
                    phases = {c['phase'] for cards in deal_samples for c in cards}
                    guard.check({'waiting','fly-to-centre','centre-hold','drop-to-hand'} <= phases, 'Source first-deal phases missing')
                    guard.check(any(abs(c['tilt']) > 1 for cards in deal_samples for c in cards), 'Source drop tilt did not advance')
                    guard.check(state.get('dealShot') and state['dealShot'].exists() and state.get('dropShot') and state['dropShot'].exists(), 'Native card flight screenshots missing')
                    report['dealScreenshots'] = [str(state['dealShot']), str(state['dropShot'])]
                    passed('source-first-deal-stagger-centre-bezier-tilt-and-input-lock')
                    huds=[r['opening']['hudIn'] for r in history if (r.get('opening') or {}).get('hudIn')]
                    moving=[h for h in huds if 0 < h['seconds'] < .5]
                    groups=('EnterancePlayerHeads','EnteranceMonsterHeads','RoundNode','Energy','Panel_LeftDown','EndTurnArea')
                    guard.check(huds and all(h['valid'] for h in huds) and moving, 'Source HUD In clips were not sampled during the 0.5 s In')
                    guard.check(all(all(h['groups'][g]['found'] for g in groups) for h in huds), 'Source HUD In group missing')
                    guard.check(any(h['groups']['EnterancePlayerHeads']['dy']<-1 and 0<h['groups']['EnterancePlayerHeads']['opacity']<1
                                    and h['groups']['EndTurnArea']['dx']>1 and h['groups']['Energy']['dx']<-1 for h in moving),
                                'HUD In did not move/fade the source groups')
                    rest=sample['opening']['hudIn']
                    guard.check(rest['finished'] and rest['masksPainted']==3 and all(abs(rest['groups'][g]['dx'])<.01 and abs(rest['groups'][g]['dy'])<.01
                                and abs(rest['groups'][g]['opacity']-1)<.001 for g in groups), 'HUD did not settle at the source rest pose')
                    guard.check(state.get('hudInShot') and state['hudInShot'].exists(), 'HUD In screenshot missing')
                    report['hudIn']=dict(samplesDuringIn=len(moving), screenshot=str(state['hudInShot']), rest=rest,
                                         firstMoving=moving[0])
                    passed('source-hud-in-groups-move-fade-and-settle')
                    view=sample['camera']; width,height=view['viewport']
                    guard.check(width>0 and height>0, 'Battle viewport size unavailable')
                    requested=report.get('requestedWindow')
                    # Floating PIE windows can add a few pixels of client area for borders.
                    guard.check(not requested or (abs(width-requested[0])<=4 and abs(height-requested[1])<=4), 'PIE viewport differs from requested window')
                    expected=source_horizontal_fov(width/height)
                    guard.check(not view['constrainAspect'] and abs(view['aspect']-width/height)<.001 and abs(view['fov']-expected)<.01,
                                'Battle camera FOV differs from source CameraBattle rule')
                    report['sourceCamera']=dict(viewport=view['viewport'],aspect=width/height,horizontalFov=view['fov'],expectedHorizontalFov=expected)
                    passed('source-camera-battle-fov-by-aspect')
                    report['firstBattleId']=sample['battleId']; passed('fresh-create-hidden-show-actual-position-unlock')
                    if report['entranceFx']:
                        fx_rows=[r['entranceFx'] for r in history if (r.get('entranceFx') or {}).get('playing')]
                        mesh_path=actor('HCZSBattlePlayer').get_component_by_class(u.SkeletalMeshComponent).get_path_name()
                        guard.check(len(fx_rows)>5 and any(sum(l.get('visible',False) for l in r['layers'])==3 for r in fx_rows),
                                    'Entrance source fx layers were not all observed visible')
                        guard.check(all(l['attachParent']==mesh_path and l.get('worldAxes') for r in fx_rows for l in r['layers']),
                                    'Entrance source fx is not following the player origin with world axes')
                        cue=[r for r in history if r.get('position',0)>=3.7*.144595-.002]
                        guard.check(cue and fx_rows[0]['seconds']<.1, 'Entrance source fx did not start at event_1')
                        final=sample['entranceFx']
                        guard.check(not final['playing'] and final['outcome']=='complete' and final['playCount']==1 and final['maxActiveLayers']==3,
                                    'Entrance source fx did not complete exactly once')
                        shots=[state.get('entrance-fx-early'), state.get('entrance-fx-late')]
                        guard.check(all(s and s.exists() for s in shots), 'Entrance source fx screenshots missing')
                        report['entranceFxResult']=dict(samples=len(fx_rows), screenshots=[str(s) for s in shots],
                                                        first=fx_rows[0], mid=fx_rows[len(fx_rows)//2], final=final)
                        passed('entrance-sfx-model-layers-reconstruction-plays-once-at-event1')
                    if report.get('roundStartDeal'):
                        game.end_turn(); stage('round-deal')
                    elif report.get('rejectPlay'):
                        state['read'] = pool.submit(read_battle, sample['battleId']); stage('reject-choose')
                    elif report.get('dragRetest'):
                        state['steps'] = [
                            ('mouse', 'tap', 'tap', 'below-drag-threshold'),
                            ('mouse', 'player', 'rejected', 'invalid-target'),
                            ('mouse', 'outside', 'rejected', 'outside'),
                            ('mouse', 'cancel', 'cancelled', 'capture-lost'),
                            ('mouse', 'focus', 'cancelled', 'focus-lost'),
                            ('mouse', 'enemy', 'submitted', ''),
                            ('touch', 'tap', 'tap', 'below-drag-threshold'),
                            ('touch', 'player', 'rejected', 'invalid-target'),
                            ('touch', 'cancel', 'cancelled', 'capture-lost'),
                        ]
                        state['step'] = 0
                        state['dragPhase'] = 'act'
                        stage('drag-matrix')
                    else:
                        capture('complete-source2133'); stage('capture-first')
                else: guard.check(sample.get('playing'), 'Fresh GI creation did not start the source entrance')
            elif current=='round-deal':
                opening = sample.get('opening') or {}
                deal = opening.get('roundDeal') or {}
                cards = [c for c in (opening.get('dealtCards') or []) if c.get('route') == 'round-start']
                phases = state.setdefault('roundPhases', set())
                phases.update(c['phase'] for c in cards)
                if deal.get('instances'): state['roundInstances'] = deal['instances']
                if cards and 'centre-hold' in {c['phase'] for c in cards} and 'roundShot' not in state:
                    target = path.parent/(prefix+'-round-deal-centre.png')
                    state['roundShot'] = target
                    u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="'+target.as_posix()+'" -nosuffix')
                if deal.get('active') and deal.get('outcome') == 'dispatching':
                    guard.check(sample.get('playableCards') == 0, 'Round-start deal left a card playable')
                if deal.get('outcome') == 'completed' and not deal.get('active'):
                    guard.check({'fly-to-centre', 'centre-hold', 'drop-to-hand'} <= phases, 'Round-start _C_H phases missing')
                    guard.check(state.get('roundShot') and state['roundShot'].exists(), 'Round-start deal screenshot missing')
                    audio = opening.get('uiAudio') or []
                    reasons = {row.get('reason') for row in audio}
                    guard.check({'opening-first-draw', 'opening-last-dispatch-end', 'round-start-draw', 'round-last-dispatch-end'} <= reasons,
                                'Draw/land cues were not played for the opening and the round-start draw')
                    guard.check(sum(row.get('reason') == 'round-start-draw' for row in audio) == 1
                                and sum(row.get('reason') == 'round-last-dispatch-end' for row in audio) == 1,
                                'Round-start draw played more than the authoritative end-turn draw')
                    guard.check(all(row.get('loaded') and row.get('playing') for row in audio), 'A UI cue asset did not start')
                    guard.check(any(row.get('reason') == 'round-start-draw' and row.get('volumeDb') == -9 for row in audio)
                                and any(row.get('reason') == 'round-last-dispatch-end' and row.get('volumeDb') == -4.5 for row in audio),
                                'Cue volume differs from the in-bank actor-mixer value')
                    report['roundDeal'] = dict(phases=sorted(phases), audio=audio, screenshot=str(state['roundShot']),
                                               instances=state.get('roundInstances'), actionIndex=sample['actionIndex'])
                    state['read'] = pool.submit(read_battle, sample['battleId']); stage('round-read')
            elif current=='round-read' and state['read'].done():
                battle = state['read'].result()
                guard.check(battle['revision'] == 2 and battle['state']['actionIndex'] == 1
                            and battle['state']['status'] == 'player-turn' and battle['state']['round'] == 2,
                            'End turn did not advance exactly one authoritative round')
                drawn = set(report['roundDeal']['instances'] or [])
                guard.check(drawn and drawn <= set(battle['state']['piles']['hand']),
                            'Animated instances are not the authoritative new hand')
                passed('round-start-draw-uses-source-flight-and-ui-cues')
                finish()
            elif current=='reject-choose' and state['read'].done():
                battle = state['read'].result()
                cards = {card['instanceId']: card['cardId'] for card in battle['state']['cards']}
                definition = battle['scenario']['definition']['cards']
                single = {'110001', '210003', '410102'}
                choice = next((instance for instance in battle['state']['piles']['hand']
                               if cards.get(instance) in single and definition[cards[instance]]['cost'] <= battle['state']['energy']), None)
                guard.check(choice, 'Tutorial hand has no affordable single-hit Elsa card')
                state['rejectCard'] = choice
                state['rejectCardId'] = cards[choice]
                widget = u.WidgetLibrary.get_all_widgets_of_class(world, u.load_class(None, '/Script/Hczs.HczsSessionWidget'), True)[0]
                guard.check(widget.development_drag_card(choice, 'enemy', False, 'begin'), 'Pointer down failed for the rejected play')
                guard.check(widget.development_drag_card(choice, 'enemy', False, 'move'), 'Pointer move failed for the rejected play')
                guard.check(widget.development_drag_card(choice, 'enemy', False, 'release'), 'Pointer up failed for the rejected play')
                state['rejectStarted'] = time.time()
                stage('reject-hold')
            elif current=='reject-hold' and not game.get_editor_property('request_in_flight'):
                if not state.get('sawAttackWindup') and time.time() - state['rejectStarted'] < 3:
                    return
                guard.check(state.get('sawAttackWindup'), 'Single-hit windup did not start before the rejected response')
                guard.check(sample['actionIndex'] == 0 and sample['revision'] == 1, 'Rejected play changed authoritative state')
                guard.check(not sample.get('busy') and sample.get('clip') and 'idle_1' in sample['clip'], 'Rejection did not restore the idle pose')
                log = native_log.read_text('utf8', errors='replace')
                if ('HCZS visual intent cleared:' not in log or 'abortedPending=0' not in log) and time.time() - state['rejectStarted'] < 8:
                    return
                guard.check('HCZS source impact held for authority' in log, 'Impact was not held until authority')
                guard.check('HCZS visual intent cleared:' in log and 'abortedPending=0' in log, 'Rejected windup was not cleared')
                state['read'] = pool.submit(read_battle, sample['battleId']); stage('reject-read')
            elif current=='reject-read' and state['read'].done():
                battle = state['read'].result()
                guard.check(battle['revision'] == 1 and battle['state']['actionIndex'] == 0
                            and state['rejectCard'] in battle['state']['piles']['hand'], 'Rejected card left the authoritative hand')
                rows = [json.loads(line) for line in Path(manifest['tracePath']).read_text('utf8').splitlines() if line.strip()]
                plays = [r for r in rows if r.get('phase') == 'ue-request' and r.get('method') == 'POST' and str(r.get('path', '')).endswith('/actions')]
                guard.check(len(plays) == 1 and plays[0].get('status') == 409 and plays[0].get('rejectedBeforeCommit') is True
                            and plays[0].get('instanceId') == state['rejectCard'], 'The rejected play was committed or repeated')
                report['rejectedPlay'] = dict(cardId=state['rejectCardId'], instanceId=state['rejectCard'], windup=state['sawAttackWindup'],
                                               held=True, restoredIdle=sample.get('clip'), httpStatus=409)
                passed('single-hit-windup-holds-for-authority-and-rejection-restores-idle')
                finish()
            elif current=='drag-matrix':
                widget = u.WidgetLibrary.get_all_widgets_of_class(world, u.load_class(None, '/Script/Hczs.HczsSessionWidget'), True)[0]
                ui = json.loads(widget.development_describe_ui())
                gesture = ui.get('lastGesture') or {}
                if state['dragPhase'] == 'check':
                    kind, target, outcome, reason = state['steps'][state['step']]
                    guard.check(not gesture.get('active') and gesture.get('outcome') == outcome and gesture.get('reason') == reason
                                and gesture.get('isTouch') == (kind == 'touch'),
                                'Gesture %s/%s ended as %s/%s' % (kind, target, gesture.get('outcome'), gesture.get('reason')))
                    guard.check(sample['actionIndex'] == state.get('actions', 0), 'Rejected gesture changed authoritative state')
                    report.setdefault('drag', []).append(dict(input=kind, target=target, outcome=gesture.get('outcome'), reason=gesture.get('reason')))
                    state['step'] += 1
                    state['dragPhase'] = 'act'
                    if state['step'] >= len(state['steps']):
                        stage('drag-hall')
                    return
                kind, target, outcome, reason = state['steps'][state['step']]
                touch = kind == 'touch'
                enabled = [c['value'] for c in ui['controls'] if c['action'] == 'play-card' and c['enabled']]
                guard.check(enabled, 'No draggable card for %s %s' % (kind, target))
                card = enabled[0]
                move_target = 'enemy' if target in ('cancel', 'focus', 'enemy') else target
                guard.check(widget.development_drag_card(card, move_target, touch, 'begin'), 'Pointer down failed for %s %s' % (kind, target))
                if target != 'tap':
                    guard.check(widget.development_drag_card(card, move_target, touch, 'move'), 'Pointer move failed for %s %s' % (kind, target))
                if target == 'focus':
                    guard.check(widget.development_drag_card(card, 'enemy', touch, 'focus-lost'), 'Real focus loss did not cancel the drag')
                else:
                    release_target = 'cancel' if target == 'cancel' else move_target
                    guard.check(widget.development_drag_card(card, release_target, touch, 'release'), 'Pointer up failed for %s %s' % (kind, target))
                if outcome == 'submitted':
                    other = next((value for value in enabled if value != card), None)
                    guard.check(other and not widget.development_drag_card(other, 'enemy', touch, 'begin'),
                                'A second card was accepted while the play request was in flight')
                    state['actions'] = 1
                    state['playedCard'] = card
                    report.setdefault('drag', []).append(dict(input=kind, target=target, outcome='submitted', duplicateBlocked=True))
                    state['step'] += 1
                    stage('drag-confirm')
                else:
                    state['dragPhase'] = 'check'
            elif current=='drag-confirm' and sample.get('actionIndex') == 1 and sample.get('canSubmit') and not sample.get('busy'):
                guard.check(sample['revision'] == 2, 'Play did not advance exactly one authoritative revision')
                passed('mouse-play-touch-paths-and-duplicate-blocked')
                stage('drag-matrix')
            elif current=='drag-hall':
                widget = u.WidgetLibrary.get_all_widgets_of_class(world, u.load_class(None, '/Script/Hczs.HczsSessionWidget'), True)[0]
                ui = json.loads(widget.development_describe_ui())
                enabled = [c['value'] for c in ui['controls'] if c['action'] == 'play-card' and c['enabled']]
                guard.check(enabled, 'No card left for the return-to-hall cancel')
                guard.check(widget.development_drag_card(enabled[0], 'enemy', False, 'begin'), 'Pointer down failed before returning to hall')
                game.return_to_hall()
                ui = json.loads(widget.development_describe_ui())
                gesture = ui.get('lastGesture') or {}
                guard.check(not gesture.get('active') and gesture.get('outcome') == 'cancelled' and gesture.get('reason') == 'state-refreshed',
                            'Returning to hall left the drag active or submitted it')
                state['read'] = pool.submit(read_battle, sample['battleId'])
                stage('drag-hall-read')
            elif current=='drag-hall-read' and sample['map'] == HALL and state['read'].done():
                battle = state['read'].result()
                guard.check(battle['state']['actionIndex'] == 1 and battle['revision'] == 2, 'Hall return changed the saved battle')
                rows = [json.loads(line) for line in Path(manifest['tracePath']).read_text('utf8').splitlines() if line.strip()]
                plays = [r for r in rows if r.get('phase') == 'ue-request' and r.get('method') == 'POST' and str(r.get('path', '')).endswith('/actions')]
                guard.check(len(plays) == 1 and plays[0].get('status') in (200, 201), 'Play was missing or sent more than once')
                report['dragWire'] = dict(actions=len(plays), status=plays[0].get('status'))
                passed('drag-retest-play-tap-invalid-cancel-focus-duplicate-and-hall')
                finish()
            elif current=='capture-first' and shot_done():
                widget = u.WidgetLibrary.get_all_widgets_of_class(world,u.load_class(None,'/Script/Hczs.HczsSessionWidget'),True)[0]
                ui = json.loads(widget.development_describe_ui())
                enabled = [c['value'] for c in ui['controls'] if c['action']=='play-card' and c['enabled']]
                guard.check(enabled, 'No draggable card after first dispatch')
                state['dragWidget'] = widget; state['dragCard'] = enabled[0]
                guard.check(widget.development_drag_card(enabled[0], 'enemy', False, 'begin'), 'Real pointer down failed after first deal')
                stage('drag-first')
            elif current=='drag-first':
                guard.check(state['dragWidget'].development_drag_card(state['dragCard'],'enemy',False,'move'), 'Post-deal pointer drag failed')
                stage('cancel-first-drag')
            elif current=='cancel-first-drag':
                guard.check(state['dragWidget'].development_drag_card(state['dragCard'],'cancel',False,'release'), 'Post-deal capture cancellation failed')
                passed('first-deal-unlocks-real-pointer-drag-and-cancel')
                state['read']=pool.submit(read_battle,state['ids'][0]); stage('read-first')
            elif current=='read-first' and state['read'].done():
                state['firstAuthority']=state['read'].result()
                guard.check(state['firstAuthority']['revision']==1 and state['firstAuthority']['state']['actionIndex']==0,
                            'Completed source entrance changed authoritative state')
                state.pop('dragWidget', None)
                game.return_to_hall(); stage('hall-continue')
            elif current=='hall-continue' and game.is_hall_scene_ready() and sample['map']==HALL:
                guard.check(not sample['locked'],'Hall retained first entrance lock'); game.continue_battle(state['ids'][0]); stage('continue')
            elif current=='continue' and sample['map']==BATTLE:
                guard.check(not sample.get('playing') and not sample['locked'] and sample.get('entrancePhase')=='none'
                            and sample.get('opening', {}).get('openingSeconds') == -1
                            and sample.get('opening', {}).get('openingPaintedNodes') == 0
                            and sample.get('opening', {}).get('dealtCards') == [], 'Continue replayed an entrance/banner')
                state.setdefault('continueObservedAt',time.monotonic())
                if time.monotonic()-state['continueObservedAt']>=5 and sample['canSubmit']:
                    passed('continue-no-replay-for-five-seconds'); capture('continue-source2133'); stage('capture-continue')
            elif current=='capture-continue' and shot_done(): game.return_to_hall(); stage('hall-new')
            elif current=='entrance-cancel' and sample['map']==BATTLE:
                if sample['battleId'] not in state['ids']: state['ids'].append(sample['battleId'])
                guard.check(len(state['ids'])==2 and sample.get('playing'), 'Second fresh creation did not start its own entrance')
                if sample['entrancePhase']=='show-visible' and sample['position']>=.1:
                    guard.check(sample['position']<.535,'Did not reach cancellation before source event_1')
                    report['cancelAt']=sample; game.return_to_hall(); stage('cancelled-hall')
            elif current=='cancelled-hall' and sample['map']==HALL and game.is_hall_scene_ready():
                guard.check(not sample['locked'] and not u.GameplayStatics.get_all_actors_with_tag(world,'HCZSBattlePresentation'), 'Cancelled entrance/timer/lock survived map return')
                passed('show-cancel-return-clears-lock'); state['read']=pool.submit(final_reads); stage('final-read')
            elif current=='final-read' and state['read'].done():
                report.update(state['read'].result()); passed('two-battles-revision1-action0-no-gameplay-command')
                passed('native-log-single-source-event-and-authored-hidden-wait')
                finish()
        except Exception: finish(traceback.format_exc())
        finally: state['busy']=False

    report['roundStartDeal'] = guard.flag(command, 'HczsRoundStartDeal')
    report['dragRetest'] = guard.flag(command, 'HczsDragRetest')
    report['rejectPlay'] = guard.flag(command, 'HczsRejectPlay')
    report['entranceFx'] = guard.flag(command, 'HczsEntranceFxReconstruction')
    guard.check(sum(bool(report[name]) for name in ('roundStartDeal', 'dragRetest', 'rejectPlay')) <= 1, 'Choose one acceptance mode')
    if report['rejectPlay']:
        guard.check(manifest.get('rejectFirstPlay') is True and manifest.get('faults') is False
                    and manifest.get('cardResponseDelayMs', 0) >= 2000, 'Rejection acceptance needs a delayed pre-commit 409')
    window = guard.argument(command, 'HczsPIEWindow')
    if window:
        size = re.fullmatch(r'(\d{3,4})x(\d{3,4})', window)
        guard.check(size, 'HczsPIEWindow must be <width>x<height>')
        report['requestedWindow'] = [int(size[1]), int(size[2])]
        save(); guard.check(u.HczsDevelopmentLibrary.request_floating_play_session(*report['requestedWindow']), 'Floating PIE request refused')
    else:
        save(); u.get_editor_subsystem(u.LevelEditorSubsystem).editor_request_begin_play()
    handle=u.register_slate_post_tick_callback(tick)
    u.log('HCZS fresh entrance report: '+str(output))


if __name__=='__main__': run()
