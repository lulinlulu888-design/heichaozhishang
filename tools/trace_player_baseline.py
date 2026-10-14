"""Reproduce an explicit base-stat configuration; execute no recovered code.

Only our existing bounded literal parser and partial disassembly are used.
The one supported source formula is checked verbatim, then evaluated using
hand-written arithmetic preserving the source float/int types and operation
order. Decimal arithmetic is only a mathematical reference, not a runtime value.
"""
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from trace_first_encounter import inventory, literal_table
from inspect_battle_rules import export
from extract_texture_samples import APK_SHA256

OUT = ROOT / 'analysis/first-encounter'


def tagged(value):
    if type(value) is int:
        return {'numeric_type': 'integer', 'decimal': str(value)}
    if type(value) is float and math.isfinite(value):
        return {'numeric_type': 'binary64', 'decimal': repr(value), 'hex': value.hex()}
    raise ValueError('only finite source integer/binary64 values supported')


def base_formula(occupation, increase, rarityratio, raritybase):
    """Our fixed arithmetic, preserving original operand types and order."""
    if any(type(v) not in (int, float) for v in
           (occupation, increase, rarityratio, raritybase)):
        raise ValueError('unsupported numeric operand type')
    return occupation * ((100 + increase) * rarityratio * 1 + raritybase)


