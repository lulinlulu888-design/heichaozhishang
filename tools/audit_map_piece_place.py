"""Show how a maze cell becomes a map-piece position."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from extract_npk import Marshal2  # noqa: E402
from inspect_battle_rules import instructions, read_module, walk_codes  # noqa: E402

relative = 'analysis/assets/decoded/script/01164_1fa9b776.marshal'
raw = (ROOT / relative).read_bytes()
obj = Marshal2(raw).obj()
row = {'output': relative, 'decoded_sha256': hashlib.sha256(raw).hexdigest(),
       'filename': obj['filename'].decode()}
print('module', row['filename'], row['decoded_sha256'])
module = read_module(row)
for path, code in walk_codes(module):
    if code['name'].decode() != 'calculatePiecePos':
        continue
    print('###', code['firstlineno'])
    for ins in instructions(code):
        print(f"  {ins['offset']:04x} {ins['source_line']:4} {ins['opname']:22} arg={ins['argument']} {ins.get('operand')!r}")
