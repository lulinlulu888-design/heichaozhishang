"""Recover prologue-course consumers from hash-verified decoded APK scripts.

No APK code is executed. This reuses the public marshal/opcode/literal parsers;
the findings are ordinary static evidence, not REA Evidence or runtime capture.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from extract_texture_samples import APK_SHA256
from inspect_battle_rules import export
from trace_first_encounter import inventory, literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/prologue-course'
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'


def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                     allow_nan=False) + '\n', encoding='utf8')


def source_search(rows):
    """Bounded negative searches over every currently indexed decoded script.

    Search names/constant bytes, not runtime calls. Check each searched file's
    digest before using matches or absence as evidence. No native/dynamic name
    construction or unextracted resource can be ruled out by this search.
    """
    terms = ['isDisableSpecialSkill', 'EnableSpecialSkillRound',
             'getAvatarCharInitCardPile', 'getBattleCharInitLevel',
             'isInitCardPileCustomized', 'getBattleChar', 'curRound']
    matches = {term: [] for term in terms}
    for index, row in sorted(rows.items()):
        raw = (ROOT / row['output']).read_bytes()
        # The two unencrypted redirect.py entries use payload_sha256 because
        # they never needed decoded transformation. Verify the actual bytes.
        expected_hash = row.get('decoded_sha256', row.get('payload_sha256'))
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError(f'decoded search input changed: {index}')
        for term in terms:
            if term.encode('utf8') in raw:
                matches[term].append({'index': index, 'filename': row['filename'],
                                      'searchedBytesSha256': expected_hash})
    result = {'evidenceKind': 'hash-verified bounded byte-string search',
              'searchedDecodedModules': len(rows), 'terms': matches,
              'limitations': ['Matches do not prove calls; selected instruction exports establish consumers.',
                              'No native libclient.so, original server, dynamic imports, generated names or absent hot updates searched.']}
    write('symbol-search.json', result)
    return result


def build():
    with APK.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    OUT.mkdir(parents=True, exist_ok=True)
    rows = inventory()
    search = source_search(rows)
    course = literal_table(4105, {2})
    fields = course['rows'][0]['fields']
    if not (fields['FirstBattleID'] == 1703 and fields['BattleChar'] == [1, 3]
            and fields['CharLevel'] == [100, 100]
            and fields['DisableSpecialSkill'] is True
            and fields['EnableSpecialSkillRound'] == 2
            and fields['SkipChooseChar'] is True and len(fields['CardPile']) == 14):
        raise ValueError('Prologue course assumptions changed')
    write('course-table.json', course)
    selectors = {
        5947: None,
        3609: {(24, 9)},
        8434: {(71, 24), (71, 231)},
        9176: {(), (124,), (260,)},
        5455: {(7, 1), (7, 29)},
        5485: {(13,), (13, 69), (13, 75)},
        2634: {(56,), (56, 3), (56, 4)},
        9641: {(2,), (2, 4)},
        1288: {(21, 16)},
        6601: {(22, 3), (22, 4)},
        8213: {(8,), (8, 2), (8, 3)},
    }
    exports = {}
    for index, paths in selectors.items():
        result = export(rows[index])
        if paths is not None:
            result['code_objects'] = [obj for obj in result['code_objects']
                                      if tuple(obj['constant_path']) in paths]
            if {tuple(obj['constant_path']) for obj in result['code_objects']} != paths:
                raise ValueError(f'Selected code object missing: {index}')
        # Keep only relevant registration windows in the two large declaration
        # bodies. Each retains the whole-body digest and states its coverage.
        for obj in result['code_objects']:
            spans = None
            if index == 9176 and obj['constant_path'] == []:
                spans = [(2731, 2750), (2782, 2794)]
            if index == 5485 and obj['constant_path'] == [13]:
                spans = [(741, 828)]
            if spans:
                obj['instructionSelection'] = {'offsetSpans': spans,
                    'semantics': 'Only selected declaration instructions; bytecode digest covers full code object.'}
                obj['instructions'] = [item for item in obj['instructions']
                    if any(start <= item['offset'] < end for start, end in spans)]
        write(f'code-{index}.json', result)
        exports[index] = result
    rule = next(obj for obj in exports[5947]['code_objects']
                if obj['name'] == 'isDisableSpecialSkill')
    if rule['bytecode_sha256'] != '907c3af520f106550475194eb269b69004e040d724534d371ad049d901422695':
        raise ValueError('Special-skill gate changed; manual review required')
    comparison = next(item for item in rule['instructions'] if item['offset'] == 120)
    if comparison['opname'] != 'COMPARE_OP' or comparison['argument'] != 0:
        raise ValueError('Expected roundNum < enableRound comparison')
    owner_cards = [{'characterId': char_id, 'configuredLevel': level,
                    'cards': [{'cardId': card, 'globalDeckIndex': position}
                              for position, (card, owner) in enumerate(fields['CardPile'])
                              if owner == char_id]}
                   for char_id, level in zip(fields['BattleChar'], fields['CharLevel'], strict=True)]
    report = {
        'evidenceKind': 'ordinary hash-verified static extraction and analyst interpretation; no original execution',
        'apkSha256': APK_SHA256,
        'course': {'tableIndex': 4105, 'row': 2, 'battleId': 1703,
                   'characterIds': fields['BattleChar'], 'configuredLevels': fields['CharLevel'],
                   'cardCount': len(fields['CardPile']), 'perCharacterCards': owner_cards},
        'specialSkillGate': {
            'function': 'common/new_player_course.py:isDisableSpecialSkill',
            'moduleIndex': 5947, 'constantPath': [9], 'sourceLines': [34, 43],
            'comparisonOffset': 120, 'comparison': 'roundNum < enableRound',
            'disableFieldTest': 'is not None (presence), not truthiness',
            'enableRound': 2,
            'derivationProbes': [{'roundNum': n, 'disabled': n < fields['EnableSpecialSkillRound']}
                                 for n in [0, 1, 2, 3]],
            'probeKind': 'Independent scalar derivation; APK function was not executed',
            'limits': ['Removes course gate only; no free ultimate or energy grant is implied.']},
        'consumers': [
            {'moduleIndex': 9176, 'constantPath': [124], 'function': 'canAddSpecialEnergy',
             'callOffset': 133, 'arguments': ['Globals.Battle.BattleID', 'Globals.BattlePlayer.BattleRound'],
             'disabledResult': -1,
             'caveat': "cardInfo['specialSkillponit'] is checked first: non-None >0 returns directly before course gate."},
            {'moduleIndex': 8434, 'constantPath': [71, 231], 'function': 'getPlayerPosForFightCard',
             'callOffset': 144, 'arguments': ['Globals.Battle.BattleID', 'Globals.BattlePlayer.BattleRound'],
             'disabledResult': [None, 0], 'purpose': 'Selected-card special-energy position/preview'},
        ],
        'roundBoundary': {
            'property': {'moduleIndex': 5455, 'constantPath': [7, 29],
                         'semantics': 'BattleRound returns self.curRound'},
            'initialValue': {'moduleIndex': 5455, 'constantPath': [7, 1],
                             'storeOffset': 49, 'value': 0},
            'syncRegistration': {'moduleIndex': 5485, 'constantPath': [13],
                                 'offsetSpan': [741, 765], 'attribute': 'curRound', 'phase': 'onReceive'},
            'receiveConsumer': {'moduleIndex': 2634, 'constantPath': [56, 4],
                                'applyOffset': 221, 'call': 'recoverDeltaOperate(ent,attrName,oprtsList[i])'},
            'conclusion': 'Course check stops disabling after synchronized curRound reaches >=2; RoundBeginAction is presentation, not an increment.',
            'unknown': 'Original server generation/order of curRound sync and RoundBeginAction are not present/verified.'},
        'teamSelectionConsumer': {
            'moduleIndex': 3609, 'constantPath': [24, 9], 'function': '_stateChooseChar',
            'selectionBranchOffsets': [101, 148],
            'semantics': "challenge.MazeIDList[0] -> maze.LoadingBattleID; SkipChooseChar -> {'charIDs': getBattleChar(battleID), 'extraData': {}}",
            'startCallOffset': 507,
            'startCall': 'context.owner.mainlineStartDungeon(activityID,challengeID,charIDs,waveExtraData=...,blessingExtraData=...)'},
        'boundedNegativeFindings': {
            'searchedDecodedModules': search['searchedDecodedModules'],
            'getAvatarCharInitCardPileSymbolModules': [entry['index'] for entry in search['terms']['getAvatarCharInitCardPile']],
            'getBattleCharInitLevelSymbolModules': [entry['index'] for entry in search['terms']['getBattleCharInitLevel']],
            'conclusion': 'Only definitions in 5947 contain these two names. This search does not prove original server/native initialization.'},
        'unresolved': [
            'Original server consumption of configured levels and ordered 14-card pile is not established.',
            'No original Android/NeoX runtime was executed; timing and guide scheduling remain unobserved.',
            'Ultimate availability still requires per-character energy, special-card construction, target and skill rules.',
            'CBattleEntityBase declares onCurRoundChange twice (curRound and cannotTarget); callback-name lookup may hit the later no-op. Preserve this static caveat; runtime refresh behavior is not proved.',
        ],
    }
    write('report.json', report)
    return report


if __name__ == '__main__':
    result = build()
    print(json.dumps({'battleId': result['course']['battleId'],
                      'teamCards': [(r['characterId'], len(r['cards']))
                                    for r in result['course']['perCharacterCards']],
                      'roundGate': result['specialSkillGate']['derivationProbes'],
                      'searchedDecodedModules': result['boundedNegativeFindings']['searchedDecodedModules']},
                     ensure_ascii=False))
