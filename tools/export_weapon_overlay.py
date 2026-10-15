"""Recover the original second weapon layer in the current prop1-local space.

Offline, hash-pinned conversion only. It neither imports UE assets nor changes
the existing weapon. Native BindType 263 is still unverified; sharing exactly
the existing weapon's conversion prevents a second, incompatible attachment.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from prepare_battle_inputs import weapon_local_glb
from export_elsa_animation import accessor_array
from export_elsa_model import split_glb, pack_glb
from inspect_neox_model import parse_model

BASE = ROOT / 'analysis/battle-visual/weapon'
OUT = BASE / 'effect/prop1-local'
PINS = {
    'ailisha_weapon.mesh': '674bff2365e5a9db6ed65939a7ec3977b3d8f26218058f54e29758823dd4e06c',
    'ailisha_weapon.mtg': '6d26d4b0a2fc004adf1f109e695ac4c930e226ea52527dc981a884648000f2eb',
    'ailisha_weapon.gim': 'dc87eeace7351727f86eca52a1a3cea5bcd5dd0f06e7696435da0f170a62c528',
    'elsa-weapon-static.glb': '17e9dc3b061ead7aa333215f22920aef706f4403e44f32765cf476302fa7babe',
    'effect/weapon-overlay.glb': '00861ba21c30702a110e60e697506b47a760626f7442f0cf05df57333cc9cf05',
    'effect/lancer2.fx': 'f26a95349b03ea7bf9077e586f07f0c9bd2ddfb92f667a4f151e39561f9d2480',
    'effect/function.fxl': 'c08dae6dd5503a004e6cef264085ebe091a98199fbd3c038581d583858423e72',
}
EXPECTED_PARAMS = {
    'g_vFloatingSpeed1': '0.100000,0.200000',
    'g_vDistortionSpeed': '0.100000,-0.100000',
    'g_fFloatingStrength1': '3.000000',
    'g_colFloatingColor1': '1.000000,0.207843,0.470588,1.000000',
    'g_fDistortionStrength': '0.100000',
    'TexDistortion': 'effects/tex/wenli/noise_gq_rlt_01.tga',
    'Tex0': 'effects/tex/wenli/noise_100.tga',
}
# Explicit SIMPLE branch from source function.fxl. Textures must have sRGB=False;
# otherwise UE's implicit decode plus this square would decode colour twice.
SHADER_CODE = '''float2 duv = UV + EffectTime * float2(0.1, -0.1);
float d = Texture2DSampleLevel(Distortion, DistortionSampler, duv, 0).r;
float2 cuv = UV + float2(d, d) * 0.1 + EffectTime * float2(0.1, 0.2);
float4 c = Texture2DSampleLevel(Flow, FlowSampler, cuv, 0);
float3 tint = float3(1.0, 0.207843, 0.470588);
return float4((c.rgb * c.rgb) * 3.0 * (tint * tint), c.a);'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected):
    raw = path.read_bytes()
    if sha(raw) != expected:
        raise ValueError('Source hash changed: ' + str(path))
    return raw


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')


def line_evidence(raw, patterns):
    lines = raw.decode('gb18030').splitlines()
    result = []
    for pattern in patterns:
        hits = [{'line': i + 1, 'text': line} for i, line in enumerate(lines) if pattern in line]
        if not hits:
            raise ValueError('Reviewed shader expression absent: ' + pattern)
        result.append({'expression': pattern, 'hits': hits})
    return result


def arrays(doc, binary):
    primitive, = doc['meshes'][0]['primitives']
    return {**{key: accessor_array(doc, binary, value) for key, value in primitive['attributes'].items()},
            'indices': accessor_array(doc, binary, primitive['indices'])}


def main():
    raw = {name: checked(BASE / name, expected) for name, expected in PINS.items()}
    binding = json.loads((BASE / 'binding-report.json').read_text('utf8'))
    model = parse_model(raw['ailisha_weapon.mesh'])
    if model['used_bones'] != [28] or model['bones'][28]['name'] != 'bip001 prop1':
        raise ValueError('Original rigid weapon binding changed')
    joints, weights = np.asarray(model['joints']), np.asarray(model['weights'])
    if not np.all(np.sum(weights, axis=1) == 1) or not np.all(joints[weights > 0] == 28):
        raise ValueError('Weapon is no longer entirely unit-weighted to prop1')
    if list(model['bones'][28]['matrix_raw']) != binding['used_bones'][0]['source_bind']:
        raise ValueError('Binding report differs from original mesh bind matrix')

    # Verify the helper is exactly the policy used by the current staged weapon.
    existing, _ = weapon_local_glb(raw['elsa-weapon-static.glb'], binding)
    staged = ROOT / 'analysis/unreal/battle-inputs/weapon/elsa_weapon.glb'
    if existing != checked(staged, 'f0acd3ca7b0b2ca6ec7bb5af763c3497123168793807c8902f8c87671c7cbb00'):
        raise ValueError('Current weapon conversion no longer matches the shared helper')

    source_doc, source_bin = split_glb(raw['effect/weapon-overlay.glb'])
    source_arrays = arrays(source_doc, source_bin)
    submesh = model['submeshes'][1]
    if (submesh['vertex_start'], submesh['vertex_count'], submesh['triangle_start'], submesh['triangle_count']) != (612, 612, 884, 884):
        raise ValueError('Original overlay topology changed')
    for key, expected in (
        ('POSITION', np.asarray(model['positions'][612:1224], dtype='<f4')),
        ('NORMAL', np.asarray(model['normals'][612:1224], dtype='<f4')),
        ('TEXCOORD_0', np.asarray(submesh['uvs'][0], dtype='<f4')),
        ('indices', np.asarray(model['indices'][884 * 3:1768 * 3]).reshape(-1) - 612),
    ):
        if not np.array_equal(source_arrays[key].reshape(-1), expected.reshape(-1)):
            raise ValueError('Source overlay accessor differs from original mesh: ' + key)
    blob, attachment = weapon_local_glb(raw['effect/weapon-overlay.glb'], binding)
    doc, binary = split_glb(blob)
    doc['meshes'][0]['name'] = 'SM_WeaponOverlay'
    for node in doc['nodes']:
        if 'mesh' in node:
            node['name'] = 'SM_WeaponOverlay'
    # One explicitly temporary slot is replaced by M_WeaponFlow during UE import.
    doc['materials'] = [{'name': 'WeaponFlowSourceSlot', 'pbrMetallicRoughness': {
        'baseColorFactor': [0, 0, 0, 0], 'metallicFactor': 0, 'roughnessFactor': 1},
        'alphaMode': 'BLEND', 'doubleSided': True}]
    doc['meshes'][0]['primitives'][0]['material'] = 0
    doc['extras']['runtimeShaderRequired'] = True
    doc['extras']['missing'] = ['NeoX native blend/HDR equivalence; UE runtime visibility must be verified']
    blob = pack_glb(doc, binary)
    reread_doc, reread_binary = split_glb(blob)
    result_arrays = arrays(reread_doc, reread_binary)
    for key in ('TEXCOORD_0', 'indices'):
        if not np.array_equal(result_arrays[key], source_arrays[key]):
            raise ValueError('Conversion modified ' + key)
    matrix = np.asarray(binding['used_bones'][0]['source_bind']).reshape(4, 4).T
    back = (matrix @ np.column_stack((result_arrays['POSITION'].astype(np.float64), np.ones(612))).T).T[:, :3]
    position_error = float(np.max(np.abs(back - source_arrays['POSITION'])))
    if position_error > 2e-6 or not np.isfinite(result_arrays['POSITION']).all():
        raise ValueError('Re-read GLB geometry roundtrip failed')

    material = ET.fromstring(raw['ailisha_weapon.mtg']).find('MaterialGroup/Material_1/Material')
    params = {e.tag: e.attrib['Value'] for e in material.find('ParamTable')}
    macros = {e.attrib['Key']: e.attrib['Val'] for e in material.find('ShaderMacro')}
    if params != EXPECTED_PARAMS or macros != {'BLOOM_SUPPORT': 'TRUE'}:
        raise ValueError('Reviewed material parameters/macros changed')
    shader = raw['effect/lancer2.fx'].decode('gb18030')
    for key in ('g_vFloatingTiling1', 'g_vDistortionTiling'):
        if not re.search(r'float2\s+' + key + r'\s*<.*?>\s*=\s*\{1.0f,1.0f\}', shader, re.S):
            raise ValueError('Source default tiling changed')
    old_report = json.loads((BASE / 'effect/report.json').read_text('utf8'))
    textures = {}
    for row, parameter in zip(old_report['textures'], ('Distortion', 'Flow')):
        output, = row['outputs']
        path = ROOT / output['png']
        checked(ROOT / row['source'], row['source_sha256'])
        checked(path, output['png_sha256'])
        if row['texture']['profile'] != 'linear':
            raise ValueError('Expected original linear-profile ASTC texture')
        textures[parameter] = {'file': str(path), 'sha256': output['png_sha256'],
            'source': row['provenance'], 'dimensions': [output['width'], output['height']],
            'srgb': False, 'address_u': 'wrap', 'address_v': 'wrap', 'filter': 'bilinear',
            'source_mip_lod_bias': -10.0}
    evidence = {
        'lancer2': line_evidence(raw['effect/lancer2.fx'], [
            'time : FrameTime', 'g_vDistortionTiling', 'float local_14 = time * g_vDistortionSpeed.x',
            'float4 local_0 = tex2D(sam_OTHER1', 'local_11.xyz = srgb2linearf3(local_11.xyz)',
            'float3 local_32 = local_31 * g_colFloatingColor1_linear.xyz',
            'float4 local_33', 'float local_88 = local_64 * alphaMtl', 'MipLODBias = -10']),
        'function': line_evidence(raw['effect/function.fxl'], [
            '#define SRGB_2_LINEAR_TYPE SRGB_2_LINEAR_TYPE_SIMPLE', 'return rgb*rgb;']),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'SM_WeaponOverlay.glb'
    target.write_bytes(blob)
    (OUT / 'weapon-flow.hlsl').write_text(SHADER_CODE + '\n', 'utf8')
    report = {
        'schema': 'hczs-source-weapon-overlay-v1', 'passed': True,
        'evidenceKind': 'Offline hash-verified extraction and numerical conversion; no native APK runtime',
        'sources': {str(BASE / name): expected for name, expected in PINS.items()},
        'sourceApkSha256': binding['sources']['mesh']['apk_sha256'],
        'glb': str(target), 'glbSha256': sha(blob), 'glbBytes': len(blob),
        'geometry': {'vertices': 612, 'triangles': 884, 'skins': 0, 'materialSlots': 1,
                     'maxPositionRoundtripError': position_error, 'uvAndIndicesUnchanged': True,
                     'sameConversionAsCurrentWeapon': True, 'actorRotationAdjusted': False},
        'attachment': attachment,
        'ueAttachment': {'policy': 'Same attach parent, socket, relative transform as current weapon root component',
                         'socket': 'bip001-prop1', 'extraInverseBind': False,
                         'interchangeAxisMapping': '(x,y,z)->(x,z,y)', 'interchangeScale': 100,
                         'additionalImportOffsetScale': 1},
        'material': {'sourceParameters': params, 'sourceMacros': macros,
                     'sourceRenderStates': dict(material.find('RenderStates').attrib),
                     'sourceTransparentMode': material.find('RenderStates/TransparentMode').attrib['TransparentMode'],
                     'shaderDefaultColourConversion': 'SIMPLE: rgb * rgb (both sampled colour and tint)',
                     'sourceDefaultTiling': [1, 1], 'sourceAlphaMtl': 1,
                     'runtimeMacroOverridesObserved': False,
                     'ueBlendAdapter': 'Translucent; native NeoX blend mode 5 is not claimed equivalent',
                     'ueExposureAdapter': 'EyeAdaptationInverse alpha=1; preserves existing camera',
                     'alphaMaskMacro': False, 'alphaTestMacroRuntimeUnknown': True,
                     'alphaClipEnabled': False, 'effectTimeParameter': 'EffectTime',
                     'hlsl': SHADER_CODE, 'hlslSha256': sha(SHADER_CODE.encode()), 'textures': textures,
                     'mipAdaptation': 'UE level-0 sampling (both source samplers use MipLODBias=-10); no fabricated higher resolution',
                     'limitations': ['Native macro overrides and HDR/bloom packing not observed',
                                     'Two-sided UE raster adapter; original CullMode 2 semantics not asserted']},
        'sourceEvidence': evidence,
        'destination': {'mesh': '/Game/Recovered/Battle/Weapon/SourceFx/SM_WeaponOverlay',
                        'material': '/Game/Recovered/Battle/Weapon/SourceFx/M_WeaponFlow'},
    }
    # Content-derived recipe identity allows safe retries of owned UE assets.
    report['recipeSha256'] = sha(json.dumps(report, sort_keys=True, separators=(',', ':')).encode())
    json_write(OUT / 'report.json', report)
    print(json.dumps({'passed': True, 'glb': str(target), 'sha256': sha(blob),
                      'roundtripError': position_error, 'vertices': 612, 'triangles': 884}))
    return report


if __name__ == '__main__':
    main()
