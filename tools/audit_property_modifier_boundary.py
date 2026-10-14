"""Locate modifier symbols without mistaking absent names for absent code."""
import hashlib
import json
import zipfile
from pathlib import Path
from trace_first_encounter import inventory
from inspect_battle_rules import read_module, walk_codes
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]
TOKENS=('addBasicPropModifier','removeBasicPropModifier','delBasicPropModifier')

def main():
    hits=[]; definitions=[]; checked=0; skipped=[]
    for row in inventory().values():
        if not row.get('decoded_sha256'):
            skipped.append(row['index']); continue
        raw=(ROOT/row['output']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['decoded_sha256']: raise ValueError('Changed module')
        checked+=1
        found=[s for s in TOKENS if s.encode() in raw]
        if not found: continue
        hits.append(dict(index=row['index'],filename=row['filename'],sha256=row['decoded_sha256'],tokens=found))
        for path,code in walk_codes(read_module(row)):
            if code['name'].decode() in TOKENS:
                definitions.append(dict(index=row['index'],path=list(path),name=code['name'].decode()))
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256: raise ValueError('Changed APK')
    libraries=[]
    with zipfile.ZipFile(apk) as archive:
        for name in archive.namelist():
            if not name.startswith('lib/') or not name.endswith('.so'): continue
            raw=archive.read(name)
            offsets={}
            for token in TOKENS:
                positions=[]; start=0
                while True:
                    pos=raw.find(token.encode(),start)
                    if pos<0: break
                    positions.append(pos); start=pos+1
                offsets[token]=positions
            libraries.append(dict(member=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),offsets=offsets))
    report=dict(evidence='Local byte/name audit only; not disassembly or original execution',apk_sha256=APK_SHA256,
        python_checked=checked,python_skipped=skipped,python_hits=hits,python_definitions=definitions,libraries=libraries,
        limits=['Exact UTF8 symbol names only; stripping, alternate names, generated bindings and remote server code are not covered.',
                'No symbol match is not evidence of no implementation.',
                'REA open_binary identified ARM ELF libclient; search_strings provider unavailable on this host; no REA search evidence obtained.'])
    dest=ROOT/'analysis/battle-visual/city-scenes/opening-buff/modifier-boundary.json'
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(python_checked=checked,python_hits=hits,definitions=definitions,
                         libraries=len(libraries),native_hits=[r for r in libraries if any(r['offsets'].values())])))

if __name__=='__main__': main()
