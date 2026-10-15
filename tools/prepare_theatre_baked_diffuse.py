"""Bind unambiguous original theatre UV1/lightmap inputs to a diffuse-only port."""
import hashlib
import json
from pathlib import Path
from export_elsa_model import split_glb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/battle-reference/baked-diffuse'
CODE = '''float3 encoded = Texture2DSample(Lightmap, LightmapSampler, UV1 * UVScaleOffset.xy + UVScaleOffset.zw).rgb * LMScale + LMAdd;
float logL = dot(float3(0.299, 0.587, 0.114), encoded);
float luminance = (exp2(logL * 16.0 - 8.0) - 0.00390625) * 0.6;
float3 irradiance = encoded * (luminance / max(logL, 0.00001));
float3 albedo = Texture2DSample(Albedo, AlbedoSampler, UV0).rgb;
float3 mix = Texture2DSample(Mix, MixSampler, UV0).rgb;
return albedo * (1 - mix.b) * mix.r * irradiance;'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'analysis/battle-visual/prologue-theatre/boss_theatre_surface/scene.glb'
    document, binary = split_glb(source.read_bytes())
    lighting_file = ROOT / 'analysis/battle-visual/lightmaps/boss_theatre/lightmaps.json'
    lighting = json.loads(lighting_file.read_text('utf8'))
    nodes = {n['extras']['sourceInstance']['UUID']: (i, n) for i, n in enumerate(document['nodes'])}
    images = {}

    def image(index, srgb):
        image_index = document['textures'][index]['source']
        view = document['bufferViews'][document['images'][image_index]['bufferView']]
        offset = view.get('byteOffset', 0)
        data = binary[offset:offset + view['byteLength']]
        sha = hashlib.sha256(data).hexdigest()
        path = OUT / ('T_' + sha[:20] + '.png')
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Derived PNG hash collision')
        path.write_bytes(data)
        key = sha + str(srgb)
        images[key] = dict(path=str(path), sha256=sha, srgb=srgb)
        return key

    bindings, deferred = [], []
    for binding in lighting['bindings']:
        index, instance = nodes[binding['instanceUuid']]
        primitives = document['meshes'][instance['mesh']]['primitives']
        if len(primitives) != 1:
            deferred.append(dict(uuid=binding['instanceUuid'], name=binding['instanceName'],
                primitiveCount=len(primitives), reason='One source lightmap entry vs multiple primitives; native shared/LOD binding semantics not established'))
            continue
        primitive = primitives[0]
        if 'TEXCOORD_1' not in primitive['attributes']:
            raise ValueError('Missing original UV1')
        material = document['materials'][primitive['material']]
        if material.get('alphaMode', 'OPAQUE') != 'OPAQUE':
            raise ValueError('Diffuse port only accepts source opaque surfaces')
        pbr = material['pbrMetallicRoughness']
        values = binding['values']
        if values['encode_type'] != '4' or values['UE4_lm'] != 'true':
            raise ValueError('Unsupported lightmap encoding')
        texture = next(t for t in lighting['textures'] if t['index'] == int(values['texture_index']))
        decoded = texture['decoded']['textures'][0]['outputs'][0]
        lm_path = ROOT / decoded['png']
        lm_sha = hashlib.sha256(lm_path.read_bytes()).hexdigest()
        key = lm_sha + 'False'
        images[key] = dict(path=str(lm_path), sha256=lm_sha, srgb=False)
        bindings.append(dict(uuid=binding['instanceUuid'], actorLabel='boss_theatre_node_' + str(index),
            sourceName=binding['instanceName'], albedo=image(pbr['baseColorTexture']['index'], True),
            mix=image(pbr['metallicRoughnessTexture']['index'], False),
            normal=image(material['normalTexture']['index'], False), lightmap=key,
            uvScaleOffset=[float(v) for field in ('uv_scale', 'uv_ofs') for v in values[field].split(',')],
            lmScale=[float(v) for v in values['lightmap_scale'].split(',')],
            lmAdd=[float(v) for v in values['lightmap_add'].split(',')[:3]]))
    result = dict(sourceMap='/Game/Recovered/SourceStages/Maps/L_Theatre',
        targetMap='/Game/Recovered/SourceStages/Maps/L_TheatreBakedDiffuse',
        sourceGlbSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        lightmapMetadataSha256=hashlib.sha256(lighting_file.read_bytes()).hexdigest(),
        shader=CODE, images=images, bindings=bindings, deferred=deferred,
        limitations=['Baked diffuse term only: original dynamic lighting, specular/probes, fog and final tone mapping are not restored.',
            'Multi-primitive lightmap bindings remain unresolved; no source slots are guessed.'])
    result['recipeSha256'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    (OUT / 'recipe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(bindings=len(bindings), deferred=len(deferred), textures=len(images))))


if __name__ == '__main__':
    main()
