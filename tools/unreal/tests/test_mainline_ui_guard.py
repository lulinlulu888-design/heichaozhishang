"""Offline safety checks; imports no Unreal runtime and makes no requests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'test_mainline_ui.py'
SPEC = importlib.util.spec_from_file_location('mainline_ui', SCRIPT)
UI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UI)


class MainlineUiGuardTests(unittest.TestCase):
    def fixture(self):
        directory = UI.ROOT / 'analysis/unreal/session-test/mainline-unit-未启动'
        manifest = dict(schemaVersion=2, mode='isolated-native-session-test', mainlineEnabled=True, faults=False,
                        port=17466, address='http://127.0.0.1:17466', mongoDatabase='hczs_test_ue_' + 'a' * 32,
                        mongoEndpoint='127.0.0.1:27027', runId='1' * 8 + '-1111-1111-1111-' + '1' * 12,
                        databaseIdentity='2' * 8 + '-2222-2222-2222-' + '2' * 12,
                        processIdentity='3' * 8 + '-3333-3333-3333-' + '3' * 12,
                        pid=123, processIndex=0, preserveDatabase=True, controlToken='a' * 48,
                        mongoUriSha256='b' * 64, recordDirectory=str(directory), tracePath=str(directory / 'http-trace.jsonl'))
        raw = json.dumps(manifest).encode()
        identity = {key: manifest[key] for key in ('pid', 'port', 'mongoDatabase', 'mongoEndpoint', 'runId', 'databaseIdentity', 'processIdentity', 'processIndex', 'mainlineEnabled')}
        identity.update(schemaVersion=1, mode='isolated-native-session-test-identity', readOnly=True,
                        databaseLifecycle='running', manifestSha256=hashlib.sha256(raw).hexdigest())
        return manifest, directory / 'server.json', raw, identity

    def test_authenticated_isolated_target_only(self):
        manifest, path, raw, identity = self.fixture()
        command = '-HczsMainlineUITest -HczsServerPort=17466'
        self.assertEqual(UI.validate_manifest(manifest, path, command), manifest['address'])
        UI.validate_identity(identity, manifest, raw)
        for key, value in [('mainlineEnabled', False), ('mongoDatabase', 'hczs_city_preview'), ('faults', True),
                           ('address', 'http://localhost:17466'), ('port', 7460), ('pid', True)]:
            modified = {**manifest, key: value}
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                UI.validate_manifest(modified, path, command)
        with self.assertRaises(RuntimeError):
            UI.validate_manifest(manifest, path, command + ' -HczsUITest')
        for key, value in [('manifestSha256', 'f' * 64), ('mainlineEnabled', False), ('pid', 124), ('databaseLifecycle', 'stopped')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                UI.validate_identity({**identity, key: value}, manifest, raw)

    def test_completed_progress_cannot_open_boss_or_substitute_city(self):
        campaign = dict(profileId='profile', contentId='content', activityId=2, policy='local-prologue-progress-v1', revision=1,
                        completed=[dict(challengeId=3997, battleId='won-battle', battleRevision=9)],
                        activityDatas={'2': {'3997': {'successTime': 1}}},
                        challenges=[dict(id=3997, battleId=5000, encounterId='tutorial-5000', executable=True, hasLoot=False, status='passed', recordPresent=True, successTime=1),
                                    dict(id=3998, battleId=1703, encounterId=None, executable=False, hasLoot=False, status='available', recordPresent=False, successTime=None)])
        UI.validate_campaign(campaign, 'profile', 'content', True, 'won-battle')
        for index, key, value in [(0, 'encounterId', 'city-preview-10405'), (1, 'executable', True), (1, 'status', 'locked'), (0, 'hasLoot', True)]:
            modified = copy.deepcopy(campaign)
            modified['challenges'][index][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                UI.validate_campaign(modified, 'profile', 'content', True, 'won-battle')
        with self.assertRaises(RuntimeError):
            UI.validate_campaign(campaign, 'profile', 'content', True, 'another-battle')
        with self.assertRaises(RuntimeError):
            UI.validate_campaign({**campaign, 'revision': 2}, 'profile', 'content', True, 'won-battle')

    def test_quoted_unicode_path_and_exact_flags(self):
        self.assertEqual(UI.argument('-HczsMainlineManifest="D:/目录/test run/server.json"', 'HczsMainlineManifest'), 'D:/目录/test run/server.json')
        self.assertFalse(UI.flag('-NotHczsMainlineUITest -HczsMainlineUITestSuffix', 'HczsMainlineUITest'))
        self.assertTrue(UI.flag('-HczsMainlineUITest -Other', 'HczsMainlineUITest'))

    def test_fault_mode_is_bound_to_command_and_live_identity(self):
        manifest, path, _, identity = self.fixture()
        manifest['mainlineFaults'] = True
        command = '-HczsMainlineUITest -HczsServerPort=17466 -HczsMainlineUIFaults'
        UI.validate_manifest(manifest, path, command)
        with self.assertRaises(RuntimeError):
            UI.validate_manifest(manifest, path, command.replace(' -HczsMainlineUIFaults', ''))
        with self.assertRaises(RuntimeError):
            UI.validate_manifest(manifest, path, command + ' -HczsMainlineUIResume')
        raw = json.dumps(manifest).encode()
        identity.update(mainlineFaults=True, manifestSha256=hashlib.sha256(raw).hexdigest())
        UI.validate_identity(identity, manifest, raw)
        with self.assertRaises(RuntimeError):
            UI.validate_identity({**identity, 'mainlineFaults': False}, manifest, raw)

    def test_pending_response_cannot_publish_completion_or_lose_retry_phase(self):
        paint = dict(mainline=dict(current=False, revision=0, firstChallengePassed=False, canConfirm=False), renderedTexts=['操作结果尚未确认'])
        UI.validate_pending_recovery(paint, True, True, False, False)
        UI.validate_pending_recovery(paint, True, True, True, True)
        for pending, retryable, confirmed in [(False, True, False), (True, False, False), (True, True, True)]:
            with self.assertRaises(RuntimeError):
                UI.validate_pending_recovery(paint, pending, retryable, confirmed, False)
        for key, value in [('current', True), ('revision', 1), ('firstChallengePassed', True), ('canConfirm', True)]:
            changed = copy.deepcopy(paint)
            changed['mainline'][key] = value
            with self.assertRaises(RuntimeError):
                UI.validate_pending_recovery(changed, True, True, False, False)

    def test_fault_trace_requires_same_original_command_and_get_only_final_retry(self):
        setup = dict(profileId='profile', contentId='content', battleId='battle')
        route = '/api/rebuild/v1/profiles/profile/mainline/settlements'
        first = dict(phase='ue-request', method='POST', path=route, status=200, replayed=False, requestId='ue-mainline-battle',
                     expectedRevision=0, contentId='content', bodySha256='a' * 64, mainlineFault='truncate-commit', droppedAfterCommit=True)
        second = {**first, 'replayed': True}
        second.pop('mainlineFault')
        failed = dict(phase='ue-request', method='GET', path=route.removesuffix('/settlements'), status=200,
                      mainlineFault='truncate-confirmed-get', droppedAfterRead=True, revision=1)
        success = {**failed}
        success.pop('mainlineFault')
        rows = [first, second, failed, success]
        self.assertEqual(len(UI.validate_settlement_trace(rows, setup, True)), 2)
        for altered in [[first, {**second, 'bodySha256': 'b' * 64}, failed, success],
                        [first, second, failed, second, success], [first, second, success], [first, second, failed]]:
            with self.assertRaises(RuntimeError):
                UI.validate_settlement_trace(altered, setup, True)


if __name__ == '__main__':
    unittest.main()
