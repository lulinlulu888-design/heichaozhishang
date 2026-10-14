"""Export hash-verified node boundaries for buff 66051; execute no APK code."""
import json
import math
from pathlib import Path

from inspect_battle_rules import export, literal_story_graph, read_module
from trace_first_encounter import inventory, literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/city-scenes/breakdown-buff'
PREFIXES = {
    3681: [(19,)],  # BaseCharacterListenerNode
    3921: [(15,), (79,)],  # round-end and HP-recovery listeners
    2905: [(147,)],  # GetRpgProps
    4956: [(10,), (13,), (21,)],  # source, damage, buff-change nodes
    8895: [(11,)],  # GetPlayingBuffInfo
    1259: [(14,)],  # TargetAddBuff, including closure
    7554: [(5, 13), (5, 14)],  # property providers
    5485: [(13, 60)],  # client buff-times view
}


def main():
    rows = inventory()
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    for index, prefixes in PREFIXES.items():
        result = export(rows[index])
        result['code_objects'] = [c for c in result['code_objects'] if any(
            tuple(c['constant_path'][:len(p)]) == p for p in prefixes)]
        if not result['code_objects']:
            raise ValueError(f'No selected nodes in {index}')
        path = OUT / f'{index}.code.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
        sources.append({'index': index, 'file': path.name,
                        'decoded_sha256': rows[index]['decoded_sha256'],
                        'code_objects': len(result['code_objects'])})
    graph = literal_story_graph(read_module(rows[260]))
    nodes = list(graph['graph']['Storyline']['nodeData'].values())
    props = [n['Data'] for n in nodes if n['Type'] == 'GetRpgProps']
    if len(props) != 1 or props[0]['method'] != 0 or props[0]['isInit'] is not False:
        raise ValueError('Unexpected property rounding/provider branch')
    table = literal_table(391, {66051})
    fields = table['rows'][0]['fields']
    if 'RPG_TARGET' in fields or fields['NEED_TIME'] is not False:
        raise ValueError('Buff source or multiplicity assumptions changed')
    # Inventory absence is scoped to indexed names, not proof no implementation exists.
    searched = ['registerGlobalListener', 'getRpgPropByKey', 'fakeMultiDamage',
                'getBuffTimes', 'onHPRecoverEvent']
    symbols = [json.loads(line) for line in
               (ROOT / 'analysis/assets/decoded/script/symbols.jsonl').read_text('utf8').splitlines()]
    definitions = {name: [{'index': r['index'], 'filename': r['filename']}
                         for r in symbols if name in r['functions']] for name in searched}
    report = {
        'evidence': 'Local static extraction with decoded hashes; not REA runtime evidence',
        'sources': sources, 'buff_table': table,
        'graph_source': rows[260], 'graph': graph,
        'indexed_function_definitions': definitions,
        'findings': [
            'Listener registration passes EVENT_NAME, targetType=1, context.owner, callback; explicit listened overrides owner.',
            'afterRoundEvent forwards args[0] as roundNum; onHPRecoverEvent forwards five arguments with no local positive-heal filter.',
            'nowTimes comes from buffOwner.getBuffTimes(buffID), not directly buffObj.times.',
            'GetRpgProps uses current getRpgPropByKey(propName, strengthFactor=1), multiplies percent/100.0, then int(math.floor(value)) for method=0.',
            'Graph feeds srcEntity to GetRpgProps and current stacks * BUFF_RATIO=20 to percent; PropAtk output feeds finalExtraDamage.',
            'BuffDealDamage uses getBuffSource separately. Absent RPG_TARGET returns context.owner, not srcEntity.',
            'Damage base is zero; extraDamage carries the rounded property result. NEED_TIME=false avoids extra stack multiplication.',
            'canUseOnDie defaults false; fakeMultiDamage is skipped when its selected source.preDie is true.',
            'Recovery graph requests num=-1 with isCommonChange=false. BuffTargetAddBuff defaults srcEntity to context.owner.',
        ],
        'limitations': [
            'targetType=1 filtering, event emission timing, overheal/zero-heal semantics remain outside these nodes.',
            'Current property provider adds ordered modifiers and clamps only PropAtk; strengthFactor is unused. Initial maxHp reads self.maxHp, other initial fields read rpgProp.get(key,0).',
            'Client getBuffTimes reads buff.get(buffID,{}).get("times",0); this does not establish server-side aggregation across casters.',
            'Source lifetime and final damage/defense/shield pipeline are not implemented here.',
            'Buff aggregation across casters, decrement/removal behavior and fakeAOE closure need further recovery.',
            'Partial opcode names remain UNKNOWN where not independently corroborated.',
            'No city battle integration, UI change, native package rebuild or original runtime validation.',
        ],
    }
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    def tagged(value):
        return {'kind': 'integer' if isinstance(value, int) else 'binary64',
                'value': str(value), **({} if isinstance(value, int) else {'hex': value.hex()})}
    # Independent Python arithmetic for the recovered node expression. Synthetic
    # inputs exercise rounding/order; these are not original runtime observations.
    cases = []
    for prop, percent, method in [(101, 40, 0), (-101, 40, 0), (-101, 40, 1),
                                  (101, 40, 1), (101, 40, 2), (0, 40, 0),
                                  (0.29, 100, 0), (123.75, 60, 0),
                                  (9007199254740993, 100, 0),
                                  (9007199254740993, 100.0, 0), (17, -20, 0)]:
        value = prop * percent / 100.0
        result = int(math.floor(value)) if method == 0 else int(math.ceil(value)) if method == 1 else value
        cases.append({'property': tagged(prop), 'percent': tagged(percent),
                      'method': method, 'expected': tagged(result)})
    (OUT / 'property-vectors.json').write_text(json.dumps({
        'source': '2905:147.8, offsets 96..215',
        'evidence': 'Synthetic Python reference arithmetic, not APK execution',
        'cases': cases}, indent=2), 'utf8')
    print(json.dumps({'sources': sources, 'indexed_function_definitions': definitions}, ensure_ascii=False))


if __name__ == '__main__':
    main()
