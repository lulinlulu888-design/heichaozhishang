"""Rebuild focused original DrawCard evidence from pinned decoded marshal modules.

Reads the script inventory and hash-checked module bytes, never an earlier draw
report. The instruction walker is static; no APK Python, game or UE is executed.
Timing probes translate the exact inspected arithmetic rather than emulate it.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from extract_texture_samples import APK_SHA256
from inspect_battle_rules import export
from trace_first_encounter import inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/entrance'

# A module pin includes constants, names and line tables, unlike bytecode-only
# hashes (several scalar getters intentionally have identical opcode bytes).
MODULE_SHA256 = {
    6601: 'd73deedc1743db25d656d04347e6c693ba84ece718659bcdb895f03094f8d365',
    5026: 'b8c27c439c7c5960f9c71f87eea09f4cf9a72423d59cf683e9acab8b93668dc9',
    938: '01c26477645f03ac60471077907131ff680dd2c800fde0269a7d5632fc710f75',
    5456: '900d268529f095c560e1b35f25aff342d06ad10280334e8256ebe9e57ae29573',
    3273: 'd1834c443cfd482f9c4e9185bbb8543a1371bec5cc8e7fad526e1ed1738a0673',
    2487: '86e92cbe59e64adce64943bcc5e1be524d39688b47e13abdf367e7768c1ab760',
    6992: '95c3eb5b7bda5036125ac09655fcb107647d64aeb05bfea5cb8379ebf7f037ee',
    2149: '7f7635e66e8f5825f88a22c6b95c890bb3fc7b6c8769e98bc55f86af21f950d9',
    6256: '489e7e6cdcebad7e8f08e21bf6aff1d4daa16d4b7b088e15c0c2c7b8f92eb7a2',
}
METHODS = {
    6601: [((12, 1), 'doInit', 54)],
    5026: [((7, 0), 'getDuration', 26), ((7, 1), '_isRoundStartDraw', 29),
           ((7, 3), 'doInit', 35), ((7, 5), 'play', 55)],
    938: [((89,), 'getFlyTime_Z_H', 285), ((94,), 'getFlyTime_CQ_Z', 300),
          ((101,), 'getDelayTime_Z', 318), ((102,), 'getDelayTime_Z_WithEffect', 321),
          ((104,), 'getScale_Z', 354), ((105,), 'getUnitMargin_Z', 357),
          ((106,), 'getAllRange_Z', 360), ((120,), 'getAction_DrawCardFirstDelay', 403),
          ((121,), 's', 406), ((122,), 'getActionTime_C_H', 410),
          ((125,), 'getActionTime_CQ_Z_H', 422)],
    5456: [((11, 121), 'drawSomeCards', 572)],
    3273: [((19, 15), '_onDrawSomeCards', 331), ((19, 56), 'onLastDispatchMoment', 764),
           ((19, 57), 'onLastDispatchEnd', 767), ((19, 58), '_createCard', 778)],
    2487: [((17,), 'createZShowAction', 116), ((19,), 'calcOffset', 137),
           ((20,), 'getZScale', 150), ((27, 2), 'enter', 218),
           ((27, 6), '_C_H', 324), ((27, 7), '_CQ_Z_H', 376),
           ((27, 8), '_onLastDispatch', 408), ((27, 9), '_onEndZ', 411),
           ((27, 10), '_onDispatchEnd', 414)],
    6992: [((17, 0), 'getZPos', 21), ((17, 2), 'getDrawCardTargetPos', 31),
           ((17, 3), 'getDrawCardBeginPos', 39), ((20, 3), 'getCSBFilePath', 73)],
    2149: [((), '<module>', 6)],
    6256: [((), '<module>', 6)],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def findings():
    return [
        {'id': 'first-marker', 'source': ['6601:12.1 L55', '5026:7.3 L36-45'],
         'value': 'BattleBeginAction.doInit saves global BattleBeginAction=True. First DrawCard '
                  'consumes it via popGlobalData; _firstDelay=0.5, otherwise 0.'},
        {'id': 'route', 'source': ['5026:7.5 L61-64', '5456:11.121 L572-574',
                                   '3273:19.15 L331-345', '2487:27.2 L234-240'],
         'value': 'drawSomeCards(showCardIDs, UNUSED_PILE, not isRoundStartDraw). Round-start '
                  'draw isSpecial=False -> _C_H. Non-round draw isSpecial=True -> _CQ_Z_H. '
                  'First draw has extra 0.5s delay, same round-start flight.'},
        {'id': 'round-flight', 'source': ['2487:27.6 L324-374'], 'value': {
            'start': '(-100-fitWidth/2, zPos.y), scale=1, rotation=0, opacity=255',
            'zPos': '(0, fitHeight/2) in local coords; 6992:17.0 L21-24',
            'stagger': 't1=.05*(N-i-1)+.1',
            'centreFlight': 'EaseSineOut MoveTo((calcOffset(i,N),zPos.y), '
                            'duration t2=.05*(N-i-1)+.04)',
            'centreHold': 't3=.01*N+.8-t1-t2',
            'nominalCommonDropBegins': '.8+.01*N after drawSomeCards',
            'dropRotation': 'EaseSineOut RotateTo(Vec3(-35,0,targetGeo.rot),.15), '
                            'then EaseSineIn RotateTo(Vec3(0,0,targetGeo.rot),.15)',
            'dropPosition': 'EaseQuarticActionIn BezierTo(cp1,cp2,targetPos,.3)',
            'bezierControlPoints': 'D=30; targetGeo.x<0: cp1=flyPos+(-D,.5D), '
                                   'cp2=flyPos+(-2D,0); else cp1=flyPos+(D,.5D), '
                                   'cp2=flyPos+(2D,0)',
            'completion': 'Nominal 1.1+.01*N after draw call; DesignConst.s()=1. '
                          'Negative t3 for N>=9 lower indices needs engine semantics verification.',
        }},
        {'id': 'centre-layout', 'source': ['2487:19 L137-148', '938:105 L357-358',
                                           '938:106 L360-361'],
         'value': 'N=1 offset=0. Otherwise cW=CardGeometryArranger.cardWidth; uW=cW+45; '
                  'allW=uW*(N-1)+cW. Clamp allW to 1120 and recompute uW=(1120-cW)/(N-1). '
                  'offset=-allW/2+i*uW+.5*cW.'},
        {'id': 'final-layout', 'source': ['6992:17.2 L31-37'],
         'value': 'getDrawCardTargetPos(True) calls '
                  'CardGeometryArranger.getOneCardNormalStateArrange(cardTypeList,card._index), '
                  'returning position and rotation.'},
        {'id': 'reserved-duration', 'source': ['5026:7.3 L45-49', '938:122 L410-411',
                                               '938:125 L422-423'],
         'value': 'For N>0, round-start action reserved=(2+.01*N)+firstDelay; .9s longer '
                  'than nominal _C_H chain. Do not stretch flight to reserved duration. '
                  'Non-round default=.3+.4+.1+.1=.9s + firstDelay. Empty-card branches return 0.'},
        {'id': 'non-round-draw', 'source': ['2487:27.7 L376-406', '2487:17 L116-118',
                                           '938:89 L285-286', '938:94 L300-301',
                                           '938:101 L318-319', '938:104 L354-355'],
         'value': '_CQ_Z_H from UsableCards pile node (6992:17.3 L39-45), scale .2 opacity 0. '
                  'First .3s EaseSineOut JumpTo(zPos+(offset,0),height100,jumps1) + '
                  'EaseSineOut FadeTo255 + ScaleTo1; default middle hold .4; then .1s '
                  'EaseSineOut MoveTo(handPos)+ScaleTo1. Core visual .8s; special effect replaces hold.'},
        {'id': 'csb', 'source': ['6992:20.3 L73-75', '2149:<module> L13',
                                 '6256:<module> L13', '2487:27.6 L359-374'],
         'value': 'Card=uires/AllCards/InFightCards/FightSmallCard_ext.csb, '
                  'parent=uires/FightPanel/OwnCardArea_ext.csb. Flight is constructed in Python '
                  'cc.Sequence/Spawn/MoveTo/BezierTo, with no separate flight CSB in the inspected '
                  '_C_H chain. A similarly named effect file is not evidence of this route.'},
        {'id': 'input-audio', 'source': ['2487:27.6 L331-332', '2487:27.10 L414-427',
                                         '3273:19.57 L767-776', '2487:27.2 L239'],
         'value': 'Round draw plays UI_DRAWCARD(True). During flight dispatch waiting=true. '
                  'Last-index completion calls onLastDispatchEnd, plays UI_FAPAI_B(False), '
                  'clears waiting, switches hand cards to STAGE_WAIT except STAGE_RELEASE_USE, '
                  'then rearranges. _onLastDispatch calls a base no-op at common drop start (3273 L764).'},
    ]


def verify_source(lookup):
    def ops(module, path):
        return lookup[module, path]['instructions']

    def scalar(path, expected):
        code = ops(938, path)
        require([x['opname'] for x in code] == ['LOAD_CONST', 'RETURN_VALUE'],
                'Scalar getter shape changed: ' + str(path))
        require(type(code[0]['operand']) is type(expected) and code[0]['operand'] == expected,
                'Scalar getter value changed: ' + str(path))
        return code[0]['operand']

    def constants(module, path, line=None):
        return [x['operand'] for x in ops(module, path) if x['opname'] == 'LOAD_CONST'
                and (line is None or x['source_line'] == line)]

    def contains(module, path, expected):
        actual = [x.get('operand') for x in ops(module, path)]
        require(all(value in actual for value in expected),
                'Expected draw operands changed: ' + str((module, path, expected)))

    scalar((120,), .5)
    scalar((121,), 1)
    scalar((104,), 1)
    scalar((105,), 45)
    scalar((106,), 1120)
    for path, value in [((89,), .1), ((94,), .3), ((101,), .4)]:
        require([x['opname'] for x in ops(938, path)] ==
                ['LOAD_CONST', 'LOAD_GLOBAL', 'CALL_FUNCTION', 'BINARY_MULTIPLY', 'RETURN_VALUE'],
                'Scaled time getter shape changed')
        require(constants(938, path) == [value], 'Scaled time constant changed')
        contains(938, path, ['s'])
    require(constants(938, (122,)) == [.01, 2], 'Reserved round duration changed')
    require(constants(938, (125,)) == [.1], 'Reserved extra draw duration changed')
    for line, expected in [(328, [-100, 0, 2]), (343, [.05, 1, .1]),
                           (344, [.05, 1, .04]), (345, [.01, .8]),
                           (346, [1]), (347, [.15]), (348, [.15]),
                           (351, [30]), (366, [-35, 0]), (367, [0, 0])]:
        require(constants(2487, (27, 6), line) == expected,
                'Flight constants changed at source line ' + str(line))
    contains(6601, (12, 1), ['saveGlobalData', 'BattleBeginAction', 'True'])
    contains(5026, (7, 3), ['popGlobalData', 'BattleBeginAction', 'getAction_DrawCardFirstDelay',
                           'getActionTime_C_H', 'getActionTime_CQ_Z_H'])
    contains(5026, (7, 5), ['delayExecute', '_firstDelay', 'drawSomeCards', '_isRoundStartDraw'])
    contains(3273, (19, 15), ['STAGE_DISPATCH', 'arrangeInfo', 'isSpecial', 'fromPileType'])
    contains(2487, (27, 2), ['UNUSED_PILE', '_isSpecial', '_C_H', '_CQ_Z_H', 'UI_DRAWCARD'])
    contains(2487, (27, 6), ['EaseSineOut', 'EaseSineIn', 'EaseQuarticActionIn', 'BezierTo',
                            'MoveTo', 'RotateTo', '_onLastDispatch', '_onDispatchEnd'])
    contains(3273, (19, 57), ['UI_FAPAI_B', 'STAGE_WAIT', 'STAGE_RELEASE_USE'])
    contains(2149, (), ['uires/AllCards/InFightCards/FightSmallCard_ext.csb'])
    contains(6256, (), ['uires/FightPanel/OwnCardArea_ext.csb'])


def timing_samples():
    samples = []
    for count in (1, 5, 10):
        cards = []
        for index in range(count):
            t1 = .05 * (count - index - 1) + .1
            t2 = .05 * (count - index - 1) + .04
            t3 = .01 * count + .8 - t1 - t2
            require(math.isclose(t1 + t2 + t3 + .3, 1.1 + .01 * count, abs_tol=1e-12),
                    'Draw timing arithmetic mismatch')
            require(math.isclose((2 + .01 * count) - (t1 + t2 + t3 + .3), .9, abs_tol=1e-12),
                    'Reserved duration difference changed')
            cards.append({'index': index, 'delay': t1, 'moveToCentre': t2, 'centreHold': t3,
                          'negativeHoldNeedsEngineVerification': t3 < 0, 'dropDuration': .3})
        require(all(c['centreHold'] >= 0 for c in cards) if count < 9 else
                any(c['centreHold'] < 0 for c in cards), 'Negative-delay boundary changed')
        samples.append({'cardCount': count, 'cardTimings': cards,
                        'nominalFlyCompleteAfterDrawCall': 1.1 + .01 * count,
                        'nominalFirstFlyCompleteAfterActionPlay': 1.6 + .01 * count,
                        'normalActionReservedDuration': 2 + .01 * count,
                        'firstActionReservedDuration': 2.5 + .01 * count})
    return samples


def recover(output_directory=OUT):
    """Write draw-evidence.json and return it; no prior report is read."""
    out = Path(output_directory).resolve()
    require(out.is_relative_to((ROOT / 'analysis').resolve()), 'Output must stay under analysis')
    rows = inventory()
    modules, lookup = [], {}
    for index, selected in METHODS.items():
        row = rows[index]
        require(row['decoded_sha256'] == MODULE_SHA256[index],
                'Pinned draw source module changed: ' + str(index))
        # export -> read_module checks the complete actual bytes against this pin,
        # validates the marshal root, and verifies its source filename.
        result = export(row)
        requested = {path: (name, line) for path, name, line in selected}
        result['code_objects'] = [o for o in result['code_objects']
                                  if tuple(o['constant_path']) in requested]
        require(len(result['code_objects']) == len(requested), 'Missing focused draw methods')
        for obj in result['code_objects']:
            path = tuple(obj['constant_path'])
            require((obj['name'], obj['firstlineno']) == requested[path],
                    'Draw method identity changed: ' + str((index, path)))
            lookup[index, path] = obj
        modules.append(result)
    verify_source(lookup)
    report = {
        'evidenceKind': 'hash-verified decoded APK Python2 marshal, static analysis only; no target execution',
        'apkSha256': APK_SHA256,
        'scope': 'Round-start DrawCard and battle-first delay',
        'findings': findings(),
        'numericValidation': {'sourceScalarAssertions': 'passed', 'sourceRouteAssertions': 'passed',
                              'sampleTimingAlgebra': 'passed', 'samples': timing_samples()},
        'limitations': ['No live playback; partial opcode map is not native execution evidence.',
                        'Viewport transforms/fit size still apply to all coordinates.',
                        'Negative DelayTime for N>=9 lower indices requires native scheduler verification; '
                        'do not silently claim clamping.',
                        'CSB names from source auto-bindings, resource bytes not parsed here.'],
        'modules': modules,
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'draw-evidence.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')
    return report


def main():
    report = recover()
    path = OUT / 'draw-evidence.json'
    print(json.dumps({'output': str(path), 'modules': len(report['modules']),
                      'methods': sum(len(m['code_objects']) for m in report['modules']),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'validation': 'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
