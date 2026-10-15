"""Recover source hall baked lighting; retain unsupported bindings explicitly."""
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image

from decode_ktx import convert, parse_ktx, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract, split_glb
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/hall/lighting'


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK changed')
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = read_catalogue(apk)
    sources = []

    def source(logical, filename):
        target = OUT / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        row = extract(apk, catalog, logical, target, APK_SHA256)
        sources.append(row)
        return target

    scene_path = source('scene/midgard_home_3d/midgard_home_3d.scn', 'source/hall.scn')
    scene = ET.fromstring(scene_path.read_bytes())
    for name, logical in [
        ('default_functions.hlsl', 'shader/built_in/vertex_fragment_models/default_functions.hlsl'),
        ('function.hlsl', 'shader/built_in/common/function.hlsl'),
        ('common.hlsl', 'shader/built_in/common/common.hlsl'),
    ]:
        source(logical, 'source/' + name)
    shader = (OUT / 'source/default_functions.hlsl').read_text('utf8')
    luminance = (OUT / 'source/function.hlsl').read_text('utf8')
    for text in ['LogBlackPoint = 0.00390625', 'ConstDirectional = 0.6', 'LogL * 16 - 8']:
        if text not in shader:
            raise ValueError('Reviewed lightmap formula changed')
    if 'float3(0.299, 0.587, 0.114)' not in luminance:
        raise ValueError('Reviewed luminance formula changed')
    table = scene.find('.//ModelLightmaps')
    base = table.find('LightMapPath').get('Path').replace('\\', '/')
    textures = []
    for entry in list(table)[1:]:
        index = len(textures)
        if entry.tag != f'lightmap_{index}':
            raise ValueError('Non-contiguous lightmap table')
        logical = base + '/' + str(Path(entry.get('Path')).with_suffix('.ktx'))
        raw = source(logical, f'source/lightmap_{index}.ktx')
        meta = parse_ktx(raw.read_bytes())
        if meta['profile'] != 'linear' or meta['faces'] != 1:
            raise ValueError('Lightmap must be a linear 2D texture')
        decoded = convert([raw], OUT / f'decoded/{index}', DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
        result = decoded['textures'][0]['outputs'][0]
        png = ROOT / result['png']
        target = OUT / f'lightmap_{index}.png'
        shutil.copyfile(png, target)
        textures.append(dict(file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                             logical=logical, source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                             ktx=meta))
    glb_path = ROOT / 'analysis/hall/midgard_home_3d/scene.glb'
    glb = glb_path.read_bytes()
    doc, binary = split_glb(glb)
    nodes = {n['extras']['sourceInstance']['UUID']: n for n in doc['nodes'] if 'mesh' in n}
    bindings, unresolved = [], []
    for model in scene.iter('model'):
        lm = model.find('Lightmap')
        if lm is None:
            continue
        row = dict(uuid=model.get('UUID'), name=model.get('Name'), parameters=[x.attrib for x in lm])
        node = nodes.get(row['uuid'])
        if node is None:
            unresolved.append(dict(**row, reason='instance not exported'))
            continue
        primitives = doc['meshes'][node['mesh']]['primitives']
        # A single sub_lightmap with several render primitives may address a LOD,
        # rather than a primitive. Preserve this ambiguity until consumer proof.
        if len(primitives) != 1 or len(lm) != 1:
            unresolved.append(dict(**row, reason='multi-primitive binding semantics unverified',
                                   primitives=len(primitives)))
            continue
        p = primitives[0]
        if 'TEXCOORD_1' not in p['attributes']:
            raise ValueError('Missing UV1: ' + row['name'])
        params = lm[0].attrib
        if params['UE4_lm'] != 'true' or params['encode_type'] != '4':
            raise ValueError('Unreviewed encoding')
        if not 0 <= int(params['texture_index']) < len(textures):
            raise ValueError('Lightmap index outside source table')
        bindings.append(dict(uuid=row['uuid'], name=row['name'], mesh=node['mesh'], primitive=0,
                             uv_count=doc['accessors'][p['attributes']['TEXCOORD_1']]['count'], parameters=params))
    lights = [dict(attributes=x.attrib, children=[dict(tag=c.tag, attributes=c.attrib) for c in x])
              for x in scene.iter('light')]
    report = dict(schema=1, apk_sha256=APK_SHA256, scene_glb_sha256=hashlib.sha256(glb).hexdigest(),
                  images=[x['file'] for x in textures], textures=textures, bindings=bindings,
                  unresolved=unresolved, lights=lights,
                  ambient=[x.attrib for x in scene.iter('AmbientLight')], sources=sources,
                  evidence_kind='Source extraction and local parser; not new REA Evidence or original runtime',
                  limitations=['Diffuse colour multiplied by original decoded baked irradiance only',
                               'Original BRDF, normal maps, emissive, HDR, dynamic lights and shadows not ported',
                               'Multi-primitive instances deliberately deferred, not assigned guessed lightmaps',
                               'Directional lightmap data and source light-channel semantics unresolved'])
    (OUT / 'lighting.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    probes = []
    for row in bindings:
        params = row['parameters']
        primitive = doc['meshes'][row['mesh']]['primitives'][0]
        accessor = doc['accessors'][primitive['attributes']['TEXCOORD_1']]
        view = doc['bufferViews'][accessor['bufferView']]
        if accessor['componentType'] != 5126 or accessor['type'] != 'VEC2' or view.get('byteStride', 8) != 8:
            raise ValueError('Unexpected UV buffer layout')
        uv = np.frombuffer(binary, dtype='<f4', count=accessor['count'] * 2,
                           offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0)).reshape(-1, 2).astype(float)
        vec = lambda key: np.array(list(map(float, params[key].split(','))))
        uv = uv * vec('uv_scale') + vec('uv_ofs')
        pixels = np.asarray(Image.open(OUT / textures[int(params['texture_index'])]['file']).convert('RGB'), dtype=float) / 255
        x = np.clip(np.rint(uv[:, 0] * (pixels.shape[1] - 1)).astype(int), 0, pixels.shape[1] - 1)
        y = np.clip(np.rint(uv[:, 1] * (pixels.shape[0] - 1)).astype(int), 0, pixels.shape[0] - 1)
        color = pixels[y, x] * vec('lightmap_scale') + vec('lightmap_add')[:3]
        log_l = color @ np.array([.299, .587, .114])
        color *= ((np.exp2(log_l * 16 - 8) - .00390625) * .6 / np.maximum(log_l, .00001))[:, None]
        if not np.isfinite(uv).all() or not np.isfinite(color).all():
            raise ValueError('Nonfinite UV or decoded irradiance')
        probes.append(dict(name=row['name'], vertices=len(uv), uv_min=uv.min(axis=0).tolist(),
                           uv_max=uv.max(axis=0).tolist(), decoded_min=float(color.min()),
                           decoded_max=float(color.max()), out_of_range=int(((uv < 0) | (uv > 1)).any(axis=1).sum())))
    validation = dict(scope='CPU nearest-texel source UV1/transform/formula finiteness probe; not GPU parity',
                      instances=len(probes), vertices=sum(x['vertices'] for x in probes),
                      out_of_range=sum(x['out_of_range'] for x in probes), rows=probes)
    (OUT / 'validation.json').write_text(json.dumps(validation, indent=2, allow_nan=False), 'utf8')
    print(json.dumps(dict(textures=len(textures), bound_instances=len(bindings),
                          deferred_instances=len(unresolved), original_lights=len(lights))))


if __name__ == '__main__':
    main()
