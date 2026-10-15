"""Trace Elsa's shipped material inputs and exact shader consumers for a UE port.

This executes only our parsers. It reuses validated extracts and the cached NPK
index; it does not run the original game or modify Unreal assets. New sources
are selected by an exact logical path, not a filename resemblance.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from decode_ktx import parse_ktx
from export_elsa_model import extract, parse_materials, SOURCE_HASHES
from extract_texture_samples import APK_SHA256
from neox_resource_paths import lookup_logical

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/elsa-material'
MAX_SHADERS = 96
MAX_INCLUDE_DEPTH = 5
REA_ROOT = 'ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3'


def canonical(value):
    return re.sub('/+', '/', value.replace('\\', '/')).removeprefix('res/')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')


def decode(payload):
    for encoding in ('utf8', 'gb18030'):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    raise ValueError('Unsupported source encoding')


def source_functions(text):
    """Lexical function spans, deliberately not a compiler/call-graph claim."""
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text, flags=re.S)
    rows = []
    pattern = r'\b(?:inline\s+)?(?:float[1-4]?(?:x[1-4])?|half[1-4]?|void|bool|int|RawData|Vertex|Fragment)\s+(\w+)\s*\([^;{}]*\)\s*(?::\s*\w+\s*)?\{'
    for match in re.finditer(pattern, clean):
        level, end = 1, match.end()
        while level and end < len(clean):
            level += (clean[end] == '{') - (clean[end] == '}')
            end += 1
        if level:
            raise ValueError('Unbalanced shader function: ' + match[1])
        rows.append(dict(name=match[1], start_line=clean[:match.start()].count('\n') + 1,
                         end_line=clean[:end].count('\n') + 1))
    return rows


class Sources:
    def __init__(self, apk, catalogue):
        self.apk, self.catalogue, self.rows, self.cache = apk, catalogue, {}, {}
        directories = ['analysis/elsa-model/shader-evidence', 'analysis/elsa-model/textures',
                       'analysis/tutorial-enemy/shader-evidence', 'analysis/battle-visual/lightmaps/shader',
                       'analysis/characters/shiranui/material-source', 'analysis/unreal/elsa-material/shaders']
        for directory in directories:
            for path in sorted((ROOT / directory).glob('*.provenance.json')):
                row = json.loads(path.read_text('utf8'))
                if row.get('logical_path') and row.get('apk_sha256') == APK_SHA256:
                    key = canonical(row['logical_path'])
                    if key in self.cache and self.cache[key]['sha256'] != row['sha256']:
                        raise ValueError('Conflicting retained sources: ' + key)
                    self.cache.setdefault(key, row)

    def get(self, logical):
        logical = canonical(logical)
        if logical in self.rows:
            return self.rows[logical]
        row = self.cache.get(logical)
        if row:
            if digest(Path(row['sample_path'])) != row['sha256']:
                raise ValueError('Retained source digest mismatch: ' + logical)
        else:
            matches = lookup_logical(self.catalogue, logical)
            if len(matches) != 1:
                item = dict(path=logical, status='missing' if not matches else 'ambiguous', matches=len(matches))
                self.rows[logical] = item
                return item
            target = OUT / 'shaders' / (hashlib.sha256(logical.encode()).hexdigest()[:20] + Path(logical).suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            row = extract(self.apk, self.catalogue, logical, target, APK_SHA256)
        item = dict(path=logical, status='present', source=row)
        self.rows[logical] = item
        return item

    def text(self, logical):
        item = self.get(logical)
        if item['status'] != 'present':
            return None
        text, encoding = decode(Path(item['source']['sample_path']).read_bytes())
        item['text_encoding'] = encoding
        return text


def value(raw):
    try:
        result = [float(p.strip()) for p in raw.split(',')]
        return result[0] if len(result) == 1 else result
    except ValueError:
        return raw


def build():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('APK identity differs from investigated artifact')
    original = json.loads((ROOT / 'analysis/elsa-model/export-report.json').read_text('utf8'))
    if original['apk_sha256'] != APK_SHA256:
        raise ValueError('Elsa source report identity mismatch')
    for key, source in original['sources'].items():
        if digest(Path(source['sample_path'])) != SOURCE_HASHES[key] or source['sha256'] != SOURCE_HASHES[key]:
            raise ValueError('Elsa retained geometry/material changed: ' + key)
    catalogue = json.loads((ROOT / 'analysis/resource-mapping/npk-indices.json').read_text('utf8'))
    sources = Sources(apk, catalogue)
    mtg = parse_materials(Path(original['sources']['mtg']['sample_path']).read_bytes())
    if mtg != original['material_slots']:
        raise ValueError('Current MTG differs from retained slot mapping')
    descriptor_path = ROOT / 'analysis/elsa-model/shader-evidence/compositor-config-index-1241.xml'
    descriptor_source = next(p for p in original['shader_sources'] if p['index'] == 1241)
    if digest(descriptor_path) != descriptor_source['sha256']:
        raise ValueError('Shader compositor descriptor changed')
    descriptor_text, descriptor_encoding = decode(descriptor_path.read_bytes())
    # The shipped descriptor has an unescaped '<' in one CmpFunc attribute.
    # Escape that literal only for our XML parser; preserve raw bytes and hash.
    descriptor = ET.fromstring(descriptor_text.replace('CmpFunc="<="', 'CmpFunc="&lt;="'))
    lighting_models = {p.attrib['Name']: canonical(p.attrib['Code']) for p in descriptor.findall('LightingModels/LightingModel')}
    seeds = set(['shader/built_in/forward_shading.hlsl', 'shader/built_in/common/common.hlsl',
                 'shader/built_in/vertex_fragment_models/model_default.hlsl', 'shader/built_in/common/lighting.hlsl',
                 'shader/built_in/common/material_common.hlsl', 'shader/built_in/material/material_setup_func.hlsl'])
    texture_index = {p['logical_path']: p for p in original['texture_inventory']}
    materials = []
    for material in mtg:
        row = dict(material)
        row['submeshes'] = [p for p in original['material_bindings'] if p['material_slot'] == material['slot']]
        row['explicit_parameters'] = {k: value(v) for k, v in material['params'].items()}
        row['textures'] = []
        for param, logical in material['params'].items():
            if logical not in texture_index:
                continue
            texture = texture_index[logical]
            source = texture['source']
            if digest(Path(source['sample_path'])) != source['sha256']:
                raise ValueError('Elsa retained texture changed: ' + logical)
            ktx = parse_ktx(Path(source['sample_path']).read_bytes())
            if ktx != texture['ktx']:
                raise ValueError('KTX readback changed: ' + logical)
            semantics = next(p['semantic_evidence'] for p in texture['uses'] if p['material_slot'] == row['slot'] and p['parameter'] == param)
            row['textures'].append(dict(parameter=param, logical_path=logical, source=source,
                width=ktx['width'], height=ktx['height'], profile=ktx['profile'],
                colour_reference_uses_texture=any(p['material_slot'] == row['slot'] and p['exported_as_colour'] for p in texture['uses']),
                semantic_evidence=semantics))
        if material['technique']['Type'] == 'Surface':
            surface_path = canonical(material['technique']['Surface'])
            surface = ET.fromstring(sources.text(surface_path)).find('Surface')
            row['material_code'] = canonical(surface.find('Code').attrib['File'])
            row['lighting_code'] = lighting_models[material['technique']['LightingModel']]
            seeds.update([row['material_code'], row['lighting_code']])
            defaults = {}
            for parameter in surface.findall('Resources/Param'):
                if 'Default' in parameter.attrib:
                    defaults[parameter.attrib['Name']] = value(parameter.attrib['Default'])
                elif list(parameter) and all('Default' in child.attrib for child in parameter):
                    defaults[parameter.attrib['Name']] = [value(child.attrib['Default']) for child in parameter]
            row['surface_defaults'] = defaults
            row['effective_static_parameters'] = {**defaults, **row['explicit_parameters']}
            row['surface_macro_defaults'] = {p.attrib['Name']: p.attrib.get('Default') for p in surface.findall('Macro/Param')}
            row['effective_static_macros'] = {**row['surface_macro_defaults'], **material['macros']}
        else:
            row['material_code'] = 'shader/u1shader/eye_ao.hlsl'
            row['effect_definition_candidate'] = 'shader/u1shader/eye_ao.nfx'
            row['effect_resolution_status'] = 'NFX and HLSL text matched; native FX dispatch not executed'
            seeds.update([row['material_code'], row['effect_definition_candidate']])
        materials.append(row)
    queue = [(p, 0) for p in sorted(seeds)]
    visited, shaders = set(), []
    keywords = re.compile(r'Toon|Ramp|Shadow|ColorAdjust|AdjustTone|GenerageTone|OutLine|Outline|InnerLine|FillLight|ContourLight|sss_curvature|GetRawPreintergratedSkin|GetStaticReflection|GetExtReflection|mtl\.emissive|SpecularParam|BackLightParam|GetSpecularFromMaterial|GetDiffuseFromMaterial|DISABLE_SHADOW|SIMPLE_SHADING')
    while queue:
        path, depth = queue.pop(0)
        if path in visited:
            continue
        if len(visited) >= MAX_SHADERS:
            raise ValueError('Focused shader dependency budget exceeded')
        visited.add(path)
        text = sources.text(path)
        if text is None:
            continue
        includes = [canonical(p) for p in re.findall(r'^\s*#\s*include\s+"([^"]+)"', text, re.M)]
        anchors = [dict(line=i, text=line.strip()) for i, line in enumerate(text.splitlines(), 1)
                   if not line.lstrip().startswith('//') and keywords.search(line)]
        shaders.append(dict(path=path, include_depth=depth, includes=includes,
                            function_spans=source_functions(text), semantic_anchors=anchors))
        if depth < MAX_INCLUDE_DEPTH:
            queue.extend((p, depth + 1) for p in includes if p.startswith('shader/'))
    module_specs = [
        dict(name='normal_and_mix_inputs', slots=[1, 2, 3, 4, 5, 7, 8],
             functions=[('shader/built_in/material/material_setup_func.hlsl', 'GetNormal'),
                        ('shader/built_in/material/material_setup_func.hlsl', 'NormalCurvatureToRoughness'),
                        ('shader/built_in/materials/material_common.hlsl', 'MakeMaterialRoughness')],
             requirements=['TEXCOORD_0 repeat filtering, original Tex1 RGB->[-1,1] tangent-space normal',
                           'Use data maps without sRGB decode; original Tex1 alpha is separate fill-light occlusion',
                           'Source TBN uses tangent and mirror sign; current GLB lacks TANGENT',
                           'Skin Tex2.B is 1-curvature; stocking and hair have custom channel semantics']),
        dict(name='skin_lut_transmission', slots=[4, 7, 8],
             functions=[('shader/built_in/materials/material_skin.hlsl', 'GetSSSCurvature'),
                        ('shader/built_in/materials/material_skin.hlsl', 'GetRawPreintergratedSkin'),
                        ('shader/built_in/shading_models/skin.hlsl', 'GetPreintergratedSkin'),
                        ('shader/built_in/shading_models/skin.hlsl', 'DirectLighting'),
                        ('shader/built_in/shading_models/skin.hlsl', 'EnvLighting')],
             requirements=['Original linear LUT, clamp sampler, UV=(0.5*NdotL+0.5,1-Tex2.B)',
                           'Transmission uses SubsurfaceColor*albedo*INV_PI*attenuation; diffuse includes curvature factor',
                           'Head/eye_nei disable shadow-map receive; body uses default macro',
                           'SIMPLE_SHADING==2 branch remains separate; original runtime branch unknown']),
        dict(name='eye_reflection', slots=[5],
             functions=[('shader/built_in/materials/material_eye_cartoon.hlsl', 'getMatCapUV'),
                        ('shader/built_in/materials/material_eye_cartoon.hlsl', 'GetExtReflectionCubeValue'),
                        ('shader/built_in/materials/material_eye_cartoon.hlsl', 'GetStaticReflection'),
                        ('shader/built_in/shading_models/eye_cartoon.hlsl', 'DirectLighting'),
                        ('shader/built_in/shading_models/eye_cartoon.hlsl', 'EnvLighting')],
             requirements=['Opacity=1, roughness=.02; source eye lighting disables direct specular/transmission',
                           'MatCap UV=(viewNormal.x,-viewNormal.y)*.5+.5; source explicitly srgb2linearf3 after linear KTX sample',
                           'Original Intensity=(1,2,0,.15): UV0 eye_hl*2 plus MatCap*.15; environment-probe specular weighted zero',
                           'DISABLE_SHADOW_MAP=TRUE; retain separate eye_ao overlay']),
        dict(name='hair_flow_highlight_transmission', slots=[3],
             functions=[('shader/built_in/materials/material_hair_cartoon.hlsl', 'GetNormal'),
                        ('shader/built_in/materials/material_hair_cartoon.hlsl', 'GetSpecular'),
                        ('shader/built_in/shading_models/hair_cartoon.hlsl', 'HairShading'),
                        ('shader/built_in/shading_models/hair_cartoon.hlsl', 'DirectLighting'),
                        ('shader/built_in/shading_models/hair_cartoon.hlsl', 'EnvLighting')],
             requirements=['Tex3 flow and Z shift build world-space hair tangent; normal XY intensity is Intensity.z',
                           'Tex4 RGB*SpecularColor*SpecularParam.r defines specular colour',
                           'Active direct highlight uses pow(NdotH,SpecularParam.y)*light.anis_spec_intensity',
                           'TT/TRT transmission and BackLightParam are active; commented R-lobe formula is not active',
                           'Tex2.B is hair diffuse gating, not generic metallic reflection']),
        dict(name='stocking_density', slots=[2],
             functions=[('shader/built_in/materials/material_stocking.hlsl', 'GetRoughness'),
                        ('shader/built_in/materials/material_stocking.hlsl', 'GetMetalness'),
                        ('shader/built_in/shading_models/stocking.hlsl', 'calculate_density'),
                        ('shader/built_in/shading_models/stocking.hlsl', 'CalcLightingData'),
                        ('shader/built_in/shading_models/stocking.hlsl', 'EnvLighting')],
             requirements=['Pattern Tex3.R samples UV0*220 with repeat; globalThickness=.5+Tex2.A*1.1; localThickness=.5*pattern',
                           'Density depends on NdotV; mixes cloth albedo and SkinColor, and two roughness lobes',
                           'Original emissive fields carry thickness/pattern/sparse intensity; EnvLighting clears emitted light',
                           'Original metalness field carries skin roughness=MakeMaterialRoughness(Intensity.b), not metallic']),
        dict(name='tone_adjust', slots=[1, 2, 3, 4, 5, 7, 8],
             functions=[('shader/u1shader/exttechnique.hlsl', 'GenerageTone'),
                        ('shader/built_in/forward_shading.hlsl', 'ps_main')],
             requirements=['After lighting/technique/fog, result += max(0,result+x*(result-mid))*y; mid=(maxRGB+minRGB)/2',
                           'Use original per-slot ColorAdjust; this is saturation/intensity addition, not a stepped Toon ramp',
                           'Reference calculation: color(.2,.4,.8), params(.5,.3) -> (.215,.505,1.085), before display tone mapping']),
        dict(name='inner_outline', slots=[1, 2, 3, 4, 5, 7, 8],
             functions=[('shader/u1shader/exttechnique.hlsl', 'CalcOutlineColor')],
             requirements=['Fresnel inner line only when INNERLINE_TECHNIUQE enabled; each Elsa surface default is 0',
                           'OutLineColor/OutLineWidth are serialized, but external geometry outline consumer is not established by this include closure',
                           'GetToonEdge assigns 1; it alone does not establish stepped lighting or a ramp texture'])]
    shader_by_path = {p['path']: p for p in shaders}
    modules = []
    for spec in module_specs:
        row = {**spec, 'status': 'source-traced; UE port not implemented', 'functions': []}
        for path, name in spec['functions']:
            spans = [p for p in shader_by_path[path]['function_spans'] if p['name'] == name]
            if not spans:
                raise ValueError('Expected shader consumer function missing: ' + path + ':' + name)
            source = sources.rows[path]['source']
            lines = sources.text(path).splitlines()
            row['functions'].append(dict(path=path, name=name, source=source,
                occurrences=[dict(**span, text='\n'.join(lines[span['start_line']-1:span['end_line']])) for span in spans]))
        modules.append(row)
    colour_gltf = json.loads((ROOT / 'analysis/elsa-model/gltf.json').read_text('utf8'))
    result = dict(schema_version=1, apk_sha256=APK_SHA256,
        evidence_kind='Local validated extraction and static source interpretation; not shader execution or new REA Evidence',
        retained_rea_root_evidence=REA_ROOT,
        scope=dict(hero_id=1, model='character/player/ailisha/ailisha_yangcheng.gim',
                   max_shader_paths=MAX_SHADERS, max_include_depth=MAX_INCLUDE_DEPTH),
        source_report_sha256=digest(ROOT / 'analysis/elsa-model/export-report.json'),
        descriptor_source=descriptor_source, descriptor_encoding=descriptor_encoding, materials=materials, shaders=shaders,
        colour_reference_attributes=[sorted(p['attributes']) for mesh in colour_gltf['meshes'] for p in mesh['primitives']],
        tangent_status='Current colour reference does not export TANGENT; original default VF consumes tangent and mirror sign. Engine-generated TBN equivalence is unverified.',
        port_modules=modules,
        sources=[sources.rows[p] for p in sorted(sources.rows)],
        limitations=['Original NeoX shader permutations and current runtime macro values were not executed',
                     'Descriptor parsed after escaping its literal CmpFunc less-than; original file bytes are unchanged',
                     'Static effective parameters combine surface defaults with MTG values; runtime overrides remain unknown',
                     'Lexical function spans and include references are not a compiler-resolved call graph',
                     'All raw material colours retain source numbers; native uniform colour-space conversion remains unverified',
                     'TransparentMode/CullMode numeric enums are retained without an assumed UE mapping',
                     'Original skin LUT/hair/stocking algorithms cannot be replaced by generic UE PBR and called identical'])
    write_json(OUT / 'report.json', result)
    print(json.dumps(dict(material_slots=len(materials), unique_textures=len(texture_index),
                         shader_paths=len(shaders), unresolved=[p for p in sources.rows if sources.rows[p]['status'] != 'present'],
                         report=str(OUT / 'report.json')), ensure_ascii=False))
    return result


if __name__ == '__main__':
    build()
