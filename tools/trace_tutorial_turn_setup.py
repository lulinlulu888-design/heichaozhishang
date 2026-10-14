"""Hash-locked static turn setup trace. Never import/execute APK code.

Only the existing bounded Marshal2 reader, partial instruction decoder and
literal action-map recognizer are used. All code-object offsets are relative
to the code object identified by constant_path, not absolute APK offsets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static
from extract_npk import jsonable
from trace_card_action import action_map

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/tutorial-turn-setup'
GUARDS = {
    126: '71092ebe4b2d26900265458b9c7f6e2b078a50ae017112cc6dfb114a4197b9b0',
    1317: 'f90cbbf489ecd3d9626a527fe6d4bd9869f0465410c59da8d4e2c5d9934266f1',
    1975: '9d2e402faf32db3600f23e02256f9a7d7a79387f92dc862bd247e5df620ccd4a',
    2634: '70a73152b2134ab85d51d701b6d36ce62e942cbf1dd9711ac968c93852af9ac7',
    2697: '6b3931b986758dfef8dbce9d84b7c9bf7b451ceb567d5a3eaab7748785d5779c',
    4153: '729277c7b95b7df13aedf87ddda4922aa3255a5dd7d77a96f706534ab8474937',
    4453: 'b36d09e2b15537edd39e025faeee5114048fce2431c5ea8a6a9e761403df6dd9',
    4793: 'b42baa7fb9728719df9b2487644219e84316a423ee5adc094c33e51f3a73c094',
    4942: 'e2911c234556cc11d601bbe566bad7da58253e91171b05ef6e1930ff2dea07c1',
    5026: 'b8c27c439c7c5960f9c71f87eea09f4cf9a72423d59cf683e9acab8b93668dc9',
    5455: '50900f11c2a737b582c90fe9e7b37577782d62e4a3c366fadc275fb417b3b61e',
    5456: '900d268529f095c560e1b35f25aff342d06ad10280334e8256ebe9e57ae29573',
    5947: '0664b730cec442bedcfc2ef3eb334a10e0f2d45cfb7ada49ae13b1aaa14d452f',
    6198: 'a7030162e6d8b39ac2b90a56bba52b0259f1912d66cd956d9432d4e1ee745252',
    6221: 'e09e9130987752b7bd2f875e86b620cb6af290cf4fd291be1bd4b932031f2b9f',
    6597: '5ac63d2ddc4cf8bd6a013db7d8eb8b531b6564dcb3e665d6bafa1318ece8f475',
    6601: 'd73deedc1743db25d656d04347e6c693ba84ece718659bcdb895f03094f8d365',
    7693: '3fd1651026d81ce7add3654d16a78322249c7bad3f38fd148413d3a1f2e71317',
    8434: '046777e2e09065e75d1c51685aa7ba9a68a4968cdddc6f1cb56c2d04e3cbdb4d',
    9555: '144ba0a0dfc93cb2facf398ce2fd8d83f74d4d92a49acc14173356f6a6e3fbe3',
}
# Explicit analyst-reviewed scope. No broad battle-formula/provider rescan.
SELECTED = {
    126: {(3, 0): '__init__'},
    1317: {(6, 2): 'onReceive', (6, 3): 'play'},
    1975: {(9, 5): 'updateAllProperties'},
    2634: {(22, 1): 'onReceive', (22, 2): 'play'},
    2697: {(12, 12): 'onBattleInit', (12, 51): 'addRawActionGroup', (12, 69): 'addFirstAction'},
    4153: {(15, 0): '__init__', (15, 1): '_initBattle', (15, 3): 'energy',
           (15, 5): 'onUpdateAllProperties', (15, 6): 'updateAllPreCalcPropertiesAfterAction',
           (15, 7): 'updateAllPropertiesAfterAction', (15, 13): 'onUpdateEnergy',
           (15, 14): 'onBeginRound', (15, 16): 'onPushActions', (15, 17): 'playPushActions'},
    4453: {(5, 10): 'init_from_dict', (5, 20): 'moveCards'},
    4793: {(9, 2): 'initEventHandlers', (9, 3): '_initInfo', (9, 4): '_onBattleStart',
           (9, 6): '_onEnergyRealChanged', (9, 7): '_refreshShowFei',
           (9, 11): '_onEnergyRealChangedPlay', (9, 12): '_changeProgressWhenInSelfRound',
           (9, 14): '_resetEnergyWhenRoundBegin'},
    4942: {(8, 2): 'onInitedFromDict', (8, 47): 'dataMoveCards', (8, 48): 'viewMoveCards',
           (8, 66): 'dataGetCardInfosByUUIDS'},
    5026: {(7, 1): '_isRoundStartDraw', (7, 3): 'doInit', (7, 4): 'onReceive', (7, 5): 'play'},
    5455: {(7, 2): 'onInitedFromDict', (7, 13): 'endRound'},
    5456: {(11, 164): 'refreshEnergy', (11, 165): 'refreshEnergyPlay', (11, 166): 'resetEnergyWhenRoundBegin'},
    5947: {(3,): 'isNewPlayerCourse', (4,): 'startNewPlayerCourse', (7,): 'getAvatarCharInitCardPile'},
    6198: {(4, 139): 'createAction'},
    6221: {},
    6597: {(25, 1): '__init__', (25, 2): 'init_from_dict'},
    6601: {(12, 1): 'doInit', (12, 2): 'onReceive', (12, 3): 'play',
           (22, 3): 'onReceive', (22, 4): 'play'},
    7693: {(55, 2): 'Start', (63, 7): 'Start', (512, 2): 'handleSet',
           (516, 2): 'handleSet', (516, 3): 'handleAdd', (516, 4): 'handleDel', (544, 2): 'Start'},
    8434: {(71, 13): 'getEndBtnStateInfo'},
    9555: {(9,): 'getEndBtnStateInfo'},
}
CONSTANTS = {'DefaultBattleEnergy': 5, 'DRAW_CARD_NUM_PER_ROUND': 6,
             'MAX_DRAW_CARD_NUM_WHEN_ROUND_START': 10, 'MAX_HAND_PILE_NUM': 10,
             'DEC_DRAW_CARD_NUM_PER_ROUND_LOST_CHAR': 1}
PROVIDER_TERMS = {'drawCardsFromDrawPile', 'setEveryRoundDrawNum', 'addEveryRoundDrawNum',
                  'subEveryRoundDrawNum', 'extraDrawCardNum', 'addMaxEnergy', 'decMaxEnergy'}


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    inventory = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    rows = {r['index']: r for r in inventory}
    modules = {}
    for index, digest in GUARDS.items():
        if rows[index]['decoded_sha256'] != digest:
            raise ValueError(f'Unreviewed marshal revision: {index}')
        modules[index] = static.read_module(rows[index])
    sources, by_key = [], {}
    for index, selection in SELECTED.items():
        codes = dict(static.walk_codes(modules[index]))
        for path, expected_name in selection.items():
            code = codes[path]
            if code['name'].decode('utf8') != expected_name:
                raise ValueError(f'Unexpected code identity: {index}:{path}')
            record = {'module_index': index, 'filename': rows[index]['filename'],
                      'marshal_sha256': GUARDS[index], 'npk_payload_offset': rows[index]['offset'],
                      'constant_path': list(path), 'function': expected_name,
                      'bytecode_sha256': hashlib.sha256(code['bytecode']).hexdigest(),
                      'bytecode_size': len(code['bytecode']), 'first_source_line': code['firstlineno'],
                      'argcount': code['argcount'], 'varnames': jsonable(code['varnames']),
                      'freevars': jsonable(code['freevars']), 'cellvars': jsonable(code['cellvars']),
                      'instructions': list(static.instructions(code))}
            sources.append(record)
            by_key[(index, path)] = record

    def anchor(index, path, start, end, expected_operand):
        record = by_key[(index, tuple(path))]
        ins = [v for v in record['instructions'] if start <= v['offset'] < end]
        if not ins or ins[0]['offset'] != start or ins[-1]['end_exclusive'] != end:
            raise ValueError('Finding range does not align with instruction boundaries')
        if expected_operand not in [v.get('operand') for v in ins]:
            raise ValueError(f'Finding operand missing: {expected_operand}')
        return {'module_index': index, 'constant_path': list(path),
                'offset_start': start, 'offset_end_exclusive': end,
                'expected_operand': expected_operand}

    findings = [
        {'id': 'tutorial-entry', 'kind': 'observed-static-call',
         'meaning': 'startNewPlayerCourse forwards the pre-first-enter configuration to athlete.doEnterChallenge; no local energy/draw formula is present in this function.',
         'anchors': [anchor(5947, [4], 0, 0x2e, 'doEnterChallenge')]},
        {'id': 'initial-team-properties', 'kind': 'observed-static-data-flow',
         'meaning': 'PlayerAvatar.init_from_dict passes bDict.battleInfo to _initBattle. Battle.onBattleInit passes team1 to AvatarTeam; AvatarTeam copies every key to itself AND Globals.BattlePlayer. Thus team1.fei/maxFei are accepted initial fields, without a client default value here.',
         'anchors': [anchor(6597, [25, 2], 0x37, 0x50, 'battleInfo'),
                     anchor(4153, [15, 1], 0x15, 0x34, 'onBattleInit'),
                     anchor(2697, [12, 12], 0x23, 0x3e, 'team1'),
                     anchor(126, [3, 0], 0, 0x40, 'BattlePlayer')]},
        {'id': 'initial-property-overlays', 'kind': 'observed-static-data-flow',
         'meaning': 'onInitedFromDict merges top-level clientCopyInfo, then team1.clientCopyInfo, then battleInfo.clientCopyInfo and setattr-applies the merged keys. team2.fei/maxFei are read separately with -1 fallback. Payload contents and their tutorial values remain unknown.',
         'anchors': [anchor(5455, [7, 2], 0x26, 0xdd, 'clientCopyInfo'),
                     anchor(5455, [7, 2], 0xdd, 0x137, 'maxFei')]},
        {'id': 'energy-final-values', 'kind': 'observed-static-action-consumer',
         'meaning': 'EnergyChange onReceive reads Args.curEnergy/curMaxEnergy and optional _isEnemy=False, then calls onUpdateEnergy. That method assigns the supplied values to fei/maxFei or enemyFei/enemyMaxFei. energy property returns fei. play forwards the same values to refreshEnergyPlay.',
         'anchors': [anchor(2634, [22, 1], 0x9, 0x3c, 'curEnergy'),
                     anchor(2634, [22, 2], 0x9, 0x3f, 'refreshEnergyPlay'),
                     anchor(4153, [15, 13], 0, 0x2d, 'maxFei'),
                     anchor(4153, [15, 3], 0, 7, 'fei')]},
        {'id': 'round-reset-is-ui', 'kind': 'observed-static-ui-flow',
         'meaning': 'RoundBegin.play invokes a UI notification. The EnergyArea handler reads getEndBtnStateInfo; its maximum comes from BattlePlayer.maxFei/enemyMaxFei. It sets UI progress to MaxFei, not authoritative player.fei. No default 5 is fetched along this path.',
         'anchors': [anchor(6601, [22, 4], 0x23, 0x33, 'resetEnergyWhenRoundBegin'),
                     anchor(5456, [11, 166], 0, 0xd, 'resetEnergyWhenRoundBegin'),
                     anchor(4793, [9, 14], 0, 0x3d, 'MaxFei'),
                     anchor(8434, [71, 13], 0, 0xd, 'getEndBtnStateInfo'),
                     anchor(9555, [9], 0x61, 0x8f, 'maxFei'),
                     anchor(4793, [9, 12], 0, 0x12, '_realCurFei')]},
        {'id': 'draw-is-explicit-instance-selection', 'kind': 'observed-static-action-consumer',
         'meaning': 'DrawCard.doInit resolves Args.uuids through syncCardInfos (unknown IDs omitted), defaults cacheRoundStartCardUUIDs to uuids if absent, and reads isRoundStartDraw to choose presentation timing. onReceive moves the resolved instances from UNUSED_PILE to HAND_CARD_PILE in the data manager; play makes the corresponding view move. No number 6, deck-top selection, or RNG is computed here.',
         'anchors': [anchor(5026, [7, 1], 0, 0xb, 'isRoundStartDraw'),
                     anchor(5026, [7, 3], 0x40, 0x82, 'uuids'),
                     anchor(4942, [8, 66], 0, 0x4d, 'syncCardInfos'),
                     anchor(5026, [7, 4], 0, 0x42, 'dataMoveCards'),
                     anchor(5026, [7, 5], 0, 0x42, 'viewMoveCards'),
                     anchor(4453, [5, 20], 0x3d, 0x95, 'append')]},
        {'id': 'first-draw-presentation-marker', 'kind': 'observed-static-ui-flow',
         'meaning': 'BattleBegin.doInit saves a UI flag; the next DrawCard.doInit consumes it to set _isBattleStartDraw and presentation delay. This is not a separate first-turn draw-count algorithm.',
         'anchors': [anchor(6601, [12, 1], 0, 0x13, 'BattleBeginAction'),
                     anchor(5026, [7, 3], 0, 0x40, '_isBattleStartDraw')]},
        {'id': 'round-count-modifier-boundary', 'kind': 'observed-static-external-call',
         'meaning': 'ModifyExtraRoundStartDrawCardNum delegates self.num to context.ownerTeam.setEveryRoundDrawNum/addEveryRoundDrawNum/subEveryRoundDrawNum. ModifyExtraDrawCardNum.handleSet assigns ownerTeam.extraDrawCardNum. Their relationship to default 6, living-character reduction and tutorial activation is not supplied by these consumers.',
         'anchors': [anchor(7693, [516, 2], 0, 0x13, 'setEveryRoundDrawNum'),
                     anchor(7693, [516, 3], 0, 0x13, 'addEveryRoundDrawNum'),
                     anchor(7693, [516, 4], 0, 0x13, 'subEveryRoundDrawNum'),
                     anchor(7693, [512, 2], 0, 0xf, 'extraDrawCardNum')]},
        {'id': 'energy-modifier-boundary', 'kind': 'observed-static-external-call',
         'meaning': 'ChangeEnergy delegates delta to ownerTeam.changeEnergy. ModifyMaxEnergy delegates positive num to addMaxEnergy and negative num negated to decMaxEnergy. These nodes do not supply an initial or per-round energy amount.',
         'anchors': [anchor(7693, [55, 2], 0, 0x13, 'changeEnergy'),
                     anchor(7693, [544, 2], 0, 0x4f, 'addMaxEnergy')]},
    ]
    declarations = []
    ops = list(static.instructions(modules[6221]))
    for before, after in zip(ops, ops[1:]):
        name = after.get('operand')
        if after['opname'] == 'STORE_NAME' and isinstance(name, str) and name in CONSTANTS:
            if before['opname'] != 'LOAD_CONST' or before.get('operand') != CONSTANTS[name]:
                raise ValueError(f'Unreviewed constant declaration: {name}')
            declarations.append({'module_index': 6221, 'constant_path': [], 'name': name,
                                 'value': before['operand'], 'offset_start': before['offset'],
                                 'offset_end_exclusive': after['end_exclusive']})
    if len(declarations) != len(CONSTANTS):
        raise ValueError('Missing/repeated constant')
    selected_constant_reads = [
        {'module_index': r['module_index'], 'constant_path': r['constant_path'], 'instruction': ins}
        for r in sources for ins in r['instructions']
        if isinstance(ins.get('operand'), str) and ins['operand'] in CONSTANTS
    ]
    symbols = [json.loads(line) for line in (static.SCRIPT / 'symbols.jsonl').read_text('utf8').splitlines()]
    if len(symbols) != len(inventory):
        raise ValueError('Symbol inventory does not match module inventory size')
    provider_hits = []
    for row in symbols:
        hits = PROVIDER_TERMS.intersection(row['names'] + row['strings'] + row['functions'])
        if hits:
            provider_hits.append({'module_index': row['index'], 'filename': row['filename'],
                                  'terms': sorted(hits),
                                  'same_named_code_objects': sorted(PROVIDER_TERMS.intersection(row['functions']))})
    mappings = action_map(dict(static.walk_codes(modules[6198]))[(4,)])
    mappings['entries'] = [e for e in mappings['entries'] if e['name'] in {'BattleBegin', 'RoundBegin', 'EnergyChange', 'DrawCard'}]
    mappings['selected_entry_count'] = len(mappings['entries'])
    input_paths = ['analysis/assets/decoded/script/index.json', 'analysis/assets/decoded/script/symbols.jsonl',
                   'analysis/first-encounter/encounter.json', 'analysis/first-encounter/new-player-course.table.json',
                   'analysis/battle-foundation/rules-evidence.json', 'analysis/card-action/client-presentation-contract.json',
                   'tools/extract_npk.py', 'tools/inspect_script_static.py', 'tools/inspect_battle_rules.py',
                   'tools/trace_card_action.py', 'tools/trace_tutorial_turn_setup.py']
    fingerprints = [{'path': p, 'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in input_paths]
    result = {
        'format': 'hczs-tutorial-turn-setup-evidence-v1',
        'apk_sha256': 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4',
        'reused_archive_evidence_id': 'ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220',
        'authority': 'Local hash-verified static analysis, not new REA evidence or runtime/server observation.',
        'findings': findings,
        'declarations_only': declarations,
        'selected_function_default_constant_references': selected_constant_reads,
        'new_provider_query': {'scope': f'{len(symbols)} decoded module symbol summaries; exact seven newly traced ownerTeam members only',
                               'terms': sorted(PROVIDER_TERMS), 'hits': provider_hits,
                               'limitation': 'No same-named code object does not exclude dynamic/native/remote providers. No game/native code executed.'},
        'policy_status': {'initial_energy_5': 'still explicit reconstruction policy',
                          'round_energy_5': 'still explicit reconstruction policy',
                          'initial_draw_6': 'still explicit reconstruction policy',
                          'round_draw_6': 'still explicit reconstruction policy'},
        'proven_interface_reduction': [
            'Initial team1 fields reach BattlePlayer through AvatarTeam.__init__, with later clientCopyInfo overlays.',
            'Current/max energy are server-supplied action values consumed in a separate receive/play flow.',
            'Draw effects use supplied card instance lists; isRoundStartDraw is a presentation flag, not a count.',
            'External ownerTeam modifier methods are precise next provider anchors.'
        ],
        'unknowns': ['No actual tutorial initialization/action payload or replay is available.',
                     'No producer of initial fei/maxFei or default per-round draw count has been established.',
                     'No ownerTeam round-start scheduler, draw RNG, ordering direction, or modifier composition recovered.',
                     'No proof the seven-card course pile is consumed top-first or that six are initially dealt.',
                     'Original tutorial trigger remains unverified; isNewPlayerCourse is a False-returning stub.',
                     'Partial opcode mapping remains explicit; unknown instructions are never executed or assigned guessed semantics.'],
    }
    # All parsing, identity and anchor validation completes before evidence writes.
    OUT.mkdir(parents=True, exist_ok=True)
    dump('turn-setup.json', result)
    dump('function-sources.json', sources)
    dump('module-sources.json', [{'apk_member': 'assets/script.npk', **rows[i]} for i in GUARDS])
    dump('input-fingerprints.json', fingerprints)
    dump('action-map-slice.json', mappings)
    lines = []
    for r in sources:
        lines += [f"\n### {r['module_index']}:{'.'.join(map(str, r['constant_path']))} {r['function']}",
                  f"module={r['filename']} marshal_sha256={r['marshal_sha256']}",
                  f"npk_payload_offset={r['npk_payload_offset']} bytecode_sha256={r['bytecode_sha256']}",
                  f"varnames={r['varnames']!r} freevars={r['freevars']!r} cellvars={r['cellvars']!r}"]
        for ins in r['instructions']:
            lines.append(f"{ins['offset']:05x} {ins['opcode']:02x} {ins['opname']:24} {str(ins['argument']):6} {ins.get('operand', '')!r}")
    (OUT / 'functions.partial-dis.txt').write_text('\n'.join(lines) + '\n', encoding='utf8')
    print(json.dumps({'modules': len(GUARDS), 'functions': len(sources), 'findings': len(findings),
                      'validated_anchors': sum(len(f['anchors']) for f in findings),
                      'default_constant_references_in_selected_functions': len(selected_constant_reads),
                      'provider_reference_modules': len(provider_hits), 'output': OUT.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    main()
