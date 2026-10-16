"""Print EndArea idle-state nodes in the same design space as HczsSourceUiTimeline."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = json.loads((ROOT / 'analysis/battle-ui/end-turn/timeline.json').read_text('utf8'))['hierarchy']


def flatten(node, parent, out):
    index = len(out)
    entry = {k: v for k, v in node.items() if k != 'children'}
    entry['parent'] = parent
    out.append(entry)
    for child in node.get('children', []):
        flatten(child, index, out)

nodes = []
flatten(TREE, -1, nodes)

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

def design_point(node_list, name, design_origin_y):
    mats = []
    for node in node_list:
        local = transform(node)
        parent = node['parent']
        mats.append(local if parent < 0 else compose(mats[parent], local))
    index = next(i for i, node in enumerate(node_list) if node['name'] == name)
    node = node_list[index]
    flip_x = node.get('flip_x', False)
    quad = (-1 if flip_x else 1, 0, 0, -1, node['size'][0] if flip_x else 0, node['size'][1])
    source_to_design = (1, 0, 0, -1, 0, design_origin_y)
    return apply(compose(source_to_design, compose(mats[index], quad)), 0, 0)

hud = json.loads((ROOT / 'analysis/battle-ui/hud-in/own-card-area-in.json').read_text('utf8'))['clip']['nodes']
for node in hud:
    node['rotation_skew'] = node['rotation_skew']
print('EndTurnArea design origin', [round(v, 4) for v in design_point(hud, 'EndTurnArea', 720)])

globals_ = []
for node in nodes:
    local = transform(node)
    parent = node['parent']
    global_ = local if parent < 0 else compose(globals_[parent], local)
    globals_.append(global_)
    flip_x = node.get('flip_x', False)
    quad = (-1 if flip_x else 1, 0, 0, -1, node['size'][0] if flip_x else 0, node['size'][1])
    source_to_design = (1, 0, 0, -1, 0, 0)
    design = compose(source_to_design, compose(global_, quad))
    if node['name'] in ('bg_s1', 'icon_s1', 'txt_s1', 'Node_s1', 'btn'):
        origin = apply(design, 0, 0)
        print(node['name'], 'design_origin', [round(v, 4) for v in origin], 'size', node['size'],
              'alpha', node['alpha'], 'scale', node['scale'])
