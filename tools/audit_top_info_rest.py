"""Print TopInfoArea and left-deck rest boxes in HUD design space."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_head_area_rest import flatten, load_csb, show, visual_box  # noqa: E402
from export_elsa_model import extract  # noqa: E402
from extract_texture_samples import APK_SHA256  # noqa: E402
from neox_resource_paths import read_catalogue  # noqa: E402

LAYOUTS = json.loads((ROOT / 'analysis/battle-ui/health/layouts.json').read_text('utf8'))['layouts']
fight = []
flatten(next(row['tree'] for row in LAYOUTS if row['name'] == 'FightMainPanel'), -1, fight)
show('round slot', fight, 720, {'EnteranceRoundNode', 'RoundNode', 'IntentionTop'})

apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
out = ROOT / 'analysis/battle-ui/TopInfoArea.csb'
catalogue = read_catalogue(apk)
extract(apk, catalogue, 'uires/FightPanel/FightNewPanel/TopInfoArea_ext.csb', out, APK_SHA256)
top = load_csb(out)
show('TopInfoArea', top, 0)
print('-- visual top')
for node in top:
    if node['classname'] not in ('ImageView', 'Text', 'TextBMFont', 'LoadingBar', 'Sprite'):
        continue
    origin, size, flip, visible = visual_box(top, 0, node['name'])
    print(f"{node['name']:20} visible={visible} flip={flip} origin=({origin[0]:8.2f},{origin[1]:8.2f}) "
          f"size=({size[0]:7.2f},{size[1]:7.2f}) text={node.get('text')!r} font={node.get('font_size')} "
          f"res={(node.get('resource') or {}).get('path')}")

hud = json.loads((ROOT / 'analysis/battle-ui/hud-in/own-card-area-in.json').read_text('utf8'))['clip']['nodes']
for node in hud:
    node.setdefault('flip_x', False)
    node.setdefault('visible', True)
print('Panel_LeftDown', [round(v, 2) for v in visual_box(hud, 720, 'Panel_LeftDown')[0]])
index = next(i for i, node in enumerate(hud) if node['name'] == 'Panel_LeftDown')
print('-- left descendants')
for node in hud:
    parent = node.get('parent', -1)
    chain = []
    while parent >= 0:
        chain.append(hud[parent]['name'])
        if hud[parent]['name'] == 'Panel_LeftDown':
            break
        parent = hud[parent].get('parent', -1)
    else:
        continue
    if node['classname'] in ('Node', 'SingleNode', 'Panel', 'ProjectNode') and not node.get('text') and not node.get('resource'):
        continue
    origin, size, flip, visible = visual_box(hud, 720, node['name'])
    print(f"{node['name']:24} {node['classname']:12} origin=({origin[0]:8.2f},{origin[1]:8.2f}) "
          f"size=({size[0]:7.2f},{size[1]:7.2f}) text={node.get('text')!r} res={(node.get('resource') or {}).get('path')}")
