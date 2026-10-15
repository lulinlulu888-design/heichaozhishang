"""Prepare source-pinned entrance model geometry, linear textures and SFX recipe.

Offline data conversion only. Three models must pass the shared exact-AABB
gate. The fourth remains excluded; no geometry scaling or shader port is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

from decode_ktx import convert, parse_ktx, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import bind_materials, extract, parse_materials, pack_glb, split_glb
from export_elsa_normal_slash import xml_tree
from export_neox_gltf import encode_glb
from extract_texture_samples import APK_SHA256
from inspect_neox_model import ModelError, parse_model
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
SFX = 'effects/player/001/fight_idle_show_chuchang.sfx'
MODEL_PREFIX = 'effects/modeleffect/char/001/'
MODEL_PINS = {
    'nengliangkuosan': (
        '3bb9ec549df8cbc546c1100f2bdfd50217b511fe95d4e3c5fe3a6b244de88297',
        '819d68cf09777427300e68225186bbf016d6a67e9cc41a40ccd6399cffc8a2cd',
        '27bf54c76cac166b2b77ac93c53e79418223d239df084e5b97b2b36051ed6415'),
    'fight_idle_show_smoke': (
        '8960846e4384bbd36857e973ac075d8a0648652a101ceed4adcc0c3ce6507c01',
        '886a08d6ab6aacb73b45913e92a13178edad092caf0836d5135c0e5acb560e19',
        'ff143fe1700d6a8a411a3f7eb1e110028243034abadde54517ddcad616c7a765'),
    'fight_idle_show_kuosan': (
        '011c5e91d6fbe4e45aa866127f38ebddf1a481396bb748abdfe65affe9e0c845',
        '81a84a2aea5c610387b067a0a430fb222339aa58c34cb2f81ed51b14f91110f3',
        '150f8544e51e4bed1875c5db10c32d86e1cfef9bcfce24eebd7890851f9907d9'),
    'fight_idle_show_nengliang': (
        'd1f5411f6a595f09216ca836f08dc6c767aab107f7118985583c24dddb3b7681',
        '5a7bc4ff0b249367293981a947df01360dd8fa062716cb42a206beaba9c53ead',
        'f0c37a1dd3509d26881830342359004bd0e3a1e0190d82c6bf2a4f6c5fb35d56'),
}
PINS = {MODEL_PREFIX+name+'.'+suffix: digest for name, values in MODEL_PINS.items()
        for suffix, digest in zip(('gim', 'mesh', 'mtg'), values)}
PINS.update({
    SFX: '4be30fddd6c2e6c0d612e33e691ac018ca0bb37699c74a54484cd32cfe2c6f5d',
    'shader/lancer3.fx': 'b5c2bde9aea9cbcf33eed81f3a4c42ed16ec8d54761a42fafc2d513a204a0993',
    'shader/shaderlib/function.fxl': 'c08dae6dd5503a004e6cef264085ebe091a98199fbd3c038581d583858423e72',
    'effects/tex/impact/impact007_32.ktx': '3443bab06f196c18f4b5643d5d88ea88763930c9b8713b92c17b65464fe091ae',
    'effects/tex/wenli/0000150_a.ktx': 'a31bf29e3586aad19afa927dfbe91b7a5368cab28e56784f2766eac3bb8a489e',
    'effects/tex/cartoon/eye_lwy_t_mul_81_single.ktx': '60450a29977c423be268bae4a5e5b879e2535a7f76feac14ffd7e37b32b5c5c0',
    'effects/tex/char/liuguang.ktx': 'f02b8121b77271b8c9b2dbf6a2e06d410abe306fe32e529de239984d0b58bfcb',
    'effects/tex/wenli/distort_07.ktx': '6ab66c1e5ec72425766f41026908d24bb277831a9bb82878e9745f6f44eb5e70',
    'effects/tex/wenli/noise_wind_04.ktx': '4b4f0fb82f5d53ad608a177551837a4fc3313c7c7741d46e764b093aa78697c8',
    'effects/tex/wenli/noise_159_3430.ktx': '8dd8ab2af1eb714bb6bd4e0d248bb8332dc46beca0cd9b2099f904e2315ec078',
    'effects/tex/wenli/noise_gq_rlt_01.ktx': '8a3219bc64a2859422ab1fe667a290992279adbfce9d41b32de420a9d1fc6ae0',
    'effects/tex/mask/01_5.ktx': 'de868db496fa7191e88098e98daf8118121e8c1b85d8cd22c2621f28f6974545',
    'effects/tex/wenli/titling_speedline.ktx': '5eea15e61df6dd3fbcf02c37982f6a7b2bee1cea475a22dbfd708b41aaf09c35',
})
APPROVED = tuple(MODEL_PINS)[:3]
EXCLUDED = 'fight_idle_show_nengliang'
LIMITATIONS = [
    'No original APK/NeoX code executed and no UE import, shader execution or visual acceptance performed.',
    'Only the first three model geometries passed the unchanged exact-AABB gate. The energy column is source data only; its conservative-bound interpretation is unproven.',
    'TrackType, DirType, CycleType, ChangeType, Interpolator, TrackFixPoint.Forward, InheritPrsOnce and native render/blend enums are retained literally; their runtime semantics are not established here.',
    'Frame.Time values are raw source literals; normalized-time mapping, TimeLen/lifespan interaction and parent-versus-child lifetime termination are not guessed.',
    'ColorKeyFrame byte component order, interpolation color space, inherited color/alpha and combination of ScaleFrame with ancestor TrackScale remain unverified.',
    'alphaMtl is a shader semantic, not a literal default. Absence of a local override does not establish a default of 1.',
    'All recovered textures are linear KTX. Lancer3 explicitly converts color texture/tint via srgb2linearf3; function.fxl defaults to SIMPLE (square), but original runtime global macro overrides remain unknown.',
    'GLBs preserve source XYZ/units/winding/UV0 and contain original material-slot metadata only. Shader implementation and the established UE coordinate adapter are separate.',
    'Complete SFX XML is retained, but sprite/particle texture dependencies, emission behavior, camera shake and all runtime attachment behavior are outside this model-only resource closure.',
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    temp = path.with_suffix(path.suffix+'.pending')
    temp.write_text(text, 'utf8')
    temp.replace(path)


def pinned(logical, raw):
    if logical not in PINS or sha(raw) != PINS[logical]:
        raise ValueError('unreviewed or changed source: '+logical)
    return raw


def make_recipe(raw):
    pinned(SFX, raw)
    root, elements = xml_tree(raw)
    kinds = {'Dummy', 'Model', 'Sprite', 'ParticleSystem', 'FxCamera'}
    layers = []
    for element in elements.values():
        if element['tag'] not in kinds:
            continue
        ancestors = []
        parent = element['xpath'].rsplit('/', 1)[0]
        while parent:
            ancestor = elements[parent]
            if ancestor['tag'] in kinds or ancestor['tag'] == 'FxGroup':
                ancestors.append({'xpath': parent, 'tag': ancestor['tag'], 'line': ancestor['line'],
                                  'attributes': ancestor['attributes']})
            parent = parent.rsplit('/', 1)[0]
        ancestors.reverse()
        owned = [x for path, x in elements.items() if path.startswith(element['xpath']+'/')
                 and not any(path.startswith(child['xpath']+'/') or path == child['xpath']
                             for child in element['children'] if child['tag'] in kinds)]
        curves = [{'xpath': x['xpath'], 'tag': x['tag'], 'line': x['line'], 'attributes': x['attributes'],
                   'frames': [{'line': c['line'], **c['attributes']} for c in x['children'] if c['tag'] == 'Frame']}
                  for x in owned if any(c['tag'] == 'Frame' for c in x['children'])]
        layers.append({'xpath': element['xpath'], 'tag': element['tag'], 'line': element['line'],
                       'attributes': element['attributes'], 'ancestors': ancestors, 'curves': curves,
                       'trackNodes': [c for c in element['children'] if c['tag'].startswith('Track')],
                       'uniformSemantics': [x for x in owned if x['tag'] == 'Semantic']})
    models = [l for l in layers if l['tag'] == 'Model']
    names = [Path(l['attributes']['ModelName'].replace('\\', '/')).stem for l in models]
    if names != list(MODEL_PINS):
        raise ValueError('original four model order/references changed')
    counts = {kind: sum(l['tag'] == kind for l in layers) for kind in sorted(kinds)}
    if counts != {'Dummy': 6, 'FxCamera': 1, 'Model': 4, 'ParticleSystem': 2, 'Sprite': 6}:
        raise ValueError('original SFX layer count changed')
    return {'schema': 'hczs-elsa-entrance-fx-recipe-v1', 'sourcePath': SFX, 'sourceSha256': sha(raw),
            'encoding': 'gb18030', 'linePolicy': 'CRCRLF/CRLF normalized to LF before XML line counting.',
            'group': root['attributes'], 'layerCounts': counts, 'layers': layers, 'xmlTree': root,
            'timingPolicy': 'Raw source literals only; no frame-to-seconds or lifetime interpretation applied.',
            'limitations': LIMITATIONS}


def shader_parameters(raw, helper):
    pinned('shader/lancer3.fx', raw)
    pinned('shader/shaderlib/function.fxl', helper)
    text = raw.decode('gb18030')
    includes = re.findall(r'^\s*#include\s+"([^"]+)"', text, re.M)
    if includes != ['shaderlib/function.fxl'] or re.search(r'^\s*#include', helper.decode('gb18030'), re.M):
        raise ValueError('shader literal include closure changed')
    defaults = {}
    for match in re.finditer(r'^\s*(float[234]?|int)\s+(\w+)\s*<[^>]*>\s*=\s*([^;]+);', text, re.M):
        literal = match[3].strip().strip('{}')
        parts = [s.strip().removesuffix('f') for s in literal.split(',')]
        if not all(re.fullmatch(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?', s) for s in parts):
            raise ValueError('nonliteral shader initializer')
        width = int(match[1][-1]) if match[1][-1].isdigit() else 1
        if len(parts) != width or match[2] in defaults:
            raise ValueError('duplicate/mismatched shader default')
        values = [float(s) for s in parts]
        defaults[match[2]] = {'literal': match[3].strip(), 'value': values[0] if width == 1 else values,
                             'line': text[:match.start()].count('\n')+1}
    semantic = re.search(r'float\s+alphaMtl\s*:\s*AlphaMtl\s*;', text)
    if semantic is None:
        raise ValueError('alphaMtl semantic changed')
    patterns = ['float3 g_colFloatingColor1_linear = srgb2linearf3(g_colFloatingColor1.xyz);',
                'float4 local_0 = tex2D(sam_OTHER3, psIN.v_texture5.xy);',
                'local_17.rgb = srgb2linearf3(local_17.rgb);',
                'float3 local_37 = mul(g_colFloatingColor2_linear, local_34.x);',
                'float mask_rate = pow(local_68.x + 0.01, alpha_mask_intensity);',
                'float local_72 = local_71.x - g_DissolveStrength;',
                'float local_73 = local_72 + 0.1f;', 'float local_74 = local_73 * 5.0f;',
                'float local_76 = pow(local_75, g_dissolve_hardness);',
                'float local_80 = local_79 * alphaMtl;']
    lines = text.splitlines()
    evidence = []
    for token in patterns:
        hits = [{'line': i+1, 'text': line} for i, line in enumerate(lines) if token in line]
        if len(hits) != 1:
            raise ValueError('shader expression changed: '+token)
        evidence.extend(hits)
    helper_text = helper.decode('gb18030')
    if '#define SRGB_2_LINEAR_TYPE SRGB_2_LINEAR_TYPE_SIMPLE' not in helper_text or 'return rgb*rgb;' not in helper_text:
        raise ValueError('source color conversion default changed')
    return {'path': 'shader/lancer3.fx', 'sha256': sha(raw), 'include': {
                'literal': includes[0], 'resolvedPath': 'shader/shaderlib/function.fxl', 'sha256': sha(helper)},
            'literalDefaults': defaults, 'semanticParameters': {'alphaMtl': {
                'semantic': 'AlphaMtl', 'literalDefault': None, 'line': text[:semantic.start()].count('\n')+1}},
            'expressionEvidence': evidence, 'colorPolicy': 'Retain original linear PNG samples. Source srgb2linearf3 default SIMPLE squares RGB; do not preapply UE sRGB decoding and square again.',
            'portDifferencesFromLancer2': ['Flow1 uses full RGB, not the slash port single R channel.',
                'Flow2 uses converted Tex1.R with its own tint/strength.',
                'Dissolve uses pow(saturate((D.r-strength+0.1)*5),hardness).',
                'ALPHA_MASK uses pow(mask.R+0.01,intensity) on the mask-specific UV.',
                'No universal literal alphaMtl default; SFX values are dynamic semantic overrides.']}


def verify_geometry(glb, raw_mesh, model):
    doc, binary = split_glb(glb)
    primitive, = doc['meshes'][0]['primitives']
    spans = {r['name']: r for r in model['ranges']}
    rows = []
    for name, span, width, component, count in [
            ('POSITION', 'positions_float32', 3, 5126, model['vertex_count']),
            ('NORMAL', 'normals_float32', 3, 5126, model['vertex_count']),
            ('TEXCOORD_0', 'submesh_0_uv_0', 2, 5126, model['vertex_count']),
            ('indices', 'triangle_indices_uint16', 1, 5123, model['triangle_count']*3)]:
        idx = primitive['indices'] if name == 'indices' else primitive['attributes'][name]
        accessor = doc['accessors'][idx]
        view = doc['bufferViews'][accessor['bufferView']]
        if (accessor['componentType'], accessor['count'], accessor['type']) != (component, count, {1:'SCALAR', 2:'VEC2', 3:'VEC3'}[width]):
            raise ValueError('geometry accessor layout changed')
        start = view.get('byteOffset', 0)+accessor.get('byteOffset', 0)
        original = raw_mesh[spans[span]['offset']:spans[span]['offset']+spans[span]['size']]
        actual = binary[start:start+spans[span]['size']]
        if start % 4 or view.get('byteStride') or accessor.get('normalized') or accessor.get('sparse') or original != actual:
            raise ValueError('exported geometry differs from original bytes: '+name)
        rows.append({'semantic': name, 'sourceOffset': spans[span]['offset'], 'bytes': len(original),
                     'sha256': sha(original), 'byteIdentical': True})
    if any(k in doc['nodes'][0] for k in ('matrix', 'rotation', 'translation', 'scale')):
        raise ValueError('unexpected geometry transform')
    if primitive['material'] != 0 or len(doc['materials']) != 1:
        raise ValueError('source material-slot mapping changed')
    return rows


def prepare_material_inputs(models, recipe, shader, converted):
    """Port only the three observed single-flow lancer3 pre-HDR branches."""
    decoded = {r['provenance']['logical_path']: r for r in converted['textures']}
    defaults = {key: row['value'] for key, row in shader['literalDefaults'].items()}
    records = []
    for model in models:
        original, = model['materials']
        expected = {'DISSOLVE_EFFECT': 'TRUE'} if model['name'] == 'nengliangkuosan' else {}
        if original['macros'] != expected:
            raise ValueError('unsupported entrance material macro branch')
        layer, = [l for l in recipe['layers'] if l['tag'] == 'Model' and
                  l['attributes']['ModelName'].replace('\\', '/') == model['gim']]
        curves = {c['tag']: c for c in layer['curves']}
        effective = dict(defaults)
        for key, literal in original['params'].items():
            if key.startswith('Tex'): continue
            parts = literal.split(',')
            if not all(re.fullmatch(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?', x.strip()) for x in parts):
                raise ValueError('nonliteral material parameter')
            numbers = [float(x) for x in parts]
            effective[key] = numbers[0] if len(numbers) == 1 else numbers

        def number(key):
            value = effective[key]
            if not isinstance(value, (float, int)):
                raise ValueError('expected scalar parameter '+key)
            return format(value, '.9g')

        def vector(key):
            values = effective[key]
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError('expected float2 parameter '+key)
            return 'float2('+','.join(format(x, '.9g') for x in values)+')'

        # SourceAlpha is never invented from an absent shader default. All three
        # exported layers explicitly have a source alphaMtl curve.
        alpha = curves.get('alphaMtl_Keyframe')
        if not alpha or not alpha['frames']:
            raise ValueError('source layer has no explicit alphaMtl key')
        dynamics = {'EffectTime': 0.0, 'SourceAlpha': float(alpha['frames'][0]['Value']),
                    'SourceTint': effective['g_colFloatingColor1'][:3],
                    'SourceDissolve': effective.get('g_DissolveStrength', 0.0),
                    'SourceStrength': effective['g_fFloatingStrength1']}
        if 'g_fFloatingStrength1_Keyframe' in curves:
            frames = curves['g_fFloatingStrength1_Keyframe']['frames']
            if len(frames) != 1:
                raise ValueError('unexpected strength curve; initial policy requires separate review')
            dynamics['SourceStrength'] = float(frames[0]['Value'])
        if 'g_DissolveStrength_Keyframe' in curves:
            dynamics['SourceDissolve'] = float(curves['g_DissolveStrength_Keyframe']['frames'][0]['Value'])

        lines = ['// Source lancer3 single-flow pre-HDR colour; SIMPLE RGB conversion.',
                 '// Raw linear textures. Output goes to UE linear emissive/opacity.',
                 'float2 distortionUV = UV * '+vector('g_vDistortionTiling')+' + EffectTime * '+vector('g_vDistortionSpeed')+';']
        bindings = [('Color', 'Tex0')]
        distortion = original['params'].get('TexDistortion', '')
        if distortion:
            bindings.append(('Noise', 'TexDistortion'))
            lines.append('float noise = Texture2DSampleLevel(Noise, NoiseSampler, distortionUV, 0).r;')
        elif effective['g_fDistortionStrength1'] == 0:
            lines.append('float noise = 0.0; // Source null distortion texture has a zero multiplier.')
        else:
            raise ValueError('active distortion texture is missing')
        lines += ['float2 flowUV = UV * float2('+number('g_vFloatingTilingU1')+', '+number('g_vFloatingTilingV1')+')'
                  ' + float2(noise, noise) * '+number('g_fDistortionStrength1')+' + EffectTime * '+vector('g_vFloatingSpeed1')+';',
                  'flowUV *= (float2('+number('mirror_u')+', '+number('mirror_v')+') - 0.5) * -2.0;',
                  'float angle = 6.283185307179586 * '+number('rotation_floatTex01')+';',
                  'flowUV = float2(flowUV.x*cos(angle)-flowUV.y*sin(angle), flowUV.x*sin(angle)+flowUV.y*cos(angle))'
                  ' + float2('+number('offset_u')+', '+number('offset_v')+');',
                  'float4 c = Texture2DSampleLevel(Color, ColorSampler, flowUV, 0);',
                  'float3 rgb = (c.rgb * c.rgb) * (SourceTint * SourceTint) * SourceStrength;']
        if expected:
            bindings.append(('Dissolve', 'TexDissolve'))
            lines += ['float2 dissolveUV = UV * '+vector('g_vDissolveTiling')+' + EffectTime * float2('
                      +number('g_vDissolveSpeedU')+', '+number('g_vDissolveSpeedV')+');',
                      'float dissolve = Texture2DSampleLevel(Dissolve, DissolveSampler, dissolveUV, 0).r;',
                      'float dissolveMask = pow(saturate((dissolve - SourceDissolve + 0.1) * 5.0), '+number('g_dissolve_hardness')+');',
                      'float alpha = c.a * dissolveMask * SourceAlpha;']
        else:
            lines.append('float alpha = c.a * SourceAlpha;')
        lines.append('return float4(rgb, alpha);')
        textures = []
        for name, parameter in bindings:
            logical = str(Path(original['params'][parameter].replace('\\', '/')).with_suffix('.ktx')).replace('\\', '/')
            record = decoded[logical]
            image = record['outputs'][0]
            path = ROOT/image['png']
            if sha(path.read_bytes()) != image['png_sha256'] or record['texture']['profile'] != 'linear':
                raise ValueError('linear material texture identity changed')
            textures.append({'name': name, 'input': name, 'parameter': parameter, 'logical': logical,
                             'file': str(path.resolve()), 'png': str(path.resolve()), 'sha256': image['png_sha256'],
                             'srgb': False, 'sourceKtxSha256': record['source_sha256'], 'width': image['width'], 'height': image['height']})
        records.append({'name': model['name'], 'gim': model['gim'], 'glb': model['glb'],
                        'glbSha256': model['sha256'], 'code': '\n'.join(lines), 'dynamicDefaults': dynamics,
                        'inputs': ['UV', 'EffectTime', 'SourceAlpha', 'SourceTint', 'SourceDissolve', 'SourceStrength']+[t['name'] for t in textures],
                        'textures': textures, 'originalMaterial': original, 'effectiveLiteralParameters': effective,
                        'sourceShaderSha256': shader['sha256'], 'sourceFunctionSha256': shader['include']['sha256'],
                        'expressionEvidence': shader['expressionEvidence'], 'sourceLayerXpath': layer['xpath'],
                        'dynamicCurves': curves,
                        'dynamicDefaultPolicy': {'EffectTime': 'Explicit adapter clock starts at zero; native time origin not established.',
                            'SourceAlpha': 'First/sole literal alphaMtl source key for initialization, not interpreted native timing.',
                            'SourceTint': 'Unconverted MTG/shader RGB literal; source ColorKeyFrame byte order remains unresolved.',
                            'SourceDissolve': 'First source dissolve key when present; otherwise material/shader literal (unused without DISSOLVE_EFFECT).',
                            'SourceStrength': 'Sole source strength key when present; otherwise material/shader literal.'},
                        'limitations': ['Only material-local macro set is ported. Original runtime global macro overrides remain unknown.',
                            'Pre-HDR RGB/alpha are adapted to UE linear emissive/opacity. NeoX HDR packing, quarter-intensity platform paths, exposure/bloom and render-state numeric mapping are not recreated.',
                            'Mip0 sampling is explicit for exported base PNG; source MipLODBias=-10/minification behavior is not reproduced exactly.',
                            'SourceTint consumes raw shader RGB and squares once; do not convert tint or texture to sRGB before this code.',
                            'Source color-keyframe byte order, parenting and curve-time behavior are not inferred.']})
    if [r['name'] for r in records] != list(APPROVED):
        raise ValueError('unexpected material port set')
    return {'schema': 'hczs-elsa-entrance-fx-material-inputs-v1', 'originalRuntimeExecuted': False,
            'materials': records, 'shaderCompiledOrExecuted': False, 'sourceShaderSha256': shader['sha256']}


def main(apk, out):
    apk, out = Path(apk).resolve(), Path(out).resolve()
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity mismatch')
    catalogue = read_catalogue(apk)
    sources, payloads = {}, {}
    for logical in PINS:
        source = extract(apk, catalogue, logical, out/'source'/logical, APK_SHA256)
        raw = Path(source['sample_path']).read_bytes()
        pinned(logical, raw)
        sources[logical], payloads[logical] = source, raw
    recipe = make_recipe(payloads[SFX])
    shader = shader_parameters(payloads['shader/lancer3.fx'], payloads['shader/shaderlib/function.fxl'])
    models, excluded = [], []
    texture_usage = {}
    for name in MODEL_PINS:
        gim_path = MODEL_PREFIX+name+'.gim'
        gim = ET.fromstring(payloads[gim_path].decode('gb18030'))
        mesh_path = gim.get('Mesh', gim_path[:-4]+'.mesh').replace('\\', '/')
        if mesh_path != gim_path[:-4]+'.mesh':
            raise ValueError('reviewed native fallback mesh reference changed')
        mtg_path = gim_path[:-4]+'.mtg'
        model = parse_model(payloads[mesh_path])
        materials = parse_materials(payloads[mtg_path], expected_slots=1)
        if model['kind'] != 0 or model['submesh_count'] != 1 or model['submeshes'][0]['uv_count'] != 1:
            raise ValueError('reviewed static one-submesh/UV geometry changed')
        if materials[0]['technique']['TechName'].replace('\\', '/') != 'shader/lancer3.fx::TShader':
            raise ValueError('unexpected material technique')
        textures = []
        for key, value in materials[0]['params'].items():
            if not key.startswith('Tex') or not value: continue
            logical = str(Path(value.replace('\\', '/')).with_suffix('.ktx')).replace('\\', '/')
            if logical not in payloads: raise ValueError('unreviewed texture dependency')
            textures.append({'parameter': key, 'sourceLiteral': value, 'logicalPath': logical, 'sha256': sha(payloads[logical])})
            texture_usage.setdefault(logical, []).append({'model': name, 'parameter': key, 'geometryExported': name in APPROVED})
        row = {'name': name, 'gim': gim_path, 'mesh': mesh_path, 'mtg': mtg_path,
               'explicitMeshReference': 'Mesh' in gim.attrib,
               'meshResolution': 'Previously recovered native same-stem extension replacement (0xc213e8 mesh, 0xc212f4 mtg, helper0x10daec6).',
               'materials': materials, 'textures': textures, 'vertices': model['vertex_count'],
               'triangles': model['triangle_count'], 'coverageBytes': model['coverage_bytes'], 'sourceBytes': model['size'],
               'sourceBounds': model['bounds'], 'shaderImplemented': False}
        try:
            bindings = bind_materials(model, ET.tostring(gim, encoding='utf8'), materials)
        except ModelError as exc:
            if name != EXCLUDED: raise
            row.update(geometryExported=False, rejectionReason=str(exc),
                       gimSubmeshes=[c.attrib for c in gim.find('SubMesh')])
            excluded.append(row)
            continue
        if name not in APPROVED:
            raise ValueError('previously excluded bounds changed; requires separate review')
        glb, doc, _ = encode_glb(model, name, skin=False)
        doc, binary = split_glb(glb)
        doc['materials'] = [{'name': name+'_slot_0', 'extras': {'originalMaterial': materials[0], 'shaderImplemented': False}}]
        doc['meshes'][0]['primitives'][0]['material'] = bindings[0]['material_slot']
        doc['extras'].update(sourceGim=gim_path, sourceMaterialGroup=mtg_path,
                             scope='Original geometry and material slot only; lancer3 shader not implemented.',
                             missing=['Original lancer3 material execution', 'SFX track, curve, lifecycle and attachment playback'])
        glb = pack_glb(doc, binary)
        verification = verify_geometry(glb, payloads[mesh_path], model)
        target = out/(name+'.glb')
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = target.with_suffix('.glb.pending')
        pending.write_bytes(glb)
        pending.replace(target)
        row.update(geometryExported=True, bindings=bindings, glb=str(target), sha256=sha(glb),
                   glbBytes=len(glb), verification=verification)
        models.append(row)
    if len(models) != 3 or len(excluded) != 1 or len(texture_usage) != 10:
        raise ValueError('resource closure count changed')
    texture_sources = []
    for logical in texture_usage:
        parsed = parse_ktx(payloads[logical])
        if parsed['profile'] != 'linear' or parsed['faces'] != 1:
            raise ValueError('expected linear 2D source texture')
        texture_sources.append(sources[logical])
    texture_provenance = out/'texture-provenance.json'
    save(texture_provenance, texture_sources)
    converted = convert([Path(s['sample_path']) for s in texture_sources], out/'png', DEFAULT_DECODER,
                        provenance_path=texture_provenance, inspector=DEFAULT_INSPECTOR)
    for row in converted['textures']:
        row['uses'] = texture_usage[row['provenance']['logical_path']]
        row['colorPolicy'] = 'Raw linear decoded PNG; no RGB transfer conversion, alpha change, vertical flip or premultiplication.'
    material_inputs = prepare_material_inputs(models, recipe, shader, converted)
    save(out/'material-inputs.json', material_inputs)
    for material in material_inputs['materials']:
        (out/(material['name']+'.hlsl')).write_text(material['code']+'\n', 'utf8')
    recipe.update(models=models, excludedModels=excluded, shader=shader,
                  resourceClosure='Four source model triplets, lancer3+literal include and ten linear textures; only three model GLBs exported.',
                  shaderParametersPolicy='Merge shader literal defaults, MTG parameters, then source SFX semantic curves; native semantic defaults remain unknown.')
    save(out/'sourcepins.json', {'schema': 'hczs-elsa-entrance-fx-pins-v1', 'apkSha256': APK_SHA256,
                                'pins': PINS, 'sources': sources})
    save(out/'playback-recipe.json', recipe)
    save(out/'texture-manifest.json', converted)
    report = {'schema': 'hczs-elsa-entrance-fx-export-v1', 'apkSha256': APK_SHA256,
              'originalRuntimeExecuted': False, 'models': models, 'excludedModels': excluded,
              'textureCount': len(converted['textures']), 'sourceCount': len(sources),
              'validatedAstcBlocks': sum(t['block_validation']['block_count'] for t in converted['textures']),
              'recipeSha256': sha((out/'playback-recipe.json').read_bytes()),
              'materialInputsSha256': sha((out/'material-inputs.json').read_bytes()),
              'pinsSha256': sha((out/'sourcepins.json').read_bytes()), 'limitations': LIMITATIONS}
    save(out/'export-report.json', report)
    return {'models': len(models), 'excluded': len(excluded), 'textures': report['textureCount'],
            'sourceCount': len(sources), 'validatedAstcBlocks': report['validatedAstcBlocks'],
            'outputs': [{'file': Path(m['glb']).name, 'sha256': m['sha256']} for m in models]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    parser.add_argument('--out', type=Path, default=ROOT/'analysis/battle-visual/entrance-fx')
    args = parser.parse_args()
    print(json.dumps(main(args.apk, args.out), ensure_ascii=False, indent=2))
