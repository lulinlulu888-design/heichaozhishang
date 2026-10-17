"""Base-only level-100 stats for the prologue boss party (course row 2).

Same verified formula and arithmetic as trace_player_baseline.py; executes no
recovered code. Excluded modifiers are a reconstruction profile choice.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from trace_first_encounter import literal_table
from trace_player_baseline import base_formula, tagged
from extract_texture_samples import APK_SHA256

OUT = ROOT / 'analysis/prologue-boss'
FORMULA = 'occupation*((100+increase)*rarityratio*1+raritybase)'


def build():
    course = literal_table(4105, {2})['rows'][0]['fields']
    assert course['FirstBattleID'] == 1703 and course['BattleChar'] == [1, 3] and course['CharLevel'] == [100, 100]
    characters = literal_table(8995, set(course['BattleChar']))
    formula = literal_table(4879, {1})
    formula_fields = formula['rows'][0]['fields']
    members, tables = [], {'character': characters, 'formula': formula}
    for position, char_id in enumerate(course['BattleChar']):
        fields = next(r for r in characters['rows'] if r['id'] == char_id)['fields']
        level = course['CharLevel'][position]
        quality = literal_table(6181, {fields['CHARRARITY']})
        level_row = literal_table(8577, {level})
        occupation = literal_table(1617, {fields['CHARTYPE']})
        tables[f'quality-{char_id}'], tables[f'level-{char_id}'], tables[f'occupation-{char_id}'] = quality, level_row, occupation
        stats, stats_tagged, inputs_by_key = {}, {}, {}
        for key in ('maxHp', 'PropAtk'):
            assert formula_fields[key] == FORMULA
            inputs = {
                'occupation': occupation['rows'][0]['fields'][key],
                'increase': level_row['rows'][0]['fields']['totalCultivateValue'],
                'rarityratio': quality['rows'][0]['fields']['rarityRatio'],
                'raritybase': quality['rows'][0]['fields']['rarityBaseValue'],
            }
            assert all(type(v) is float for v in inputs.values())
            stats[key] = base_formula(**inputs)
            stats_tagged[key] = tagged(stats[key])
            inputs_by_key[key] = {k: tagged(v) for k, v in inputs.items()}
        members.append({'characterId': char_id, 'name': fields['NAME'], 'formationIndex': position,
                        'level': level, 'rarity': fields['CHARRARITY'], 'subRarity': fields['CHAR_SUB_RARITY'],
                        'charType': fields['CHARTYPE'], 'baseStats': stats, 'baseStatsTagged': stats_tagged,
                        'inputsTagged': inputs_by_key})
    assert members[0]['baseStats'] == {'maxHp': 1768.8000000000002, 'PropAtk': 482.4}
    evidence_path = OUT / 'party-baseline.evidence.json'
    evidence_path.write_text(json.dumps({'sourceApkSha256': APK_SHA256, 'course': course, 'tables': tables},
                                        ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    result = {
        'schemaVersion': 1, 'kind': 'explicit-reconstruction-base-stat-configuration',
        'profileId': 'prologue-party-level100-base-only', 'battleId': 1703, 'courseId': 2,
        'members': members, 'sourceFormula': FORMULA,
        'originalFinalCombatStatsRecovered': False,
        'raritySelection': 'character_basic_info.CHARRARITY; the original tutorial account rarity is not proven.',
        'modifierPolicy': 'base-formula-only; same exclusions as elsa-level100-rarity4-base-only',
        'evidence': {'file': evidence_path.name, 'sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                     'sourceApkSha256': APK_SHA256, 'reproduce': 'python tools/trace_party_baseline.py'},
    }
    out = OUT / 'party-baseline.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({m['name']: m['baseStats'] for m in members}, ensure_ascii=False))


if __name__ == '__main__':
    build()
