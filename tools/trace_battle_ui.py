"""Trace original fight UI modules to CSB layouts and plist frames, without executing them."""
import hashlib
import json
import plistlib
import re
from pathlib import Path
import inspect_battle_rules as static
from export_elsa_model import extract, write_json
from neox_resource_paths import read_catalogue, lookup_logical
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'


def main():
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    catalogue = read_catalogue(apk)
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    OUT.mkdir(parents=True, exist_ok=True)
    layouts = []
    for name in ('FightMainPanel', 'EnergyArea', 'EnergyNumArea', 'EndArea', 'OwnCardArea', 'FightSmallCard', 'FightSelectedCard', 'kafei', 'EffectCardSelected_SmallCard'):
        if name == 'EffectCardSelected_SmallCard':
            module_path = 'ui_auto\\uires_AllCards_EffectSmallCard_EffectCardSelected_SmallCard.py'
        elif name == 'kafei':
            module_path = 'ui_auto\\uires_AllCards_kafei.py'
        elif name in ('FightSmallCard', 'FightSelectedCard'):
            module_path = f'ui_auto\\uires_AllCards_InFightCards_{name}.py'
        else:
            module_path = f'ui_auto\\uires_FightPanel_{name}.py' if name == 'OwnCardArea' else f'ui_auto\\uires_FightPanel_FightNewPanel_{name}.py'
        row = next(r for r in index if r['filename'] == module_path)
        module = static.read_module(row)
        paths = [v.decode('utf8') for v in module['consts'] if isinstance(v, bytes) and v.endswith(b'.csb')]
        if len(paths) != 1:
            raise ValueError('Ambiguous layout source')
        path = OUT/(name+'.csb')
        source = extract(apk, catalogue, paths[0], path, APK_SHA256)
        # These are byte strings only; not inferred hierarchy, positions or animation frames.
        strings = {}
        for match in re.finditer(rb'[\x20-\x7e]{5,}', path.read_bytes()):
            value = match.group().decode('ascii')
            if value.endswith(('.png', '.plist', '.csb')):
                strings.setdefault(value, []).append(match.start())
        layouts.append(dict(name=name, module_source=row, layout_source=source,
            resource_string_offsets=strings))
    path = OUT/'FightPanel.plist'
    source = extract(apk, catalogue, 'uires/FightPanel.plist', path, APK_SHA256)
    plist = plistlib.loads(path.read_bytes())
    requested = {name for layout in layouts for name in layout['resource_string_offsets'] if name.endswith('.png')}
    found = {name: plist['frames'][name] for name in sorted(requested) if name in plist['frames']}
    missing = sorted(requested-set(found))
    texture = 'uires/'+plist['metadata']['textureFileName']
    write_json(OUT/'layout-links.json', dict(apk_sha256=APK_SHA256, layouts=layouts,
        atlas=dict(source=source, metadata=plist['metadata'], total_frames=len(plist['frames']),
            requested_frames=found, other_atlas_or_unresolved=missing,
            texture_logical_path=texture, direct_texture_matches=lookup_logical(catalogue, texture)),
        evidence_kind='Hash-checked static marshal constants, CSB byte strings and original plist data; no original UI execution',
        unresolved=['CSB hierarchy, positions and animation schema', 'Texture storage path/codec and atlas pixels',
                    'Referenced images outside FightPanel.plist', 'Shared-client UI reconstruction']))
    print(json.dumps(dict(layouts=len(layouts), atlas_frames=len(plist['frames']),
        referenced_images=len(requested), matched_frames=len(found), other_atlas_or_unresolved=len(missing))))


if __name__ == '__main__':
    main()
