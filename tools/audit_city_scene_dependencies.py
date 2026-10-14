"""Trace city scene XML/model/material/texture references without executing game code."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue, lookup_logical

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/city-scenes'
PATH = re.compile(r'^(?:character|model|effects|scene|shader|texture)/[^\r\n]+\.[A-Za-z0-9]+$')


def main(scene_names=('city_battle_1', 'city_battle_2'), output=None):
    global OUT
    if output is not None:
        OUT = Path(output)
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    records, scenes, queue = {}, [], []
    def enqueue(logical):
        logical = logical.replace('\\', '/')
        if logical not in records:
            records[logical] = dict(path=logical, status='pending', references=[])
            queue.append(logical)
        return logical
    for name in scene_names:
        scenes.append(enqueue(f'scene/{name}/{name}.scn'))
    while queue:
        if len(records) > 1500:
            raise ValueError('Dependency traversal exceeded reviewed bound')
        path = queue.pop(0)
        record = records[path]
        suffix = Path(path).suffix.lower()
        candidates = [path]
        if suffix in ('.dds', '.tga', '.png'):
            candidates.append(path.rsplit('.', 1)[0] + '.ktx')
        matches = [(p, lookup_logical(catalogue, p)) for p in candidates]
        available = [(p, rows) for p, rows in matches if rows]
        record['lookupCandidates'] = [dict(path=p, matches=rows) for p, rows in matches]
        if not available:
            record['status'] = 'missing'
            continue
        # Prefer exact resource; texture extension conversion is explicitly recorded.
        selected, rows = available[0]
        if len(rows) != 1:
            record['status'] = 'ambiguous'
            continue
        target = OUT / 'source' / (hashlib.sha256(selected.encode()).hexdigest()[:20] + Path(selected).suffix)
        source = extract(apk, catalogue, selected, target, APK_SHA256)
        payload = target.read_bytes()
        record.update(status='present', selectedPath=selected, source=source,
                      localPath=str(target.relative_to(ROOT)), sha256=hashlib.sha256(payload).hexdigest())
        if suffix == '.mesh':
            try:
                parsed = parse_model(payload, preserve_nonunit_normals=True)
                record['mesh'] = {k:parsed[k] for k in ('vertex_count','triangle_count','submesh_count',
                    'coverage_bytes','size','bounds','normal_length_range','normal_policy')}
            except (ValueError, KeyError) as error:
                record['meshError'] = str(error)
        if suffix not in ('.scn', '.gim', '.mtg', '.sfx'):
            record['coverage'] = 'leaf; payload extracted, internal references not parsed'
            continue
        try:
            xml = ET.fromstring(payload)
        except ET.ParseError:
            record['coverage'] = 'non-XML; internal references unresolved'
            continue
        record['coverage'] = 'XML path attributes and text; GIM sibling mesh/material convention'
        if suffix == '.scn':
            record['cameras'] = [e.attrib for e in xml.iter('Camera')]
            record['instances'] = [e.attrib for e in xml.iter('model')]
        for element in xml.iter():
            for key, value in list(element.attrib.items()) + [('text', (element.text or '').strip())]:
                normalized = value.replace('\\', '/').split('::', 1)[0]
                if PATH.fullmatch(normalized):
                    record['references'].append(dict(tag=element.tag, attribute=key,
                        original=value, target=enqueue(normalized), evidence='explicit XML'))
        if suffix == '.gim':
            for extension in ('.mesh', '.mtg'):
                record['references'].append(dict(target=enqueue(path[:-4]+extension),
                    evidence='GIM sibling naming convention; presence/parse checked separately'))
    report = dict(apkSha256=APK_SHA256, evidence='Static extraction and XML parsing, no original execution',
        scenes=scenes, records=list(records.values()),
        counts={status:sum(r['status']==status for r in records.values()) for status in ('present','missing','ambiguous')},
        limitations=['Shader includes, non-XML effects, animations and implicit runtime dependencies are not fully traversed.',
                     'Texture .ktx fallback is a candidate mapping recorded explicitly; render equivalence not proven.',
                     'Missing editor/test actors may not be required at runtime; no automatic substitution made.'])
    (OUT / 'dependencies.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(counts=report['counts'], missing=[r['path'] for r in records.values() if r['status']=='missing'],
                         meshErrors=[r['path'] for r in records.values() if 'meshError' in r]), ensure_ascii=False))


if __name__ == '__main__':
    main()
