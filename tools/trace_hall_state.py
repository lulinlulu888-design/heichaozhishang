"""Export focused hall data consumers without executing original scripts."""
import json
from pathlib import Path
from inspect_battle_rules import export
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]


def widget_bindings(modules):
    """Recognize only the observed direct findNodeByPath/STORE_ATTR sequence."""
    result = []
    pattern = ['LOAD_ATTR', 'LOAD_CONST', 'CALL_FUNCTION', 'LOAD_FAST', 'STORE_ATTR']
    for module in modules:
        for code in module['code_objects']:
            if code['name'] != '_initAutoWidgets':
                continue
            instructions = code['instructions']
            for index in range(len(instructions) - 4):
                seq = instructions[index:index + 5]
                if seq[0].get('operand') != 'findNodeByPath':
                    continue
                if [i['opname'] for i in seq] != pattern:
                    raise ValueError('Unrecognized widget binding sequence')
                result.append(dict(module=module['source']['index'],
                    constant_path=code['constant_path'],
                    bytecode_sha256=code['bytecode_sha256'],
                    offset=seq[0]['offset'], path=seq[1]['operand'], widget=seq[4]['operand']))
    return result


def main():
    rows = json.loads((ROOT/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    row = next(r for r in rows if r['index'] == 5795)
    if row['filename'] != 'ui\\ui_hall\\HallNewPanel.py':
        raise ValueError('Hall module identity changed')
    evidence = export(row, ('updatePlayerInfo', 'init588Btn', 'initBackFlowBtn',
                            'init1212Btn', 'initActivityBtn', 'initSpringFirstPayBtn'))
    expected = {'updatePlayerInfo', 'init588Btn', 'initBackFlowBtn', 'init1212Btn',
                'initActivityBtn', 'initSpringFirstPayBtn'}
    if {c['name'] for c in evidence['code_objects']} != expected:
        raise ValueError('Expected hall consumers missing')
    observations = [
        dict(function='updatePlayerInfo', constant_path=[70, 11],
             fact='getMasterInfo supplies level/exp/maxExp/name; level uses PLAYER_LEVEL localization, bar uses exp*100/maxExp; name has a visibility branch.'),
        dict(function='initBackFlowBtn', constant_path=[68, 11],
             fact='_cbtnBackFlow visibility consumes getInBackFlowActivity.'),
        dict(function='init588Btn', constant_path=[68, 10],
             fact='_cOpen588 visibility consumes getIsStartScoreActivityEnableNew(GetCard288), with visibleIndex=1.'),
        dict(function='init1212Btn', constant_path=[68, 12],
             fact='Reads getDoubleTwelveOpen/getWhiteFutureOpen/getBlackFutureOpen; boolean jump opcodes remain unidentified, so exact combination is not asserted.'),
    ]
    for observation in observations:
        match = [c for c in evidence['code_objects'] if c['name'] == observation['function']
                 and c['constant_path'] == observation['constant_path']]
        if len(match) != 1:
            raise ValueError('Consumer constant path changed')
        observation['bytecode_sha256'] = match[0]['bytecode_sha256']
    out = ROOT/'analysis/hall/state'
    out.mkdir(parents=True, exist_ok=True)
    # Preserve the distinct preview, confirmation and exit handlers. This is
    # static call-site evidence, not proof of original server persistence/RPCs.
    hero_selection = export(row, ('_onCharListChooseChar', '_onCharListChooseClicked',
                                 '_onCharListQuitClicked', 'onChangeChar', 'onCloseChangeChar'))
    (out/'hero-selection.json').write_text(json.dumps(hero_selection,ensure_ascii=False,indent=2),'utf8')
    (out/'consumers.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), 'utf8')
    bindings = [export(next(r for r in rows if r['index']==index),
                       ('_initAutoWidgets', '_initAutoControls')) for index in (4567, 8233)]
    (out/'auto-bindings.json').write_text(json.dumps(bindings, ensure_ascii=False, indent=2), 'utf8')
    direct_bindings = widget_bindings(bindings)
    required = {'_wPlayerName': 'Panel_Top.Panel_VX.PlayerName',
                '_wTextNum': 'Panel_Top.Panel_VX.LvBg.TextNum',
                '_wBar': 'Panel_Top.Panel_VX.BarBg.Bar'}
    for widget, path in required.items():
        matches = [b for b in direct_bindings if b['module'] == 4567 and b['widget'] == widget]
        if len(matches) != 1 or matches[0]['path'] != path:
            raise ValueError('Player head widget binding changed: ' + widget)
    (out/'widget-paths.json').write_text(json.dumps(direct_bindings, ensure_ascii=False, indent=2), 'utf8')
    # Keep unresolved boolean instructions explicit, rather than evaluating them.
    activity = next(c for c in evidence['code_objects'] if c['name'] == 'initActivityBtn')
    spring = next(c for c in evidence['code_objects'] if c['name'] == 'initSpringFirstPayBtn')
    (out/'activity-consumers.json').write_text(json.dumps(dict(
        evidence_kind='Ordinary-tool static bytecode evidence; not runtime or REA Evidence',
        activity=dict(function=activity['name'], bytecode_sha256=activity['bytecode_sha256'],
            fact='_cOpenHuoDong.setVisible consumes getDataSource().isHuoDongBtnEnabled(), visibleIndex=1'),
        spring_first_pay=dict(function=spring['name'], bytecode_sha256=spring['bytecode_sha256'],
            inputs=['getFirstPayDataCheck(FirstChargeFestivalType.SpringCharge)', 'switches.ENABLE_FIRST_PAY_1'],
            unresolved=[i for i in spring['instructions'] if i['opname'] == 'UNKNOWN'],
            limitation='Boolean combination not inferred; original activity state unavailable')),
        ensure_ascii=False, indent=2), 'utf8')
    producer = export(next(r for r in rows if r['index']==3058), ('getMasterInfo',))
    if len(producer['code_objects']) != 1 or producer['code_objects'][0]['constant_path'] != [30]:
        raise ValueError('Master-info producer identity changed')
    levels = export_table(3554)
    (out/'master-info-producer.json').write_text(json.dumps(producer, ensure_ascii=False, indent=2), 'utf8')
    (out/'player-levels.json').write_text(json.dumps(levels, ensure_ascii=False, indent=2), 'utf8')
    (out/'observations.json').write_text(json.dumps(dict(observations=observations,
        evidence_kind='Hash-verified local static marshal/partial opcode analysis; not REA runtime evidence',
        limits=['Master-info producer traced in module3058; original player initialization/experience awards still unverified',
                'Auto widget/control bytecode retained separately for binding analysis',
                'No original account state, network response or event visibility fabricated',
                'Unknown opcodes are retained; no exact boolean predicate inferred from names']),
        ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(consumers=len(evidence['code_objects']), observations=len(observations))))


if __name__ == '__main__':
    main()
