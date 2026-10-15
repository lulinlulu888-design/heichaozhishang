"""Dedicated UE5.8 PIE readback of the source weapon001 overlay.

Use -HczsMainlineUITest -HczsServerPort=17468
-HczsMainlineManifest=<owned run/server.json> -ExecCmds="py <this file>".
The existing mainline manifest/live-identity guards are reused unchanged.
Only HTTP profile/battle creation is permitted; no card, turn or settlement
command is issued. The dedicated Editor exits after restoring test overrides.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback
import urllib.request
import uuid

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import test_mainline_ui as mainline

ROOT = TOOLS.parents[1]
MESH = '/Game/Recovered/Battle/Weapon/SourceFx/SM_WeaponOverlay.SM_WeaponOverlay'
MATERIAL = '/Game/Recovered/Battle/Weapon/SourceFx/M_WeaponFlow.M_WeaponFlow'
OVERLAY_TAG = 'HCZSWeaponSourceOverlay'


def transform_record(value):
    return dict(translation=[value.translation.x, value.translation.y, value.translation.z],
                rotation=[value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w],
                scale=[value.scale3d.x, value.scale3d.y, value.scale3d.z])


def same_transform(actual, expected, label):
    for key, tolerance in (('translation', .02), ('scale', .00001)):
        a, b = actual[key], expected[key]
        mainline.check(len(a) == len(b) == 3 and all(math.isfinite(v) for v in a + b)
                       and max(abs(x-y) for x, y in zip(a, b)) <= tolerance, label + ' ' + key + ' differs')
    a, b = actual['rotation'], expected['rotation']
    mainline.check(len(a) == len(b) == 4 and all(math.isfinite(v) for v in a + b), label + ' quaternion is invalid')
    # q and -q describe the same rotation.
    mainline.check(min(max(abs(x-y) for x, y in zip(a, b)), max(abs(x+y) for x, y in zip(a, b))) <= .00001,
                   label + ' rotation differs')


def png_record(path):
    data = path.read_bytes()
    mainline.check(1024 < len(data) <= 64 * 1024 * 1024 and data[:8] == b'\x89PNG\r\n\x1a\n'
                   and data[12:16] == b'IHDR', 'Actual PNG screenshot is missing or invalid')
    width, height = struct.unpack('>II', data[16:24])
    mainline.check(320 <= width <= 20000 and 180 <= height <= 20000, 'Unexpected native screenshot dimensions')
    return dict(path=str(path), width=width, height=height, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def run():
    import unreal as u

    command = u.SystemLibrary.get_command_line()
    mainline.check(Path(mainline.__file__).resolve() == TOOLS / 'test_mainline_ui.py', 'Unexpected guard module')
    manifest_arg = mainline.argument(command, 'HczsMainlineManifest')
    mainline.check(manifest_arg, 'Pass -HczsMainlineManifest=<owned server.json>')
    manifest_path = Path(manifest_arg).resolve()
    raw = manifest_path.read_bytes()
    mainline.check(len(raw) < 1024 * 1024, 'Manifest too large')
    manifest = json.loads(raw)
    address = mainline.validate_manifest(manifest, manifest_path, command)
    mainline.check(manifest.get('mainlineFaults', False) is False,
                   'Weapon FX acceptance requires dedicated port 17468 without settlement faults')
    mainline.check(not any(mainline.flag(command, name) for name in
                          ('HczsMainlineUIResume', 'HczsMainlineUIKeepEditor', 'HczsMainlineUIFaults')),
                   'This test requires a fresh run and always exits its dedicated Editor')
    mainline.check(Path(u.Paths.project_dir()).resolve() == (ROOT / 'clients/unreal5 5.8').resolve(), 'Unexpected UE project')
    mainline.check(u.SystemLibrary.get_engine_version().startswith('5.8.'), 'Weapon FX test requires UE5.8')
    editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    mainline.check(not editor.get_game_world(), 'Use a dedicated Editor before PIE; never reuse a running game')

    started_ms = int(time.time() * 1000)
    prefix = 'weapon-source-fx-' + str(time.time_ns())
    output = manifest_path.parent / (prefix + '.json')

    def http(route, body=None, control=False):
        mainline.check(route.startswith('/api/rebuild/v1/') or control and route == '/__hczs_test_control/identity',
                       'Unexpected test HTTP route')
        headers = {'Accept': 'application/json'}
        if control:
            headers['Authorization'] = 'Bearer ' + manifest['controlToken']
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(address + route, headers=headers,
                                         data=None if body is None else json.dumps(body).encode('utf8'))
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), mainline.NoRedirect()).open(request, timeout=15) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        mainline.check(len(data) <= 8 * 1024 * 1024, 'Oversized isolated response')
        return json.loads(data)

    def identity():
        mainline.check(manifest_path.read_bytes() == raw, 'Run manifest changed while the Editor was testing')
        live = http('/__hczs_test_control/identity', control=True)
        mainline.validate_identity(live, manifest, raw)
        return live

    live = identity()
    report = dict(schemaVersion=1, mode='native-weapon001-source-overlay', passed=False,
                  serverIdentity=live, engine=u.SystemLibrary.get_engine_version(), startedAtUnixMs=started_ms,
                  preparation='isolated HTTP profile and player-turn tutorial creation; explicit GI selection/continue',
                  nativePointerInput=False, noBusinessActions=True, weaponDaoGroupImplemented=False,
                  originalApkExecuted=False, checks=[], samples=[], screenshots=[])

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')

    def prepare():
        identity()
        bootstrap = http('/api/rebuild/v1/bootstrap')
        mainline.check(bootstrap.get('profiles') == [] and 'mainline-progression' in bootstrap.get('capabilities', []),
                       'Fresh owned mainline test database must contain no profiles')
        content = bootstrap.get('content', {}).get('mainlineId')
        mainline.check(isinstance(content, str) and len(content) == 64, 'Missing mainline identity')
        profile = http('/api/rebuild/v1/profiles', {'displayName': '武器流光独立验收'})['profile']
        create_id = 'weapon-fx-create-' + str(uuid.uuid4())
        battle = http('/api/rebuild/v1/profiles/' + profile['id'] + '/battles',
                      {'requestId': create_id, 'encounterId': 'tutorial-5000', 'seed': 7})['battle']
        mainline.check(battle['profileId'] == profile['id'] and battle['revision'] == 1
                       and battle['state']['status'] == 'player-turn' and battle['state']['actionIndex'] == 0
                       and battle['scenario']['encounterId'] == 'tutorial-5000'
                       and battle['scenario']['definition']['player']['id'] == '1'
                       and battle['scenario']['definition']['enemy']['id'] == '991', 'Unexpected initial authoritative tutorial')
        campaign = http('/api/rebuild/v1/profiles/' + profile['id'] + '/mainline')['campaign']
        mainline.validate_campaign(campaign, profile['id'], content, False)
        identity()
        return dict(profileId=profile['id'], battleId=battle['id'], contentId=content, createRequestId=create_id,
                    initialBattle=battle, initialCampaign=campaign)

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-weapon-fx-isolated')
    prepared = pool.submit(prepare)
    state = dict(stage='prepare', started=time.monotonic(), entered=time.monotonic(), busy=False, finished=False,
                 game=None, fx=None, player=None, enemy=None, weapon=None, world=None, controller=None, camera=None, originals=None)
    save()

    def stage(name):
        state.update(stage=name, entered=time.monotonic())
        report['stage'] = name
        save()
        u.log('HCZS weapon source FX stage=' + name)

    def record_check(name, **values):
        report['checks'].append(dict(name=name, passed=True, **values))

    def overlay_count():
        return len([component for component in state['presentation'].get_components_by_class(u.StaticMeshComponent)
                    if component.component_has_tag(OVERLAY_TAG)])

    def sample(name, visible=True):
        fx, player, weapon = state['fx'], state['player'], state['weapon']
        mainline.check(fx.is_ready(), 'Weapon overlay is not ready: ' + fx.get_problem())
        described = json.loads(fx.development_describe())
        overlay, material = fx.get_overlay_component(), fx.get_dynamic_material()
        root = weapon.get_editor_property('root_component')
        mainline.check(overlay and material and overlay_count() == 1, 'Expected exactly one live source overlay')
        mainline.check(described.get('mode') == 'weapon001-source-overlay' and described.get('ready') is True
                       and described.get('weaponDaoGroupImplemented') is False, 'Overlay scope/readiness report differs')
        mainline.check(overlay.get_owner() == state['presentation'] and overlay.get_attach_parent() == root.get_attach_parent() == player
                       and overlay.get_attach_socket_name() == root.get_attach_socket_name()
                       and str(overlay.get_attach_socket_name()) == 'bip001-prop1', 'Same-parent source bone attachment differs')
        mainline.check(overlay.get_editor_property('static_mesh').get_path_name() == MESH
                       and material.get_editor_property('parent').get_path_name() == MATERIAL
                       and overlay.get_material(0) == material, 'Actual overlay mesh/material reference differs')
        same_transform(transform_record(overlay.get_relative_transform()), transform_record(root.get_relative_transform()), 'Relative attachment')
        same_transform(transform_record(overlay.get_world_transform()), transform_record(root.get_world_transform()), 'World attachment')
        for key in ('absolute_location', 'absolute_rotation', 'absolute_scale'):
            mainline.check(overlay.get_editor_property(key) == root.get_editor_property(key), 'Absolute transform flag differs: ' + key)
        mainline.check(not overlay.get_editor_property('owner_no_see') and not overlay.get_editor_property('only_owner_see'),
                       'Overlay unexpectedly uses owner-only visibility')
        actual_time = float(material.get_scalar_parameter_value('EffectTime'))
        mainline.check(math.isfinite(actual_time) and abs(actual_time - fx.get_effect_time()) <= .0001
                       and abs(actual_time - described['materialEffectTime']) <= .0001, 'Actual MID time differs from component readback')
        mainline.check(described.get('visible') is visible and described.get('hiddenInGame') is not visible,
                       'Overlay did not follow the expected source visibility')
        mainline.check(state['controller'].get_view_target() == state['camera'], 'Default battle view target was changed')
        same_transform(transform_record(state['camera'].get_actor_transform()), state['cameraTransform'], 'Default camera')
        pose = dict(player=float(player.get_position()), enemy=float(state['enemy'].get_position()))
        if state.get('frozenPose'):
            mainline.check(all(abs(pose[key]-state['frozenPose'][key]) <= .00001 for key in pose),
                           'Character animation pose changed during the controlled visual comparison')
            mainline.check(player.get_editor_property('pause_anims') and state['enemy'].get_editor_property('pause_anims'),
                           'Character pose is not frozen for the visual comparison')
        described.update(stage=name, actualMIDTime=actual_time, overlayCount=overlay_count(),
                         componentTickEnabled=bool(fx.is_component_tick_enabled()), atUnixMs=int(time.time() * 1000),
                         viewTarget=state['camera'].get_path_name(), animationPosition=pose)
        report['samples'].append(described)
        return described

    def finish(error=None):
        if state['finished']:
            return
        state['finished'] = True
        restored = []
        try:
            world = state['world']
            if world and u.GameplayStatics.is_game_paused(world):
                restored.append(dict(action='unpause', result=bool(u.GameplayStatics.set_game_paused(world, False))))
            if state['originals']:
                original = state['originals']
                state['weapon'].set_actor_hidden_in_game(original['weaponHidden'])
                state['player'].set_hidden_in_game(original['playerHidden'], False)
                state['player'].set_editor_property('pause_anims', original['playerPause'])
                state['enemy'].set_editor_property('pause_anims', original['enemyPause'])
                fx = state['fx']
                if not fx.is_ready():
                    mainline.check(fx.initialise(state['player'], state['weapon']), 'Could not restore released source overlay')
                fx.set_component_tick_enabled(True)
                overlay = fx.get_overlay_component()
                overlay.set_visibility(True, False)
                overlay.set_hidden_in_game(False, False)
                restored.append(dict(action='restore-source-visibility-and-normal-fx-tick', ready=bool(fx.is_ready())))
        except Exception:
            report['restoreError'] = traceback.format_exc()
            error = error or report['restoreError']
        report.update(passed=error is None, error=error, lastStage=state['stage'], restoration=restored,
                      finishedAtUnixMs=int(time.time() * 1000),
                      limitation='Native component/clock/visibility and actual camera PNGs; no claim of original NeoX blend or weapon_dao equivalence')
        save()
        u.unregister_slate_post_tick_callback(handle)
        pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS weapon source FX report: ' + str(output))
        if error:
            u.log_error(error)
        if error or not mainline.flag(command, 'HczsWeaponFxKeepEditor'):
            u.SystemLibrary.quit_editor()

    def request_capture(name, next_stage, visible=True):
        observed = sample('capture-' + name, visible)
        target = manifest_path.parent / (prefix + '-' + name + '.png')
        mainline.check(target.parent == manifest_path.parent and not target.exists(), 'Capture path must be new and inside this owned run')
        mainline.check(not any(c in target.as_posix() for c in ('"', '\r', '\n')), 'Invalid console capture path')
        state.update(screenshot=target, screenshotSample=observed, screenshotName=name, afterCapture=next_stage)
        stage('capture-wait')
        u.SystemLibrary.execute_console_command(state['world'], 'Shot SHOWUI filename="' + target.as_posix() + '" -nosuffix')

    def final_readback():
        setup = report['preparationResult']
        live_after = identity()
        profiles = http('/api/rebuild/v1/bootstrap')['profiles']
        mainline.check(len(profiles) == 1 and profiles[0]['id'] == setup['profileId'], 'Test unexpectedly created another profile')
        route = '/api/rebuild/v1/profiles/' + setup['profileId']
        battles = http(route + '/battles')['battles']
        mainline.check(len(battles) == 1 and battles[0]['id'] == setup['battleId'], 'Test unexpectedly created another battle')
        battle = http(route + '/battles/' + setup['battleId'])['battle']
        campaign = http(route + '/mainline')['campaign']
        mainline.check(battle == setup['initialBattle'], 'Visual acceptance changed the authoritative battle')
        mainline.check(campaign == setup['initialCampaign'], 'Visual acceptance changed mainline progress')
        rows = [json.loads(line) for line in Path(manifest['tracePath']).read_text('utf8').splitlines() if line.strip()]
        writes = [row for row in rows if row.get('phase') == 'ue-request' and row.get('method') in ('POST', 'PATCH', 'DELETE')
                  and row.get('receivedAtUnixMs', -1) >= started_ms]
        mainline.check(len(writes) == 2 and [row.get('path') for row in writes] ==
                       ['/api/rebuild/v1/profiles', route + '/battles'] and writes[1].get('requestId') == setup['createRequestId'],
                       'Wire contains an unexpected business mutation; no actions/settlements are permitted')
        identity()
        return dict(serverIdentityAfter=live_after, finalBattle=battle, finalCampaign=campaign,
                    mutations=[{key: row.get(key) for key in ('method', 'path', 'status', 'requestId')} for row in writes])

    def tick(delta):
        if state['busy'] or state['finished']:
            return
        state['busy'] = True
        try:
            current = state['stage']
            elapsed = time.monotonic() - state['entered']
            mainline.check(time.monotonic() - state['started'] < 240, 'Weapon source FX deadline at ' + current)
            world = editor.get_game_world()
            if not world:
                return
            state['world'] = world
            game = state['game'] = u.GameplayStatics.get_game_instance(world)
            if not game or game.get_editor_property('request_in_flight'):
                return
            mainline.check(not game.get_editor_property('has_pending_intent'), 'Visual test must not have a pending business intent')
            if current == 'prepare':
                if not prepared.done():
                    return
                report['preparationResult'] = prepared.result()
                game.refresh_bootstrap()
                stage('choose-profile')
                return
            mainline.check(game.get_editor_property('local_service_available') and not game.get_editor_property('error_code'),
                           'Native isolated service/session failed: ' + str(game.get_editor_property('error_code')))
            setup = report['preparationResult']
            if current == 'choose-profile':
                game.select_profile(setup['profileId'])
                stage('await-hall')
                return
            if current == 'await-hall':
                if not game.is_hall_scene_ready() or not game.get_editor_property('mainline_state_current') or \
                        u.GameplayStatics.get_current_level_name(world, True) != 'L_ElsaHallFxPreview':
                    return
                mainline.check(game.get_editor_property('selected_profile_id') == setup['profileId'], 'Native GI selected the wrong profile')
                game.continue_battle(setup['battleId'])
                stage('await-battle')
                return
            if current == 'await-battle':
                if not game.is_battle_scene_ready() or u.GameplayStatics.get_current_level_name(world, True) != 'L_TutorialBattle':
                    return
                widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsSessionWidget, True)
                if len(widgets) != 1:
                    return
                paint = json.loads(widgets[0].development_describe_ui())
                if not paint.get('visible') or not paint.get('battleScene') or paint.get('paintSerial', 0) <= 0:
                    return
                mainline.check(paint.get('battleId') == setup['battleId'] and paint.get('serverStatus') == 'player-turn'
                               and paint.get('revision') == 1 and paint.get('actionIndex') == 0
                               and not paint.get('presentationBusy') and not paint.get('sceneProblem'),
                               'Native scene is not the untouched player-turn tutorial')
                found = {}
                for tag in ('HCZSBattlePresentation', 'HCZSBattlePlayer', 'HCZSBattleEnemy', 'HCZSBattleWeapon', 'HCZSBattleCamera'):
                    actors = u.GameplayStatics.get_all_actors_with_tag(world, tag)
                    mainline.check(len(actors) == 1, 'Native actor tag is not unique: ' + tag)
                    found[tag] = actors[0]
                state['presentation'] = found['HCZSBattlePresentation']
                state['player'] = found['HCZSBattlePlayer'].get_component_by_class(u.SkeletalMeshComponent)
                state['enemy'] = found['HCZSBattleEnemy'].get_component_by_class(u.SkeletalMeshComponent)
                mainline.check(state['player'] and state['enemy'], 'Missing actual player/enemy skeletal mesh')
                state['weapon'], state['camera'] = found['HCZSBattleWeapon'], found['HCZSBattleCamera']
                state['controller'] = u.GameplayStatics.get_player_controller(world, 0)
                state['cameraTransform'] = transform_record(state['camera'].get_actor_transform())
                state['fx'] = state['presentation'].get_weapon_source_fx()
                mainline.check(state['fx'] and state['fx'].is_ready(), 'Integrated Presentation did not initialise its source overlay')
                mainline.check(state['fx'].is_component_tick_enabled() and not u.GameplayStatics.is_game_paused(world), 'Normal FX tick/clock is not running')
                state['originals'] = dict(weaponHidden=bool(state['weapon'].get_editor_property('hidden')),
                                          playerHidden=bool(state['player'].get_editor_property('hidden_in_game')),
                                          playerPause=bool(state['player'].get_editor_property('pause_anims')),
                                          enemyPause=bool(state['enemy'].get_editor_property('pause_anims')))
                report['initialUI'] = paint
                stage('load-wait')
                return
            if current == 'load-wait' and elapsed >= 10:
                baseline = sample('baseline')
                state['timeSample'] = baseline
                old_component, old_mid = baseline['component'], baseline['material']
                for _ in range(3):
                    mainline.check(state['fx'].initialise(state['player'], state['weapon']), 'Repeat Initialise failed')
                again = sample('repeat-initialise')
                mainline.check(again['component'] == old_component and again['material'] == old_mid, 'Repeat Initialise replaced or duplicated the live overlay')
                record_check('idempotent-initialise', overlayCount=1, component=old_component)
                stage('time-advance')
            elif current == 'time-advance' and elapsed >= .8:
                before, after = state['timeSample'], sample('time-advanced')
                mainline.check(after['actualMIDTime'] - before['actualMIDTime'] > .05
                               and abs((after['actualMIDTime']-before['actualMIDTime']) - (after['worldTime']-before['worldTime'])) < .05,
                               'MID did not advance with actual game world time')
                record_check('world-time-advances-mid', before=before['actualMIDTime'], after=after['actualMIDTime'])
                mainline.check(u.GameplayStatics.set_game_paused(world, True), 'Could not pause the dedicated test world')
                stage('pause-baseline')
            elif current == 'pause-baseline':
                state['pauseSample'] = sample('pause-baseline')
                stage('pause-hold')
            elif current == 'pause-hold' and elapsed >= .8:
                before, after = state['pauseSample'], sample('pause-held')
                mainline.check(after['worldPaused'] and abs(after['worldTime']-before['worldTime']) <= .000001
                               and abs(after['actualMIDTime']-before['actualMIDTime']) <= .000001, 'Paused world still advanced the flow clock')
                record_check('pause-holds-world-and-mid', time=after['actualMIDTime'])
                mainline.check(u.GameplayStatics.set_game_paused(world, False), 'Could not unpause the test world')
                state['weapon'].set_actor_hidden_in_game(True)
                stage('weapon-hidden')
            elif current == 'weapon-hidden' and elapsed >= .15:
                sample('weapon-hidden', False)
                record_check('weapon-hide-follows')
                state['weapon'].set_actor_hidden_in_game(state['originals']['weaponHidden'])
                stage('weapon-restored')
            elif current == 'weapon-restored' and elapsed >= .15:
                sample('weapon-restored')
                record_check('weapon-show-restores')
                state['player'].set_hidden_in_game(True, False)
                stage('player-hidden')
            elif current == 'player-hidden' and elapsed >= .15:
                sample('player-hidden', False)
                record_check('player-component-hide-follows')
                state['player'].set_hidden_in_game(state['originals']['playerHidden'], False)
                stage('player-restored')
            elif current == 'player-restored' and elapsed >= .15:
                sample('player-restored')
                old = state['fx'].get_overlay_component()
                state['releasedPath'] = old.get_path_name()
                state['fx'].release()
                mainline.check(not state['fx'].is_ready() and state['fx'].get_overlay_component() is None and overlay_count() == 0
                               and not u.SystemLibrary.is_valid(old), 'Release did not destroy and unregister the owned overlay')
                record_check('release-destroys-overlay', oldComponent=state['releasedPath'])
                stage('released')
            elif current == 'released':
                mainline.check(state['fx'].initialise(state['player'], state['weapon']), 'Source overlay could not be reinitialised after Release')
                after = sample('reinitialised')
                mainline.check(after['component'] != state['releasedPath'], 'Reinitialise reused a destroyed component')
                record_check('release-then-reinitialise', newComponent=after['component'], overlayCount=1)
                state['player'].set_editor_property('pause_anims', True)
                state['enemy'].set_editor_property('pause_anims', True)
                state['frozenPose'] = dict(player=float(state['player'].get_position()), enemy=float(state['enemy'].get_position()))
                stage('capture-pose-wait')
            elif current == 'capture-pose-wait' and elapsed >= .25:
                request_capture('on-a', 'on-b-wait')
            elif current == 'on-b-wait' and elapsed >= .8:
                mainline.check(u.GameplayStatics.set_game_paused(world, True), 'Could not freeze world time for on/off comparison')
                stage('capture-paused-wait')
            elif current == 'capture-paused-wait' and elapsed >= .15:
                state['comparisonSample'] = sample('comparison-time-frozen')
                mainline.check(state['comparisonSample']['worldPaused'], 'Visual comparison world is not paused')
                request_capture('on-b', 'disable-overlay')
            elif current == 'disable-overlay':
                state['fx'].set_component_tick_enabled(False)
                state['fx'].get_overlay_component().set_visibility(False, False)
                state['fx'].get_overlay_component().set_hidden_in_game(True, False)
                stage('off-wait')
            elif current == 'off-wait' and elapsed >= .5:
                mainline.check(not state['fx'].is_component_tick_enabled(), 'Off comparison did not hold the FX tick override')
                request_capture('off', 'restore-overlay', False)
            elif current == 'restore-overlay':
                state['fx'].set_component_tick_enabled(True)
                stage('restored-wait')
            elif current == 'restored-wait' and elapsed >= .5:
                mainline.check(state['fx'].is_component_tick_enabled(), 'Normal component ticking was not restored')
                request_capture('restored', 'final-readback')
            elif current == 'capture-wait':
                mainline.check(elapsed < 25, 'Native screenshot write timed out')
                if elapsed >= 2 and state['screenshot'].exists():
                    screenshot = png_record(state['screenshot'])
                    screenshot.update(stage=state['screenshotName'], sample=state['screenshotSample'],
                                      worldMap=u.GameplayStatics.get_current_level_name(world, True))
                    report['screenshots'].append(screenshot)
                    stage(state['afterCapture'])
            elif current == 'final-readback':
                on = [shot for shot in report['screenshots'] if shot['stage'] in ('on-a', 'on-b')]
                mainline.check(len(on) == 2 and on[1]['sample']['actualMIDTime'] > on[0]['sample']['actualMIDTime'] + .05,
                               'Different-time captures did not have advancing real MID values')
                mainline.check([shot['stage'] for shot in report['screenshots']] == ['on-a', 'on-b', 'off', 'restored'], 'Missing actual on/off/restored frames')
                frozen = state['comparisonSample']
                for shot in report['screenshots'][1:]:
                    observed = shot['sample']
                    mainline.check(observed['worldPaused'] and abs(observed['worldTime']-frozen['worldTime']) <= .000001
                                   and abs(observed['actualMIDTime']-frozen['actualMIDTime']) <= .000001
                                   and observed['animationPosition'] == frozen['animationPosition'],
                                   'On/off/restored captures do not share the exact world clock and frozen character pose')
                record_check('controlled-on-off-frames', worldTime=frozen['worldTime'],
                             animationPosition=frozen['animationPosition'], defaultCameraUnchanged=True)
                state['verified'] = pool.submit(final_readback)
                stage('verify-persistence')
            elif current == 'verify-persistence' and state['verified'].done():
                report.update(state['verified'].result())
                record_check('battle-and-campaign-unchanged', actionCount=0, settlementCount=0)
                report['finalFX'] = sample('final-restored')
                finish()
        except Exception:
            finish(traceback.format_exc())
        finally:
            state['busy'] = False

    u.get_editor_subsystem(u.LevelEditorSubsystem).editor_request_begin_play()
    handle = u.register_slate_post_tick_callback(tick)
    u.log('HCZS weapon source FX report: ' + str(output))


if __name__ == '__main__':
    run()
