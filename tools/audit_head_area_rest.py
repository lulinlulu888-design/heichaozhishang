"""Print PlayerHead, MonsterHead and Energy rest boxes in HUD design space."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from inspect_battle_ui_layout import Reader  # noqa: E402

LAYOUTS = json.loads((ROOT / 'analysis/battle-ui/health/layouts.json').read_text('utf8'))['layouts']


def flatten(node, parent, out):
    index = len(out)
    entry = {k: v for k, v in node.items() if k != 'children'}
    entry['parent'] = parent
    out.append(entry)
    for child in node.get('children', []):
        flatten(child, index, out)


def transform(node):
    angle = node['rotation_skew'][0] * math.pi / 180
    c, s = math.cos(angle), math.sin(angle)
    sx, sy = node['scale']
    ax, ay = node['anchor']
    w, h = node['size']
    px, py = node['position']
    m00, m01 = c * sx, s * sy
    m10, m11 = -s * sx, c * sy
    tx = px - m00 * ax * w - m01 * ay * h
    ty = py - m10 * ax * w - m11 * ay * h
    return m00, m01, m10, m11, tx, ty


def compose(a, b):
    a00, a01, a10, a11, atx, aty = a
    b00, b01, b10, b11, btx, bty = b
    return (a00 * b00 + a01 * b10, a00 * b01 + a01 * b11,
            a10 * b00 + a11 * b10, a10 * b01 + a11 * b11,
            a00 * btx + a01 * bty + atx, a10 * btx + a11 * bty + aty)


def apply(m, x, y):
    return m[0] * x + m[1] * y + m[4], m[2] * x + m[3] * y + m[5]


def globals_of(nodes, design_origin_y):
    mats = []
    for node in nodes:
        local = transform(node)
        parent = node['parent']
        mats.append(local if parent < 0 else compose(mats[parent], local))
    source_to_design = (1, 0, 0, -1, 0, design_origin_y)
    out = []
    for node, mat in zip(nodes, mats):
        flip_x = node.get('flip_x', False)
        quad = (-1 if flip_x else 1, 0, 0, -1, node['size'][0] if flip_x else 0, node['size'][1])
        out.append(compose(source_to_design, compose(mat, quad)))
    return out


def load_csb(path):
    data = path.read_bytes()
    reader = Reader(data)
    root = reader.scalar('I', 0)
    tree = reader.node(reader.pointer(reader.field(root, 3)))
    nodes = []
    flatten(tree, -1, nodes)
    return nodes


def tree_nodes(name):
    tree = next(row['tree'] for row in LAYOUTS if row['name'] == name)
    nodes = []
    flatten(tree, -1, nodes)
    return nodes


def visual_box(nodes, design_origin_y, name):
    """Unflipped top-left and scaled size. flip_x mirrors pixels inside that box."""
    mats = []
    for node in nodes:
        stored = dict(node)
        stored['flip_x'] = False
        local = transform(stored)
        parent = node['parent']
        mats.append(local if parent < 0 else compose(mats[parent], local))
    index = next(i for i, node in enumerate(nodes) if node['name'] == name)
    node = nodes[index]
    source_to_design = (1, 0, 0, -1, 0, design_origin_y)
    quad = (1, 0, 0, -1, 0, node['size'][1])
    origin = apply(compose(source_to_design, compose(mats[index], quad)), 0, 0)
    width = abs(node['scale'][0]) * node['size'][0]
    height = abs(node['scale'][1]) * node['size'][1]
    return origin, (width, height), bool(node.get('flip_x')), bool(node.get('visible', True))


def show(title, nodes, design_origin_y, names=None):
    print('==', title)
    mats = globals_of(nodes, design_origin_y)
    for node, mat in zip(nodes, mats):
        if names and node['name'] not in names:
            continue
        if node['classname'] not in ('ImageView', 'Text', 'LoadingBar', 'Sprite', 'TextBMFont', 'ProjectNode', 'SingleNode', 'Panel', 'Node'):
            continue
        origin = apply(mat, 0, 0)
        extra = ''
        if node.get('resource'):
            extra += ' res=' + str(node['resource'].get('path'))
        if node.get('text'):
            extra += ' text=' + json.dumps(node['text'], ensure_ascii=False) + ' font=' + str(node.get('font_size'))
        if 'percent' in node:
            extra += ' percent=' + str(node['percent']) + ' dir=' + str(node['direction'])
        print(f"{node['name']:24} {node['classname']:12} origin=({origin[0]:8.2f},{origin[1]:8.2f}) size={node['size']}{extra}")


def raw(title, nodes, wanted):
    print('-- raw', title)
    for node in nodes:
        if node['name'] in wanted:
            print(node['name'], 'pos', [round(v, 2) for v in node['position']],
                  'anchor', [round(v, 2) for v in node['anchor']],
                  'scale', [round(v, 2) for v in node['scale']],
                  'size', [round(v, 2) for v in node['size']],
                  'flip', node.get('flip_x'), node.get('flip_y'))

def main():
    fight = tree_nodes('FightMainPanel')
    show('FightMainPanel slots', fight, 720, {
        'EnterancePlayerHeads', 'EnteranceMonsterHeads', 'RoundNode', 'HPArea_left_1', 'HPArea_right_1',
        'HPArea_right_boss', 'TopInfo', 'IntentionTop'})
    player = tree_nodes('PlayerHeadArea')
    monster = tree_nodes('MonsterHeadArea')
    show('PlayerHeadArea', player, 0)
    raw('player', player, {'bg2', 'bg1', 'icon', 'hp', 'txt_name', 'txt_hp', 'Panel'})
    show('MonsterHeadArea', monster, 0)
    raw('monster', monster, {'bg2', 'bg1', 'icon', 'hp', 'txt_name', 'txt_hp', 'Panel'})
    energy = load_csb(ROOT / 'analysis/battle-ui/EnergyArea.csb')
    show('EnergyArea', energy, 0)
    hud = json.loads((ROOT / 'analysis/battle-ui/hud-in/own-card-area-in.json').read_text('utf8'))['clip']['nodes']
    for node in hud:
        node.setdefault('flip_x', False)
        node.setdefault('visible', True)
    print('Energy slot', [round(v, 2) for v in visual_box(hud, 720, 'Energy')[0]])
    for title, nodes in (('player', player), ('monster', monster)):
        print('-- visual', title)
        for name in ('bg2', 'bg1', 'icon', 'txt_name', 'hp_bg', 'hp', 'txt_hp', 'icon_shield', 'debug_hp'):
            origin, size, flip, visible = visual_box(nodes, 0, name)
            print(f'{name:12} visible={visible} flip={flip} origin=({origin[0]:7.2f},{origin[1]:7.2f}) size=({size[0]:6.2f},{size[1]:6.2f})')
    number = load_csb(ROOT / 'analysis/battle-ui/EnergyNumArea.csb')
    show('EnergyNumArea', number, 0)
    print('-- visual energy')
    for name in ('bg_s2', 'icon_s2', 'energy_icon_s1', 'EnergyNum'):
        origin, size, flip, visible = visual_box(energy, 0, name)
        print(f'{name:16} visible={visible} flip={flip} origin=({origin[0]:7.2f},{origin[1]:7.2f}) size=({size[0]:6.2f},{size[1]:6.2f})')


if __name__ == '__main__':
    main()
