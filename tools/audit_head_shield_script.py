"""List PlayerHeadArea code objects that mention the shield bar."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from inspect_battle_rules import instructions, read_module, walk_codes  # noqa: E402

row = {
    'output': 'analysis/assets/decoded/script/05410_8f4a5e65.marshal',
    'decoded_sha256': 'c0b7e097d82541820ebb3e19c323fe38c43bcdc77386639ff851d8cf08aa592c',
    'filename': 'ui/ui_fight/PlayerHeadArea.py',
}
raw = (ROOT / row['output']).read_bytes()
from extract_npk import Marshal2
obj = Marshal2(raw).obj()
print('filename', obj.get('filename'))
row['filename'] = obj['filename'].decode('utf8')
module = read_module(row)
for path, obj in walk_codes(module):
    names = [n.decode('utf8', 'replace') if isinstance(n, bytes) else str(n) for n in obj['names']]
    consts = []
    for value in obj['consts']:
        if isinstance(value, (bytes, str)) and b'shield' in (value if isinstance(value, bytes) else value.encode()):
            consts.append(value.decode() if isinstance(value, bytes) else value)
    interesting = [n for n in names if 'shield' in n.lower() or 'Shield' in n or n in ('setPercent', 'setVisible', 'setString')]
    name = obj['name'].decode()
    if name in {'setShieldPercent', 'setPvpShieldPercent', 'refreshShield', 'update', 'onChangeShield', '_refreshShieldEffect'}:
        print('###', name, 'line', obj['firstlineno'], 'vars', [v.decode() if isinstance(v, bytes) else v for v in obj['varnames']])
        if obj['firstlineno'] != 1203:
            continue
        for ins in instructions(obj):
            print(f"  {ins['offset']:04x} {ins['source_line']:4} {ins['opname']:22} arg={ins['argument']} {ins.get('operand')!r}")
