"""Port the recovered NeoX character shading models onto the tutorial battle actors.

Ordinary Python --plan prints the recipe without importing Unreal. Inside a
dedicated UE5.8 Editor (-ExecutePythonScript) it imports the decoded source
mix/aux textures, builds one Unlit material per actor slot whose Custom node
evaluates the source lighting equations, binds them as map overrides on
L_TutorialSource2133 and saves only that map plus the owned namespace.

Ported from source (shader.npk): forward_shading/lighting Lighting(), the
Isotropy, Stocking, Skin, HairCartoon (Lambert + R lobe) and Eye Cartoon
lighting models, GenerageTone, and the pszdu_battle_1.scn lights whose
RenderCondition is 0, plus the scene reflection probe (decoded to a DDS cube by
prepare_probe). Not ported: shadow maps, SSR,
hair TT/TRT transmission, CharacterLight cubes, outlines and fog.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'clients/unreal5 5.8/Hczs.uproject'
MAP = '/Game/Recovered/Battle/Maps/L_TutorialSource2133'
VISUAL_FIX = '/Game/Recovered/Battle/VisualFix/v3_6cb61a645192f5c0'
TEXTURES = ROOT / 'analysis/battle-visual/source-shading/textures'
REPORT = ROOT / 'analysis/unreal/battle-shading/source-shading-result.json'
SCENE = ROOT / 'analysis/battle-visual/prologue-theatre/source/b887b567a0b3244a4b1a.scn'
SHADERS = ROOT / 'analysis/elsa-model/shader-evidence'
VERSION = 'neox-character-shading-v1'

SCENE_SHA256 = 'e12d873d6e6916effef155f3a1c792b173f3674f93f2e81589fcba5a678bc2c2'

# Source expressions this port depends on; a changed extraction must fail here.
SHADER_FACTS = {
    'shading-models/stocking.hlsl': [
        'density = sparse_intensity * (sparse_intensity - x) / Pow2(sparse_intensity + 1);',
        'density = saturate(density/(thickness_global+thickness_local));',
        'data.diff = lerp(mtl.albedo, mtl.sss_color, data.density);',
        'return max(0.0f, lerp(b, a, data_r.density) * data_rw.n_dot_l);',
        'result.env_diff = input.sh.rgb * data_r.diff*1.2;'],
    'material_stocking.hlsl': [
        'raw_data.tex3 = Tex3.Sample(DefaultSampler, frag.uv.xy * tilling);',
        'mtl.emissive = float3(thickness_pattern2*raw_data.tex3.r, thickness_global, Intensity.a);',
        'float thickness_global = thickness + raw_data.tex2.a * thickness_pattern;'],
    'shading-models/skin.hlsl': [
        'light_diffuse = LightingDiffuse(input, data_r, data_rw, mtl) * data_r.diff * data_rw.atten * (mtl.sss_curvature * 0.1 + 0.88);',
        'light_transmission = GetPreintergratedSkin(data_rw.n_dot_l_raw, mtl) * SubsurfaceColor * data_r.diff * INV_PI * data_rw.atten;',
        'result.env_trans = input.sh2.rgb * SubsurfaceColor * data_r.diff * GetRawPreintergratedSkin(float2(0.0, mtl.sss_curvature));'],
    'material_skin.hlsl': ['mtl.sss_curvature = 1.0 - raw_data.tex2.b;', 'mtl.specular = 0.35f;'],
    'shading-models/hair_cartoon.hlsl': [
        'lit_specular = data_r.spec * pow(data_rw.n_dot_h, SpecularParam.y) * data_rw.anis_spec_intensity;',
        'lit_diffuse = data_r.diff * data_r.metallic * data_rw.n_dot_l * Intensity.y;',
        'result.env_diff = input.sh.rgb * data_r.diff * Intensity.y * data_r.metallic;'],
    'material_hair_cartoon.hlsl': ['mtl.specular = SpecularColor.rgb * raw_data.tex4.rgb * SpecularParam.r;'],
    'shading-models/eye_cartoon.hlsl': [
        'result.env_spec = spec_brdf_term * (spec * Intensity.b) + ext_spec * Intensity.a + GetStaticReflection(input);'],
    'material_eye_cartoon.hlsl': ['return Tex3.Sample(DefaultSampler, frag.uv.xy).xyz * Intensity.g;',
                                  'return float2(norm.x, -norm.y) * 0.5 + 0.5;'],
    'shading-models/lighting.hlsl': [
        'result.direct_diff *= INV_PI;',
        'result.direct_diff += direct_light_diffuse * l.color * mtl.occlusion_filllight;',
        'float LightRadiusMask = Square( saturate( 1 - Square( DistanceSqr * inv_range * inv_range ) ) );',
        'result.env_diff *= mtl.occlusion;'],
    'shading-models/forward_shading.hlsl': [
        'result = lighting.direct_diff + lighting.direct_trans + lighting.direct_spec + lighting.env_diff + lighting.env_spec + lighting.env_trans + lighting.baked.rgb + lighting.emissive;'],
    'shading-models/constants.hlsl': ['#define COMMON_MIN_ROUGHNESS 0.01'],
}

# UE component slot -> source material name and lighting model.
PLAYER_SLOTS = {0: 'eye', 1: 'siwa', 2: 'yifu', 3: 'eye_nei', 4: 'head', 7: 'hair', 8: 'body'}
MODELS = {'eye': 'eye', 'siwa': 'stocking', 'yifu': 'isotropy', 'eye_nei': 'skin', 'head': 'skin',
          'hair': 'hair', 'body': 'skin', 'enemy': 'isotropy'}
TEXTURE_FILES = {
    'cloth_m': ('ailisha_new_cloth_m', 'mask'), 'cloth_n': ('ailisha_new_cloth_n', 'mask'),
    'body_m': ('ailisha_new_body_m', 'mask'), 'head_m': ('ailisha_new_head_m', 'mask'),
    'hair_m': ('ailisha_new_hair_m', 'mask'), 'hair_h': ('ailisha_new_hair_h', 'linear'),
    'siwa_d': ('ailisha_new_siwa_d', 'colour'), 'lut': ('lut_newfix', 'lut'),
    'eye_hl': ('ailisha_new_eye_hl', 'linear'), 'matcap': ('matcap_04', 'colour'),
    'mofang_m': ('mofang_m', 'mask'), 'mofang_e': ('mofang_e', 'colour'),
    'cloth_nm': ('ailisha_new_cloth_n', 'normal'), 'body_nm': ('ailisha_new_body_n', 'normal'),
    'head_nm': ('ailisha_new_head_n', 'normal'), 'hair_nm': ('ailisha_new_hair_n', 'normal'),
    'eye_nm': ('ailisha_new_eye_n', 'normal'), 'mofang_nm': ('mofang_n', 'normal'),
}
# Every normal strength in the MTGs is 1 (Intensity.r, or Intensity.z for hair).
# A curl test on all five maps shows green points down the image, matching UE's
# tangent basis, so the maps are sampled without a green flip.
SLOT_NORMALS = {'siwa': 'cloth_nm', 'yifu': 'cloth_nm', 'body': 'body_nm', 'head': 'head_nm', 'eye_nei': 'head_nm',
                'hair': 'hair_nm', 'eye': 'eye_nm', 'enemy': 'mofang_nm'}
SLOT_TEXTURES = {'siwa': ('cloth_m', 'cloth_n', 'siwa_d'), 'yifu': ('cloth_m', 'cloth_n', None),
                 'body': ('body_m', None, None), 'head': ('head_m', None, None), 'eye_nei': ('head_m', None, None),
                 'hair': ('hair_m', None, 'hair_h'), 'eye': (None, None, 'eye_hl'), 'enemy': ('mofang_m', None, 'mofang_e')}


PROBE_KTX = SHADERS / 'shading-models/07E30718-0B2B0004-5A818AEA-60322C3B.ktx'
PROBE_DIR = ROOT / 'analysis/battle-visual/source-shading/probe'
PROBE_DDS = PROBE_DIR / 'reflectionProbe_pszdu_battle_1.dds'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare_probe():
    """Decode every face/mip of the scene reflection probe into one RGBA8 DDS cube."""
    sys.path.insert(0, str(ROOT / 'tools'))
    from decode_ktx import convert, parse_ktx, read_bounded, DEFAULT_DECODER
    from PIL import Image
    texture = parse_ktx(read_bounded(PROBE_KTX))
    check(texture['faces'] == 6 and texture['width'] == texture['height'] == 128 and texture['mip_count'] == 8
          and texture['profile'] == 'linear', 'Reflection probe format changed')
    faces = [[None] * texture['mip_count'] for _ in range(6)]
    for mip in range(texture['mip_count']):
        manifest = convert([PROBE_KTX], PROBE_DIR / ('mip%d' % mip), DEFAULT_DECODER, mip=mip)
        for out in manifest['textures'][0]['outputs']:
            with Image.open(ROOT / out['png']) as image:
                faces[out['face']][mip] = image.convert('RGBA').tobytes('raw', 'BGRA')
    size = texture['width']
    header = struct.pack('<4sIIIIIII44xII4sIIIII', b'DDS ', 124, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000, size, size,
                         size * 4, 0, texture['mip_count'], 32, 0x41, b'\0\0\0\0', 32,
                         0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000)
    header += struct.pack('<IIIII', 0x1000 | 0x8 | 0x400000, 0x200 | 0xFC00, 0, 0, 0)
    check(len(header) == 128, 'DDS header size')
    PROBE_DDS.write_bytes(header + b''.join(b''.join(levels) for levels in faces))
    return dict(source_sha256=sha(PROBE_KTX.read_bytes()), dds_sha256=sha(PROBE_DDS.read_bytes()), mips=texture['mip_count'])


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def floats(text):
    return [float(v) for v in text.split(',')]


def source_lights():
    raw = SCENE.read_bytes()
    check(sha(raw) == SCENE_SHA256, 'Tutorial scene changed')
    root = ET.fromstring(raw.decode('utf8'))
    glob = root.find('Scene/Global')
    sh = [float(v.text) for v in glob.findall('LightProbe/SkyBoxSH/SHValue')]
    check(len(sh) == 27 and all(abs(v) < 1e-5 for v in sh[3:]), 'Expected an L0-only sky SH')
    lights = list(glob.findall('Lights/light')) + list(root.findall('Scene/Lights/light'))
    chosen = []
    for light in lights:
        a = light.attrib
        if a.get('Enable') != 'true':
            continue
        row = dict(name=a['Name'], type=int(a['Type']), render_condition=int(a.get('RenderCondition', '0')),
                   position=floats(a['Position']), direction=floats(a['Direction']), intensity=float(a['Intensity']),
                   colour=floats(light.find('Diffuse/Key_0').attrib['Color']), range=float(a.get('Range', '0')))
        chosen.append(row)
    names = {r['name']: r for r in chosen}
    check(set(names) == {'dir_light', 'js_b_light', 'fill_light'}, 'Tutorial scene light inventory changed')
    check(names['dir_light']['type'] == 3 and names['fill_light']['type'] == 1, 'Light types changed')
    check(names['js_b_light']['render_condition'] == 20 and names['fill_light']['render_condition'] == 0, 'Render conditions changed')
    return dict(sh_l0=sh[:3], directional=names['dir_light'], point=names['fill_light'],
                excluded=[dict(name='js_b_light', reason='RenderCondition=20 is not unconditional; only RenderCondition=0 lights are ported')])


def mtg_params():
    out = {}
    for path in ('analysis/elsa-model/source/elsa-mtg.mtg', 'analysis/tutorial-enemy/source/enemy-991.mtg'):
        root = ET.fromstring((ROOT / path).read_text('utf8'))
        for material in root.iter('Material'):
            name = material.attrib.get('Name')
            table = material.find('ParamTable')
            if name is None or table is None:
                continue
            key = 'enemy' if 'enemy' in path else name
            out[key] = {child.tag: child.attrib['Value'] for child in table}
    return out


def verify_shader_facts():
    digests = {}
    for relative, expressions in SHADER_FACTS.items():
        text = (SHADERS / relative).read_text('utf8', errors='replace')
        for expression in expressions:
            check(expression in text, 'Source shader expression missing in %s: %s' % (relative, expression))
        digests[relative] = sha((SHADERS / relative).read_bytes())
    return digests


# Combatants are spawned at (100x, 100z, 100y) under the X-reflecting
# HCZSBattleCoordinateAdapter, so source world maps to UE (-100x, 100z, 100y).
def to_ue_direction(v):
    return [-v[0], v[2], v[1]]


def to_ue_position(v):
    return [-v[0] * 100, v[2] * 100, v[1] * 100]


def texture_inputs():
    manifest = json.loads((TEXTURES / 'manifest.json').read_text('utf8'))
    rows = {}
    for record in manifest['textures']:
        out = record['outputs'][0]
        stem = Path(out['png']).name.split('.')[0]
        rows[stem] = dict(png=str(ROOT / out['png']), png_sha256=out['png_sha256'], source_sha256=record['source_sha256'],
                          width=out['width'], height=out['height'])
    result = {}
    for key, (stem, kind) in TEXTURE_FILES.items():
        check(stem in rows, 'Decoded texture missing: ' + stem)
        row = rows[stem]
        check(sha(Path(row['png']).read_bytes()) == row['png_sha256'], 'Decoded PNG changed: ' + stem)
        result[key] = dict(row, kind=kind, asset='T_' + stem + ('_Normal' if kind == 'normal' else ''))
    return result


def plan():
    params = mtg_params()
    lights = source_lights()
    return dict(version=VERSION, tool_sha256=sha(Path(__file__).read_bytes()), shader_sha256=verify_shader_facts(), lights=lights, mtg=params,
                textures=texture_inputs(), player_slots=PLAYER_SLOTS, models=MODELS,
                probe=dict(source=str(PROBE_KTX.relative_to(ROOT)), source_sha256=sha(PROBE_KTX.read_bytes()),
                           dds_sha256=sha(PROBE_DDS.read_bytes()), mip_scale=7.0, box_projection=False))


def recipe_digest(p):
    return sha(json.dumps(p, sort_keys=True, separators=(',', ':')).encode())[:16]


# ---------------------------------------------------------------- HLSL ----

def f3(v):
    return 'float3(%r, %r, %r)' % tuple(float(x) for x in v)


def vis(nl, nv, a):
    return '(0.5 / max((%s) * ((%s) * (1 - (%s)) + (%s)) + (%s) * ((%s) * (1 - (%s)) + (%s)), 1e-5))' % (nl, nv, a, a, nv, nl, a, a)


def ggx(nh, r2):
    h = 'min(0.999, %s)' % nh
    a = '((%s) * (%s))' % (r2, r2)
    return '(%s / (PI_ * Square((%s * %s - %s) * %s + 1.0)))' % (a, h, a, h, h)


PRELUDE = '''
const float PI_ = 3.141592654;
const float INV_PI_ = 0.31831;
float3 N = normalize(Nin);
float3 V = normalize(Vin);
float3 VD = -V;
float NoV = dot(V, N);
float3 RW = reflect(-V, N);
float3 SrcR = float3(-RW.x, RW.z, RW.y);
float3 SH = %(sh)s;
float3 DD = 0, DS = 0, DT = 0;
float3 PointDelta = (P - %(point_pos)s) * 0.01;
float PointDist = max(length(PointDelta), 1e-4);
float3 PointL = PointDelta / PointDist;
float PointD2 = PointDist * PointDist;
float PointAtten = 1.0 / (PointD2 + 1.0) * Square(saturate(1.0 - Square(PointD2 * %(inv_range)r * %(inv_range)r)));
'''


def lights_block(body, occlusion_fill):
    """Expand one lighting-model body for the directional and the point light."""
    return ('{ float3 L = DirL; float3 LC = DirC; float A = 1.0; float ANIS = 1.0; %s }\n'
            '{ float3 L = PointL; float3 LC = PointC * %s; float A = PointAtten; float ANIS = 0.0; %s }\n') % (body, occlusion_fill, body)


HALF = '''
float NoLr = dot(N, -L);
float LoV = dot(L, VD);
float ILH = rsqrt(max(2 + 2 * LoV, 1e-5));
float NoH = saturate((NoLr + NoV) * ILH);
float VoH = saturate(ILH + ILH * LoV);
'''


def schlick(spec):
    return '(saturate(50.0 * (%s).g) * pow(1 - VoH, 5) + (1 - pow(1 - VoH, 5)) * (%s))' % (spec, spec)


def env_spec(var, spec, rough):
    """EnvBRDFApprox(spec, rough, NoV) * EnvironmentSpecular, probe mip = roughness * 7."""
    return '''float3 %(v)s;
{ float4 ER = (%(r)s) * float4(-1, -0.0275, -0.572, 0.022) + float4(1, 0.0425, 1.04, -0.04);
  float A004 = min(ER.x * ER.x, exp2(-9.28 * NoV)) * ER.x + ER.y;
  float2 AB = float2(-1.04, 1.04) * A004 + ER.zw;
  %(v)s = ((%(s)s) * AB.x + AB.y) * TextureCubeSampleLevel(Probe, ProbeSampler, SrcR, (%(r)s) * 7.0).rgb; }
''' % dict(v=var, s=spec, r=rough)


def tone(adjust):
    if not adjust[1]:
        return ''
    return '''
{ float MX = max(R.r, max(R.g, R.b)); float MN = min(R.r, min(R.g, R.b)); float MID = 0.5 * (MX + MN);
  R += max(0.0, R + %r * (R - MID)) * %r; }
''' % (float(adjust[0]), float(adjust[1]))


def shader(model, p, slot):
    lights = p['lights']
    d = lights['directional']
    pt = lights['point']
    m = p['mtg'][slot]
    out = PRELUDE % dict(sh=f3([v * 0.2820948 for v in lights['sh_l0']]), point_pos=f3(to_ue_position(pt['position'])),
                         inv_range=1.0 / pt['range'])
    out += 'float3 DirL = normalize(%s);\nfloat3 DirC = %s;\nfloat3 PointC = %s;\n' % (
        f3(to_ue_direction(d['direction'])), f3([c * d['intensity'] for c in d['colour'][:3]]),
        f3([c * pt['intensity'] for c in pt['colour'][:3]]))
    adjust = floats(m.get('ColorAdjust', '0,0'))
    if model == 'isotropy':
        intensity = floats(m.get('Intensity', '1,1,1,0' if slot != 'enemy' else '1,1,1,1'))
        out += '''
float Rough = clamp(Mix.g * %r, 0.09, 1.0);
float Metal = saturate(Mix.b * %r);
float3 DiffC = Albedo * (1 - Metal);
float3 SpecC = lerp(0.04, Albedo, Metal);
float NoVa = saturate(abs(NoV) + 1e-5);
float R2 = Square(max(0.01, Rough));
''' % (intensity[1], intensity[2])
        body = HALF + '''
if (NoLr > 0) { float NoL = NoLr; float3 F = %s;
  DD += NoL * DiffC * A * LC;
  DS += max(0.0, %s * %s * NoL) * F * A * LC; }
''' % (schlick('SpecC'), vis('NoL', 'NoVa', 'R2'), ggx('NoH', 'R2'))
        out += lights_block(body, 'Fill')
        out += env_spec('ES', 'SpecC', 'Rough')
        out += 'float3 R = DD * INV_PI_ + DS + (SH * DiffC + ES) * Mix.r;\n'
        if slot == 'enemy':
            emissive = floats(m['EmissiveColor'])
            out += 'R += Aux.rgb * %s * %r;\n' % (f3(emissive[:3]), floats(m['EmissiveParams'])[1])
    elif model == 'stocking':
        intensity = floats(m['Intensity'])
        stocking = floats(m['StockingColor'])
        skin = floats(m['SkinColor'])
        out += '''
float3 Alb = Albedo * %s;
float Rough = clamp(Mix.g * %r, 0.09, 1.0);
float SkinRough = clamp(%r, 0.09, 1.0);
float TG = %r + Mix.a * %r;
float TL = %r * Aux.r;
float S = %r;
float Xv = sqrt(saturate(1 - NoV * NoV));
float Dens = saturate(S * (S - Xv) / Square(S + 1) / (TG + TL));
float3 Diff = lerp(Alb, %s, Dens);
float NoVa = abs(NoV);
float R2 = Square(max(0.01, Rough));
float R02 = Square(max(0.01, SkinRough));
''' % (f3(stocking[:3]), intensity[1], intensity[2], float(m['thickness']), float(m['thickness_pattern']),
       float(m['thickness_pattern2']), intensity[3], f3(skin[:3]))
        body = HALF + '''
if (NoLr >= 0) { float NoL = max(NoLr, 0.0); float3 F = %s;
  float SA = %s * %s;
  float SB = %s * %s;
  DD += NoL * Diff * A * LC;
  DS += max(0.0, lerp(SB, SA, Dens) * NoL) * F * A * LC; }
''' % (schlick('float3(0.04, 0.04, 0.04)'), vis('NoL', 'NoVa', 'R02'), ggx('NoH', 'R02'), vis('NoL', 'NoVa', 'R2'), ggx('NoH', 'R2'))
        out += lights_block(body, 'Fill')
        out += env_spec('ES1', 'float3(0.04, 0.04, 0.04)', 'Rough') + env_spec('ES2', 'float3(0.04, 0.04, 0.04)', 'SkinRough')
        out += 'float3 R = DD * INV_PI_ + DS + (SH * Diff * 1.2 + lerp(ES1, ES2, Dens)) * Mix.r;\n'
    elif model == 'skin':
        sss = floats(m['SubsurfaceColor'])
        out += '''
float Rough = clamp(Mix.g, 0.09, 1.0);
float Curv = 1.0 - Mix.b;
float3 DiffC = Albedo;
float3 SpecC = float3(0.028, 0.028, 0.028);
float NoVa = saturate(abs(NoV) + 1e-5);
float R2 = Square(max(0.01, Rough));
float3 SSS = %s;
''' % f3(sss[:3])
        body = HALF + '''
{ float NoL = max(0.0, NoLr); float3 F = %s;
  DD += NoL * DiffC * A * (Curv * 0.1 + 0.88) * LC;
  DS += max(0.0, %s * %s * NoL) * F * A * LC;
  DT += Texture2DSampleLevel(Lut, LutSampler, float2(0.5 * NoLr + 0.5, Curv), 0).rgb * SSS * DiffC * INV_PI_ * A * LC; }
''' % (schlick('SpecC'), vis('NoL', 'NoVa', 'R2'), ggx('NoH', 'R2'))
        out += lights_block(body, '1.0')
        out += env_spec('ES', 'SpecC', 'Rough')
        out += '''float3 R = DD * INV_PI_ + DT + DS + (SH * DiffC * (Curv * 0.1 + 0.88) + ES) * Mix.r
  + SH * SSS * DiffC * Texture2DSampleLevel(Lut, LutSampler, float2(0.0, Curv), 0).rgb;
'''
    elif model == 'hair':
        intensity = floats(m['Intensity'])
        spec = floats(m['SpecularColor'])
        sp = floats(m['SpecularParam'])
        out += '''
float Metal = Mix.b;
float3 Spec = %s * Aux.rgb * %r;
''' % (f3(spec[:3]), sp[0])
        body = HALF + '''
{ float NoL = saturate(NoLr);
  DD += Albedo * Metal * NoL * %r * A * LC;
  DS += Spec * pow(NoH, %r) * saturate(ANIS) * A * LC; }
''' % (intensity[1], sp[1])
        out += lights_block(body, '1.0')
        out += 'float HairRough = clamp(Mix.g, 1.0 / 255.0, 1.0);\n' + env_spec('ES', 'float3(0.04, 0.04, 0.04)', 'HairRough')
        out += 'float3 R = DD * INV_PI_ + DS + (SH * Albedo * %r * Metal + ES * %r * 0.2) * Mix.r + SH * Albedo * %r * Metal * %r;\n' % (
            intensity[1], intensity[1], intensity[1], floats(m['BackLightParam'])[0])
    elif model == 'eye':
        intensity = floats(m['Intensity'])
        body = HALF + '''
{ float NoL = max(NoLr, 0.0); DD += NoL * Albedo * A * LC; }
'''
        out += lights_block(body, '1.0')
        out += '''float2 MUV = float2(NView.x, -NView.y) * 0.5 + 0.5;
float3 MC = Texture2DSampleLevel(Matcap, MatcapSampler, MUV, %r).rgb;
float3 R = DD * INV_PI_ + SH * Albedo + MC * %r + Aux.rgb * %r;
''' % (0.02 * 7.0, intensity[3], intensity[1])
    else:
        raise ValueError(model)
    out += tone(adjust)
    out += 'return R;\n'
    return out


# ----------------------------------------------------------- Unreal side ----

def run():
    import unreal
    p = plan()
    digest = recipe_digest(p)
    dest = '/Game/Recovered/Battle/SourceShading/v1_' + digest
    check(Path(unreal.Paths.get_project_file_path()).resolve() == PROJECT, 'Wrong project')
    world = unreal.EditorLoadingAndSavingUtils.load_map(MAP)
    check(world and world.get_path_name().split('.')[0] == MAP, 'Tutorial map did not load')
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()

    def tagged(tag):
        found = [a for a in actors if a.actor_has_tag(tag)]
        check(len(found) == 1, 'Missing/ambiguous ' + tag)
        return found[0].get_component_by_class(unreal.SkeletalMeshComponent)

    player, enemy = tagged('HCZSBattlePlayer'), tagged('HCZSBattleEnemy')
    check(player.get_num_materials() == 9 and enemy.get_num_materials() == 1, 'Actor slot inventory changed')
    edit = unreal.MaterialEditingLibrary
    assets = unreal.EditorAssetLibrary
    textures = {}
    for key, row in p['textures'].items():
        path = dest + '/Textures/' + row['asset']
        if not assets.does_asset_exist(path):
            task = unreal.AssetImportTask()
            task.set_editor_property('filename', row['png'])
            task.set_editor_property('destination_path', dest + '/Textures')
            task.set_editor_property('destination_name', row['asset'])
            task.set_editor_property('automated', True)
            task.set_editor_property('replace_existing', True)
            task.set_editor_property('save', False)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        texture = unreal.load_asset(path)
        check(isinstance(texture, unreal.Texture2D), 'Texture import failed: ' + path)
        kind = row['kind']
        texture.set_editor_property('virtual_texture_streaming', False)
        texture.set_editor_property('compression_settings', {
            'mask': unreal.TextureCompressionSettings.TC_MASKS,
            'lut': unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
            'linear': unreal.TextureCompressionSettings.TC_DEFAULT,
            'normal': unreal.TextureCompressionSettings.TC_NORMALMAP,
            'colour': unreal.TextureCompressionSettings.TC_DEFAULT}[kind])
        if kind == 'normal':
            texture.set_editor_property('flip_green_channel', False)
        if kind == 'lut':
            texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            texture.set_editor_property('address_x', unreal.TextureAddress.TA_CLAMP)
            texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)
        texture.set_editor_property('srgb', kind == 'colour')
        check(bool(texture.get_editor_property('srgb')) == (kind == 'colour'), 'Texture colour space readback failed')
        assets.set_metadata_tag(texture, 'HczsSourcePNGSHA256', row['png_sha256'])
        check(assets.save_loaded_asset(texture, False), 'Texture save failed')
        textures[key] = texture
    probe_path = dest + '/Textures/T_ReflectionProbe'
    if not assets.does_asset_exist(probe_path):
        task = unreal.AssetImportTask()
        task.set_editor_property('filename', str(PROBE_DDS))
        task.set_editor_property('destination_path', dest + '/Textures')
        task.set_editor_property('destination_name', 'T_ReflectionProbe')
        task.set_editor_property('automated', True)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('save', False)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    probe = unreal.load_asset(probe_path)
    check(isinstance(probe, unreal.TextureCube), 'Reflection probe did not import as a TextureCube')
    probe.set_editor_property('srgb', False)
    probe.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    assets.set_metadata_tag(probe, 'HczsSourceDDSSHA256', p['probe']['dds_sha256'])
    check(assets.save_loaded_asset(probe, False), 'Probe save failed')
    textures['probe'] = probe

    def node(material, kind, x, y, **props):
        obj = edit.create_material_expression(material, kind, x, y)
        check(obj, 'Expression creation failed')
        for k, v in props.items():
            obj.set_editor_property(k, v)
        return obj

    def link(a, out, b, pin):
        check(edit.connect_material_expressions(a, out, b, pin), 'Link failed ' + pin)

    def sampler(kind):
        return {'mask': unreal.MaterialSamplerType.SAMPLERTYPE_MASKS, 'colour': unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
                'normal': unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
                'linear': unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR}[kind]

    def build(side, slot, name):
        model = MODELS[name]
        source_path = '%s/M_%s_%d_SourceRGBA' % (VISUAL_FIX, side, slot)
        source = unreal.load_asset(source_path)
        check(isinstance(source, unreal.Material), 'Missing VisualFix colour material ' + source_path)
        albedo_tex = edit.get_material_default_texture_parameter_value(source, 'SourceColorTexture')
        tint = edit.get_material_default_vector_parameter_value(source, 'SourceColorFactor')
        asset_name = 'M_%s_%d_%s' % (side, slot, model)
        path = dest + '/' + asset_name
        if assets.does_asset_exist(path):
            material = unreal.load_asset(path)
            if assets.get_metadata_tag(material, 'HczsSourceShadingState') == 'complete':
                return material
            edit.delete_all_material_expressions(material)
        else:
            material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(asset_name, dest, unreal.Material, unreal.MaterialFactoryNew())
        check(material, 'Material creation failed')
        assets.set_metadata_tag(material, 'HczsSourceShadingState', 'building')
        material.set_editor_property('blend_mode', source.get_editor_property('blend_mode'))
        material.set_editor_property('opacity_mask_clip_value', source.get_editor_property('opacity_mask_clip_value'))
        material.set_editor_property('two_sided', source.get_editor_property('two_sided'))
        material.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
        edit.set_base_material_usage(material, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)
        code = shader(model, p, 'enemy' if side == 'enemy' else name)
        custom = node(material, unreal.MaterialExpressionCustom, 0, 0, code=code,
                      output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description='NeoX ' + model + ' lighting')
        names = ['Albedo', 'Mix', 'Aux', 'Fill', 'Nin', 'Vin', 'P', 'NView', 'Lut', 'Matcap', 'Probe']
        inputs = []
        for n in names:
            ci = unreal.CustomInput()
            ci.set_editor_property('input_name', n)
            inputs.append(ci)
        custom.set_editor_property('inputs', inputs)
        base = node(material, unreal.MaterialExpressionTextureSampleParameter2D, -900, -300, parameter_name='SourceColorTexture',
                    texture=albedo_tex, sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        factor = node(material, unreal.MaterialExpressionVectorParameter, -900, -100, parameter_name='SourceColorFactor', default_value=tint)
        albedo = node(material, unreal.MaterialExpressionMultiply, -600, -300)
        link(base, 'RGB', albedo, 'A')
        link(factor, 'RGB', albedo, 'B')
        link(albedo, '', custom, 'Albedo')
        mix_key, fill_key, aux_key = SLOT_TEXTURES['enemy' if side == 'enemy' else name]
        y = 0
        for pin, key in (('Mix', mix_key), ('Fill', fill_key), ('Aux', aux_key)):
            if key is None and pin == 'Fill':
                link(node(material, unreal.MaterialExpressionConstant, -600, y, r=1.0), '', custom, pin)
            elif key is None:
                const = node(material, unreal.MaterialExpressionConstant4Vector, -600, y,
                             constant=unreal.LinearColor(1, 1, 1, 1))
                link(const, '', custom, pin)
            else:
                kind = p['textures'][key]['kind']
                props = dict(texture=textures[key], sampler_type=sampler(kind))
                sample = node(material, unreal.MaterialExpressionTextureSample, -600, y, **props)
                if key == 'siwa_d':
                    tiling = float(p['mtg']['siwa']['tilling'])
                    uv = node(material, unreal.MaterialExpressionTextureCoordinate, -900, y, coordinate_index=0,
                              u_tiling=tiling, v_tiling=tiling)
                    link(uv, '', sample, 'UVs')
                if pin == 'Fill':
                    link(sample, 'A', custom, pin)
                else:
                    append = node(material, unreal.MaterialExpressionAppendVector, -350, y)
                    link(sample, 'RGB', append, 'A')
                    link(sample, 'A', append, 'B')
                    link(append, '', custom, pin)
            y += 200
        normal_map = node(material, unreal.MaterialExpressionTextureSample, -1200, 600,
                          texture=textures[SLOT_NORMALS['enemy' if side == 'enemy' else name]],
                          sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        normal = node(material, unreal.MaterialExpressionTransform, -900, 600,
                      transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_TANGENT,
                      transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
        link(normal_map, 'RGB', normal, '')
        sign = node(material, unreal.MaterialExpressionTwoSidedSign, -900, 700)
        signed = node(material, unreal.MaterialExpressionMultiply, -600, 650)
        link(normal, '', signed, 'A')
        link(sign, '', signed, 'B')
        link(signed, '', custom, 'Nin')
        camera = node(material, unreal.MaterialExpressionCameraVectorWS, -600, 800)
        link(camera, '', custom, 'Vin')
        position = node(material, unreal.MaterialExpressionWorldPosition, -600, 900)
        link(position, '', custom, 'P')
        view = node(material, unreal.MaterialExpressionTransform, -350, 650,
                    transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
                    transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_VIEW)
        link(signed, '', view, '')
        link(view, '', custom, 'NView')
        for i, (pin, key) in enumerate((('Lut', 'lut'), ('Matcap', 'matcap'), ('Probe', 'probe'))):
            obj = node(material, unreal.MaterialExpressionTextureObject, -600, 1000 + 100 * i,
                       texture=textures[key], sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR
                       if key == 'matcap' else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
            link(obj, '', custom, pin)
        inverse = node(material, unreal.MaterialExpressionEyeAdaptationInverse, 300, 0)
        one = node(material, unreal.MaterialExpressionConstant, 100, 200, r=1.0)
        pins = [str(n) for n in edit.get_material_expression_input_names(inverse)]
        def pin_of(prefix):
            found = [n for n in pins if ''.join(c for c in n.lower() if c.isalnum()).startswith(prefix)]
            check(len(found) == 1, 'EyeAdaptationInverse pins changed ' + repr(pins))
            return found[0]
        link(custom, '', inverse, pin_of('lightvalue'))
        link(one, '', inverse, pin_of('alpha'))
        check(edit.connect_material_property(inverse, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR), 'Emissive link failed')
        blend = source.get_editor_property('blend_mode')
        if blend != unreal.BlendMode.BLEND_OPAQUE:
            alpha = node(material, unreal.MaterialExpressionMultiply, -350, -200)
            link(base, 'A', alpha, 'A')
            link(factor, 'A', alpha, 'B')
            target = unreal.MaterialProperty.MP_OPACITY_MASK if blend == unreal.BlendMode.BLEND_MASKED else unreal.MaterialProperty.MP_OPACITY
            check(edit.connect_material_property(alpha, '', target), 'Opacity link failed')
        result = edit.recompile_material(material)
        errors = list(result) if result is not None else ['no compiler result']
        check(not errors, 'Shader compile failed for %s: %r' % (asset_name, errors))
        assets.set_metadata_tag(material, 'HczsSourceShadingRecipe', digest)
        assets.set_metadata_tag(material, 'HczsSourceShadingState', 'complete')
        check(assets.save_loaded_asset(material, False), 'Material save failed')
        return material

    report = dict(schema='hczs-battle-source-shading-v1', recipe=digest, destination=dest, lights=p['lights'],
                  shader_sha256=p['shader_sha256'], bindings=[], passed=False,
                  normal_maps='Source tangent-space maps through UE TangentToWorld; green convention chosen by curl test',
                  probe=p['probe'],
                  not_ported=['shadow maps', 'SSR', 'probe box projection / blend weight (single probe, weight 1)',
                              'hair TT/TRT transmission', 'CharacterLight cube maps', 'inverted-hull outlines', 'fog',
                              'GenerageTone runs on the UE unlit result before UE tonemapping'],
                  sh_evaluation='L0 coefficient * Y00 (0.2820948); SH packing not recovered from native code')
    for slot, name in PLAYER_SLOTS.items():
        material = build('player', slot, name)
        player.set_material(slot, material)
        check(player.get_material(slot) == material, 'Player override readback failed')
        report['bindings'].append(dict(side='player', slot=slot, source=name, model=MODELS[name], material=material.get_path_name()))
    material = build('enemy', 0, 'enemy')
    enemy.set_material(0, material)
    check(enemy.get_material(0) == material, 'Enemy override readback failed')
    report['bindings'].append(dict(side='enemy', slot=0, source='initialShadingGroup', model='isotropy+emissive', material=material.get_path_name()))
    check(unreal.EditorLoadingAndSavingUtils.save_map(world, MAP), 'Map save failed')
    report['passed'] = True
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    unreal.log('HCZS SOURCE SHADING applied: ' + dest)
    return report


if __name__ == '__main__':
    if '--prepare' in sys.argv:
        print(json.dumps(prepare_probe(), indent=2))
    elif '--plan' in sys.argv:
        p = plan()
        print(json.dumps(dict(recipe=recipe_digest(p), lights=p['lights']), ensure_ascii=False, indent=2))
        if '--hlsl' in sys.argv:
            print(shader(sys.argv[sys.argv.index('--hlsl') + 1], p, sys.argv[sys.argv.index('--hlsl') + 2]))
    else:
        try:
            run()
        except Exception as error:  # noqa: BLE001
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(json.dumps(dict(passed=False, error=repr(error)), ensure_ascii=False, indent=2), 'utf8')
            raise
