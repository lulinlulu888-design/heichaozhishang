"""Recover the city monster's base curve and property composition evidence."""
import json
from pathlib import Path
import inspect_battle_rules as static
from trace_first_encounter import inventory, literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-visual/city-scenes/monster-properties'


def tagged(value):
    if type(value) is int:
        return dict(kind='integer', value=str(value))
    if type(value) is float:
        return dict(kind='binary64', value=repr(value), hex=value.hex())
    raise TypeError('Expected numeric literal')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = inventory()
    sources = []
    for index, names in (
        (5304, ('resetMonsterMouldData', 'getMonsterMouldData')),
        (3510, ('getForceProp', 'getMonsterHP', 'getMonsterATK', 'getMonsterAtkDef', 'getMonsterMgcDef',
                'getMonsterHPDiffRatio', 'getMonsterAtkDiffRatio', 'getMonsterAtkDefDiffRatio', 'getMonsterMgcDefDiffRatio',
                'getMazeHPDiffRatio', 'getMazeAtkDiffRatio', 'getMazeAtkDefDiffRatio', 'getMazeMgcDefDiffRatio',
                'getChallengeHPDiffRatio', 'getChallengeAtkDiffRatio', 'getChallengeAtkDefDiffRatio', 'getChallengeMgcDefDiffRatio')),
        (9419, ('getMonsterLevel',)),
    ):
        report = static.export(rows[index], names)
        (OUT/f'{index}.code.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
        sources.append(rows[index])
    monster = literal_table(2363, {6605})
    battle = literal_table(6500, {10405})
    m = monster['rows'][0]['fields']
    table = literal_table(6708)
    curve = [r for r in table['rows'] if r['fields']['Math_model'] == m['Math_model']]
    levels = [r['fields']['Level'] for r in curve]
    if sorted(levels) != list(range(1, 401)):
        raise ValueError('Elite level coverage changed or duplicated')
    table['rows'] = curve
    result = dict(evidence='Local hash-verified static parsing; not original runtime or REA execution',
        monster=monster, battle=battle, curve=table, script_sources=sources,
        composition='enforce_<property> when not None; otherwise base * monsterRatio * mazeRatio * challengeRatio, in that order',
        limitations=[
            'No actual monster level selected: challenge, dungeon and max-three-character level branches depend on runtime state.',
            'shuzhi_moban=37 is not a level and is not read by these base-property functions.',
            'UseChallengeLevel is table data; its authoritative server consumer is not recovered.',
            'Map/challenge ratios are unresolved inputs; absent battleID yields maze ratio 0 in shipped code, not 1.',
            'Base properties are not final skill damage or HP changes; buffs and battle rules still apply.'])
    (OUT/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    cases = []
    for row in curve:
        if row['fields']['Level'] not in (1, 10, 20, 100, 241, 400):
            continue
        for key in ('maxHp', 'PropAtk'):
            base = row['fields'][key]
            # Explicit neutral-context examples, not selected encounter stats.
            ratios = [1.0, 1.0, 1]
            value = base
            for ratio in ratios:
                value *= ratio
            cases.append(dict(label=f"elite level {row['fields']['Level']} {key}; neutral context",
                force=None, base=tagged(base), ratios=[tagged(r) for r in ratios], expected=tagged(value)))
    for force in (0, 1.0):
        cases.append(dict(label='enforced value bypasses all multipliers', force=tagged(force), expected=tagged(force)))
    for ratios in ([1.0, 0, 1], [0.1, 0.2, 0.3]):
        value = 87.0
        for ratio in ratios:
            value *= ratio
        cases.append(dict(label='explicit context multiplier sequence', force=None, base=tagged(87.0),
            ratios=[tagged(r) for r in ratios], expected=tagged(value)))
    (OUT/'vectors.json').write_text(json.dumps(dict(evidence='Independent Python arithmetic with parsed base literals; not original execution', cases=cases), indent=2), 'utf8')
    print(json.dumps(dict(monster=6605, level_rows=len(curve), selected_level=None, vectors=len(cases))))


if __name__ == '__main__':
    main()
