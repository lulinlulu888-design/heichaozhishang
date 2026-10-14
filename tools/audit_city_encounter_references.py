"""Bounded numeric-constant reference scan; no runtime/string/map reference claim."""
import json
from pathlib import Path
from inspect_battle_rules import read_module, walk_codes
from trace_first_encounter import inventory

ROOT = Path(__file__).resolve().parents[1]


def main():
    parsed, errors, hits = 0, [], []
    for index, row in inventory().items():
        try:
            module = read_module(row)
        except Exception as error:
            errors.append(dict(index=index, filename=row['filename'], error=str(error)))
            continue
        parsed += 1
        for path, code in walk_codes(module):
            for offset, value in enumerate(code['consts']):
                if type(value) is int and value == 10405:
                    hits.append(dict(module=index, filename=row['filename'], constant_path=path,
                        constant_index=offset, decoded_sha256=row['decoded_sha256']))
    result = dict(parsed=parsed, errors=errors, hits=hits,
        scope='Exact standalone integer10405 in constant pools, not serialized JSON/text, archive map contents or dynamic references.',
        conclusion='Numeric hits are candidates only. No incoming challenge association established by this scan.')
    destination = ROOT/'analysis/battle-visual/city-scenes/encounter-reference-scan.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(parsed=parsed, errors=len(errors), hits=len(hits))))


if __name__ == '__main__':
    main()
