"""PIE acceptance: hall selection of city-preview-10405 travels to the city map
and a real play-card starts Elsa's source ultimate there.

The prologue tutorial encounter is not selected. Nine animation attack cues are
not paired with the eight server damage events.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import traceback
import urllib.request

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import test_mainline_ui as guard

ROOT = TOOLS.parents[1]
HALL = 'L_ElsaHallFxPreview'
CITY = 'L_City2077Preview'


def run():
    import unreal as u
    command = u.SystemLibrary.get_command_line()
    argument = guard.argument(command, 'HczsMainlineManifest')
    guard.check(argument and guard.flag(command, 'HczsCityUltimate'), 'Require the city ultimate session flag and owned manifest')
    path = Path(argument).resolve()
    raw = path.read_bytes()
    manifest = json.loads(raw)
    address = guard.validate_manifest(manifest, path, command)
    log_arg = guard.argument(command, 'abslog') or guard.argument(command, 'ABSLOG')
    guard.check(log_arg and Path(log_arg).resolve().parent == path.parent, 'Pass -abslog inside this run directory')
    native_log = Path(log_arg).resolve()
    editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    guard.check(not editor.get_game_world(), 'Use a dedicated Editor before PIE')
    output = path.parent / ('city-ultimate-' + str(time.time_ns()) + '.json')
    report = dict(schemaVersion=1, mode='native-city-ultimate-session', passed=False, checks=[],
                  startedAtUnixMs=int(time.time() * 1000), damageMappingVerified=False)

    def http(route, body=None, control=False):
        guard.check(route.startswith('/api/rebuild/v1/') or control and route == '/__hczs_test_control/identity', 'Unexpected HTTP route')
        headers = {'Accept': 'application/json'}
        if control:
            headers['Authorization'] = 'Bearer ' + manifest['controlToken']
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(address + route, headers=headers, data=None if body is None else json.dumps(body).encode())
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), guard.NoRedirect()).open(request, timeout=15) as response:
            value = response.read(8 * 1024 * 1024 + 1)
        guard.check(len(value) <= 8 * 1024 * 1024, 'Oversized isolated response')
        return json.loads(value)

    def identity():
        guard.check(path.read_bytes() == raw, 'Manifest changed during acceptance')
        value = http('/__hczs_test_control/identity', control=True)
        guard.validate_identity(value, manifest, raw)
        return value

    report['identity'] = identity()

    def prepare():
        bootstrap = http('/api/rebuild/v1/bootstrap')
        guard.check(bootstrap.get('profiles') == [], 'Use an empty owned run')
        return http('/api/rebuild/v1/profiles', {'displayName': '城市终结技正式战斗'})['profile']['id']

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-city-ultimate')
    future = pool.submit(prepare)
    state = dict(stage='prepare', entered=time.monotonic(), started=time.monotonic(), busy=False, done=False, plays=0)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')

    def stage(name):
        state.update(stage=name, entered=time.monotonic())
        report['stage'] = name
        save()

    def passed(name):
        report['checks'].append(dict(name=name, passed=True))

    def finish(error=None):
        if state['done']:
            return
        state['done'] = True
        report.update(passed=error is None, error=error, finishedAtUnixMs=int(time.time() * 1000))
        save()
        u.unregister_slate_post_tick_callback(handle)
        pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS city ultimate result: ' + str(output))
        if error:
            u.log_error(error)
        u.SystemLibrary.quit_editor()

    def hand(game):
        battle = game.get_editor_property('current_battle')
        cards = []
        for card in battle.get_editor_property('hand'):
            cards.append((card.get_editor_property('instance_id'), card.get_editor_property('card_id'), int(card.get_editor_property('cost'))))
        return battle, cards

    def tick(delta):
        if state['busy'] or state['done']:
            return
        state['busy'] = True
        try:
            guard.check(time.monotonic() - state['started'] < 200, 'City ultimate acceptance deadline at ' + state['stage'])
            world = editor.get_game_world()
            if not world:
                return
            game = u.GameplayStatics.get_game_instance(world)
            if not game:
                return
            level = u.GameplayStatics.get_current_level_name(world, True)
            current = state['stage']
            if game.get_editor_property('request_in_flight'):
                if current == 'ultimate-watch' and u.GameplayStatics.is_game_paused(world):
                    state['sawPause'] = True
                return
            if current not in ('ultimate-watch',):
                guard.check(not game.get_editor_property('has_pending_intent') and not game.get_editor_property('error_code'),
                            'Native request failed or left an unresolved intent')
            presenter = None
            actors = u.GameplayStatics.get_all_actors_with_tag(world, 'HCZSBattlePresentation')
            if len(actors) == 1:
                presenter = actors[0]
            busy = bool(presenter.is_presentation_busy()) if presenter else False
            if u.GameplayStatics.is_game_paused(world):
                state['sawPause'] = True
            if current == 'prepare' and future.done():
                state['profile'] = future.result()
                game.refresh_bootstrap()
                stage('profile')
            elif current == 'profile':
                game.select_profile(state['profile'])
                stage('hall')
            elif current == 'hall' and game.is_hall_scene_ready() and level == HALL:
                game.select_encounter('city-preview-10405')
                stage('scenario')
            elif current == 'scenario' and game.get_editor_property('encounter_scenario_ready'):
                guard.check(game.get_editor_property('selected_encounter_id') == 'city-preview-10405', 'City preview was not selected')
                game.create_selected_battle()
                stage('travel')
            elif current == 'travel' and level == CITY:
                battle, _cards = hand(game)
                guard.check(battle.get_editor_property('encounter_id') == 'city-preview-10405'
                            and battle.get_editor_property('enemy_id') == '6605', 'City battle identity changed')
                guard.check(presenter and presenter.is_scene_ready(), 'City presentation did not become ready')
                passed('session-traveled-to-city-preview-map')
                stage('ready')
            elif current == 'ready' and game.can_submit_battle_intent() and not busy:
                battle, cards = hand(game)
                ultimate = next((card for card in cards if card[1] == '410104'), None)
                if ultimate:
                    guard.check(ultimate[2] == 0, 'Ultimate cost is not the source zero')
                    game.play_card(ultimate[0])
                    state['ultimate'] = ultimate[0]
                    stage('ultimate-watch')
                else:
                    guard.check(state['plays'] < 8, 'Combo did not generate the source ultimate')
                    energy = int(battle.get_editor_property('energy'))
                    choice = min((card for card in cards if card[2] <= energy), key=lambda card: card[2], default=None)
                    guard.check(choice, 'No affordable combo card')
                    state['plays'] += 1
                    game.play_card(choice[0])
                    stage('between-plays')
            elif current == 'between-plays' and game.can_submit_battle_intent() and not busy:
                stage('ready')
            elif current == 'ultimate-watch':
                log = native_log.read_text('utf8', errors='replace')
                started = 'HCZS ultimate battle sequence started:' in log
                if started:
                    state['startedSequence'] = True
                if 'HCZS ultimate receipt during source sequence: damageEvents=8' in log:
                    state['receipt'] = True
                if state.get('startedSequence') and state.get('sawPause') and state.get('receipt') and not busy and not u.GameplayStatics.is_game_paused(world):
                    battle, cards = hand(game)
                    guard.check(all(card[1] != '410104' for card in cards), 'Played ultimate remained in hand')
                    guard.check('nine attack cues stay unmapped' in log, 'Receipt log dropped the mapping boundary')
                    report.update(playsBeforeUltimate=state['plays'], ultimateInstance=state['ultimate'],
                                  videoPauseObserved=True, damageEvents=8, map=level)
                    passed('formal-city-battle-starts-source-ultimate-and-keeps-eight-damages-unmapped')
                    finish()
        except Exception:
            finish(traceback.format_exc())
        finally:
            state['busy'] = False

    save()
    guard.check(u.HczsDevelopmentLibrary.request_floating_play_session(1600, 900), 'Floating PIE request refused')
    handle = u.register_slate_post_tick_callback(tick)
    u.log('HCZS city ultimate report: ' + str(output))


if __name__ == '__main__':
    run()
