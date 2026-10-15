"""Prepare a source-BRDF reflection comparison; runtime selection remains unknown."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_elsa_model import split_glb
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/unreal/battle-reference/baked-diffuse'
BRDF = ROOT / 'analysis/unreal/elsa-material/shaders/6212c1c114bd815a3065.hlsl'
SAMPLING = ROOT / 'analysis/unreal/elsa-material/shaders/141a48c15789f0295894.hlsl'
BRDF_SHA = 'f561cfa8321bb18e142cf3e0239670ab70109ba41eeb3426780c3669c4bbdfc6'
SAMPLING_SHA = '702378f3c74c43794e03ef27659d20ea4e9a3acb8fe6487f4063cfc19654d3fd'


def function_body(text, signature):
    start = text.index('{', text.index(signature))
    level, end = 1, start + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start+1:end-1]


def prepare():
    for path, expected in ((BRDF, BRDF_SHA), (SAMPLING, SAMPLING_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Reviewed APK shader changed')
        provenance = json.loads(path.with_suffix('.hlsl.provenance.json').read_text('utf8'))
        if provenance['apk_sha256'] != APK_SHA256 or provenance['sha256'] != expected:
            raise ValueError('Shader APK provenance differs')
    body = function_body(BRDF.read_text('utf8'), 'float3 EnvBRDFApprox(')
    expected_return = 'return SpecularColor * AB.x + AB.y;'
    if body.count(expected_return) != 1:
        raise ValueError('Original environment BRDF return differs')
    cube_folder = ROOT / 'analysis/battle-visual/reflection/boss_theatre'
    dds = json.loads((cube_folder / 'dds.json').read_text('utf8'))
    cube = json.loads((ROOT / 'analysis/unreal/battle-reference/source-reflection-import.json').read_text('utf8'))
    if cube['sourceDdsSha256'] != dds['ddsSha256'] or cube['builtTextureSize'] != [128,128,6] or cube['srgb']:
        raise ValueError('Native cube import readback differs')
    lightmaps = ROOT / 'analysis/battle-visual/lightmaps/boss_theatre'
    metadata = json.loads((lightmaps / 'lightmaps.json').read_text('utf8'))
    scene_bytes = (lightmaps / 'scene.scn').read_bytes()
    if hashlib.sha256(scene_bytes).hexdigest() != metadata['sceneSource']['sha256'] or metadata['apkSha256'] != APK_SHA256:
        raise ValueError('Original scene identity differs')
    scene = ET.fromstring(scene_bytes)
    probes = scene.findall('.//ReflectionProbes/Probes/Probe')
    if len(probes) != 1 or any(probes[0].get(key) != 'false' for key in
            ('UseBoxProjection', 'UseSHNormalization', 'UseBrightnessCompress')):
        raise ValueError('This comparison only supports the single unnormalized, uncompressed, non-box-projected probe')
    recipe = json.loads((BASE / 'recipe.json').read_text('utf8'))
    glb = ROOT / 'analysis/battle-visual/prologue-theatre/boss_theatre_surface/scene.glb'
    document, _ = split_glb(glb.read_bytes())
    if hashlib.sha256(glb.read_bytes()).hexdigest() != recipe['sourceGlbSha256']:
        raise ValueError('Staged source mesh changed')
    instances = {n['extras']['sourceInstance']['UUID']: n['extras']['sourceInstance'] for n in document['nodes']}
    for binding in recipe['bindings']:
        flag = instances[binding['uuid']].get('UseReflectionProbe')
        binding.update(sourceReflectionFlag=flag, reflectionWeight=1 if flag == '1' else 0)
    shader = recipe['shader']
    original = 'return albedo * (1 - mix.b) * mix.r * irradiance;'
    if shader.count(original) != 1:
        raise ValueError('Baked diffuse recipe changed')
    shader = shader.replace(original, 'float3 baked = albedo * (1 - mix.b) * mix.r * irradiance;')
    shader += '''
// Source world adapter: UE (-X,Z,Y) is the inverse of the imported stage basis.
float3 sourceR = float3(-ReflectionDirectionUE.x, ReflectionDirectionUE.z, ReflectionDirectionUE.y);
float Roughness = clamp(mix.g, 0.09, 1.0);
float NoV = dot(normalize(WorldNormal), normalize(ViewDirectionUE));
float3 SpecularColor = lerp(float3(0.04,0.04,0.04), albedo, mix.b);
float3 environment = SourceProbe.SampleLevel(SourceProbeSampler, sourceR, Roughness * MaxMip).rgb;
'''
    shader += body.replace(expected_return, 'return baked + (SpecularColor * AB.x + AB.y) * environment * mix.r * ReflectionWeight;')
    recipe.update(shader=shader, reflectionCube=cube['asset'], reflectionDdsSha256=dds['ddsSha256'],
        probeSourceAttributes=probes[0].attrib, sourceBrdfSha256=BRDF_SHA, sourceSamplingSha256=SAMPLING_SHA,
        previewMaxMip=dds['mipCount']-1,
        limitations=[
            'Partial baked diffuse and candidate environment reflection only; original dynamic-light units, fog and final tone mapping remain unverified.',
            *recipe['limitations'][1:],
            'Independent reflection comparison only: SIMPLE_SHADING selection, original ReflectionProbeInfo mip scalar and KTX/D3D cube basis remain unobserved.',
            'Preview uses explicit max mip 7 and inverse stage world-axis adapter; original runtime equivalence is not asserted.',
            'Reflection is enabled only on the two instances with explicit UseReflectionProbe=1; missing source flags remain disabled in this comparison.',
            'Source BRDF approximation and sampled RGB term are ported; UE direct lighting and tone mapping remain adapters.'])
    recipe.pop('recipeSha256')
    recipe['recipeSha256'] = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
    (BASE / 'reflection-recipe.json').write_text(json.dumps(recipe, indent=2), 'utf8')
    print(json.dumps(dict(bindings=len(recipe['bindings']), reflectionInstances=sum(row['reflectionWeight'] for row in recipe['bindings']), recipeSha256=recipe['recipeSha256'])))


if __name__ == '__main__':
    prepare()
