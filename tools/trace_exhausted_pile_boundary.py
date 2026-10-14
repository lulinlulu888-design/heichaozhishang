"""Bounded exact-reference survey for exhaustion routing; no target execution."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/piles/exhaustion'
TERMS = {'ExhaustedCardPileChangeAction', 'CONSUMED_PILE', 'exhaustedPile',
         'ExhaustedPile', 'moveCards', 'dstPileType'}


def main():
    rows = json.loads((static.SCRIPT / 'index.json').read_text('utf8'))
    OUT.mkdir(parents=True, exist_ok=True)
    references = []
    for row in rows:
        raw = (ROOT / row['output']).read_bytes()
        if not any(term.encode() in raw for term in TERMS):
            continue
        module = static.read_module(row)
        for path, code in static.walk_codes(module):
            instructions = list(static.instructions(code))
            hits = [dict(instruction=ins, window=instructions[max(0, n-3):n+5])
                    for n, ins in enumerate(instructions)
                    if isinstance(ins.get('operand'), str) and ins['operand'] in TERMS]
            if hits:
                references.append(dict(source=row, method=code['name'].decode(),
                    constant_path=path, bytecode_sha256=hashlib.sha256(code['bytecode']).hexdigest(), hits=hits))
    report = dict(evidence_kind='Hash-checked local static extraction; not original runtime or REA Evidence',
                  search_terms=sorted(TERMS), indexed_modules=len(rows), references=references,
                  limitations=['Exact decoded names/literals only; dynamic references, native code and server code are not covered.',
                               'Client receipt of a destination does not prove how that destination was chosen.'])
    (OUT / 'references.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    by_id = {row['index']: row for row in rows}
    actions = static.export(by_id[5026])
    (OUT / 'draw-discard-actions.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2), 'utf8')
    def method(path):
        return next(code for code in actions['code_objects'] if code['constant_path'] == path)
    equivalence = []
    for slot in (1, 2):
        exhaust, remove = method([23, slot]), method([25, slot])
        # Bytecode indexes alone are insufficient: compare their resolved operands too.
        # Source line numbers differ between class definitions.
        def semantic(code):
            return [{key: value for key, value in ins.items() if key != 'source_line'}
                    for ins in code['instructions']]
        same = semantic(exhaust) == semantic(remove)
        if not same:
            raise ValueError('Exhaust/Remove routing equivalence changed; review evidence')
        equivalence.append(dict(method=exhaust['name'], exhaust_path=exhaust['constant_path'],
            remove_path=remove['constant_path'], exhaust_bytecode_sha256=exhaust['bytecode_sha256'],
            remove_bytecode_sha256=remove['bytecode_sha256'], resolved_instructions_equal=same))
    (OUT / 'remove-exhaust-equivalence.json').write_text(json.dumps(dict(
        source=actions['source'], comparisons=equivalence,
        observation='Both client action handlers route HAND_CARD_PILE to CONSUMED_PILE from Args.cardIDs.',
        limitation='This does not establish identical server semantics, keyword policy, or permanent removal behavior.'
    ), ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(modules=len({r['source']['index'] for r in references}), methods=len(references))))
    for ref in references:
        print(ref['source']['index'], ref['method'], ','.join(sorted({h['instruction']['operand'] for h in ref['hits']})))


if __name__ == '__main__':
    main()
