"""Confirm the first-battle remaining-turn plate and the fields that stay unwired."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_head_area_rest import load_csb, visual_box

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf8'))


def function(document, name):
    return next(item for item in document['code_objects'] if item['name'] == name)


success = function(load('analysis/prologue-boss/consumer-MaxRoundFail-9555.json'), 'getBattleRoundSuccess')
assert success['bytecode_sha256'] == 'f51628c05f06462162381c33152256595e917355236a8e47de61a76afca0e9de'
assert [step.get('operand') for step in success['instructions']].count('RoundSuccess') == 1
assert [step.get('operand') for step in success['instructions']].count('MaxRoundFail') == 1
assert any(step['opname'] == 'COMPARE_OP' and step['argument'] == 3 for step in success['instructions'])
assert any(step.get('operand') == 'min' for step in success['instructions'])
assert any(step.get('operand') == 'max' for step in success['instructions'])

damage = function(load('analysis/battle-ui/piles/providers/9555.json'), 'getIsShowTotalDamage')
assert damage['bytecode_sha256'] == 'e1c96052578be5e4743d9b11222d6e3a9790c05fbcf61af8bd3a3942fb92aacd'
assert any(step.get('operand') == 'ShowTotalDamaga' for step in damage['instructions'])
assert any(step.get('operand') == 'False' for step in damage['instructions'])

row = next(item for item in load('analysis/mainline-progression/prologue.json')['sourceTables']['battles']
           if item['source']['filename'].endswith('maze_battle_table_6.py'))
battle = next(item for item in row['rows'] if item['id'] == 5000)
assert battle['fields']['MaxRoundFail'] == 30
assert 'RoundSuccess' not in battle['fields']
assert 'ShowTotalDamaga' not in battle['fields']

const = next(item for item in load('analysis/first-encounter/const-first-encounter.code.json')['code_objects']
             if item['name'] == '<module>')
stored = next(step for step in const['instructions'] if step.get('operand') == 'FightLastWarnTurn')
assert stored['source_line'] == 6725
value = const['instructions'][const['instructions'].index(stored) - 1]
assert value['opname'] == 'LOAD_CONST' and value['operand'] == 3

fight = load_csb(ROOT / 'analysis/battle-ui/FightMainPanel.csb')
top = load_csb(ROOT / 'analysis/battle-ui/TopInfoArea.csb')
info = load_csb(ROOT / 'analysis/battle-ui/TopInfoArea_2_ext.csb')
merged = list(fight)
round_i = next(i for i, node in enumerate(fight) if node['name'] == 'RoundNode')
index = {}
for node in top:
    if node['parent'] < 0:
        index[top.index(node)] = round_i
        continue
    child = dict(node)
    child['parent'] = index[node['parent']]
    index[top.index(node)] = len(merged)
    merged.append(child)
host = next(i for i, node in enumerate(merged) if node['name'] == 'TopInfoNode')
index2 = {}
for node in info:
    if node['parent'] < 0:
        index2[info.index(node)] = host
        continue
    child = dict(node)
    child['name'] = 'T2/' + node['name']
    child['parent'] = index2[node['parent']]
    index2[info.index(node)] = len(merged)
    merged.append(child)
boxes = {}
seen = set()
for node in merged:
    if not node['name'].startswith('T2/') or node['name'] in seen:
        continue
    if node['classname'] not in ('ImageView', 'Text'):
        continue
    origin, size, _flip, visible = visual_box(merged, 720, node['name'])
    boxes[node['name']] = (tuple(round(v, 2) for v in origin), tuple(round(v, 2) for v in size), visible)
    seen.add(node['name'])
assert boxes['T2/bg_1'] == ((545.0, 1.0), (192.0, 34.0), True)
assert boxes['T2/icon_1'] == ((595.0, 9.0), (20.0, 18.0), True)
assert boxes['T2/txt_turn_1'] == ((629.5, 8.0), (23.0, 20.0), True)
print('top turn audit passed')
