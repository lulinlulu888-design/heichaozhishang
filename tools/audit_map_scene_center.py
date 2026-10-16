"""Confirm scene 239's map origin, width, row offset, and the height that still blocks placement."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_npk import Marshal2
from inspect_battle_rules import instructions, read_module, walk_codes

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

scene_tools = 'analysis/assets/decoded/script/06048_a00daec8.marshal'
tools_raw = (ROOT / scene_tools).read_bytes()
tools_obj = Marshal2(tools_raw).obj()
tools_module = read_module({
    'output': scene_tools,
    'decoded_sha256': hashlib.sha256(tools_raw).hexdigest(),
    'filename': tools_obj['filename'].decode(),
})
short_formula = tools_module['consts'][62]
assert [step['opname'] for step in instructions(short_formula)] == [
    'LOAD_FAST', 'LOAD_ATTR', 'LOAD_CONST', 'LOAD_CONST', 'CALL_FUNCTION', 'RETURN_VALUE']
assert [step.get('operand') for step in instructions(short_formula)][2:4] == ['ShortSide', 0]
live_offset = next(code for _path, code in walk_codes(tools_module) if code['name'] == b'getDungeonOffset')
offset_ops = [(step['opname'], step.get('operand')) for step in instructions(live_offset)]
assert ('LOAD_CONST', 2) in offset_ops and ('BINARY_MODULO', None) in offset_ops
assert offset_ops[offset_ops.index(('LOAD_CONST', 2)) + 1][0] == 'BINARY_MODULO'
assert scene['fields']['ShortSide'] == 14
assert scene['fields']['ShortSide'] % 2 == 0

mainline = 'analysis/assets/decoded/script/07743_cc53d0cc.marshal'
main_raw = (ROOT / mainline).read_bytes()
main_obj = Marshal2(main_raw).obj()
main_module = read_module({
    'output': mainline,
    'decoded_sha256': hashlib.sha256(main_raw).hexdigest(),
    'filename': main_obj['filename'].decode(),
})
outline = next(code for _path, code in walk_codes(main_module) if code['name'] == b'generateMapOutline')
outline_ops = [step['opname'] + ':' + str(step.get('operand')) for step in instructions(outline)]
assert outline_ops[outline_ops.index('UNPACK_SEQUENCE:None') + 1:outline_ops.index('UNPACK_SEQUENCE:None') + 7] == [
    'LOAD_FAST:self', 'STORE_ATTR:_mapData', 'LOAD_FAST:self', 'STORE_ATTR:_height',
    'LOAD_FAST:self', 'STORE_ATTR:_width']
detail = next(code for _path, code in walk_codes(main_module) if code['name'] == b'generateMapOutlineDetail')
detail_ops = [(step['opname'], step.get('operand')) for step in instructions(detail)]
assert detail_ops[:6] == [
    ('LOAD_FAST', 'long_side'), ('LOAD_CONST', 3), ('BINARY_ADD', None),
    ('STORE_FAST', 'height'), ('LOAD_CONST', 1), ('LOAD_FAST', 'long_side')]
long_side, short_side = scene['fields']['LongSide'], scene['fields']['ShortSide']
map_height = long_side + 3
map_width = 1 + (long_side - short_side) * 2 + 2
assert (long_side, short_side, map_width, map_height) == (27, 14, 29, 30)
center_x, center_y = map_width // 2, map_height // 2
origin = scene['fields']['SceneCenter']
pieces = []
for key, kind in (('21,22', 'start'), ('20,22', 'challenge'), ('19,22', 'end')):
    cell_y, cell_x = (int(part) for part in key.split(','))
    temp_x, temp_y = cell_y + 1, map_width - cell_x + 1
    even = abs(center_y - temp_x) % 2 == 0
    if even:
        ground_z = origin[2] + (center_x - temp_y) * 27.712 - 27.712
    elif center_x > temp_y:
        ground_z = origin[2] + (center_x - temp_y - 1) * 27.712 + 13.856
    else:
        ground_z = origin[2] + (center_x - temp_y) * 27.712 - 13.856
    pieces.append((kind, cell_x, cell_y, origin[0] + (center_y - temp_x) * 24, ground_z, even))
assert pieces == [
    ('start', 22, 21, -165, 386.116, False),
    ('challenge', 22, 20, -141, 372.26, True),
    ('end', 22, 19, -117, 386.116, False),
]
piece_pos = next(code for _path, code in walk_codes(
    read_module({
        'output': 'analysis/assets/decoded/script/01164_1fa9b776.marshal',
        'decoded_sha256': hashlib.sha256((ROOT / 'analysis/assets/decoded/script/01164_1fa9b776.marshal').read_bytes()).hexdigest(),
        'filename': 'logic\\dungeon\\iMapScene.py',
    })) if code['name'] == b'calculatePiecePos')
assert any(step['opcode'] == 0x42 for step in instructions(piece_pos))

print('scene 239 CenterPos is SceneCenter [3, 16.26, 233.7]')
print('extra editor center is absent, so it is not added')
print('dungeon width is 29 and the even-row offset is 1')
print('piece ground positions stay unplaced: the layer height opcodes are still unread')
