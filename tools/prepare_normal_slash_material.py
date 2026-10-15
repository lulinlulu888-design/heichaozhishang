"""Prepare the pinned original luminous ordinary-slash layer for UE5.8.

This ports only lancer2 TWO_FLOAT + DISSOLVE_EFFECT. It does not substitute
emissive shading for the separate refraction model or the four source sprites.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from PIL import Image

from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import split_glb, pack_glb, parse_materials
from export_elsa_normal_slash import verify_glb_arrays, bind_daoguang_full_ring
from export_weapon_overlay import line_evidence
from inspect_neox_model import parse_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/normal-slash'
OUT = BASE / 'material-inputs'
GIM = 'effects/modeleffect/char/001/new_daoguang_01.gim'
MTG = GIM[:-4] + '.mtg'
MESH = 'effects/modeleffect/char/001/daoguang_01.mesh'
PINS = {
    GIM: 'a9b9256e6b57a24b33653698b271dc3f870bc64e721efe5105ff1fca8a0c9ed6',
    MTG: 'ab1fa830b794780a20fb96e071209deaf939f1b948e3feeadb5bcbccd0b4cacb',
    MESH: '50613e1489873fa492f312d60fda63cda4e6605869c25a6d7308b3f6c9f51472',
    'shader/lancer2.fx': 'f26a95349b03ea7bf9077e586f07f0c9bd2ddfb92f667a4f151e39561f9d2480',
    'effects/tex/trail/trail_28_2.ktx': '70ee05e34102b26dc526b219c040dc6249e621b06bf774a609bfd6e265e4d82f',
    'effects/tex/wenli/0150_e.ktx': '7f263ebda83e51fb6c91eb48602c46f98d60c19c9937a2973ec7398b3be0f1a6',
    'effects/tex/wenli/energytile01.ktx': 'ea4502670c96832500ffa480427ae48c6f0084b159d6ef3f36d361816138553a',
    'effects/tex/wenli/0150_a.ktx': 'd387c774fa48f3a3ed4b55db5846623fb0ad274920cebb7d8af8ef92bc6206a0',
    'effects/player/001/new_daoguang_01.sfx': '095c60658874ef91dcf5f9c1f80a64ed86354d72e6b6ab703412790acf4646e4',
}
FUNCTION = ROOT / 'analysis/battle-visual/weapon/effect/function.fxl'
FUNCTION_SHA = 'c08dae6dd5503a004e6cef264085ebe091a98199fbd3c038581d583858423e72'
GLB_SHA = 'cf94d0756a7538487ab675a8ff0411d002ce4f06837670deefc82d53eca224f9'
SHADER = '''// Original lancer2: TWO_FLOAT + DISSOLVE_EFFECT, SIMPLE colour branch.
float2 distortionUV = UV * float2(1.5, 1.0) + EffectTime * float2(-1.0, 0.5);
float distortion = Texture2DSampleLevel(Distortion, DistortionSampler, distortionUV, 0).r;
float2 flowUV1 = UV + float2(distortion, distortion) * 0.15;
float2 flowUV2 = UV * float2(1.0, 1.5) + float2(distortion, distortion) * 0.15 + EffectTime * float2(-1.0, 0.2);
float4 c1 = Texture2DSampleLevel(Flow1, Flow1Sampler, flowUV1, 0);
float4 c2 = Texture2DSampleLevel(Flow2, Flow2Sampler, flowUV2, 0);
float3 rgb = (SourceColor1.rgb * SourceColor1.rgb) * (c1.r * c1.r)
           + (SourceColor2.rgb * SourceColor2.rgb) * (c2.r * c2.r);
// The source vertex shader uses panned distortion UV here, NOT sampled noise.
float2 dissolveUV = UV * float2(0.05, 1.5) + distortionUV * 0.15 + EffectTime * float2(-0.1, 0.05);
float dissolve = Texture2DSampleLevel(Dissolve, DissolveSampler, dissolveUV, 0).r;
float dissolveMask = saturate(c1.r * c1.r - (0.01 + dissolve) * SourceDissolve);
float alpha = saturate(dissolveMask * (c1.a + c2.a) * SourceAlpha);
// Source strengths are both 1. SourceStrength is an explicit UE gain, default 1.
return float4(rgb * SourceStrength, alpha);'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')


def sample(image, uv):
    h, w = image.shape[:2]
    xy = uv * [w, h] - 0.5
    lower = np.floor(xy).astype(int)
    fraction = xy - lower
    x, y = lower[:, 0] % w, lower[:, 1] % h
    fx, fy = fraction[:, 0, None], fraction[:, 1, None]
    return ((image[y, x] * (1 - fx) + image[y, (x + 1) % w] * fx) * (1 - fy)
            + (image[(y + 1) % h, x] * (1 - fx) + image[(y + 1) % h, (x + 1) % w] * fx) * fy)


def cpu_reference(images, uv, time, alpha=1, dissolve=0.5, strength=1):
    duv = uv * [1.5, 1] + time * np.array([-1, .5])
    d = sample(images['Distortion'], duv)[:, :1]
    c1 = sample(images['Flow1'], uv + d * .15)
    c2 = sample(images['Flow2'], uv * [1, 1.5] + d * .15 + time * np.array([-1, .2]))
    rgb = np.array([.1529, 0, 0]) ** 2 * c1[:, :1] ** 2 + np.array([1, .0745, .3333]) ** 2 * c2[:, :1] ** 2
    ds = sample(images['Dissolve'], uv * [.05, 1.5] + duv * .15 + time * np.array([-.1, .05]))[:, 0]
    opacity = np.clip(np.clip(c1[:, 0] ** 2 - (.01 + ds) * dissolve, 0, 1) * (c1[:, 3] + c2[:, 3]) * alpha, 0, 1)
    return np.column_stack((rgb * strength, opacity))


def main():
    recipe_path = BASE / 'playback-recipe.json'
    recipe = json.loads(recipe_path.read_text('utf8'))
    sources = {r['logical_path']: r for r in recipe['sources']}
    payloads = {}
    checked_sources = {}
    for logical, expected in PINS.items():
        source = sources[logical]
        path = Path(source['sample_path'])
        raw = path.read_bytes()
        if sha(raw) != expected or source['sha256'] != expected or source['apk_sha256'] != recipe['apkSha256']:
            raise ValueError('Pinned original source changed: ' + logical)
        payloads[logical] = raw
        checked_sources[str(path)] = expected
    function = FUNCTION.read_bytes()
    if sha(function) != FUNCTION_SHA:
        raise ValueError('Original colour helper changed')
    checked_sources[str(FUNCTION)] = FUNCTION_SHA
    model = parse_model(payloads[MESH])
    material, = parse_materials(payloads[MTG], expected_slots=1)
    bind_daoguang_full_ring(model, payloads[GIM], [material])
    if material['macros'] != {'BLOOM_SUPPORT': 'TRUE', 'TWO_FLOAT': 'TRUE', 'DISSOLVE_EFFECT': 'TRUE'}:
        raise ValueError('Reviewed shader macro set changed')
    params = material['params']
    defaults = {'g_vFloatingTiling1': [1, 1], 'g_fFloatingStrength1': 1,
                'g_fFloatingStrength2': 1, 'g_DissolveChannel': False}
    shader = payloads['shader/lancer2.fx'].decode('gb18030')
    for name, token in [('g_vFloatingTiling1', r'\{1.0f,1.0f\}'),
                        ('g_fFloatingStrength1', '1.0f'), ('g_fFloatingStrength2', '1.0f'),
                        ('g_DissolveChannel', 'false')]:
        if not re.search(r'\b' + name + r'\s*<.*?>\s*=\s*' + token + r'\s*;', shader, re.S):
            raise ValueError('Shader default changed: ' + name)
    for name in ('BLEND_BLOOM', 'DISSOLVEONLY_EFFECT', 'ALPHA_MASK', 'ALPHA_TEST_ENABLE', 'FRESNEL_ALPHA', 'FRESNEL_COLOR'):
        if not re.search(r'#ifndef ' + name + r'\s+#define ' + name + r' 0', shader):
            raise ValueError('Default macro changed: ' + name)
    original_glb = BASE / 'new_daoguang_01.glb'
    original = original_glb.read_bytes()
    if sha(original) != GLB_SHA:
        raise ValueError('Source geometry GLB changed')
    checked_sources[str(original_glb)] = GLB_SHA
    verification = verify_glb_arrays(original, payloads[MESH], model)
    doc, binary = split_glb(original)
    doc['meshes'][0]['name'] = 'SM_NormalSlashLuminous'
    for node in doc['nodes']:
        if 'mesh' in node:
            node['name'] = 'SM_NormalSlashLuminous'
    doc['materials'][0].update(name='NormalSlashSourceSlot', alphaMode='BLEND',
        pbrMetallicRoughness={'baseColorFactor': [0, 0, 0, 0], 'metallicFactor': 0, 'roughnessFactor': 1})
    glb = pack_glb(doc, binary)
    if verify_glb_arrays(glb, payloads[MESH], model) != verification:
        raise ValueError('Naming changed original mesh bytes')
    OUT.mkdir(parents=True, exist_ok=True)
    texture_rows = [r for r in recipe['sourceReferences'] if r.get('materialGroup') == MTG and r['kind'] == 'texture']
    provenance = OUT / 'texture-provenance.json'
    write_json(provenance, [r['source'] for r in texture_rows])
    converted = convert([Path(r['source']['sample_path']) for r in texture_rows], OUT / 'png',
                        DEFAULT_DECODER, provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    by_sha = {r['source_sha256']: r for r in converted['textures']}
    names = {'Tex0': 'Flow1', 'Tex1': 'Flow2', 'TexDistortion': 'Distortion', 'TexDissolve': 'Dissolve'}
    textures, images = {}, {}
    for ref in texture_rows:
        row = by_sha[ref['source']['sha256']]
        output, = row['outputs']
        path = ROOT / output['png']
        if row['texture']['profile'] != 'linear' or sha(path.read_bytes()) != output['png_sha256']:
            raise ValueError('Expected unchanged linear ASTC-decoded samples')
        name = names[ref['parameter']]
        textures[name] = {'file': str(path), 'sha256': output['png_sha256'], 'srgb': False,
                          'source': ref['source'], 'sourceParameter': ref['parameter'],
                          'dimensions': [output['width'], output['height']], 'decoder': output['decoder_mode']}
        images[name] = np.asarray(Image.open(path).convert('RGBA'), dtype=np.float64) / 255
    if set(textures) != set(names.values()):
        raise ValueError('Incomplete source texture set')
    uv = np.asarray(model['submeshes'][0]['uvs'][0])
    samples = []
    for time in (0, .05, .124, .3, .5):
        value = cpu_reference(images, uv, time)
        if not np.isfinite(value).all() or np.any(value[:, 3] < 0) or np.any(value[:, 3] > 1):
            raise ValueError('CPU shader reference not finite or source alpha clamp violated')
        zero = cpu_reference(images, uv, time, alpha=0)
        if np.count_nonzero(zero[:, 3]) != 0:
            raise ValueError('Source alpha zero did not hide the layer')
        samples.append({'effectTime': time, 'minRGBA': value.min(axis=0).tolist(),
                        'maxRGBA': value.max(axis=0).tolist(), 'vertices': len(uv),
                        'referenceSHA256': sha(value.astype('<f4').tobytes())})
    layer, = [l for l in recipe['layers'] if l.get('geometry', {}).get('gim') == GIM]
    unimplemented = [{'tag': l['node']['tag'], 'name': l['node']['attributes'].get('Name'),
                       'sourceLine': l['node']['line'], 'sourceXpath': l['node']['xpath'],
                       'reason': 'Separate refraction shader' if l['node']['tag'] == 'Model' else 'Separate sprite renderer/curves',
                       'implemented': False} for l in recipe['layers'] if l['enabledInSource'] and l is not layer]
    target = OUT / 'SM_NormalSlashLuminous.glb'
    target.write_bytes(glb)
    (OUT / 'normal-slash.hlsl').write_text(SHADER + '\n', 'utf8')
    evidence = line_evidence(payloads['shader/lancer2.fx'], [
        'float2 local_31 = mul(local_13, g_fDistortionStrength)',
        'float3 local_24 = mul(g_colFloatingColor1_linear.xyz, local_11.x)',
        'float3 local_26 = mul(g_colFloatingColor2_linear.xyz, local_23.x)',
        'float local_29 = local_11.w + local_23.w', 'local_11.xyz = srgb2linearf3(local_11.xyz)',
        'float local_60 = local_11.x - local_59', 'float local_88 = local_64 * alphaMtl',
        'local_65.a = clamp(local_65.a, 0.0, 1.0)', 'float3 local_66 = mul(local_62, bloom_factor)'])
    plan = {'schema': 'hczs-normal-slash-material-v1', 'passed': True, 'originalRuntimeExecuted': False,
        'sources': checked_sources, 'sourceApkSha256': recipe['apkSha256'],
        'playbackRecipe': str(recipe_path), 'playbackRecipeSha256': sha(recipe_path.read_bytes()),
        'glb': str(target), 'glbSha256': sha(glb), 'geometry': {'vertices': 205, 'triangles': 320,
            'byteIdenticalArrays': verification, 'sourceUnitsAndAxisPreserved': True},
        'material': {'source': material, 'shaderDefaults': defaults,
            'effectiveBranches': {'TWO_FLOAT': True, 'DISSOLVE_EFFECT': True, 'BLOOM_SUPPORT': True,
                'BLEND_BLOOM': False, 'ALPHA_MASK': False, 'DISSOLVEONLY_EFFECT': False, 'g_DissolveChannel': False},
            'nativeMacroOverridesObserved': False, 'hlsl': SHADER, 'hlslSha256': sha(SHADER.encode()),
            'textures': textures, 'scalars': {'EffectTime': 0, 'SourceAlpha': 1, 'SourceDissolve': .5, 'SourceStrength': 1},
            'vectors': {'SourceColor1': [.1529, 0, 0, 1], 'SourceColor2': [1, .0745, .3333, 1]},
            'parameterSemantics': {'EffectTime': 'Original shader time value; runtime chooses source effect clock',
                'SourceAlpha': 'alphaMtl; accept source curve values above 1, clamp only final alpha',
                'SourceDissolve': 'g_DissolveStrength; source MTG default .5, SFX curve supplied separately',
                'SourceStrength': 'UE overall gain, default 1; both source g_fFloatingStrength uniforms remain 1',
                'SourceColor1/2': 'Raw source colour uniform before SIMPLE squaring; SFX ColorKeyFrame ordering not inferred'},
            'sourceCurves': layer['shaderCurves'], 'bloomFactorAppliedToMainRGB': False,
            'ueAdapters': ['Translucent source alpha over', 'EyeAdaptationInverse alpha=1, unchanged camera',
                'Two-sided per source CullBack=False', 'Linear wrap level0 sampling for source MipLODBias=-10'],
            'unverified': ['Native HDR/bloom blend targets and runtime macro overrides', 'SFX curve enum/colour ordering']},
        'sourceEvidence': evidence, 'cpuReference': samples,
        'runtimeLayer': {'nominalFirstEmissionStartSeconds': layer['nominalFirstEmissionStartSeconds'],
                         'sourceLifeSeconds': layer['sourceLifeSeconds'], 'sourceNode': layer['node'],
                         'ancestors': layer['ancestors']},
        'separateUnimplementedLayers': unimplemented,
        'destination': {'mesh': '/Game/Recovered/Battle/NormalSlash/SM_NormalSlashLuminous',
                        'material': '/Game/Recovered/Battle/NormalSlash/M_NormalSlashLuminous'}}
    plan['recipeSha256'] = sha(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode())
    write_json(OUT / 'report.json', plan)
    print(json.dumps({'passed': True, 'glbSha256': sha(glb), 'textures': len(textures),
                      'separateUnimplementedLayers': len(unimplemented), 'cpuSamples': len(samples)}))
    return plan


if __name__ == '__main__':
    main()
