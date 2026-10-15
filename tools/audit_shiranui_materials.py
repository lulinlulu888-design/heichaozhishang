"""Audit original Shiranui MTG, shader branches and texture inputs without rendering."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from export_elsa_model import extract, parse_materials
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical
from decode_ktx import parse_ktx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/characters/shiranui/material-source'


def canonical(path):
    return re.sub('/+', '/', path.replace('\\', '/')).removeprefix('res/')


def main():
    audit_path = ROOT / 'analysis/characters/shiranui/asset-audit.json'
    audit = json.loads(audit_path.read_text('utf8'))
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256 or audit['apk_sha256'] != APK_SHA256:
            raise ValueError('APK identity mismatch')
    cat = read_catalogue(apk)
    cache = {}
    for directory in ['analysis/elsa-model/shader-evidence', 'analysis/tutorial-enemy/shader-evidence',
                      'analysis/battle-visual/lightmaps/shader', 'analysis/characters/shiranui/source',
                      'analysis/characters/shiranui/material-source']:
        for path in (ROOT / directory).glob('*.provenance.json'):
            row = json.loads(path.read_text('utf8'))
            if row.get('logical_path') and row.get('apk_sha256') == APK_SHA256:
                cache[canonical(row['logical_path'])] = row
    sources = {}

    def get(logical):
        logical = canonical(logical)
        if logical in sources:
            return sources[logical]
        row = cache.get(logical)
        if row:
            raw = Path(row['sample_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Retained source changed: ' + logical)
            result = dict(path=logical, status='present', reused=True, source=row)
        else:
            matches = lookup_logical(cat, logical)
            if len(matches) != 1:
                result = dict(path=logical, status='missing' if not matches else 'ambiguous', matches=len(matches))
                sources[logical] = result
                return result
            target = OUT / (hashlib.sha256(logical.encode()).hexdigest()[:20] + Path(logical).suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            row = extract(apk, cat, logical, target, APK_SHA256)
            result = dict(path=logical, status='present', reused=False, source=row)
        sources[logical] = result
        return result

    def text(logical):
        row = get(logical)
        if row['status'] != 'present':
            return None
        payload = Path(row['source']['sample_path']).read_bytes()
        for encoding in ('utf8', 'gb18030'):
            try:
                decoded = payload.decode(encoding)
                row['text_encoding'] = encoding
                return decoded
            except UnicodeDecodeError:
                pass
        raise ValueError('Unsupported source encoding: ' + logical)

    models = []
    shader_seeds = set(['shader/built_in/common/lighting.hlsl', 'shader/built_in/material/material_setup_func.hlsl'])
    for model in audit['models']:
        mtg = get(model['path'][:-4] + '.mtg')
        materials = parse_materials(Path(mtg['source']['sample_path']).read_bytes(), expected_slots=None)
        for material in materials:
            technique = material['technique']
            surface = technique.get('Surface')
            if surface:
                xml = text(surface)
                if xml is None:
                    raise ValueError('Required surface missing')
                element = ET.fromstring(xml).find('Surface')
                material['surface_parameters'] = [dict(attributes=p.attrib,
                    children=[dict(attributes=c.attrib) for c in p]) for p in element.findall('Resources/Param')]
                material['surface_macro_defaults'] = [p.attrib for p in element.findall('Macro/Param')]
                shader_seeds.add(canonical(element.find('Code').get('File')))
                material['code'] = canonical(element.find('Code').get('File'))
            else:
                logical = canonical(technique['TechName'].split('::')[0])
                material['effect_path'] = get(logical)['path']
                if get(logical)['status'] != 'present' and logical.endswith('.fx'):
                    candidate = logical[:-3] + '.nfx'
                    material['effect_nfx_candidate'] = dict(path=candidate, status=get(candidate)['status'],
                        limitation='Same basename NFX candidate, not proof of runtime .fx resolution')
                    if get(candidate)['status'] == 'present':
                        shader_seeds.add(candidate)
                else:
                    shader_seeds.add(logical)
            textures = []
            for key, value in material['params'].items():
                if not value.lower().endswith(('.dds', '.png', '.tga', '.ktx')):
                    continue
                logical = canonical(value)
                candidate = str(Path(logical).with_suffix('.ktx')).replace('\\', '/')
                row = get(candidate)
                result = dict(parameter=key, original_path=logical, ktx_path=candidate, status=row['status'],
                    interpretation='Same-basename KTX path match; original loader dispatch not executed')
                if row['status'] == 'present':
                    result['ktx'] = parse_ktx(Path(row['source']['sample_path']).read_bytes())
                textures.append(result)
            material['texture_inputs'] = textures
        models.append(dict(path=model['path'], materials=materials))
    queue = [(path, 0) for path in sorted(shader_seeds)]
    shaders = []
    visited = set()
    while queue:
        path, depth = queue.pop(0)
        if path in visited:
            continue
        if len(visited) >= 64:
            raise ValueError('Focused shader dependency budget exceeded')
        visited.add(path)
        raw = text(path)
        if raw is None:
            continue
        includes = [canonical(p) for p in re.findall(r'#\s*include\s+"([^"]+)"', raw)]
        anchors = [dict(line=i, text=line.strip()) for i, line in enumerate(raw.splitlines(), 1)
                   if re.search(r'GetNormal|GetRoughness|GetSpecular|GetOcclusion|GetMetalness|GetSSS|Tex[0-9].*Sample|SIMPLE_SHADING|NORMAL_MAP_ENABLE|NEOX_PUBLISH|USE_FILL_LIGHT|USE_CONTOUR_LIGHT|LightingModel|DirLight|LightChannel|_FurLength|_SpecShift|Preintergrated|sss_curvature|SpecularParam|mtl\.roughness|mtl\.metalness', line)]
        shaders.append(dict(path=path, includes=includes, include_depth=depth, anchors=anchors))
        if depth < 1:
            queue.extend((p, depth + 1) for p in includes if p.startswith('shader/'))
    report = dict(apk_sha256=APK_SHA256, asset_audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                  models=models, shaders=shaders, sources=list(sources.values()),
                  evidence_kind='Local extraction and static source interpretation; not new REA Evidence or runtime',
                  retained_rea_root_evidence='ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3',
                  limitations=['No original shader permutation executed', 'Shader includes traversed one level only',
                               'NFX candidates do not prove FX path mapping', 'No renderer or light configuration changed'])
    destination = ROOT / 'analysis/characters/shiranui/material-audit.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    print(json.dumps(dict(materials=sum(len(m['materials']) for m in models), shaders=len(shaders),
                         present=sum(s['status']=='present' for s in sources.values()),
                         unresolved=[s['path'] for s in sources.values() if s['status']!='present'])))


if __name__ == '__main__':
    main()
