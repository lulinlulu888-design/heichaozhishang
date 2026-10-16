"""Show how ModelUIArea places the intention panel."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from extract_npk import Marshal2  # noqa: E402
from inspect_battle_rules import instructions, read_module, walk_codes  # noqa: E402

row = {
    'output': 'analysis/assets/decoded/script/00923_194eb319.marshal',
    'decoded_sha256': 'c336b8dbcaf892c7ce5b48f297d40a6afae70a48caaf59c29aa8d8814b6bc814',
    'filename': 'ui/ui_fight/ModelUIArea.py',
}
raw = (ROOT / row['output']).read_bytes()
row['filename'] = Marshal2(raw).obj()['filename'].decode('utf8')
module = read_module(row)
for path, code in walk_codes(module):
    names = [n.decode('utf8', 'replace') if isinstance(n, bytes) else str(n) for n in code['names']]
    consts = []
    for value in code['consts']:
        if isinstance(value, (bytes, str)):
            text = value.decode() if isinstance(value, bytes) else value
            if 'ntent' in text or 'screen' in text or 'bone' in text or 'head' in text:
                consts.append(text)
    name = code['name'].decode()
    if name != 'setIntenUIPos':
        continue
    print('###', name, code['firstlineno'])
    for ins in instructions(code):
        print(f"  {ins['offset']:04x} {ins['source_line']:4} {ins['opname']:22} arg={ins['argument']} {ins.get('operand')!r}")
