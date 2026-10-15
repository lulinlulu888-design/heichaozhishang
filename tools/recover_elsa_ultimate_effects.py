"""Extract source ultimate event bindings and their explicit resource graph."""
import hashlib
import json
from collections import deque
from pathlib import Path
import xml.etree.ElementTree as ET
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical
from decode_ktx import convert, DEFAULT_DECODER
from inspect_neox_model import parse_model

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Original APK identity changed')
    gim = ROOT / 'analysis/battle-visual/scene-export/source/File_26.gim'
    raw = gim.read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'cec24d79e67c9bc86993d0ab4115f484d6e222f0954252d02d8505899d0eccf7':
        raise ValueError('Original actor binding identity changed')
    tracks = ET.fromstring(raw).findall('.//crit_4')
    if len(tracks) != 1:
        raise ValueError('Ambiguous original crit_4 bindings')
    bindings = [{'event': e.tag, 'triggers': [dict(t.attrib) for t in e]} for e in tracks[0]]
    catalogue = read_catalogue(apk)
    pending = deque(t['ObjectFileName'].replace('\\', '/') for e in bindings for t in e['triggers'] if t.get('ObjectFileName'))
    seen, files, references = set(), [], []
    OUT.mkdir(parents=True, exist_ok=True)
    extensions = {'.sfx', '.gim', '.mtg', '.mesh', '.dds', '.tga', '.png', '.ktx', '.par', '.particle', '.wav', '.ogg', '.nfx', '.fx', '.gisacl'}
    while pending:
        logical = pending.popleft()
        if logical in seen:
            continue
        if len(seen) >= 256:
            raise ValueError('Resource traversal exceeded budget')
        seen.add(logical)
        matches = lookup_logical(catalogue, logical)
        if len(matches) != 1:
            references.append({'path': logical, 'matches': len(matches), 'extracted': False})
            continue
        target = OUT / 'source' / (hashlib.sha256(logical.encode()).hexdigest()[:20] + Path(logical).suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = extract(apk, catalogue, logical, target, APK_SHA256)
        item = {'source': source}
        files.append(item)
        if logical.endswith('.gim'):
            for suffix in ('.mesh', '.mtg'):
                companion = logical[:-4] + suffix
                matches = lookup_logical(catalogue, companion)
                references.append({'parent': logical, 'path': companion, 'matches': len(matches),
                                   'relationship': 'same-stem companion candidate; loader behavior not asserted'})
                if len(matches) == 1:
                    pending.append(companion)
        if logical.endswith('.mesh'):
            model = parse_model(target.read_bytes())
            item['geometry'] = {'vertices': len(model['positions']), 'submeshes': len(model['submeshes'])}
        try:
            tree = ET.fromstring(target.read_bytes().decode('gb18030'))
        except (ET.ParseError, UnicodeDecodeError):
            continue
        item['elements'] = [{'tag': e.tag, 'attributes': dict(e.attrib)} for e in tree.iter()]
        for node in tree.iter():
            for field, value in node.attrib.items():
                ref = (value.split('::', 1)[0] if field == 'TechName' else value).replace('\\', '/')
                if Path(ref).suffix.lower() not in extensions:
                    continue
                matches = lookup_logical(catalogue, ref)
                entry = {'parent': logical, 'tag': node.tag, 'field': field, 'path': ref, 'matches': len(matches)}
                references.append(entry)
                if len(matches) == 1:
                    pending.append(ref)
                elif Path(ref).suffix.lower() in {'.dds', '.tga', '.png'}:
                    candidate = str(Path(ref).with_suffix('.ktx')).replace('\\', '/')
                    entry['containerCandidate'] = candidate
                    entry['containerMatches'] = len(lookup_logical(catalogue, candidate))
                    entry['containerMappingRuntimeVerified'] = False
                    if entry['containerMatches'] == 1:
                        pending.append(candidate)
    result = {'apkSha256': APK_SHA256, 'originalApkExecuted': False, 'bindings': bindings,
              'files': files, 'references': references, 'ueEffectsImplemented': False}
    (OUT / 'bindings.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    textures = [f['source'] for f in files if f['source']['logical_path'].endswith('.ktx')]
    provenance = OUT / 'texture-provenance.json'
    provenance.write_text(json.dumps(textures, ensure_ascii=False, indent=2), 'utf8')
    decoded = convert([Path(s['sample_path']) for s in textures], OUT / 'png', DEFAULT_DECODER,
                      provenance_path=provenance)
    print(json.dumps({'bindings': len(bindings), 'resources': len(files), 'references': len(references), 'report': str(OUT / 'bindings.json')}))
    print(json.dumps({'decodedTextures': len(decoded['textures']), 'verifiedMeshes': sum('geometry' in f for f in files)}))


if __name__ == '__main__':
    main()
