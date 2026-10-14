"""Record the static tutorial monster -> difficulty -> IsBoss chain."""
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/health'


def main():
    index = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    requests = {
        'monster-is-boss': ('net\\battle\\CMonster.py', ('IsBoss', 'getPropertyData')),
        'monster-type-enum': ('common\\const.py', ('MonsterType',)),
        'ui-monster-data': ('ui\\UIDataSource.py', ('getMonsterStaticData',)),
        'monster-data-mapping': ('ui\\ui_data\\MonsterDataTools.py', ('<module>', 'getMonsterStaticData', '<lambda>')),
    }
    evidence = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for label, (filename, methods) in requests.items():
        row = next(r for r in index if r['filename'] == filename)
        report = static.export(row, methods)
        if label == 'monster-data-mapping':
            report['code_objects'] = [c for c in report['code_objects']
                if c['name'] != '<lambda>' or c['constant_path'] == [44]]
        evidence[label] = report
        (OUT / (label + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    # Re-read the table through the hash-verified literal parser, rather than
    # trusting an earlier exported row as the source of the classification.
    table_row = next(r for r in index if r['filename'] == 'common\\cdata\\monster_table.py')
    table = static.export_table(table_row['index'], [991])
    (OUT / 'monster-991.json').write_text(json.dumps(table, ensure_ascii=False, indent=2), 'utf8')
    monster = next(r for r in table['rows'] if r['id'] == 991)
    if monster['fields']['difficulty_type'] != 1:
        raise ValueError('Tutorial monster difficulty changed')
    enum = evidence['monster-type-enum']['code_objects'][0]['instructions']
    assignments = {enum[i]['operand']: enum[i-1].get('operand') for i in range(1,len(enum))
        if enum[i]['opname']=='STORE_NAME' and enum[i-1]['opname']=='LOAD_CONST'}
    if assignments.get('Elite') != 1 or assignments.get('Boss') != 2:
        raise ValueError('MonsterType evidence changed')
    mapping = next(c for c in evidence['monster-data-mapping']['code_objects'] if c['constant_path']==[44])
    if [(i['opname'],i.get('operand')) for i in mapping['instructions']] != [
        ('LOAD_FAST','monsterData'),('LOAD_ATTR','difficulty_type'),('RETURN_VALUE',None)]:
        raise ValueError('Difficulty mapping changed')
    result = dict(monster_id=991, difficulty_type=1, enum_name='Elite', boss_enum=2,
        inferred_is_boss=False, source_layout='MonsterHeadArea',
        evidence_files=[label+'.json' for label in requests]+['monster-991.json'],
        interpretation='Static source chain: DifficultyType maps to monsterData.difficulty_type; IsBoss compares DifficultyType with MonsterType.Boss.',
        limitations=['No original runtime execution or server property override verification',
            'Head selection includes additional scene/entity conditions; full runtime behavior not emulated'])
    (OUT / 'tutorial-kind.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
