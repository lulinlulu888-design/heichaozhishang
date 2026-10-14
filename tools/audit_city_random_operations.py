"""Bounded symbol presence audit, not a proof that original AI code is absent."""
import hashlib
import json
from pathlib import Path
from trace_first_encounter import inventory
from inspect_battle_rules import read_module, walk_codes

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ['RandomSkillAndShowIntentions', 'RoundMod', 'ShowSkillIntentions',
          'forceChooseRandomSkillAndShowIntentions', 'RANDOM_SKILL_IDS']

def main():
    checked, skipped, hits = [], [], []
    for row in inventory().values():
        if not row.get('decoded_sha256'):
            skipped.append(dict(index=row['index'], reason='No decoded hash'))
            continue
        raw = (ROOT / row['output']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['decoded_sha256']:
            raise ValueError('Changed decoded module')
        checked.append(dict(index=row['index'],sha256=row['decoded_sha256']))
        found = [s for s in TOKENS if s.encode() in raw]
        if not found or 'cdata' in row['filename']:
            continue
        names = []
        for path, obj in walk_codes(read_module(row)):
            refs = [s for s in found if s.encode() in obj['names']]
            if refs:
                names.append(dict(name=obj['name'].decode('utf8'),constant_path=list(path),
                                  references=refs,bytecode_sha256=hashlib.sha256(obj['bytecode']).hexdigest()))
        hits.append(dict(source=row,raw_tokens=found,code_name_references=names))
    result = dict(evidence='Local hash-verified decoded Python symbol audit; no REA or original execution',
        tokens=TOKENS,checked=checked,skipped=skipped,non_cdata_hits=hits,
        limits=['Exact symbol scan only; renamed/dynamic/native/server implementation is not ruled out.',
                'Presence of an invocation does not supply its implementation or PRNG semantics.',
                'Table data excluded from hit details; covered module hashes retained.'])
    out=ROOT/'analysis/battle-visual/city-scenes/random-operations.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(checked=len(checked),skipped=skipped,hits=[h['source']['index'] for h in hits])))

if __name__ == '__main__': main()