def build():
    assert (sys.float_info.radix, sys.float_info.mant_dig, sys.float_info.max_exp) == (2, 53, 1024)
    OUT.mkdir(parents=True, exist_ok=True)
    definitions = {
        'character': (8995, 1), 'course': (4105, 1),
        'quality': (6181, 4), 'level': (8577, 100),
        'occupation': (1617, 1), 'formula': (4879, 1),
    }
    tables = {name: literal_table(index, {row})
              for name, (index, row) in definitions.items()}
    fields = {name: table['rows'][0]['fields'] for name, table in tables.items()}
    assert fields['character']['NAME'] == '艾尔莎'
    assert fields['character']['CHARRARITY'] == 4
    assert fields['character']['CHAR_SUB_RARITY'] == 0
    assert fields['character']['CHARTYPE'] == 1
    assert fields['character']['InitChar'] is True
    assert fields['course']['FirstBattleID'] == 5000
    assert fields['course']['BattleChar'] == [1]
    assert fields['course']['CharLevel'] == [100]
    expected_formula = 'occupation*((100+increase)*rarityratio*1+raritybase)'
    values = {}
    values_tagged = {}
    calculation = {}
    for key in ('maxHp', 'PropAtk'):
        assert fields['formula'][key] == expected_formula
        inputs = {
            'occupation': fields['occupation'][key],
            'increase': fields['level']['totalCultivateValue'],
            'rarityratio': fields['quality']['rarityRatio'],
            'raritybase': fields['quality']['rarityBaseValue'],
        }
        assert all(type(v) is float for v in inputs.values())
        value = base_formula(**inputs)
        assert type(value) is float and math.isfinite(value) and value > 0
        values[key] = value
        values_tagged[key] = tagged(value)
        # Intentionally separate decimal-mathematics reference from binary64.
        reference = {k: Decimal(str(v)) for k, v in inputs.items()}
        exact = reference['occupation'] * (
            (Decimal(100) + reference['increase']) * reference['rarityratio']
            * Decimal(1) + reference['raritybase'])
        calculation[key] = {
            'sourceFormula': expected_formula,
            'inputs': inputs,
            'inputsTagged': {k: tagged(v) for k, v in inputs.items()},
            'formulaConstantsTagged': {'100': tagged(100), '1': tagged(1)},
            'exactDecimal': format(exact.normalize(), 'f'),
            'exactDecimalMeaning': 'Mathematical reference using decimal spellings of inputs; not a runtime/binary64 result and never used for baseStats.',
            'calculationMethod': 'Hand-written Python float/int arithmetic in original expression order after exact formula match; no eval/exec or game-code execution.',
        }
    assert values == {'maxHp': 1768.8000000000002, 'PropAtk': 482.4}
    assert values['maxHp'] != float(calculation['maxHp']['exactDecimal'])
    rows = inventory()
    code = {str(index): export(rows[index], names) for index, names in {
        9420: ('__init__', 'init_from_dict', 'onCreate', 'getCharRarity', 'getCharSubRarity',
               'getCalculationRarity', 'unLockChar'),
        1703: ('addANewCharacter',),
        2165: ('getCharLevelBasicProp', 'getCharLevelBasicPropByLvAndRarity',
               'getSingleCharBasicProp', 'getCharMaxHP'),
        5947: ('startNewPlayerCourse', 'getBattleCharInitLevel'),
    }.items()}
    evidence = {
        'sourceApkSha256': APK_SHA256,
        'verification': 'Each decoded module SHA and complete marshal consumption checked. APK identity was verified by trace_first_encounter.py; this supplement does not rehash the whole APK.',
        'tables': tables, 'code': code,
    }
    evidence_path = OUT / 'player-baseline.evidence.json'
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    result = {
        'schemaVersion': 2,
        'kind': 'explicit-reconstruction-base-stat-configuration',
        'profileId': 'elsa-level100-rarity4-base-only',
        'battleId': 5000, 'characterId': 1, 'characterName': '艾尔莎',
        'level': 100, 'rarity': 4, 'rarityName': fields['quality']['name'],
        'subRarity': 0, 'baseStats': values, 'baseStatsTagged': values_tagged,
        'originalFinalCombatStatsRecovered': False,
        'originalTutorialRarityProven': False,
        'raritySelection': 'Explicit reconstruction choice matching character_basic_info[1].CHARRARITY and the client no-characterDbData fallback; not proof of the original tutorial account state.',
        'calculation': calculation,
        'modifierPolicy': {
            'mode': 'base-formula-only',
            'excludedSources': ['level storyline additions', 'rarity storyline additions',
                'favor', 'equipment', 'special equipment', 'relics', 'life-tree base and talents',
                'antiques', 'DBG activity', 'bondage effects', 'GM overrides',
                'temporary rarity overrides', 'combat buffs and other runtime modifiers'],
            'interpretation': 'Exclusions define this reconstruction profile, not the state of the original tutorial account.',
        },
        'numericPolicy': {
            'output': 'binary64 base-formula results with decimal/hex type tags', 'rounding': None,
            'arithmetic': 'Source float/int operand types and expression order preserved with host Python binary64 operations; no Decimal-to-float substitution.',
            'observation': 'Static reconstruction calculation, not an observation of the original APK runtime.',
            'decimalReference': 'exactDecimal is decimal mathematical reference only, not the runtime value.',
            'sourceFunction': '2165:[6,7] getCharLevelBasicPropByLvAndRarity returns formula result directly at 0xf9.',
            'hpWrapper': '2165:[6,22] getCharMaxHP returns composed arithmetic directly at 0x1a8; no int/round conversion.',
            'aggregate': '2165:[6,3] getSingleCharBasicProp stores arithmetic directly into data[k] at 0x2e9, returns data at 0x363. Its int(charID) call at 0x100..0x109 does not round stats.',
            'remainingUnknown': 'Any later combat-entity, serializer, display, or damage-layer numeric conversion is outside this bounded check.',
        },
        'evidence': {
            'file': evidence_path.name,
            'sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            'sourceApkSha256': APK_SHA256,
            'reproduce': 'python tools/trace_player_baseline.py',
        },
        'limitations': [
            'Course table specifies character 1 and level 100, but no rarity override.',
            'getCharRarity reads characterDbData[str(charID)][rarity] if present; the shipped client does not prove the server-created initial rarity.',
            'InitChar=True is source metadata; a complete server initialization path using it was not recovered.',
            'Original getSingleCharBasicProp/getCharMaxHP include modifiers deliberately excluded by this profile.',
        ],
    }
    output = OUT / 'player-baseline.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    reread = json.loads(output.read_text('utf8'))
    assert reread['baseStats'] == values and reread['numericPolicy']['rounding'] is None
    for key, value in values.items():
        tag = reread['baseStatsTagged'][key]
        assert tag['numeric_type'] == 'binary64'
        assert reread['baseStats'][key].hex() == value.hex() == tag['hex']
        assert float(tag['decimal']).hex() == value.hex()
        assert float.fromhex(tag['hex']).hex() == value.hex()
    print(json.dumps({'output': str(output), 'baseStats': values, 'baseStatsTagged': values_tagged,
                      'evidenceSha256': result['evidence']['sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    build()
