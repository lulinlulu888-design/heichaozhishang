"""Confirm scene 239's map-piece origin, and the fields that still block placement."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf8'))


def function(document, name):
    return next(item for item in document['code_objects'] if item['name'] == name)


def names(code):
    return [step['opname'] + ':' + str(step.get('operand')) for step in code['instructions']]


scene_module = load('analysis/mainline-dungeon/scripts/1164.json')
center = function(scene_module, 'CenterPos')
center_names = names(center)
assert center['firstlineno'] == 53
assert 'LOAD_ATTR:_sceneCenter' in center_names
assert 'LOAD_ATTR:getDungeonCenter' in center_names
assert 'LOAD_ATTR:getSceneCenter' in center_names
assert 'INPLACE_ADD:None' in center_names
assert center_names[-1] == 'RETURN_VALUE:None'

dungeon = load('analysis/mainline-dungeon/scripts/6048.json')
dungeon_center = function(dungeon, 'getDungeonCenter')
assert [step.get('operand') for step in dungeon_center['instructions']].count('SceneCenter') == 1
assert dungeon_center['instructions'][-2]['opname'] == 'BINARY_SUBSCR'
assert dungeon_center['instructions'][-1]['opname'] == 'RETURN_VALUE'

helper = load('analysis/mainline-dungeon/scripts/890.json')
editor_center = function(helper, 'getSceneCenter')
assert any(step.get('operand') == 'CenterPos' for step in editor_center['instructions'])
assert any(step.get('operand') is None and step['opname'] == 'LOAD_CONST' for step in editor_center['instructions'])

scenes = load('analysis/mainline-dungeon/data/scenes.json')
scene = next(row for row in scenes['rows'] if row['id'] == 239)
assert scene['fields']['SceneCenter'] == [3, 16.26, 233.7]
assert scene['fields']['ScenePath'] == 'scene/chess_xuzhang/chess_xuzhang.scn'
assert 'MLShortSide' not in scene['fields']

extra = load('analysis/assets/npk/assets/00145_8a9e76dc.json')
assert '239' not in extra

maze = load('analysis/mainline-dungeon/data/map50002.json')
assert 'width' not in maze['data'] and 'height' not in maze['data']

width = function(scene_module, 'DungeonWidth')
assert [step.get('operand') for step in width['instructions']] == ['self', '_dungeonInfo', 'width', None, None]
offset = function(dungeon, 'getDungeonOffset')
assert any(step.get('operand') == 'MLShortSide' for step in offset['instructions'])
assert any(step['opname'] == 'UNKNOWN' for step in offset['instructions'])

print('scene 239 CenterPos is SceneCenter [3, 16.26, 233.7]')
print('extra editor center is absent, so it is not added')
print('piece positions stay unplaced: map 50002 has no width, and MLShortSide is absent')
