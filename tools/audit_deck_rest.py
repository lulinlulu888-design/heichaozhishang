"""Print the left-deck and menu rest boxes from the nested FightPanel CSBs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_head_area_rest import load_csb, show  # noqa: E402
from export_elsa_model import extract  # noqa: E402
from extract_texture_samples import APK_SHA256  # noqa: E402
from neox_resource_paths import read_catalogue  # noqa: E402

apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
catalogue = read_catalogue(apk)
out_dir = ROOT / 'analysis/battle-ui'
for logical in (
    'uires/FightPanel/FightNewPanel/btn_card_ext.csb',
    'uires/FightPanel/FightNewPanel/btn_menu_ext.csb',
):
    name = Path(logical).stem
    target = out_dir / f'{name}.csb'
    extract(apk, catalogue, logical, target, APK_SHA256)
    show(name, load_csb(target), 0)
