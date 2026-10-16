"""Show which model point becomes the intention anchor."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from extract_npk import Marshal2  # noqa: E402
from inspect_battle_rules import instructions, read_module, walk_codes  # noqa: E402

import hashlib
files = [
    'analysis/assets/decoded/script/02945_4ee6b5b0.marshal',
    'analysis/assets/decoded/script/04652_7bb33dc3.marshal',
    'analysis/assets/decoded/script/05456_90cd8c5b.marshal',
]
for relative in files:
    raw = (ROOT / relative).read_bytes()
    obj = Marshal2(raw).obj()
    print('FILE', relative, obj['filename'])
    row = {'output': relative, 'decoded_sha256': hashlib.sha256(raw).hexdigest(),
           'filename': obj['filename'].decode()}
    module = read_module(row)
    for path, code in walk_codes(module):
        if code['name'].decode() != '_getModelSocketPosition':
            continue
        print('###', code['firstlineno'])
        for ins in instructions(code):
            print(f"  {ins['offset']:04x} {ins['source_line']:4} {ins['opname']:22} arg={ins['argument']} {ins.get('operand')!r}")
