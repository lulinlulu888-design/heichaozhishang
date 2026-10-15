"""Prepare the source DISSOLVE_EFFECT-only lancer3 branch for UE translation."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'


def main():
    source = json.loads((BASE / 'bindings.json').read_text('utf8'))
    shader = next(f['source'] for f in source['files'] if f['source']['logical_path'] == 'shader/lancer3.fx')
    raw = Path(shader['sample_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != shader['sha256']:
        raise ValueError('Original shader changed')
    text = raw.decode('gb18030')
    defaults = {name: value.strip().strip('{}').replace('f', '') for name, value in
                re.findall(r'^(?:float[234]?|int)\s+(\w+)\s*<[^>]*>\s*=\s*([^;]+);', text, re.M)}
    meshes = json.loads((BASE / 'mesh-export.json').read_text('utf8'))
    decoded = json.loads((BASE / 'png/manifest.json').read_text('utf8'))
    textures = {r['provenance']['logical_path']: r for r in decoded['textures']}
    recipes = []
    for model in meshes['models']:
        for mat in model['materials']:
            if mat['technique']['TechName'].replace('\\', '/') != 'shader/lancer3.fx::TShader' or mat['macros'] != {'DISSOLVE_EFFECT': 'TRUE'}:
                continue
            p = {**defaults, **mat['params']}
            def number(key):
                return ','.join(format(float(x), '.9g') for x in p[key].split(','))
            def vec(key):
                values = number(key)
                return 'float%d(%s)' % (len(values.split(',')), values)
            rows = []
            for name in ('g_vDistortionTiling', 'g_vDistortionSpeed', 'g_vFloatingSpeed1', 'g_vDissolveTiling'):
                rows.append(f'float2 {name} = {vec(name)};')
            for name in ('g_vFloatingTilingU1', 'g_vFloatingTilingV1', 'g_fDistortionStrength1', 'mirror_u', 'mirror_v',
                         'rotation_floatTex01', 'offset_u', 'offset_v', 'g_fFloatingStrength1', 'g_vDissolveSpeedU',
                         'g_vDissolveSpeedV', 'g_DissolveStrength', 'g_dissolve_hardness'):
                dynamic = {'g_DissolveStrength': 'SourceDissolve', 'g_fFloatingStrength1': 'SourceStrength'}
                rows.append(f'float {name} = {dynamic.get(name, number(name))};')
            # UE colour texture sampling performs sRGB decode; numerical textures remain linear.
            colour = [float(x) for x in p['g_colFloatingColor1'].split(',')[:3]]
            colour = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in colour]
            rows.append('float3 tint = SourceTint;')
            rows.append('''float noise = Texture2DSample(Noise,NoiseSampler,UV*g_vDistortionTiling+Time*g_vDistortionSpeed).r;
float2 uv = UV*float2(g_vFloatingTilingU1,g_vFloatingTilingV1)+noise*g_fDistortionStrength1+Time*g_vFloatingSpeed1;
uv *= (float2(mirror_u,mirror_v)-0.5)*-2;
float a = 6.283185307179586*rotation_floatTex01;
uv = float2(uv.x*cos(a)-uv.y*sin(a),uv.x*sin(a)+uv.y*cos(a))+float2(offset_u,offset_v);
float4 c = Texture2DSample(Color,ColorSampler,uv);
float d = Texture2DSample(Dissolve,DissolveSampler,UV*g_vDissolveTiling+Time*float2(g_vDissolveSpeedU,g_vDissolveSpeedV)).r;
float opacity = pow(saturate((d-g_DissolveStrength+0.1)*5),g_dissolve_hardness)*c.a*SourceAlpha;
return float4(c.rgb*tint*g_fFloatingStrength1,opacity);''')
            bindings = []
            for name, key, srgb in [('Color', 'Tex0', True), ('Noise', 'TexDistortion', False), ('Dissolve', 'TexDissolve', False)]:
                logical = str(Path(p[key].replace('\\', '/')).with_suffix('.ktx')).replace('\\', '/')
                texture = textures[logical]['outputs'][0]
                bindings.append({'input': name, 'logical': logical, 'png': str(ROOT / texture['png']),
                                 'sha256': texture['png_sha256'], 'srgb': srgb})
            recipes.append({'gim': model['gim'], 'code': '\n'.join(rows), 'textures': bindings,
                            'dynamicDefaults': {'SourceTint': colour, 'SourceDissolve': float(p['g_DissolveStrength']),
                                                'SourceStrength': float(p['g_fFloatingStrength1'])},
                            'originalMaterial': mat, 'defaultValuesFromShader': defaults,
                            'sourceShaderSha256': shader['sha256']})
    if len(recipes) != 2:
        raise ValueError('Expected two reviewed dissolve-only materials')
    result = {'materials': recipes, 'limitations': ['UE linear colour pipeline adaptation; original runtime global macros unobserved',
               'Particle alpha, lifecycle and source transforms must be provided by effect playback', 'Other lancer3 branches are not implemented']}
    (BASE / 'lancer3-recipe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({'materials': len(recipes), 'shaderSha256': shader['sha256']}))


if __name__ == '__main__':
    main()
