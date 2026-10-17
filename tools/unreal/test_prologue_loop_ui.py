"""PIE acceptance for the whole prologue loop through the native client.

Loop phase (-HczsPrologueLoopUI): new profile -> hall -> dungeon explore -> tutorial 5000 with
guide group 1001 answered by real widget presses/drags -> 3997 settlement -> back to the dungeon
-> AVG138 -> boss 1703 -> 3998 settlement -> back to the dungeon -> AVG134 narration.
Restart phase (-HczsPrologueLoopRestart): a fresh editor process against the same isolated
server selects the saved profile and checks that the finished prologue is not replayed.
Requires -HczsMainlineUITest -HczsServerPort=<isolated port> -HczsMainlineManifest=<owned server.json>
-abslog=<same run directory>.
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

HALL = 'L_ElsaHallFxPreview'
DUNGEON = 'L_Chess239'
TUTORIAL = 'tutorial-5000'
BOSS = 'prologue-boss-1703'
PROFILE_NAME = '序章全流程验收'
GUIDE_REQUIRED = {1850, 1851, 1852, 1853, 1854, 1855, 1858, 1859, 1860}


def run():
    import unreal as u
    command = u.SystemLibrary.get_command_line()
    restart = guard.flag(command, 'HczsPrologueLoopRestart')
    argument = guard.argument(command, 'HczsMainlineManifest')
    guard.check(argument and (restart or guard.flag(command, 'HczsPrologueLoopUI')),
                'Require -HczsPrologueLoopUI or -HczsPrologueLoopRestart and an owned manifest')
    path = Path(argument).resolve()
    raw = path.read_bytes()
    manifest = json.loads(raw)
    address = guard.validate_manifest(manifest, path, command)
    log_arg = guard.argument(command, 'abslog') or guard.argument(command, 'ABSLOG')
    guard.check(log_arg and Path(log_arg).resolve().parent == path.parent, 'Pass -abslog inside this run directory')
    editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    guard.check(not editor.get_game_world(), 'Use a dedicated Editor before PIE')
    phase = 'restart' if restart else 'loop'
    output = path.parent / ('prologue-boss-ui-' + phase + '-' + str(time.time_ns()) + '.json')
    report = dict(schemaVersion=1, mode='native-prologue-loop-' + phase, passed=False, checks=[], steps=[], guideSteps=[],
                  startedAtUnixMs=int(time.time() * 1000), screenshots=[])

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

    guard.check(path.read_bytes() == raw, 'Manifest changed during acceptance')
    report['identity'] = http('/__hczs_test_control/identity', control=True)
    guard.validate_identity(report['identity'], manifest, raw)

    def prepare():
        bootstrap = http('/api/rebuild/v1/bootstrap')
        if restart:
            saved = [p for p in bootstrap.get('profiles', []) if p.get('displayName') == PROFILE_NAME]
            guard.check(len(saved) == 1, 'The loop profile was not persisted across the restart')
            campaign = http('/api/rebuild/v1/profiles/' + saved[0]['id'] + '/mainline')['campaign']
            guard.check(campaign.get('revision') == 2 and [r.get('challengeId') for r in campaign.get('completed', [])] == [3997, 3998],
                        'Persisted campaign is not the finished prologue')
            return dict(profileId=saved[0]['id'], campaign=campaign)
        guard.check(bootstrap.get('profiles') == [], 'Use an empty owned run')
        profile = http('/api/rebuild/v1/profiles', {'displayName': PROFILE_NAME})['profile']
        return dict(profileId=profile['id'])

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-prologue-loop')
    future = pool.submit(prepare)
    state = dict(stage='prepare', started=time.monotonic(), entered=time.monotonic(), busy=False, done=False,
                 visits=0, acted=0.0, plays=0, ends=0, dragRefused=False, battle=None)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')

    def stage(name):
        state.update(stage=name, entered=time.monotonic())
        report['stage'] = name
        save()
        u.log('HCZS prologue loop UI stage=' + name)

    def passed(name, **detail):
        report['checks'].append(dict(name=name, passed=True, **detail))
        save()

    def finish(error=None):
        if state['done']:
            return
        state['done'] = True
        report.update(passed=error is None, error=error, finishedAtUnixMs=int(time.time() * 1000))
        save()
        u.unregister_slate_post_tick_callback(handle)
        pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS prologue loop UI result: ' + str(output))
        if error:
            u.log_error(error)
        u.SystemLibrary.quit_editor()

    def shoot(world, name, then):
        shot = path.parent / ('prologue-loop-' + name + '-' + str(time.time_ns()) + '.png')
        u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="' + shot.as_posix() + '" -nosuffix')
        state.update(shot=shot, after=then)
        report['screenshots'].append(dict(name=name, path=str(shot)))
        stage('capture-wait')

    def session_widget(game):
        widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsSessionWidget, True)
        return widgets[0] if len(widgets) == 1 else None

    def dungeon_widget(game):
        widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsDungeonWidget, True)
        return widgets[0] if len(widgets) == 1 else None

    def drag(widget, card):
        for phase_name in ('begin', 'move', 'release'):
            guard.check(widget.development_drag_card(card, 'enemy', False, phase_name), 'Real card ' + phase_name + ' failed')

    def battle_turn(game, presenter, guided):
        """One real UI action in the current battle; returns True when an action was sent."""
        widget = session_widget(game)
        if not widget or (presenter and presenter.is_presentation_busy()) or not game.can_submit_battle_intent():
            return False
        battle = game.get_editor_property('current_battle')
        if battle.get_editor_property('status') != 'player-turn':
            return False
        paint = json.loads(widget.development_describe_ui())
        guide = paint.get('guide', {})
        enabled = [c['value'] for c in paint.get('controls', []) if c.get('action') == 'play-card' and c.get('enabled')]
        if guided and guide.get('stepId', -1) > 0:
            if not guide.get('shown'):
                guard.check(time.monotonic() - state['entered'] < 30, 'Guide step %s never became visible' % guide.get('stepId'))
                return False
            step = guide['stepId']
            if not report['guideSteps'] or report['guideSteps'][-1] != step:
                report['guideSteps'].append(step)
            if guide['advance'] == 'tap':
                if not state['dragRefused'] and enabled:
                    # The touch mask swallows the card press and treats it as the step's tap.
                    guard.check(not widget.development_drag_card(enabled[0], 'enemy', False, 'begin'), 'A card drag passed through tap step %d' % step)
                    state['dragRefused'] = True
                    passed('guide-tap-step-blocks-card-drag', step=step)
                else:
                    guard.check(widget.development_click_control('guide-next', '', False), 'Guide tap did not route at %d' % step)
                after = json.loads(widget.development_describe_ui()).get('guide', {})
                guard.check(after.get('stepId') != step, 'Guide tap did not advance %d' % step)
                if step == 1852 - 1 and not state.get('shotSwipe'):
                    state['shotSwipe'] = True
                    state['entered'] = time.monotonic()
                return False
            if guide['advance'] == 'play-card':
                hand = [c.get_editor_property('instance_id') for c in battle.get_editor_property('hand')]
                card = hand[2] if len(hand) > 2 and hand[2] in enabled else (enabled[0] if enabled else None)
                guard.check(card, 'No draggable card for the drag lesson')
                drag(widget, card)
                report['steps'].append(dict(action='play-card', guide=step))
                state['plays'] += 1
                return True
            guard.check(widget.development_click_control('end-turn', '', False), 'Guide end-turn did not route')
            report['steps'].append(dict(action='end-turn', guide=step))
            state['ends'] += 1
            return True
        end_enabled = any(c.get('action') == 'end-turn' and c.get('enabled') for c in paint.get('controls', []))
        if time.monotonic() - state['acted'] < 1.0 or not (enabled or end_enabled):
            return False
        guard.check(state['plays'] + state['ends'] < 100, 'Battle did not finish within bounds')
        if enabled:
            drag(widget, enabled[0])
            report['steps'].append(dict(action='play-card'))
            state['plays'] += 1
        else:
            guard.check(widget.development_click_control('end-turn', '', False), 'End-turn did not route')
            report['steps'].append(dict(action='end-turn'))
            state['ends'] += 1
        return True

    def tick(delta):
        if state['busy'] or state['done']:
            return
        state['busy'] = True
        try:
            current = state['stage']
            guard.check(time.monotonic() - state['started'] < 900, 'Prologue loop deadline at ' + current)
            if current == 'capture-wait':
                if state['shot'].exists() and time.monotonic() - state['entered'] > 2:
                    guard.check(state['shot'].stat().st_size > 1024, 'Screenshot was not written')
                    if state['after'] == 'finish':
                        finish()
                    else:
                        stage(state['after'])
                return
            world = editor.get_game_world()
            if not world:
                return
            game = u.GameplayStatics.get_game_instance(world)
            if not game or game.get_editor_property('request_in_flight'):
                return
            guard.check(not game.get_editor_property('has_pending_intent') and not game.get_editor_property('error_code'),
                        'Native request failed: ' + str(game.get_editor_property('error_code')))
            level = u.GameplayStatics.get_current_level_name(world, True)
            presenters = u.GameplayStatics.get_all_actors_with_tag(world, 'HCZSBattlePresentation')
            presenter = presenters[0] if len(presenters) == 1 else None
            if current == 'prepare' and future.done():
                report['preparation'] = future.result()
                game.refresh_bootstrap()
                stage('profile')
            elif current == 'profile':
                game.select_profile(report['preparation']['profileId'])
                stage('hall')
            elif current == 'hall' and level == HALL and game.is_hall_scene_ready() and game.get_editor_property('mainline_state_current'):
                game.enter_mainline_dungeon()
                stage('restart-dungeon' if restart else 'dungeon')
            elif current == 'restart-dungeon' and level == DUNGEON:
                widget = dungeon_widget(game)
                if not widget or time.monotonic() - state['entered'] < 2:
                    return
                info = json.loads(widget.development_describe())
                guard.check(not info['avg134Pending'] and info['avg138Index'] == -1, 'Restart replayed prologue narration')
                guard.check(widget.development_press_control('explore'), 'Explore press did not route after restart')
                state['pressed'] = time.monotonic()
                stage('restart-hold')
            elif current == 'restart-hold':
                if time.monotonic() - state['entered'] < 3:
                    return
                guard.check(level == DUNGEON and not game.get_editor_property('current_battle').get_editor_property('id'),
                            'A finished prologue started another battle after restart')
                passed('restart-keeps-finished-prologue', campaignRevision=report['preparation']['campaign']['revision'])
                shoot(world, 'restart-dungeon', 'finish')
            elif current == 'dungeon' and level == DUNGEON:
                widget = dungeon_widget(game)
                if not widget or time.monotonic() - state['entered'] < 2:
                    return
                info = json.loads(widget.development_describe())
                progress = game.get_editor_property('mainline_progress')
                if state['visits'] == 2:
                    guard.check(info['avg134Pending'], 'AVG134 did not open after the 3998 settlement')
                    if info['avg134Index'] <= 0 and not state.get('shot134'):
                        state['shot134'] = True
                        shoot(world, 'avg134', 'dungeon')
                        return
                    line = info['avg134Line']
                    report['steps'].append(dict(action='avg134', index=info['avg134Index'], line=line[:24]))
                    if info['avg134Index'] == info['avg134Count'] - 1:
                        guard.check(line.startswith('我叫' + PROFILE_NAME + '，'), 'Row 100 did not use the profile name')
                    guard.check(widget.development_press_control('avg134'), 'AVG134 press did not route')
                    after = json.loads(widget.development_describe())
                    if after['avg134Pending']:
                        state['entered'] = time.monotonic() - 1.5
                        return
                    passed('avg134-read-after-boss', lines=info['avg134Count'])
                    shoot(world, 'loop-end', 'finish')
                    return
                guard.check(info['sourceReady'] and 'explore' in info['enabledControls'], 'Dungeon explore control is not painted')
                if state['visits'] == 1 and info['avg138Index'] < info['avg138Count']:
                    guard.check(progress.get_editor_property('first_challenge_passed'), 'Second visit before 3997 passed')
                    shots = state.setdefault('shot138', set())
                    if info['avg138Index'] in (0, 4) and info['avg138Index'] not in shots:
                        shots.add(info['avg138Index'])
                        shoot(world, 'avg138-%d' % info['avg138Index'], 'dungeon')
                        return
                    guard.check(widget.development_press_control('explore'), 'Explore press for AVG138 did not route')
                    state['entered'] = time.monotonic() - 1.5
                    return
                guard.check(widget.development_press_control('explore'), 'Explore press did not route')
                stage('travel')
            elif current == 'travel' and level != DUNGEON and presenter and presenter.is_scene_ready():
                battle = game.get_editor_property('current_battle')
                expected = BOSS if state['visits'] == 1 else TUTORIAL
                guard.check(battle.get_editor_property('encounter_id') == expected, 'Explore opened ' + battle.get_editor_property('encounter_id'))
                report.setdefault('battles', []).append(dict(encounterId=expected, id=battle.get_editor_property('id'), map=level))
                state.update(plays=0, ends=0, acted=0.0)
                passed('explore-entered-' + expected, map=level)
                stage('battle')
            elif current == 'battle':
                battle = game.get_editor_property('current_battle')
                status = battle.get_editor_property('status')
                if status == 'won':
                    stage('victory')
                    return
                guard.check(status != 'lost', 'Battle was lost')
                guided = battle.get_editor_property('encounter_id') == TUTORIAL
                if guided and state.get('shotSwipe') and not state.get('shotSwipeDone'):
                    paint = json.loads(session_widget(game).development_describe_ui())
                    if paint.get('guide', {}).get('stepId') == 1852 and paint['guide'].get('shown'):
                        state['shotSwipeDone'] = True
                        shoot(world, 'guide-1852', 'battle')
                    return
                if battle_turn(game, presenter, guided):
                    state['acted'] = time.monotonic()
            elif current == 'victory' and not (presenter and presenter.is_presentation_busy()):
                widget = session_widget(game)
                paint = json.loads(widget.development_describe_ui()) if widget else {}
                if not any(c.get('action') == 'settle-mainline' and c.get('enabled') for c in paint.get('controls', [])):
                    return
                if state['visits'] == 0:
                    guide = paint.get('guide', {})
                    missing = sorted(GUIDE_REQUIRED - set(report['guideSteps']))
                    guard.check(guide.get('complete') and not missing, 'Guide 1001 incomplete; missing %s' % missing)
                    passed('guide-1001-answered-through-widget', steps=report['guideSteps'])
                guard.check(widget.development_click_control('settle-mainline', '', False), 'Native settle press did not route')
                stage('settled')
            elif current == 'settled':
                widget = session_widget(game)
                progress = game.get_editor_property('mainline_progress')
                key = 'boss_challenge_passed' if state['visits'] == 1 else 'first_challenge_passed'
                if not progress.get_editor_property(key) or not game.get_editor_property('mainline_state_current'):
                    return
                passed('settled-' + ('3998' if state['visits'] == 1 else '3997'), plays=state['plays'], endTurns=state['ends'])
                guard.check(widget and widget.development_click_control('hall', '', False), 'Result hall press did not route')
                state['visits'] += 1
                stage('dungeon')
        except Exception:
            finish(traceback.format_exc())
        finally:
            state['busy'] = False

    save()
    guard.check(u.HczsDevelopmentLibrary.request_floating_play_session(1600, 900), 'Floating PIE request refused')
    handle = u.register_slate_post_tick_callback(tick)
    u.log('HCZS prologue loop UI report: ' + str(output))


if __name__ == '__main__':
    run()
