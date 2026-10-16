"""Print the battle side-button rest boxes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_head_area_rest import load_csb, visual_box  # noqa: E402
from export_elsa_model import extract  # noqa: E402
from extract_texture_samples import APK_SHA256  # noqa: E402
from neox_resource_paths import read_catalogue  # noqa: E402

apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
catalogue = read_catalogue(apk)
out = ROOT / 'analysis/battle-ui/FightSideBtnArea.csb'
extract(apk, catalogue, 'uires/FightPanel/FightNewPanel/FightSideBtnArea_ext.csb', out, APK_SHA256)
for name in ('btn_chat_ext.csb', 'btn_record_ext.csb'):
    target = ROOT / 'analysis/battle-ui' / name
    extract(apk, catalogue, 'uires/FightPanel/FightNewPanel/' + name, target, APK_SHA256)
    print('##', name)
    child = load_csb(target)
    for node in child:
        resource = (node.get('resource') or {}).get('path') or ''
        print(f"  {node['name']:20} {node['classname']:12} pos={node.get('position')} size={node.get('size')} "
              f"text={node.get('text')!r} font={node.get('font_size')} {resource}")
fight = load_csb(ROOT / 'analysis/battle-ui/FightMainPanel.csb')
side = load_csb(out)
merged = list(fight)
side_index = next(i for i, node in enumerate(fight) if node['name'] == 'SideBtnArea')
index_of = {}
for node in side:
    if node['parent'] < 0:
        index_of[side.index(node)] = side_index
        continue
    copied = dict(node)
    copied['parent'] = index_of[node['parent']]
    index_of[side.index(node)] = len(merged)
    merged.append(copied)
for label, filename in (('Chat', 'btn_chat_ext.csb'), ('Record', 'btn_record_ext.csb')):
    button = load_csb(ROOT / 'analysis/battle-ui' / filename)
    host = next(i for i, node in enumerate(merged) if node['name'] == label and node.get('project_path'))
    button_index = {}
    for node in button:
        if node['parent'] < 0:
            button_index[button.index(node)] = host
            continue
        copied = dict(node)
        copied['name'] = label + '/' + node['name']
        copied['parent'] = button_index[node['parent']]
        button_index[button.index(node)] = len(merged)
        merged.append(copied)
    origin, size, flip, visible = visual_box(merged, 720, label + '/Img_hand')
    expected = (16, 292) if label == 'Chat' else (16, 362)
    if (round(origin[0], 2), round(origin[1], 2)) != expected or size != (56, 56) or not visible:
        raise SystemExit(f'{label} box changed: {origin} {size} {visible}')
    print(f'{label} Img_hand design origin=({origin[0]:.2f},{origin[1]:.2f}) size=({size[0]:.2f},{size[1]:.2f})')
