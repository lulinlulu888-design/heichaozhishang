"""Export source-identified tutorial enemy 991 with skin and proven Tex0 colour.

Only static data is parsed. This bounded wrapper does not change the shared
mesh reader or bypass its AABB gate: this asset instead requires an independent
61-bone GISACL reference-pose comparison before adding skin to static geometry.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import numpy as np
from decode_ktx import convert, parse_ktx, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_animation import quaternion_matrix
from export_elsa_model import bind_materials, extract, pack_glb, split_glb, write_json
from export_neox_gltf import encode_glb, flatten_columns
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_library
from inspect_neox_model import (ModelError, extract_npk_entry, inverse4, matrix_rows,
                                multiply4, parse_model, validate_bind_pose)
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'character/monster/yuanjieguai_yijiemofang/'
GIM_PATH = PREFIX+'yuanjieguai_yijiemofang_purple.gim'
HASHES = {
    'gim': '99c37714e0912f7cd6bef546e7e7774860155bebf5853bd3953ce7137b58dcb6',
    'mesh': '21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa',
    'mtg': '281066fafcf1df444f2b22650e0cc68b1c5a244730e0430fdceb4495aa4b7136',
    'gisacl': 'cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0',
}
SHADERS = ['shader/surface/emission.surf',
           'shader/built_in/materials/material_emission.hlsl',
           'shader/built_in/materials/material_common.hlsl',
           'shader/built_in/material/material_setup_func.hlsl',
           'shader/u1shader/exttechnique.hlsl'] + [
    'shader/built_in/vertex_fragment_models/'+name+'.hlsl'
    for name in ('model_default', 'default_functions', 'default_vertex_struct')]
REA_ID = 'ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3'
LIMITATIONS = [
    'Unlit Tex0 colour reference only; original emission (Tex6), purple glow, lighting, tone adjustment, shadows and outlines are not rendered.',
    'Tex1 normal, Tex2 mix/occlusion/roughness/metalness and all authored material values are retained as evidence, not connected to glTF shading.',
    'Animation clips, particles, triggers, music and physics are not included in this GLB.',
    '28-byte bone auxiliary blocks fail the Elsa influenced-vertex-AABB interpretation; their enemy-specific role remains unknown.',
    'Original units, XYZ, winding, UVs and decoded image row order are preserved; no UI, Cocos import or visual orientation acceptance was performed.',
    'Entity SCALE=[0.7,0.7,0.7] is recorded, not baked into the source-coordinate GLB. Render-state enums are preserved but not fully mapped.',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity_chain():
    """Verify explicit foreign keys in prior data-only table exports."""
    rows = []
    for file, index, row_id in [('monsters.json', 2363, 991), ('enemy-entity.json', 1955, 6605),
                                 ('enemy-lod.json', 1268, 6605), ('lod-index.json', 6328, 66051)]:
        path = ROOT/'analysis/first-encounter'/file
        blob = path.read_bytes()
        obj = json.loads(blob)
        matches = [r for r in obj['rows'] if r['id'] == row_id]
        if obj['source']['index'] != index or len(matches) != 1:
            raise ValueError('identity table/index mismatch')
        marshal = ROOT/obj['source']['output']
        if sha(marshal.read_bytes()) != obj['source']['decoded_sha256']:
            raise ValueError('identity table original marshal hash changed')
        rows.append({'file': str(path.resolve()), 'sha256': sha(blob), 'module_source': obj['source'], **matches[0]})
    monster, entity, lod, level = [r['fields'] for r in rows]
    if (monster['NAME'], monster['ENTITY_ID'], entity['LOD_ID'], lod['LOD_MODEL_LIST'],
        level['LEVEL'], level['MODEL_PATH']) != ('幻眼魔方', 6605, 6605, [66051, 66052], 0, GIM_PATH):
        raise ValueError('enemy identity chain changed')
    return {'monster_id': 991, 'name': '幻眼魔方', 'entity_id': 6605, 'lod_id': 6605,
            'lod_index_id': 66051, 'logical_gim': GIM_PATH, 'entity_scale_unapplied': entity['SCALE'],
            'authority': 'Previously recovered static literal table rows; not runtime execution.', 'rows': rows}


def parse_material(payload):
    root = ET.fromstring(payload)
    group = root.find('MaterialGroup')
    if group is None or group.attrib.get('MaterialCount') != '1' or [x.tag for x in group] != ['Material_0']:
        raise ValueError('expected exactly one explicit enemy material slot')
    material = group[0].find('Material')
    params = material.find('ParamTable')
    if len({p.tag for p in params}) != len(params):
        raise ValueError('duplicate material parameter')
    render = material.find('RenderStates')
    row = {'slot': 0, 'name': material.attrib['Name'], 'technique': material.find('Technique').attrib,
           'params': {p.tag: p.attrib['Value'] for p in params},
           'macros': {p.attrib['Key']: p.attrib['Val'] for p in material.findall('ShaderMacro/*')},
           'render_states': {**render.attrib, **render.find('TransparentMode').attrib}}
    if row['technique'] != {'Type': 'Surface', 'Surface': 'shader/surface/emission.surf',
                            'VertexFragmentModel': 'DefaultVF', 'LightingModel': 'Isotropy'}:
        raise ValueError('unsupported material technique')
    if {k for k in row['params'] if k.startswith('Tex')} != {'Tex0', 'Tex1', 'Tex2', 'Tex6'}:
        raise ValueError('unexpected texture parameter set')
    return row


def shader_evidence(directory):
    surf = ET.parse(directory/'emission.surf').getroot().find('Surface')
    if surf.find('Code').attrib['File'] != 'shader/built_in/materials/material_emission.hlsl':
        raise ValueError('surface implementation changed')
    parameters = {p.attrib['Name']: dict(p.attrib) for p in surf.findall('Resources/Param')}
    checks = {
        'material_emission.hlsl': ['raw_data.tex0 = Tex0.Sample(DefaultSampler, frag.uv.xy);',
                                  'mtl.albedo = raw_data.tex0.rgb * BaseColor.rgb;',
                                  'mtl.opacity = raw_data.tex0.a * BaseColor.a;',
                                  'mtl.occlusion = raw_data.tex2.r;',
                                  'mtl.roughness = MakeMaterialRoughness(raw_data.tex2.g * Intensity.g);',
                                  'mtl.metalness = saturate(raw_data.tex2.b * Intensity.b);'],
        'default_functions.hlsl': ['vert.uv.xy = input.texcoord0;', 'frag.uv = vert.uv;'],
        'default_vertex_struct.hlsl': ['float2 texcoord0 : TEXCOORD0;'],
        'material_common.hlsl': ['U1CommonSampler Trilinear_Wrap'],
        'material_setup_func.hlsl': ['res/shader/u1shader/exttechnique.hlsl',
                                     'float3 n = raw_data.tex1.xyz * 2.0f - 1.0;'],
        'exttechnique.hlsl': ['float4 tex6 = Tex6.Sample(DefaultSampler, input.uv.xy);',
                              'mtl.emissive = srgb2linearf3(tex6.rgb) * EmissiveColor.rgb;',
                              'mtl.emissive *= EmissiveParams.g;'],
    }
    evidence = []
    for name, tokens in checks.items():
        lines = (directory/name).read_text('utf8').splitlines()
        for token in tokens:
            matches = [i for i, line in enumerate(lines, 1) if token in line]
            if len(matches) != 1:
                raise ValueError(f'missing/ambiguous shader evidence: {name}: {token}')
            evidence.append({'file': name, 'line': matches[0], 'text': token})
    return {'checked_source_lines': evidence, 'surface_parameters': parameters,
            'Tex0': 'UV0 -> RGB albedo * BaseColor.rgb; A opacity * BaseColor.a',
            'Tex1': 'UV0 -> tangent normal (default normal path); alpha additionally feeds fill-light occlusion',
            'Tex2': 'UV0 -> R occlusion, G roughness * Intensity.g, B metalness * Intensity.b',
            'Tex6': 'UV0 -> srgb2linearf3(RGB) * EmissiveColor.rgb * EmissiveParams.g; omitted from reference rendering'}


def validate_reference_bind(model, library):
    """Independent library local TRS corroborates mesh raw global matrices."""
    names = [b['name'] for b in model['bones']]
    if len(names) != 61 or len(set(names)) != 61 or set(names) != set(library['bone_names']):
        raise ModelError('reference and mesh must contain the same 61 unique bone names')
    poses = dict(zip(library['bone_names'], library['reference_pose']))
    local = []
    for name in names:
        p = poses[name]
        m = np.eye(4)
        m[:3, :3] = quaternion_matrix(p[3:7])*p[7:10]
        m[:3, 3] = p[:3]
        local.append(m)
    worlds = {}
    def world(i):
        if i not in worlds:
            parent = model['bones'][i]['parent']
            worlds[i] = local[i] if parent is None else world(parent)@local[i]
        return worlds[i]
    rows = []
    for i, b in enumerate(model['bones']):
        raw = np.asarray(matrix_rows(b['matrix_raw']))
        parent = b['parent']
        raw_local = raw if parent is None else np.linalg.inv(matrix_rows(model['bones'][parent]['matrix_raw']))@raw
        errors = {'global_max_error': float(np.max(np.abs(raw-world(i)))),
                  'local_max_error': float(np.max(np.abs(raw_local-local[i])))}
        if not all(math.isfinite(x) and x <= 1e-5 for x in errors.values()):
            raise ModelError(f'reference bind differs for {b["name"]}: {errors}')
        rows.append({'mesh_joint_index': i, 'name': b['name'], 'parent': parent, **errors})
    try:
        aabb = validate_bind_pose(model)
    except ModelError as exc:
        aabb = {'validated': False, 'error': str(exc), 'interpretation': 'Not used as a validation gate for this asset; unknown auxiliary semantics preserved.'}
    return {'validated': True, 'method': 'Independently stored GISACL name-matched local TRS accumulated through mesh hierarchy equals mesh raw global bind matrices.',
            'tolerance': 1e-5, 'reference_sha256': library['sha256'], 'rows': rows,
            'max_global_error': max(r['global_max_error'] for r in rows),
            'max_local_error': max(r['local_max_error'] for r in rows), 'auxiliary_aabb_check': aabb}


def append_accessor(doc, binary, rows, width, fmt='f', target=None):
    binary.extend(b'\0'*(-len(binary) % 4))
    start = len(binary)
    for row in rows:
        binary.extend(struct.pack('<'+fmt*width, *row))
    view = {'buffer': 0, 'byteOffset': start, 'byteLength': len(binary)-start}
    if target is not None:
        view['target'] = target
    doc['bufferViews'].append(view)
    doc['accessors'].append({'bufferView': len(doc['bufferViews'])-1, 'componentType': {'f': 5126, 'B': 5121}[fmt],
                             'count': len(rows), 'type': {4: 'VEC4', 16: 'MAT4'}[width]})
    return len(doc['accessors'])-1


def read_accessor(doc, binary, index):
    """Read back exported arrays independently of the writer's row packing."""
    accessor = doc['accessors'][index]
    view = doc['bufferViews'][accessor['bufferView']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[accessor['type']]
    fmt = {5121: 'B', 5123: 'H', 5126: 'f'}[accessor['componentType']]
    record = struct.Struct('<'+fmt*width)
    start = view.get('byteOffset', 0)+accessor.get('byteOffset', 0)
    size = accessor['count']*record.size
    if (start % 4 or start < view.get('byteOffset', 0)
            or start+size > view.get('byteOffset', 0)+view['byteLength']
            or view.get('byteOffset', 0)+view['byteLength'] > len(binary)):
        raise ValueError('accessor outside aligned buffer view')
    return list(record.iter_unpack(binary[start:start+size]))


def audit_glb(blob, model):
    """Full-array equality, independent hierarchy, IBM, and CPU rest skinning."""
    doc, binary = split_glb(blob)
    if len(doc['meshes'][0]['primitives']) != 1 or len(doc['skins']) != 1:
        raise ValueError('wrong primitive/skin count')
    skin = doc['skins'][0]
    if skin['joints'] != list(range(1, 62)) or skin['skeleton'] != 62 or doc['nodes'][0]['skin'] != 0:
        raise ValueError('joint or mesh skin binding mismatch')
    parents = {}
    for i, node in enumerate(doc['nodes']):
        if '/' in node['name'] or '\\' in node['name']:
            raise ValueError('node name conflicts with engine path lookup')
        for child in node.get('children', []):
            if child in parents: raise ValueError('multiple node parents')
            parents[child] = i
    worlds, active = {}, set()
    def world(i):
        if i in active: raise ValueError('cyclic export hierarchy')
        if i not in worlds:
            active.add(i)
            node = doc['nodes'][i]
            m = np.array(matrix_rows(node['matrix'])) if 'matrix' in node else np.eye(4)
            worlds[i] = world(parents[i])@m if i in parents else m
            active.remove(i)
        return worlds[i]
    ibm = read_accessor(doc, binary, skin['inverseBindMatrices'])
    matrices = []
    max_world, max_identity, max_inverse = 0.0, 0.0, 0.0
    for i, (node, b) in enumerate(zip(skin['joints'], model['bones'])):
        if doc['nodes'][node]['name'] != b['name']:
            raise ValueError('joint name mapping mismatch')
        expected_parent = 62 if b['parent'] is None else b['parent']+1
        if parents.get(node) != expected_parent: raise ValueError('joint parent mismatch')
        source = np.asarray(matrix_rows(b['matrix_raw']))
        inverse = np.asarray(matrix_rows(ibm[i]))
        expected_ibm = np.asarray(inverse4(source), dtype=np.float32).astype(np.float64)
        max_inverse = max(max_inverse, float(np.max(np.abs(inverse-expected_ibm))))
        max_world = max(max_world, float(np.max(np.abs(world(node)-source))))
        posed = world(node)@inverse
        max_identity = max(max_identity, float(np.max(np.abs(posed-np.eye(4)))),
                           float(np.max(np.abs(inverse@world(node)-np.eye(4)))))
        matrices.append(posed)
    if max_inverse != 0 or max_world > 1e-10 or max_identity > 1e-5:
        raise ValueError('export inverse/global bind mismatch')
    primitive = doc['meshes'][0]['primitives'][0]
    attrs = primitive['attributes']
    arrays = [('POSITION', model['positions']), ('NORMAL', model['normals'])]
    arrays += [(f'TEXCOORD_{i}', values) for i, values in enumerate(model['submeshes'][0]['uvs'])]
    for key, source in arrays:
        if read_accessor(doc, binary, attrs[key]) != source:
            raise ValueError('source array changed: '+key)
    indices = [v[0] for v in read_accessor(doc, binary, primitive['indices'])]
    if indices != model['indices'] or any(i < 0 or i >= 4208 for i in indices):
        raise ValueError('source index array changed')
    if primitive['material'] != 0: raise ValueError('material binding mismatch')
    joints = read_accessor(doc, binary, attrs['JOINTS_0'])
    weights = read_accessor(doc, binary, attrs['WEIGHTS_0'])
    expected_joints = [tuple(0 if j == 255 else j for j in row) for row in model['joints']]
    expected_weights = [tuple(np.asarray([w/sum(row) for w in row], dtype=np.float32).tolist()) for row in model['weights']]
    if joints != expected_joints or weights != expected_weights:
        raise ValueError('source skin influences changed')
    positions = np.asarray(model['positions'])
    posed = []
    for p, js, ws in zip(positions, joints, weights):
        if any(j < 0 or j >= 61 for j in js) or abs(sum(ws)-1) > 1e-6:
            raise ValueError('invalid exported influence')
        v = np.array([*p, 1])
        posed.append(sum(w*(matrices[j]@v)[:3] for j, w in zip(js, ws)))
    posed = np.asarray(posed)
    error = float(np.max(np.abs(posed-positions)))
    if not np.all(np.isfinite(posed)) or error > 1e-5:
        raise ValueError('CPU bind skinning changed original positions')
    image = doc['images'][0]
    view = doc['bufferViews'][image['bufferView']]
    png = binary[view['byteOffset']:view['byteOffset']+view['byteLength']]
    if sha(png) != image['extras']['pngSha256']:
        raise ValueError('embedded colour image hash mismatch')
    return {'checked_vertices': len(posed), 'checked_triangles': len(indices)//3, 'checked_bones': len(ibm),
            'geometry_normals_all_uvs_indices_exact': True, 'uv_channels': len(model['submeshes'][0]['uvs']),
            'normalized_skin_influences_exact': True,
            'max_global_bind_error': max_world, 'max_inverse_bind_storage_error': max_inverse,
            'max_inverse_times_global_identity_error': max_identity, 'max_cpu_bind_position_error': error,
            'source_aabb': model['bounds'], 'cpu_bind_aabb': {'min': posed.min(axis=0).tolist(), 'max': posed.max(axis=0).tolist()},
            'scope': 'Numeric static bind/reference validation; not animation playback or visual acceptance.'}


def encode_reference(model, library, material, binding, texture, identity):
    validation = validate_reference_bind(model, library)
    raw, _, _ = encode_glb(model, 'TutorialEnemy991Mesh', skin=False)
    doc, binary = split_glb(raw)
    matrices = [matrix_rows(b['matrix_raw']) for b in model['bones']]
    inverses = [inverse4(m) for m in matrices]
    roots, shear_errors = [], []
    for i, b in enumerate(model['bones']):
        local = matrices[i] if b['parent'] is None else multiply4(inverses[b['parent']], matrices[i])
        rot = np.asarray(local)[:3, :3]
        norms = np.linalg.norm(rot, axis=0)
        if np.any(norms < 1e-8):
            raise ModelError('singular local bind')
        error = float(np.max(np.abs((rot/norms).T@(rot/norms)-np.eye(3))))
        if error > 1e-4:
            raise ModelError('unsupported local matrix shear')
        shear_errors.append(error)
        node = {'name': b['name'], 'matrix': flatten_columns(local)}
        children = [j+1 for j, other in enumerate(model['bones']) if other['parent'] == i]
        if children: node['children'] = children
        doc['nodes'].append(node)
        if b['parent'] is None: roots.append(i+1)
    doc['nodes'].append({'name': 'TutorialEnemy991Skeleton', 'children': roots})
    doc['scenes'][0]['nodes'].append(62)
    ibm = append_accessor(doc, binary, [flatten_columns(m) for m in inverses], 16)
    doc['skins'] = [{'name': 'TutorialEnemy991Bind', 'joints': list(range(1, 62)), 'skeleton': 62, 'inverseBindMatrices': ibm}]
    doc['nodes'][0]['skin'] = 0
    for sub, primitive in zip(model['submeshes'], doc['meshes'][0]['primitives']):
        a, b = sub['vertex_start'], sub['vertex_start']+sub['vertex_count']
        primitive['attributes']['JOINTS_0'] = append_accessor(doc, binary, [tuple(0 if j == 255 else j for j in v) for v in model['joints'][a:b]], 4, 'B', 34962)
        primitive['attributes']['WEIGHTS_0'] = append_accessor(doc, binary, [tuple(w/sum(v) for w in v) for v in model['weights'][a:b]], 4, target=34962)
        primitive['material'] = binding['material_slot']
        primitive['extras']['sourceSubmeshName'] = binding['name']
    png = Path(texture['gltf_png']).read_bytes()
    if not png.startswith(b'\x89PNG\r\n\x1a\n') or sha(png) != texture['gltf_png_sha256']:
        raise ValueError('PNG hash mismatch')
    binary.extend(b'\0'*(-len(binary) % 4))
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(png)})
    binary.extend(png)
    doc['images'] = [{'name': 'Enemy991Tex0Colour', 'mimeType': 'image/png', 'bufferView': len(doc['bufferViews'])-1,
                      'extras': {'sourcePath': material['params']['Tex0'], 'sourceKtxSha256': texture['source_sha256'], 'pngSha256': sha(png)}}]
    doc['textures'] = [{'source': 0, 'sampler': 0}]
    doc['samplers'] = [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}]
    doc['extensionsUsed'] = ['KHR_materials_unlit']
    # Every decoded Tex0 alpha is 255 for this source; no enum guess is needed.
    if texture['decoder_record']['outputs'][0]['channel_extrema_rgba'][3] != (255, 255):
        raise ValueError('unexpected nonopaque enemy albedo alpha')
    doc['materials'] = [{'name': 'Enemy991ColourReference', 'alphaMode': 'OPAQUE', 'doubleSided': True,
                         'pbrMetallicRoughness': {'baseColorTexture': {'index': 0, 'texCoord': 0},
                           'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0, 'roughnessFactor': 1},
                         'extensions': {'KHR_materials_unlit': {}},
                         'extras': {'sourceMaterial': material, 'scope': 'Tex0 albedo only; purple emission is omitted.',
                                    'alphaPolicy': 'All source Tex0 pixels alpha=255, surface BaseColor default alpha=1.',
                                    'cullingPolicy': 'doubleSided reference; original CullMode enum retained but not interpreted.'}}]
    doc['extras'].update(monsterId=991, entityId=6605, sourceGim=GIM_PATH,
                         identityChain=[r['id'] for r in identity['rows']], missing=LIMITATIONS,
                         bindPoseEvidence={k: v for k, v in validation.items() if k != 'rows'},
                         localMatrixMaxOrthogonalityError=max(shear_errors),
                         uvPolicy='Preserved the source UV0 channel and decoded image rows without flips.',
                         sourceEntityScaleUnapplied=identity['entity_scale_unapplied'])
    return pack_glb(doc, binary), validation


def run(apk, out):
    with apk.open('rb') as stream:
        apk_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    if apk_sha != APK_SHA256:
        raise ValueError('APK differs from investigated artifact')
    identity = identity_chain()
    catalogue = read_catalogue(apk)
    sources = {}
    def get(kind, logical):
        row = extract(apk, catalogue, logical, out/'source'/('enemy-991.'+kind), apk_sha)
        if row['sha256'] != HASHES[kind]: raise ValueError('source hash mismatch: '+kind)
        sources[kind] = row
        return Path(row['sample_path']).read_bytes()
    gim = get('gim', identity['logical_gim'])
    xml = ET.fromstring(gim)
    mesh = get('mesh', xml.attrib['Mesh'])
    # Same-stem MTG is a native loader rule, not an appearance/name inference.
    mtg = get('mtg', str(Path(identity['logical_gim']).with_suffix('.mtg')).replace('\\', '/'))
    gis_paths = [e.attrib['value'] for e in xml.findall('GisFiles/*')]
    if len(gis_paths) != 1: raise ValueError('expected one referenced GISACL library')
    library = parse_library(get('gisacl', gis_paths[0]))
    model = parse_model(mesh)
    if (model['vertex_count'], model['triangle_count'], model['submesh_count'], len(model['bones'])) != (4208, 6246, 1, 61):
        raise ModelError('unexpected enemy mesh counts')
    material = parse_material(mtg)
    bindings = bind_materials(model, gim, [material])
    shader_dir = out/'shader-evidence'
    shaders = [extract(apk, catalogue, logical, shader_dir/Path(logical).name, apk_sha) for logical in SHADERS]
    cfg_path = shader_dir/'compositor-config-index-1241.xml'
    cfg = extract_npk_entry(apk, 'assets/res/shader.npk', 1241, cfg_path)
    if cfg['sha256'] != 'bb8067e2bcf29cc22d62521f85a0bfe2413f84984a7e181c7396d21f1984c972':
        raise ValueError('compositor configuration changed')
    shaders.append({**cfg, 'logical_path': None, 'apk_sha256': apk_sha, 'sample_path': str(cfg_path.resolve())})
    semantics = shader_evidence(shader_dir)
    if semantics['surface_parameters']['BaseColor']['Default'].replace(' ', '') != '1,1,1,1':
        raise ValueError('unsupported default base colour')
    inventory = []
    for param, logical in material['params'].items():
        if not param.startswith('Tex'): continue
        archive = str(Path(logical).with_suffix('.ktx')).replace('\\', '/')
        source = extract(apk, catalogue, archive, out/'textures'/Path(archive).name, apk_sha)
        inventory.append({'parameter': param, 'material_path': logical, 'archive_path': archive,
                          'source': source, 'ktx': parse_ktx(Path(source['sample_path']).read_bytes()),
                          'semantic': semantics[param], 'exported_as_colour': param == 'Tex0'})
    colour = next(r for r in inventory if r['parameter'] == 'Tex0')
    provenance = out/'texture-provenance.json'
    write_json(provenance, [colour['source']])
    converted = convert([Path(colour['source']['sample_path'])], out/'colour-png', DEFAULT_DECODER,
                        provenance_path=provenance, inspector=DEFAULT_INSPECTOR)
    decoded = converted['textures'][0]
    if decoded['texture']['profile'] != 'srgb' or decoded['texture']['faces'] != 1:
        raise ValueError('expected observed sRGB 2D albedo')
    png = ROOT/decoded['outputs'][0]['png']
    texture = {'source_sha256': decoded['source_sha256'], 'gltf_png': str(png.resolve()),
               'gltf_png_sha256': sha(png.read_bytes()), 'decoder_record': decoded,
               'colour_policy': 'sRGB KTX decoded with -ds; glTF baseColorTexture sRGB, linear alpha.'}
    glb, bind = encode_reference(model, library, material, bindings[0], texture, identity)
    readback = audit_glb(glb, model)
    doc, _ = split_glb(glb)
    output = out/'tutorial-enemy-991.colour-reference.glb'
    output.write_bytes(glb)
    report = {'format_version': 1, 'apk_sha256': apk_sha, 'identity': identity,
              'rea_evidence': {'id': REA_ID, 'scope': 'Existing REA APK/root ZIP manifest evidence only.',
                'source': 'analysis/rea/initial-artifact-evidence.json', 'conversion_authority': 'Ordinary local bounded data-only conversion; not newly retained REA Evidence.'},
              'sources': sources, 'shader_sources': shaders, 'shader_semantics': semantics,
              'native_mtg_rule': {'loader_range': '0xc212f4-0xc212fe', 'replace_extension': '0x10daec6',
                'evidence_files': ['analysis/resource-mapping/mesh-loader.thumb.txt', 'analysis/resource-mapping/replace-extension.thumb.txt']},
              'vertex_count': model['vertex_count'], 'triangle_count': model['triangle_count'], 'bones': 61,
              'source_coverage_bytes': model['coverage_bytes'], 'source_ranges': model['ranges'],
              'max_weight_sum_error': model['max_weight_sum_error'], 'bind_validation': bind,
              'glb_readback_validation': readback,
              'material_bindings': bindings, 'material_slots': [material], 'texture_inventory': inventory,
              'decoded_colour_texture': texture, 'output': str(output.resolve()), 'glb_bytes': len(glb),
              'glb_sha256': sha(glb), 'glbSha': sha(glb), 'limitations': LIMITATIONS}
    write_json(out/'export-report.json', report)
    write_json(out/'gltf.json', doc)
    write_json(out/'bone-map.json', {'mesh_sha256': model['sha256'], 'gisacl_sha256': library['sha256'],
        'glb_sha256': sha(glb), 'animation_mapping': 'Use clip ID -> library name -> mesh name; this export contains no clips.',
        'bones': [{'mesh_joint_index': i, 'gltf_node_index': i+1, 'name': b['name'],
                   'parent_mesh_joint_index': b['parent'], 'source_global_bind': b['matrix_raw'],
                   'gltf_local_bind': doc['nodes'][i+1]['matrix'], 'source_auxiliary_unknown': b['auxiliary_unknown']}
                  for i, b in enumerate(model['bones'])]})
    return {k: report[k] for k in ('output', 'glb_bytes', 'glb_sha256', 'vertex_count', 'triangle_count', 'bones')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    parser.add_argument('--out', type=Path, default=ROOT/'analysis/tutorial-enemy')
    args = parser.parse_args()
    print(json.dumps(run(args.apk.resolve(), args.out.resolve()), indent=2))
