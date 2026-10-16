"""Run in a dedicated full UE Editor via -ExecCmds="py <this file>".

Requires -HczsMainlineUITest -HczsServerPort=<isolated port>
-HczsMainlineManifest=<owned server.json>. HTTP prepares one real tutorial win;
settlement is only invoked by the painted widget's native Slate pointer route.
Optional -HczsMainlineUIResume performs readback after an editor/server restart.
Optional -HczsMainlineUIKeepEditor leaves the finished PIE available for inspection.
Optional -HczsMainlineUICapture records the actual Slate window after settling.
Optional -HczsMainlineUIFaults requires the matching isolated response-fault mode.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
RESERVED_PORTS = {7456, 7457, 7458, 7460, 7470, 7471}


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def flag(command, name):
    return bool(re.search(r'(?:^|\s)-' + re.escape(name) + r'(?=\s|$)', command))


def argument(command, name):
    match = re.search(r'(?:^|\s)-' + re.escape(name) + r'=(?:"([^"]+)"|(\S+))', command)
    return (match[1] or match[2]) if match else None


def validate_manifest(manifest, path, command):
    path = Path(path).resolve()
    allowed = (ROOT / 'analysis/unreal/session-test').resolve()
    check(path.name == 'server.json' and path.parent != allowed and path.is_relative_to(allowed), 'Manifest must be in an owned isolated run directory')
    port = manifest.get('port')
    check(type(port) is int and 0 < port <= 65535 and port not in RESERVED_PORTS, 'Production/invalid port refused')
    check(flag(command, 'HczsMainlineUITest') and not flag(command, 'HczsUITest')
          and argument(command, 'HczsServerPort') == str(port), 'Require dedicated mainline UI flag and matching isolated port; omit HczsUITest')
    check(manifest.get('schemaVersion') == 2 and manifest.get('mode') == 'isolated-native-session-test'
          and manifest.get('mainlineEnabled') is True and manifest.get('faults') is False,
          'Require an explicitly mainline-enabled isolated server without ordinary battle faults')
    faults = manifest.get('mainlineFaults', False)
    check(type(faults) is bool and faults == flag(command, 'HczsMainlineUIFaults')
          and not (faults and flag(command, 'HczsMainlineUIResume')), 'Mainline fault mode must match exactly and cannot resume')
    check(re.fullmatch(r'hczs_test_ue_[0-9a-f]{32}', manifest.get('mongoDatabase', ''))
          and manifest.get('mongoEndpoint') == '127.0.0.1:27027'
          and manifest.get('address') == f'http://127.0.0.1:{port}', 'Server/database target differs')
    for key in ('runId', 'databaseIdentity', 'processIdentity'):
        check(re.fullmatch(UUID, manifest.get(key, '')), 'Invalid isolated ' + key)
    for key, minimum in (('pid', 1), ('processIndex', 0)):
        check(type(manifest.get(key)) is int and manifest[key] >= minimum, 'Invalid isolated ' + key)
    check(type(manifest.get('preserveDatabase')) is bool and re.fullmatch(r'[0-9a-f]{48}', manifest.get('controlToken', ''))
          and re.fullmatch(r'[0-9a-f]{64}', manifest.get('mongoUriSha256', '')), 'Invalid isolated ownership metadata')
    check(Path(manifest.get('recordDirectory', '')).resolve() == path.parent
          and Path(manifest.get('tracePath', '')).resolve() == path.parent / 'http-trace.jsonl', 'Run paths differ from manifest location')
    return manifest['address']


def validate_identity(identity, manifest, manifest_bytes):
    check(identity.get('schemaVersion') == 1 and identity.get('mode') == 'isolated-native-session-test-identity'
          and identity.get('readOnly') is True and identity.get('databaseLifecycle') == 'running'
          and identity.get('mainlineEnabled') is True, 'Live server is not an active isolated mainline run')
    for key in ('pid', 'port', 'mongoDatabase', 'mongoEndpoint', 'runId', 'databaseIdentity', 'processIdentity', 'processIndex'):
        check(identity.get(key) == manifest[key], 'Live ownership differs: ' + key)
    check(type(identity.get('mainlineFaults', False)) is bool
          and identity.get('mainlineFaults', False) == manifest.get('mainlineFaults', False), 'Live mainline fault mode differs')
    check(identity.get('manifestSha256') == hashlib.sha256(manifest_bytes).hexdigest(), 'Published manifest hash differs')


def validate_campaign(campaign, profile_id, content_id, passed, battle_id=None):
    check(campaign.get('profileId') == profile_id and campaign.get('contentId') == content_id
          and campaign.get('activityId') == 2 and campaign.get('policy') == 'local-prologue-progress-v1', 'Campaign identity/policy differs')
    check(campaign.get('revision') == int(passed) and len(campaign.get('completed', [])) == int(passed), 'Campaign completion count/revision differs')
    nodes = campaign.get('challenges', [])
    check(len(nodes) == 2, 'Unexpected mainline nodes')
    first, second = nodes
    check(first.get('id') == 3997 and first.get('battleId') == 5000 and first.get('encounterId') == 'tutorial-5000'
          and first.get('executable') is True and first.get('hasLoot') is False
          and first.get('status') == ('passed' if passed else 'available')
          and first.get('recordPresent') is passed and first.get('successTime') == (1 if passed else None)
          and 'successCount' not in first, 'First challenge projection differs')
    records = campaign.get('activityDatas')
    check(records == ({'2': {'3997': {'successTime': 1}}} if passed else None), 'activityDatas invented a zero-success record')
    check(second.get('id') == 3998 and second.get('battleId') == 1703 and second.get('encounterId') is None
          and second.get('executable') is False and second.get('hasLoot') is False
          and second.get('status') == ('available' if passed else 'locked')
          and second.get('recordPresent') is False and second.get('successTime') is None
          and 'successCount' not in second,
          'Unrestored boss was opened or next challenge status differs')
    if passed:
        done = campaign['completed'][0]
        check(done.get('challengeId') == 3997 and done.get('battleId') == battle_id
              and type(done.get('battleRevision')) is int and done['battleRevision'] > 0, 'Completion does not reference the actual tutorial win')
    else:
        check(campaign.get('updatedAt') is None, 'Fresh campaign has an invented timestamp')


def validate_pending_recovery(paint, pending, retryable, confirmed, expected_confirmed):
    mainline = paint.get('mainline', {})
    check(pending is True and retryable is True and confirmed is expected_confirmed, 'Failed response lost pending intent or confirmation phase')
    check(mainline.get('current') is False and mainline.get('revision') == 0 and mainline.get('firstChallengePassed') is False
          and mainline.get('canConfirm') is False and '已记录通关' not in paint.get('renderedTexts', []),
          'Unverified response was published as completed progress')


def validate_settlement_trace(rows, setup, faults=False):
    route = '/api/rebuild/v1/profiles/' + setup['profileId'] + '/mainline/settlements'
    indexed = [(index, row) for index, row in enumerate(rows) if row.get('phase') == 'ue-request' and row.get('method') == 'POST' and row.get('path') == route]
    writes = [row for _, row in indexed]
    check(len(writes) == (2 if faults else 1), 'Settlement POST count differs; UI produced an extra mutation or did not retry')
    for index, row in enumerate(writes):
        check(row.get('status') == 200 and row.get('replayed') is (index == 1)
              and row.get('requestId') == 'ue-mainline-' + setup['battleId'] and row.get('expectedRevision') == 0
              and row.get('contentId') == setup['contentId'], 'Native settlement command/receipt identity differs')
    if faults:
        check(writes[0].get('mainlineFault') == 'truncate-commit' and writes[0].get('droppedAfterCommit') is True
              and re.fullmatch(r'[0-9a-f]{64}', writes[0].get('bodySha256', ''))
              and writes[1].get('bodySha256') == writes[0]['bodySha256'], 'Unknown result retry changed the original payload')
        reads = [(index, row) for index, row in enumerate(rows) if row.get('phase') == 'ue-request'
                 and row.get('method') == 'GET' and row.get('path') == route.removesuffix('/settlements')]
        failed = [(index, row) for index, row in reads if row.get('mainlineFault') == 'truncate-confirmed-get']
        check(len(failed) == 1 and failed[0][0] > indexed[1][0] and failed[0][1].get('droppedAfterRead') is True,
              'Confirmed receipt was not followed by the intended failed GET')
        check(not any(index > failed[0][0] for index, _ in indexed), 'Confirmed read retry incorrectly submitted a third POST')
        check(any(index > failed[0][0] and row.get('status') == 200 and not row.get('mainlineFault')
                  and row.get('revision') == 1 for index, row in reads), 'No successful authoritative GET after confirmed read failure')
    return writes


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Isolated HTTP redirects are forbidden')


def run():
    import unreal as u

    command = u.SystemLibrary.get_command_line()
    manifest_arg = argument(command, 'HczsMainlineManifest')
    check(manifest_arg, 'Pass -HczsMainlineManifest=<owned server.json>')
    path = Path(manifest_arg).resolve()
    raw = path.read_bytes()
    check(len(raw) < 1024 * 1024, 'Manifest too large')
    manifest = json.loads(raw)
    address = validate_manifest(manifest, path, command)
    check(Path(u.Paths.project_dir()).resolve() == (ROOT / 'clients/unreal5 5.8').resolve(), 'Unexpected UE project')
    check(u.SystemLibrary.get_engine_version().startswith('5.8.'), 'Mainline UI test requires UE 5.8')
    check(not u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world(), 'Start this test in a dedicated editor before PIE')
    resume = flag(command, 'HczsMainlineUIResume')
    keep_editor = flag(command, 'HczsMainlineUIKeepEditor')
    capture = flag(command, 'HczsMainlineUICapture')
    faults = manifest.get('mainlineFaults', False)
    output = path.parent / ('mainline-ui-' + ('faults-' if faults else 'resume-' if resume else '') + str(time.time_ns()) + '.json')

    def http(route, body=None, control=False):
        check(route.startswith('/api/rebuild/v1/') or (control and route == '/__hczs_test_control/identity'), 'Unexpected test HTTP route')
        headers = {'Accept': 'application/json'}
        if control:
            headers['Authorization'] = 'Bearer ' + manifest['controlToken']
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(address + route, data=None if body is None else json.dumps(body).encode('utf8'), headers=headers)
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        check(len(data) <= 8 * 1024 * 1024, 'Oversized test response')
        return json.loads(data)

    def identity():
        actual = http('/__hczs_test_control/identity', control=True)
        validate_identity(actual, manifest, raw)
        return actual

    live = identity()
    report = dict(schemaVersion=1, passed=False, mode='mainline-ui-fault-recovery' if faults else 'mainline-ui-resume' if resume else 'mainline-ui-settlement',
                  serverIdentity=live, engine=u.SystemLibrary.get_engine_version(), nativePointerInput=True,
                  preparation='authoritative HTTP tutorial play-card/end-turn commands', steps=[])

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')

    def prepare():
        identity()
        bootstrap = http('/api/rebuild/v1/bootstrap')
        check('mainline-progression' in bootstrap.get('capabilities', []), 'Service did not enable mainline')
        content = bootstrap.get('content', {}).get('mainlineId')
        check(re.fullmatch(r'[a-f0-9]{64}', content or ''), 'Mainline content identity missing')
        profiles = bootstrap.get('profiles', [])
        if resume:
            check(len(profiles) == 1, 'Resume requires exactly one owned test profile')
            profile = profiles[0]
            battles = http('/api/rebuild/v1/profiles/' + profile['id'] + '/battles')['battles']
            check(len(battles) == 1, 'Resume requires exactly one owned test battle')
            battle = http('/api/rebuild/v1/profiles/' + profile['id'] + '/battles/' + battles[0]['id'])['battle']
            actions = 0
        else:
            check(profiles == [], 'Fresh UI run requires an empty owned test database; use a new run or explicit UIResume')
            profile = http('/api/rebuild/v1/profiles', {'displayName': '主线通关原生交互验收'})['profile']
            route = '/api/rebuild/v1/profiles/' + profile['id'] + '/battles'
            battle = http(route, {'requestId': 'mainline-ui-create-' + str(uuid.uuid4()), 'encounterId': 'tutorial-5000', 'seed': 7})['battle']
            actions = 0
            while battle['state']['status'] == 'player-turn':
                check(actions < 256, 'Tutorial did not finish within the bounded preparation')
                state, definition = battle['state'], battle['scenario']['definition']
                instances = {card['instanceId']: card['cardId'] for card in state['cards']}
                playable = [instance for instance in state['piles']['hand'] if definition['cards'][instances[instance]]['cost'] <= state['energy']]

                def priority(instance):
                    card = definition['cards'][instances[instance]]
                    damage = sum(int(effect['amount']) for effect in card['effects'] if effect['type'] == 'damage' and effect['target'] == 'opponent')
                    return damage / max(1, card['cost'])

                payload = {'requestId': 'mainline-ui-action-' + str(uuid.uuid4()), 'expectedRevision': battle['revision'],
                           'type': 'play-card' if playable else 'end-turn'}
                if playable:
                    payload['instanceId'] = max(playable, key=priority)
                battle = http(route + '/' + battle['id'] + '/actions', payload)['battle']
                actions += 1
        check(battle['state']['status'] == 'won' and battle['scenario'].get('encounterId') == 'tutorial-5000', 'Preparation must win the actual tutorial')
        campaign = http('/api/rebuild/v1/profiles/' + profile['id'] + '/mainline')['campaign']
        validate_campaign(campaign, profile['id'], content, resume, battle['id'])
        identity()
        return dict(profileId=profile['id'], battleId=battle['id'], battleRevision=battle['revision'], contentId=content,
                    actionCount=actions, campaignBefore=campaign)

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hczs-mainline-preparation')
    prepared = pool.submit(prepare)
    state = dict(stage='prepare', started=time.monotonic(), busy=False, game=None, widget=None, afterPaint=-1)
    save()

    def readback(passed):
        setup = report['preparationResult']
        campaign = http('/api/rebuild/v1/profiles/' + setup['profileId'] + '/mainline')['campaign']
        validate_campaign(campaign, setup['profileId'], setup['contentId'], passed, setup['battleId'])
        if passed:
            check(campaign['completed'][0]['battleRevision'] == setup['battleRevision'], 'Settled battle revision differs from authoritative win')
        report['steps'].append(dict(stage=state['stage'], campaign=campaign))
        return campaign

    def click(action, touch=False):
        widget = state['widget']
        before = json.loads(widget.development_describe_ui())
        at = int(time.time() * 1000)
        check(widget.development_click_control(action, '', touch), 'Real Slate route failed: ' + action)
        after = json.loads(widget.development_describe_ui())
        check(after['pointerEventSerial'] == before['pointerEventSerial'] + 1 and after['lastPointerAction'] == action
              and after['lastPointerTouch'] == touch, 'Actual native pointer observation differs')
        report['steps'].append(dict(action=action, input='touch' if touch else 'mouse', pointerEventSerial=after['pointerEventSerial'], atUnixMs=at))
        state['afterPaint'] = before['paintSerial']

    def finish(error=None):
        report.update(passed=error is None, error=error, lastStage=state['stage'])
        try:
            if state['widget']:
                report['finalUI'] = json.loads(state['widget'].development_describe_ui())
        except Exception as describe_error:
            report['finalUIUnavailable'] = str(describe_error)
        save()
        u.unregister_slate_post_tick_callback(handle)
        pool.shutdown(wait=False, cancel_futures=True)
        u.log('HCZS mainline UI result: ' + str(output))
        if error:
            u.log_error(error)
        if not keep_editor:
            u.SystemLibrary.quit_editor()

    def tick(delta):
        if state['busy']:
            return
        state['busy'] = True
        try:
            stage = state['stage']
            if report.get('lastStage') != stage:
                report['lastStage'] = stage
                save()
                u.log('HCZS mainline UI stage=' + stage)
            check(time.monotonic() - state['started'] < 240, 'Mainline UI deadline at ' + stage)
            if stage == 'capture-wait':
                if state['screenshot'].exists() and time.monotonic() - state['captureAt'] > 2:
                    check(state['screenshot'].stat().st_size > 1024, 'Screenshot was not written')
                    report['screenshot'] = str(state['screenshot'])
                    finish()
                return
            world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
            if not world:
                return
            game = state['game'] = u.GameplayStatics.get_game_instance(world)
            if not game or game.get_editor_property('request_in_flight'):
                return
            recovering = faults and stage in ('fault-await-unknown', 'fault-await-confirmed-get')
            if game.get_editor_property('has_pending_intent') and not recovering:
                return
            if stage == 'prepare':
                if not prepared.done():
                    return
                report['preparationResult'] = prepared.result()
                game.refresh_bootstrap()
                state['stage'] = 'choose-profile'
                return
            setup = report['preparationResult']
            check(game.get_editor_property('local_service_available'), 'Local UE service connection failed')
            if recovering:
                check(game.get_editor_property('has_pending_intent') and game.get_editor_property('error_code') in
                      ('TRANSPORT_FAILURE', 'INVALID_JSON', 'RESPONSE_TOO_LARGE', 'UNEXPECTED_RESPONSE'), 'Injected failure did not preserve an uncertain UI operation')
            else:
                check(not game.get_editor_property('error_code'), 'Unexpected UE error: ' + str(game.get_editor_property('error_code')))
            if stage == 'choose-profile':
                game.select_profile(setup['profileId'])
                state['stage'] = 'profile'
                return
            if stage in ('profile', 'hall-return'):
                if not game.is_hall_scene_ready() or not game.get_editor_property('mainline_state_current') or \
                        u.GameplayStatics.get_current_level_name(world, True) != 'L_ElsaHallFxPreview':
                    return
                readback(resume or stage == 'hall-return')
                game.continue_battle(setup['battleId'])
                state['stage'] = 'victory' if stage == 'profile' else 'reopened'
                state['afterPaint'] = -1
                return
            widgets = u.WidgetLibrary.get_all_widgets_of_class(game, u.HczsSessionWidget, True)
            if not widgets:
                return
            check(len(widgets) == 1, 'Expected one native session widget')
            widget = state['widget'] = widgets[0]
            paint = json.loads(widget.development_describe_ui())
            if not paint.get('battleScene') or not paint.get('visible') or paint.get('paintSerial', 0) <= max(0, state['afterPaint']) or paint.get('presentationBusy'):
                return
            check(paint.get('battleId') == setup['battleId'] and paint.get('serverStatus') == 'won'
                  and paint.get('playerId') == '1' and paint.get('enemyId') == '991' and not paint.get('sceneProblem'), 'Native scene differs from the restored tutorial victory')
            if recovering:
                if not any(control.get('action') == 'retry-intent' and control.get('enabled') for control in paint.get('controls', [])):
                    return
                expected_confirmed = stage == 'fault-await-confirmed-get'
                validate_pending_recovery(paint, bool(game.get_editor_property('has_pending_intent')),
                                          bool(game.get_editor_property('pending_intent_retryable')),
                                          bool(game.is_pending_receipt_confirmed()), expected_confirmed)
                report['steps'].append(dict(stage=stage, pending=True, receiptConfirmed=expected_confirmed,
                                           mainline=paint['mainline'], renderedTexts=paint.get('renderedTexts', [])))
                # Do not perform an independent campaign GET here: the first
                # GET following the replayed receipt must be the native client's.
                click('retry-intent', expected_confirmed)
                state['stage'] = 'settled' if expected_confirmed else 'fault-await-confirmed-get'
            elif stage == 'victory' and not resume:
                if not any(control.get('action') == 'settle-mainline' and control.get('enabled') for control in paint.get('controls', [])):
                    return
                readback(False)
                check(paint.get('mainline', {}).get('canConfirm') and '确认序章首战通关' in paint.get('renderedTexts', []), 'Real victory confirmation did not paint')
                identity()
                click('settle-mainline')
                # Attempt a second real pointer immediately. It may hit the old
                # painted control, but the native pending guard must prevent another POST.
                repeated = widget.development_click_control('settle-mainline', '', True)
                report['steps'].append(dict(action='settle-mainline-during-pending', nativePointerRouted=bool(repeated)))
                state['stage'] = 'fault-await-unknown' if faults else 'settled'
            elif stage in ('settled', 'reopened') or (stage == 'victory' and resume):
                if '已记录通关' not in paint.get('renderedTexts', []) or not any(
                        control.get('action') == 'refresh-mainline' and control.get('enabled') for control in paint.get('controls', [])):
                    return
                mainline = paint.get('mainline', {})
                check(mainline.get('current') and mainline.get('revision') == 1 and mainline.get('firstChallengePassed') is True
                      and mainline.get('completedBattleId') == setup['battleId'] and mainline.get('canConfirm') is False, 'UE did not publish authoritative completed progress')
                check(not widget.development_click_control('settle-mainline', '', True), 'Completed confirmation remains clickable')
                readback(True)
                click('refresh-mainline', True)
                state['stage'] = 'read-latest' if stage == 'settled' else 'verify-final'
            elif stage == 'read-latest':
                if not any(control.get('action') == 'hall' and control.get('enabled') for control in paint.get('controls', [])):
                    return
                readback(True)
                click('hall')
                state['stage'] = 'hall-return'
            elif stage == 'verify-final':
                readback(True)
                rows = [json.loads(line) for line in Path(manifest['tracePath']).read_text('utf8').splitlines() if line.strip()]
                report['settlementRequests'] = validate_settlement_trace(rows, setup, faults)
                if faults:
                    check([step.get('receiptConfirmed') for step in report['steps'] if step.get('stage') in
                           ('fault-await-unknown', 'fault-await-confirmed-get')] == [False, True], 'Missing distinct unknown/confirmed native recovery stages')
                report['serverIdentityAfter'] = identity()
                report['finalCampaign'] = readback(True)
                if capture:
                    # Give asynchronous streaming/rendering time before requesting
                    # the engine's Slate-inclusive screenshot on a later tick.
                    state['captureAt'] = time.monotonic()
                    state['stage'] = 'capture-ready'
                else:
                    finish()
            elif stage == 'capture-ready' and time.monotonic() - state['captureAt'] >= 10:
                target = path.parent / ('mainline-native-' + str(time.time_ns()) + '.png')
                check(not target.exists() and target.parent == path.parent, 'Unexpected capture path')
                u.SystemLibrary.execute_console_command(world, 'Shot SHOWUI filename="' + target.as_posix() + '" -nosuffix')
                state.update(stage='capture-wait', screenshot=target, captureAt=time.monotonic())
        except Exception:
            finish(traceback.format_exc())
        finally:
            state['busy'] = False

    u.get_editor_subsystem(u.LevelEditorSubsystem).editor_request_begin_play()
    handle = u.register_slate_post_tick_callback(tick)
    u.log('HCZS mainline UI report: ' + str(output))


if __name__ == '__main__':
    run()
