"""Print the source intention panel boxes and the script nodes that fill them."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_head_area_rest import load_csb, show, tree_nodes  # noqa: E402
from export_elsa_model import extract  # noqa: E402
from extract_npk import Marshal2  # noqa: E402
from extract_texture_samples import APK_SHA256  # noqa: E402
from inspect_battle_rules import instructions, read_module, walk_codes  # noqa: E402
from neox_resource_paths import read_catalogue  # noqa: E402

apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
catalogue = read_catalogue(apk)
out = ROOT / 'analysis/battle-ui/intention'
out.mkdir(parents=True, exist_ok=True)
for logical in (
    'uires/FightPanel/SimUI/IntentionArea_ext.csb',
    'uires/FightPanel/SimUI/IntentionItem_type1_ext.csb',
    'uires/FightPanel/SimUI/IntentionItem_type2_ext.csb',
):
    target = out / (Path(logical).stem + '.csb')
    extract(apk, catalogue, logical, target, APK_SHA256)
    show(target.stem, load_csb(target), 0)

fight = tree_nodes('FightMainPanel')
show('intention slot', fight, 720, {'IntentionTop', 'EnteranceMonsterHeads', 'HPArea_right_1'})

row = {
    'output': 'analysis/assets/decoded/script/01695_2e37df00.marshal',
    'decoded_sha256': '17e4a1254a3ae19b3ace97726c26b818d088229f8ca079d52991ae643d602bc3',
    'filename': 'ui/ui_fight/IntentionArea.py',
}
raw = (ROOT / row['output']).read_bytes()
obj = Marshal2(raw).obj()
row['filename'] = obj['filename'].decode('utf8')
module = read_module(row)
print('module', row['filename'])
for path, code in walk_codes(module):
    names = [n.decode('utf8', 'replace') if isinstance(n, bytes) else str(n) for n in code['names']]
    name = code['name'].decode()
    if name not in {'setAreaPosition', 'arrange'}:
        continue
    print('###', name, code['firstlineno'])
    for ins in instructions(code):
        print(f"  {ins['offset']:04x} {ins['source_line']:4} {ins['opname']:22} arg={ins['argument']} {ins.get('operand')!r}")
