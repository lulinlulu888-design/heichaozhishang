"""Export recovered city environment geometry/colour; no replacement tutorial or actors."""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import split_glb, pack_glb
from export_neox_gltf import encode_glb
from inspect_neox_model import parse_model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'analysis/battle-visual/city-scenes'


def run(name, base=None, surface_materials=False):
    global BASE
    if base is not None:
        BASE = Path(base)
    records = {r['path']:r for r in json.loads((BASE/'dependencies.json').read_text('utf8'))['records']}
    out = BASE / (name + ('_surface' if surface_materials else ''))
    out.mkdir(parents=True, exist_ok=True)
    sources, skipped = set(), []
    def read(path):
        row = records[path.replace('\\', '/')]
        if row['status'] != 'present':
            raise ValueError(f'Missing resource: {path}')
        local = ROOT / row['localPath']
        payload = local.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row['sha256']:
            raise ValueError(f'Source changed: {path}')
        sources.add(row['path'])
        return payload, local
    source_path = f'scene/{name}/{name}.scn'
    scene = ET.fromstring(read(source_path)[0])
    doc = dict(asset=dict(version='2.0', generator='hczs source city environment'),
        bufferViews=[], accessors=[], meshes=[], nodes=[], images=[], textures=[], materials=[],
        scenes=[dict(nodes=[])], scene=0, extensionsUsed=['KHR_materials_unlit'])
    binary, textures, meshes = bytearray(), {}, {}
    def append(payload):
        binary.extend(b'\0'*(-len(binary)%4))
        offset = len(binary)
        binary.extend(payload)
        return offset
    def texture(path):
        path = path.replace('\\', '/')
        if path in textures:return textures[path]
        _, local = read(path)
        key = hashlib.sha256(path.encode()).hexdigest()[:20]
        result = convert([local], out/'png'/key, DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
        png = ROOT / result['textures'][0]['outputs'][0]['png']
        payload = png.read_bytes()
        offset = append(payload)
        doc['bufferViews'].append(dict(buffer=0, byteOffset=offset, byteLength=len(payload)))
        doc['images'].append(dict(bufferView=len(doc['bufferViews'])-1, mimeType='image/png'))
        doc['textures'].append(dict(source=len(doc['images'])-1))
        textures[path] = len(doc['textures'])-1
        return textures[path]
    for entry in scene.find('.//AllFiles'):
        path = entry.attrib['Path'].replace('\\', '/')
        if not path.endswith('.gim'):continue
        if path.startswith('character/') or records[path]['status'] != 'present':
            skipped.append(dict(path=path, reason='scene actor excluded from environment' if path.startswith('character/') else 'missing source'))
            continue
        gim = ET.fromstring(read(path)[0])
        model = parse_model(read(path[:-4]+'.mesh')[0], preserve_nonunit_normals=True)
        mtg = ET.fromstring(read(path[:-4]+'.mtg')[0])
        if any(item.find('Material/ParamTable/Tex0') is None for item in mtg.find('MaterialGroup')):
            skipped.append(dict(path=path,reason='material has no Tex0; native shader required, no invented colour'))
            continue
        materials = []
        for item in mtg.find('MaterialGroup'):
            material = item.find('Material')
            tex = material.find('ParamTable/Tex0')
            if tex is None:raise ValueError(f'No colour texture for {path}')
            tex_id = texture(tex.attrib['Value'])
            materials.append(len(doc['materials']))
            mode = material.find('RenderStates/TransparentMode').attrib['TransparentMode']
            technique=material.find('Technique').attrib.get('TechName','').replace('\\','/')
            params={e.tag:e.attrib['Value'] for e in material.find('ParamTable')}
            extra_textures={}
            if path=='effects/modeleffect/scene/plane_yun.gim':
                for key in ('TexDistortion','TexMask'):extra_textures[key]=texture(params[key])
            doc['materials'].append(dict(name=material.attrib.get('Name', path), doubleSided=True,
                pbrMetallicRoughness=dict(baseColorTexture=dict(index=tex_id), metallicFactor=0, roughnessFactor=1),
                extensions={'KHR_materials_unlit':{}}, alphaMode='BLEND' if mode=='2' else 'OPAQUE',
                extras=dict(sourceMaterialXML=ET.tostring(material, encoding='unicode'),
                    sourceTechnique=technique, sourceParams=params, extraTextures=extra_textures,
                    sourceModel=path,
                    limitation='Tex0 colour reference; mode 2 conventional alpha blending, native blending/shader not reproduced')))
            technique_attributes = material.find('Technique').attrib
            if surface_materials and technique_attributes.get('Type') == 'Surface':
                target = doc['materials'][-1]
                target['extensions'].pop('KHR_materials_unlit')
                intensity = [float(v) for v in params.get('Intensity', '1,1,1,0').split(',')]
                if len(intensity) != 4 or not all(math.isfinite(v) for v in intensity):
                    raise ValueError('Unsupported source surface intensity')
                pbr = target['pbrMetallicRoughness']
                pbr.update(roughnessFactor=intensity[1], metallicFactor=intensity[2])
                if 'Tex1' in params:
                    target['normalTexture'] = dict(index=texture(params['Tex1']), scale=intensity[0])
                if 'Tex2' in params:
                    mix = texture(params['Tex2'])
                    pbr['metallicRoughnessTexture'] = dict(index=mix)
                    target['occlusionTexture'] = dict(index=mix, strength=1)
                target['extras'].update(sourceTechniqueAttributes=technique_attributes,
                    limitation='Source basic.surf R=AO/G=roughness/B=metalness into glTF PBR; NeoX BRDF, probes and runtime SIMPLE_SHADING branch not reproduced')
        if surface_materials:
            # glTF normals are unit directions. Preserve raw NeoX lengths in
            # the source parser/report, normalize only this derived PBR mesh.
            model['normals'] = [tuple(v / math.sqrt(sum(c*c for c in normal)) for v in normal)
                                for normal in model['normals']]
        local, payload = split_glb(encode_glb(model, path)[0])
        offset, view_base, accessor_base = append(payload), len(doc['bufferViews']), len(doc['accessors'])
        for view in local['bufferViews']:
            view['byteOffset'] = view.get('byteOffset',0)+offset
            doc['bufferViews'].append(view)
        for accessor in local['accessors']:
            accessor['bufferView'] += view_base
            doc['accessors'].append(accessor)
        primitives = local['meshes'][0]['primitives']
        subs = list(gim.find('SubMesh'))
        if len(primitives)!=len(subs):raise ValueError('GIM submesh mismatch')
        for primitive, sub in zip(primitives,subs):
            primitive['indices'] += accessor_base
            # Unlit export uses no normals; retain original non-unit vectors in source audit.
            primitive['attributes'] = {k:v+accessor_base for k,v in primitive['attributes'].items()
                                       if surface_materials or k!='NORMAL'}
            primitive['material'] = materials[int(sub.attrib['MtlIdx'])]
        meshes[entry.tag.removeprefix('File_')] = len(doc['meshes'])
        doc['meshes'].append(local['meshes'][0])
    actor_paths = {e.tag.removeprefix('File_'):e.attrib['Path'].replace('\\','/') for e in scene.find('.//AllFiles') if e.attrib['Path'].replace('\\','/').startswith('character/')}
    actor_instances = []
    for item in scene.iter('model'):
        a = item.attrib
        if a['FilePathIndex'] not in meshes and a['FilePathIndex'] not in actor_paths:continue
        matrix = list(map(float,a.get('Rotation','1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1').split(',')))
        scale = list(map(float,a.get('Scale','1,1,1').split(',')))
        position = list(map(float,a.get('Position','0,0,0').split(',')))
        if (len(matrix),len(scale),len(position))!=(16,3,3):raise ValueError('Transform dimensions')
        for axis in range(3):
            for row in range(3):matrix[axis*4+row] *= scale[axis]
        matrix[12:15] = position
        if not all(math.isfinite(x) for x in matrix):raise ValueError('Nonfinite transform')
        if a['FilePathIndex'] in actor_paths:
            actor_instances.append(dict(path=actor_paths[a['FilePathIndex']],matrix=matrix,sourceInstance=a))
            continue
        doc['scenes'][0]['nodes'].append(len(doc['nodes']))
        doc['nodes'].append(dict(name=a['Name'],mesh=meshes[a['FilePathIndex']],matrix=matrix,extras=dict(sourceInstance=a)))
    doc['extras'] = dict(sourceScene=source_path, sourceCameras=[e.attrib for e in scene.iter('Camera')],sourceActorInstances=actor_instances,
        skipped=skipped, limitations=['Environment-only colour reference; source actor placements and SFX not rendered.',
        'Source matrices retained; camera convention and rendering require visual verification.',
        'Original shader, reflection probes, dynamic effects and lighting not reproduced.'])
    output = pack_glb(doc,binary)
    (out/'scene.glb').write_bytes(output)
    report = dict(scene=source_path,sha256=hashlib.sha256(output).hexdigest(),bytes=len(output),
        meshes=len(doc['meshes']),instances=len(doc['nodes']),textures=len(textures),
        sources=[dict(path=p,sha256=records[p]['sha256']) for p in sorted(sources)],scope=doc['extras'])
    (out/'export.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:report[k] for k in ('scene','sha256','bytes','meshes','instances','textures')}))


if __name__=='__main__':
    for scene_name in ('city_battle_1','city_battle_2'):run(scene_name)
