"""PIE acceptance for prologue 3998/1703 through the native client.

Requires -HczsMainlineUITest -HczsServerPort=<isolated port> -HczsPrologueBossUI
-HczsMainlineManifest=<owned server.json> -abslog=<same run directory>.
HTTP only prepares the settled 3997 tutorial; the dungeon explore/AVG138 presses,
boss battle cards and the 3998 settlement all go through the running client.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import traceback
import urllib.request
import uuid

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import test_mainline_ui as guard

HALL = 'L_ElsaHallFxPreview'
DUNGEON = 'L_Chess239'
BOSS_MAP = 'L_PrologueBoss1703'
BOSS = 'prologue-boss-1703'
FUTURE_ACTIONS = TOOLS.parents[1] / 'analysis/prologue-boss/future-actions/report.json'


PARTY_CARD_TYPES = {'140002': 'skill', '440302': 'skill', '440303': 'ability', '140004': 'def', '240008': 'def'}


def validate_party_faces(sprites, texts, hand_cards, shields):
    guard.check({'player-1', 'player-3', 'monster-2013'} <= sprites, 'Party/boss portraits were not painted')
    seen = sorted(set(PARTY_CARD_TYPES) & hand_cards)
    guard.check(seen, 'No Future card reached the hand')
    for cid in seen:
        kind = PARTY_CARD_TYPES[cid]
        required = {'card-' + cid, 'card-frame-' + kind, 'card-type-bar-' + kind, 'card-type-icon-' + kind}
        guard.check(required <= sprites, 'Card %s face parts not painted: %s' % (cid, sorted(required - sprites)))
    shield_lines = sorted(t for t in texts if '获得' in t and any(value in t for value in shields))
    guard.check(not {'140004', '240008', '440302'} & hand_cards or (shields and all(any(v in t for t in shield_lines) for v in shields)),
                'Shield card description lacks its value: %s in %s' % (sorted(shields), sorted(t for t in texts if '获得' in t or '护' in t)))
    guard.check(not any('#R' in t or '#l' in t for t in texts), 'Rich-text markup leaked into painted text')
    return dict(cards=seen, shieldLines=shield_lines[:4])


def validate_ally_actions(log, steps, card_clips):
    rows = [line.split('side=ally member=1 clip=', 1)[1].split(' ', 1)[0]
            for line in log.splitlines() if 'HCZS source animation playing: side=ally member=1 clip=' in line]
    expected = [card_clips[s['cardId']] for s in steps if s.get('action') == 'play-card' and s.get('ownerIndex') == 1]
    card_rows = [clip for clip in rows if clip in set(card_clips.values())]
    guard.check(expected and card_rows == expected, 'Future card clips differ from source timelines: %s vs %s' % (card_rows, expected))
    guard.check(all(clip in set(card_clips.values()) | {'hit_1', 'death'} for clip in rows), 'Unexpected Future clip: %s' % rows)
    return dict(cardClips=card_rows, hits=rows.count('hit_1'), deaths=rows.count('death'),
                entranceShow='HCZS entrance ally SHOW:' in log)


def validate_future_sounds(log, clips):
    def heard(clip):
        return [line for line in log.splitlines() if 'HCZS ally source sound: clip=%s ' % clip in line]
    expected = {
        'show': ('future_show_2', '815007610', '-3.0', 1),
        'shield_1': ('future_shield1', '787477600', '-5.0', clips.count('shield_1')),
        'buff_2': ('future_buff2', '132220398', '2.0', clips.count('buff_2')),
    }
    counts = {}
    for clip, (event, source, volume, count) in expected.items():
        rows = heard(clip)
        guard.check(count > 0 and len(rows) == count, 'Future %s sound count %d != %d' % (clip, len(rows), count))
        guard.check(all('event=%s ' % event in line and 'source=%s ' % source in line and 'volumeDb=%s ' % volume in line
                        and 'loaded=1' in line and 'playing=1' in line for line in rows),
                    'Future %s sound log differs: %s' % (clip, rows))
        counts[clip] = len(rows)
    return counts


def validate_boss_campaign(campaign, profile_id, battle_id):
    guard.check(campaign.get('profileId') == profile_id and campaign.get('revision') == 2
                and [row.get('challengeId') for row in campaign.get('completed', [])] == [3997, 3998]
                and campaign['completed'][1].get('battleId') == battle_id
                and campaign.get('activityDatas') == {'2': {'3997': {'successTime': 1}, '3998': {'successTime': 1}}},
                'Boss completion was not recorded once after 3997')
    second = campaign['challenges'][1]
    guard.check(second.get('id') == 3998 and second.get('status') == 'passed' and second.get('successTime') == 1
                and second.get('encounterId') == BOSS and second.get('executable') is True, 'Passed 3998 projection differs')


def run():
    import unreal as u
    command = u.SystemLibrary.get_command_line()
    argument = guard.argument(command, 'HczsMainlineManifest')
    guard.check(argument and guard.flag(command, 'HczsPrologueBossUI'), 'Require -HczsPrologueBossUI and an owned manifest')
    path = Path(argument).resolve()
    raw = path.read_bytes()
    manifest = json.loads(raw)
    address = guard.validate_manifest(manifest, path, command)
    log_arg = guard.argument(command, 'abslog') or guard.argument(command, 'ABSLOG')
    guard.check(log_arg and Path(log_arg).resolve().parent == path.parent, 'Pass -abslog inside this run directory')
    native_log = Path(log_arg).resolve()
    lose = guard.flag(command, 'HczsPrologueBossLose')
    editor = u.get_editor_subsystem(u.UnrealEditorSubsystem)
    guard.check(not editor.get_game_world(), 'Use a dedicated Editor before PIE')
    output = path.parent / ('prologue-boss-ui-' + str(time.time_ns()) + '.json')
    report = dict(schemaVersion=1, mode='native-prologue-boss-1703', passed=False, checks=[], steps=[],
                  startedAtUnixMs=int(time.time() * 1000), rules='prologue-party-reconstruction-v1', lose=lose)

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
        content = bootstrap['content']['mainlineId']
        profile = http('/api/rebuild/v1/profiles', {'displayName': '序章首领战原生验收'})['profile']
        route = '/api/rebuild/v1/profiles/' + profile['id'] + '/battles'
        battle = http(route, {'requestId': 'boss-ui-tutorial-' + str(uuid.uuid4()), 'encounterId': 'tutorial-5000', 'seed': 7})['battle']
        for _ in range(256):
            if battle['state']['status'] != 'player-turn':
                break
            state, definition = battle['state'], battle['scenario']['definition']
            instances = {card['instanceId']: card['cardId'] for card in state['cards']}
            playable = [i for i in state['piles']['hand'] if definition['cards'][instances[i]]['cost'] <= state['energy']]
            payload = {'requestId': 'boss-ui-tutorial-' + str(uuid.uuid4()), 'expectedRevision': battle['revision'],
                       'type': 'play-card' if playable else 'end-turn', **({'instanceId': playable[0]} if playable else {})}
            battle = http(route + '/' + battle['id'] + '/actions', payload)['battle']
        guard.check(battle['state']['status'] == 'won', 'Tutorial preparation did not win')
        settled = http('/api/rebuild/v1/profiles/' + profile['id'] + '/mainline/settlements',
                       {'requestId': 'boss-ui-settle-' + str(uuid.uuid4()), 'expectedRevision': 0, 'contentId': content, 'battleId': battle['id']})
        campaign = settled['campaign']
        guard.check(campaign['revision'] == 1 and campaign['challenges'][1]['status'] == 'available'
                    and campaign['challenges'][1]['encounterId'] == BOSS and campaign['challenges'][1]['executable'] is True,
                    'Settled 3997 did not open the bound boss challenge')
        return dict(profileId=profile['id'], tutorialBattleId=battle['id'], contentId=content)

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-prologue-boss')
    future = pool.submit(prepare)
    state = dict(stage='prepare', started=time.monotonic(), entered=time.monotonic(), busy=False, done=False, plays=0, ends=0)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')

    def stage(name):
        state.update(stage=name, entered=time.monotonic())
        report['stage'] = name
        save()
        u.log('HCZS prologue boss UI stage=' + name)

    def passed(name, **detail):
        report['checks'].append(dict(name=name, passed=True, **detail))

    def finish(error=None):
        if state['done']:
            return
        state['done'] = True
        report.update(passed=error is None, error=error, finishedAtUnixMs=int(time.time() * 1000))
        save()
        u.unregister_slate_post_tick_callback(handle)
        pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS prologue boss UI result: ' + str(output))
        if error:
            u.log_error(error)
        u.SystemLibrary.quit_editor()

    def session_widget(game):
        widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsSessionWidget, True)
        return widgets[0] if len(widgets) == 1 else None

    def tick(delta):
        if state['busy'] or state['done']:
            return
        state['busy'] = True
        try:
            current = state['stage']
            guard.check(time.monotonic() - state['started'] < 420, 'Prologue boss acceptance deadline at ' + current)
            if current == 'capture-wait':
                if state['shot'].exists() and time.monotonic() - state['entered'] > 2:
                    guard.check(state['shot'].stat().st_size > 1024, 'Screenshot was not written')
                    report['screenshot'] = str(state['shot'])
                    finish()
                return
            world = editor.get_game_world()
            if not world:
                return
            if state.get('allyShotAt') and time.monotonic() >= state['allyShotAt']:
                state['allyShotAt'] = 0
                report['allyActionScreenshot'] = str(path.parent / ('prologue-boss-future-action-' + str(time.time_ns()) + '.png'))
                u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="' + Path(report['allyActionScreenshot']).as_posix() + '" -nosuffix')
            game = u.GameplayStatics.get_game_instance(world)
            if not game or game.get_editor_property('request_in_flight'):
                return
            guard.check(not game.get_editor_property('has_pending_intent') and not game.get_editor_property('error_code'),
                        'Native request failed: ' + str(game.get_editor_property('error_code')))
            level = u.GameplayStatics.get_current_level_name(world, True)
            presenters = u.GameplayStatics.get_all_actors_with_tag(world, 'HCZSBattlePresentation')
            presenter = presenters[0] if len(presenters) == 1 else None
            busy = bool(presenter.is_presentation_busy()) if presenter else False
            if current == 'prepare' and future.done():
                report['preparation'] = future.result()
                game.refresh_bootstrap()
                stage('profile')
            elif current == 'profile':
                game.select_profile(report['preparation']['profileId'])
                stage('hall')
            elif current == 'hall' and level == HALL and game.is_hall_scene_ready() and game.get_editor_property('mainline_state_current'):
                game.enter_mainline_dungeon()
                stage('dungeon')
            elif current == 'dungeon' and level == DUNGEON:
                widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsDungeonWidget, True)
                if len(widgets) != 1 or time.monotonic() - state['entered'] < 2:
                    return
                info = json.loads(widgets[0].development_describe())
                guard.check(info['sourceReady'] and 'explore' in info['enabledControls'], 'Dungeon explore control is not painted')
                if info['avg138Index'] < info['avg138Count']:
                    guard.check(widgets[0].development_press_control('explore'), 'Native explore press did not route')
                    after = json.loads(widgets[0].development_describe())
                    guard.check(after['avg138Index'] > info['avg138Index'] and not game.get_editor_property('request_in_flight'),
                                'Explore did not advance AVG138 before the boss battle')
                    report['steps'].append(dict(action='explore', avg138Index=after['avg138Index']))
                    state['entered'] = time.monotonic() - 1.5
                    return
                passed('avg138-played-in-order-before-battle', lines=info['avg138Count'])
                guard.check(widgets[0].development_press_control('explore'), 'Native explore press after AVG138 did not route')
                stage('travel')
            elif current == 'travel' and level == BOSS_MAP:
                battle = game.get_editor_property('current_battle')
                guard.check(battle.get_editor_property('encounter_id') == BOSS and battle.get_editor_property('is_party')
                            and battle.get_editor_property('enemy_id') == '2013', 'Boss battle identity differs')
                guard.check(presenter and presenter.is_scene_ready(), 'Boss presentation did not become ready')
                ally = u.GameplayStatics.get_all_actors_with_tag(world, 'HCZSBattleAlly3')
                guard.check(len(ally) == 1, 'Future is not standing in the boss theatre')
                report['battleId'] = battle.get_editor_property('id')
                passed('explore-traveled-to-boss-theatre', map=level)
                stage('battle')
            elif current == 'battle' and not busy and game.can_submit_battle_intent():
                battle = game.get_editor_property('current_battle')
                status = battle.get_editor_property('status')
                if status != 'player-turn':
                    return
                energy = int(battle.get_editor_property('energy'))
                hand = [(c.get_editor_property('instance_id'), c.get_editor_property('card_id'), int(c.get_editor_property('cost')),
                         c.get_editor_property('owner_index')) for c in battle.get_editor_property('hand')]
                widget = session_widget(game)
                if widget:
                    ui = json.loads(widget.development_describe_ui())
                    state.setdefault('sprites', set()).update(ui.get('actualPaintedSprites', []))
                    state.setdefault('texts', set()).update(ui.get('renderedTexts', []))
                    state.setdefault('handCards', set()).update(card[1] for card in hand)
                    state.setdefault('shields', set()).update(row['firstShield'] for row in ui.get('hand', []) if row.get('firstShield'))
                choice = None if lose else next((card for card in hand if card[2] <= energy), None)
                guard.check(state['plays'] + state['ends'] < 80, 'Boss battle did not finish within bounds')
                if choice:
                    if choice[3] == 1 and 'allyShotAt' not in state:
                        state['allyShotAt'] = time.monotonic() + .6
                    state['plays'] += 1
                    report['steps'].append(dict(action='play-card', cardId=choice[1], ownerIndex=choice[3]))
                    game.play_card(choice[0])
                else:
                    state['ends'] += 1
                    report['steps'].append(dict(action='end-turn'))
                    game.end_turn()
                stage('between')
            elif current == 'between' and not busy:
                battle = game.get_editor_property('current_battle')
                status = battle.get_editor_property('status')
                if status == 'won':
                    stage('victory')
                elif status == 'lost' and lose:
                    stage('defeat')
                elif status == 'lost':
                    raise RuntimeError('Party lost the boss battle')
                elif game.can_submit_battle_intent():
                    stage('battle')
            elif current == 'defeat' and not busy and time.monotonic() - state['entered'] > 1:
                log = native_log.read_text('utf8', errors='replace')
                rows = [line.split('clip=', 1)[1].split(' ', 1)[0] + '@' + line.split('side=', 1)[1].split(' ', 1)[0]
                        for line in log.splitlines() if 'HCZS source animation playing: side=' in line]
                hits, ally_deaths, elsa_deaths = rows.count('hit_1@ally'), rows.count('death@ally'), rows.count('death@player')
                guard.check(hits > 0 and ally_deaths == 1 and elsa_deaths == 1,
                            'Defeat did not present Future hit/death once each: hits=%d allyDeaths=%d elsaDeaths=%d' % (hits, ally_deaths, elsa_deaths))
                guard.check(rows.index('death@player') < rows.index('hit_1@ally') < rows.index('death@ally'),
                            'Future was hit before Elsa fell or died before being hit')
                campaign = http('/api/rebuild/v1/profiles/' + report['preparation']['profileId'] + '/mainline')['campaign']
                guard.check([row.get('challengeId') for row in campaign.get('completed', [])] == [3997], 'A defeat recorded 3998')
                report['defeat'] = dict(allyHits=hits, allyDeaths=ally_deaths, elsaDeaths=elsa_deaths, endTurns=state['ends'])
                passed('future-hit-and-death-after-elsa-falls', **report['defeat'])
                state['shot'] = path.parent / ('prologue-boss-defeat-' + str(time.time_ns()) + '.png')
                u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="' + state['shot'].as_posix() + '" -nosuffix')
                stage('capture-wait')
            elif current == 'victory' and not busy:
                widget = session_widget(game)
                if not widget:
                    return
                paint = json.loads(widget.development_describe_ui())
                if not any(c.get('action') == 'settle-mainline' and c.get('enabled') for c in paint.get('controls', [])):
                    return
                guard.check('确认序章首领战通关' in paint.get('renderedTexts', []), 'Boss victory confirmation did not paint')
                guard.check(paint.get('party') and len(paint.get('partyMembers', [])) == 2, 'Party HUD was not described')
                report['victoryUI'] = dict(partyMembers=paint['partyMembers'], enemyAttackBuff=paint.get('enemyAttackBuff'))
                guard.check(widget.development_click_control('settle-mainline', '', False), 'Native settle press did not route')
                passed('boss-victory-settled-through-widget', plays=state['plays'], endTurns=state['ends'])
                stage('settled')
            elif current == 'settled':
                widget = session_widget(game)
                paint = json.loads(widget.development_describe_ui()) if widget else {}
                if not paint.get('mainline', {}).get('bossChallengePassed'):
                    return
                guard.check(any('序章首领战已通关' in text for text in paint.get('renderedTexts', [])), 'Boss settlement result did not paint')
                campaign = http('/api/rebuild/v1/profiles/' + report['preparation']['profileId'] + '/mainline')['campaign']
                validate_boss_campaign(campaign, report['preparation']['profileId'], report['battleId'])
                report['finalCampaign'] = campaign
                log = native_log.read_text('utf8', errors='replace')
                report['bossSkillClipsLogged'] = 'enemy skill has no recovered animation mapping' not in log
                effects = [line.split('sfx=', 1)[1].split(' ', 1)[0] for line in log.splitlines()
                           if 'HCZS enemy skill source effect:' in line and 'mode=hook-only' in line]
                allowed = {'effects/boss/muoumaxitua/muoumaxituan_shouji_01.sfx',
                           'effects/boss/muoumaxitua/muoumaxituan_skill_2_03.sfx'}
                guard.check(effects and set(effects) <= allowed, 'Boss skill effect hook differs: %s' % sorted(set(effects)))
                report['bossSkillEffects'] = sorted(set(effects))
                ally_effects = [line.split('clip=', 1)[1].split(' ', 1)[0] + '=' + line.split('sfx=', 1)[1].split(' ', 1)[0]
                                for line in log.splitlines()
                                if 'HCZS ally clip source effect:' in line and 'mode=hook-only' in line]
                guard.check(set(ally_effects) == {'shield_1=effects/player/future/future_buff_2.sfx',
                                                   'buff_2=effects/player/future/future_buff_2.sfx'},
                            'Future clip effect hook differs: %s' % sorted(set(ally_effects)))
                report['allyClipEffects'] = sorted(set(ally_effects))
                passed('authoritative-3998-success-recorded')
                card_clips = json.loads(FUTURE_ACTIONS.read_text('utf8'))['cardClips']
                report['futureActions'] = validate_ally_actions(log, report['steps'], card_clips)
                guard.check(report['futureActions']['entranceShow'], 'Future SHOW did not start with the Elsa entrance')
                report['futureSounds'] = validate_future_sounds(log, report['futureActions']['cardClips'])
                passed('future-source-battle-actions', **report['futureActions'])
                report['partyFaces'] = validate_party_faces(state.get('sprites', set()), state.get('texts', set()),
                                                            state.get('handCards', set()), state.get('shields', set()))
                passed('party-portraits-and-card-faces-painted', **report['partyFaces'])
                state['shot'] = path.parent / ('prologue-boss-native-' + str(time.time_ns()) + '.png')
                u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="' + state['shot'].as_posix() + '" -nosuffix')
                stage('capture-wait')
        except Exception:
            finish(traceback.format_exc())
        finally:
            state['busy'] = False

    save()
    guard.check(u.HczsDevelopmentLibrary.request_floating_play_session(1600, 900), 'Floating PIE request refused')
    handle = u.register_slate_post_tick_callback(tick)
    u.log('HCZS prologue boss UI report: ' + str(output))


if __name__ == '__main__':
    run()
