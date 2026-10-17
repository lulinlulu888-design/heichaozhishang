"""Reproduce Elsa's source-identified, skinned, base-colour GLB from the APK.

This is deliberately an unlit colour reference, not a port of the NeoX shader.
The original mesh, both UV sets, complete skeleton and texture provenance stay
available for a later shader/animation port. No target code is executed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from decode_ktx import convert, parse_ktx, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_neox_gltf import encode_glb
from extract_texture_samples import APK_SHA256
from inspect_neox_model import extract_npk_entry, parse_model, ModelError
from neox_resource_paths import lookup_logical, read_catalogue

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = 'character/player/ailisha/ailisha_yangcheng'
SOURCE_HASHES = {
    'gim': 'e04de6992fbd43a73f221b5a3ccc5d9744db5a46585e0f3beb43cc5b33460a51',
    'mesh': '22677b92724bdc12c0e7aae0e8450a70602949f5f242dc1e965150cab316b618',
    'mtg': '672f08c5a8280f407db221142764c93b7f414e3c24865f90366480ec72323a74',
}
SURFACES = ['basic', 'stocking', 'hair_cartoon', 'skin', 'eye_cartoon']
MATERIAL_CODES = ['material', 'material_stocking', 'material_hair_cartoon',
                  'material_skin', 'material_eye_cartoon', 'material_common']
SHADERS = ([f'shader/surface/{x}.surf' for x in SURFACES] +
           [f'shader/built_in/materials/{x}.hlsl' for x in MATERIAL_CODES] +
           ['shader/u1shader/eye_ao.nfx', 'shader/u1shader/eye_ao.hlsl'] +
           [f'shader/built_in/vertex_fragment_models/{x}.hlsl' for x in
            ['model_default', 'default_functions', 'default_vertex_struct']])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


def extract(apk, catalogue, logical, output, apk_sha):
    matches = lookup_logical(catalogue, logical)
    if len(matches) != 1:
        raise ValueError(f'expected unique path match: {logical}: {matches}')
    row = matches[0]
    source = extract_npk_entry(apk, row['member'], row['index'], output)
    source.update(logical_path=logical, apk_sha256=apk_sha, sample_path=str(output.resolve()))
    # Keep the extension: e.g. eye_ao.hlsl and eye_ao.nfx are distinct evidence.
    write_json(Path(str(output)+'.provenance.json'), source)
    return source


def parse_materials(payload, *, expected_slots=9):
    root = ET.fromstring(payload)
    result = []
    for slot, el in enumerate(root.find('MaterialGroup')):
        if el.tag != f'Material_{slot}':
            raise ValueError('material slots are not contiguous')
        m = el.find('Material')
        render = m.find('RenderStates')
        params = {p.tag: p.attrib['Value'] for p in m.find('ParamTable')}
        result.append({'slot': slot, 'name': m.attrib['Name'],
                       'technique': m.find('Technique').attrib, 'params': params,
                       'render_states': {**render.attrib, **render.find('TransparentMode').attrib},
                       'macros': {p.attrib['Key']: p.attrib['Val'] for p in m.findall('ShaderMacro/*')}})
    if not 1 <= len(result) <= 64 or (expected_slots is not None and len(result) != expected_slots):
        raise ValueError(f'unexpected material count: {len(result)}; expected {expected_slots}')
    return result


def bind_materials(model, gim, materials, *, allow_bounds_mismatch=False):
    """Validate the XML->mesh ordinal association using independent AABBs.

    allow_bounds_mismatch keeps the ordinal MtlIdx binding when GIM bounds are
    stale, recording each disagreement instead of raising.
    """
    children = ET.fromstring(gim).find('SubMesh')
    if len(children) != len(model['submeshes']):
        raise ModelError('GIM submesh count mismatch')
    rows = []
    for i, (el, sub) in enumerate(zip(children, model['submeshes'])):
        if el.tag != f'Sub{i}':
            raise ModelError('GIM submesh order mismatch')
        slot = int(el.attrib['MtlIdx'])
        if not 0 <= slot < len(materials):
            raise ModelError('GIM material slot outside table')
        positions = model['positions'][sub['vertex_start']:sub['vertex_start']+sub['vertex_count']]
        lo = [min(p[k] for p in positions) for k in range(3)]
        hi = [max(p[k] for p in positions) for k in range(3)]
        center = [float(x) for x in el.attrib['BoundingCenter'].split(',')]
        half = [float(x) for x in el.attrib['BoundingHalf'].split(',')]
        errors = [abs(lo[k]-(center[k]-half[k])) for k in range(3)]
        errors += [abs(hi[k]-(center[k]+half[k])) for k in range(3)]
        if not all(math.isfinite(x) for x in errors) or max(errors) > 1e-4:
            if not allow_bounds_mismatch:
                raise ModelError(f'GIM independent bounds mismatch for submesh {i}')
        if not sub['uvs'] or any(len(uv) != sub['vertex_count'] for uv in sub['uvs']):
            raise ModelError('missing or mismatched UV arrays')
        rows.append({'submesh_index': i, 'name': el.attrib['Name'], 'material_slot': slot,
                     'material_name': materials[slot]['name'], 'bounds_max_error': max(errors),
                     'vertex_count': sub['vertex_count'], 'triangle_count': sub['triangle_count'],
                     'uv_ranges': [{'channel': c, 'min': [min(v[k] for v in uv) for k in range(2)],
                                    'max': [max(v[k] for v in uv) for k in range(2)]}
                                   for c, uv in enumerate(sub['uvs'])]})
    return rows


def assert_shader_evidence(directory):
    """Fail closed if the observed shader chain no longer supports the mapping."""
    def text(name):
        return (directory/name).read_text('utf8')
    for name in MATERIAL_CODES[:-1]:
        code = text(name+'.hlsl')
        if 'raw_data.tex0 = Tex0.Sample(DefaultSampler, frag.uv.xy);' not in code:
            raise ValueError(f'missing UV0 colour sample: {name}')
        if 'mtl.albedo = raw_data.tex0.rgb' not in code:
            raise ValueError(f'missing colour assignment: {name}')
    if 'mtl.opacity = 1.0;' not in text('material_eye_cartoon.hlsl'):
        raise ValueError('eye opacity evidence changed')
    if 'raw_data.tex0.rgb * StockingColor.rgb' not in text('material_stocking.hlsl'):
        raise ValueError('stocking colour evidence changed')
    uv = text('default_functions.hlsl')
    if 'vert.uv.xy = input.texcoord0;' not in uv or 'frag.uv = vert.uv;' not in uv:
        raise ValueError('default UV forwarding evidence changed')
    ao = text('eye_ao.hlsl')
    if 'output.uv = input.texcoord0.xy;' not in ao or 'float4 fragment_color = base_color;' not in ao:
        raise ValueError('overlay colour/UV evidence changed')


def shader_semantics(material, shader_dir):
    tech = material['technique']
    if tech['Type'] == 'Effect':
        if tech['TechName'].replace('\\', '/') != 'shader/u1shader/eye_ao.fx::TShader':
            raise ValueError('unsupported effect')
        return {'Tex0': {'semantic': 'direct RGBA overlay colour (eye_ao.hlsl ps_main)',
                         'uv': 'TEXCOORD_0', 'source': 'eye_ao.hlsl + eye_ao.nfx'}}
    surface = Path(tech['Surface']).name
    info = ET.parse(shader_dir/surface).findall('.//Resources/Param')
    result = {p.attrib['Name']: {'semantic': p.attrib.get('UiLabel'), 'description': p.attrib.get('Desc'),
                                'sampler': p.attrib.get('SamplerBinding'), 'source': surface}
              for p in info if p.attrib.get('Type') == 'Texture'}
    # UI labels are not authoritative when the actual material code overrides
    # them (notably skin Tex2.B). Preserve both sources instead of treating every
    # file called *_m as glTF metallic-roughness.
    overrides = {
        'basic.surf': {'Tex0': 'RGB albedo * BaseColor.rgb; A opacity * BaseColor.a',
                       'Tex2': 'R occlusion; G roughness * Intensity.g; B metalness * Intensity.b'},
        'skin.surf': {'Tex0': 'RGB albedo * BaseColor.rgb; A opacity * BaseColor.a',
                     'Tex2': 'R occlusion; G roughness * Intensity.g; B stores 1-SSS_curvature; metalness explicitly 0'},
        'hair_cartoon.surf': {'Tex0': 'RGB albedo; A opacity',
                              'Tex2': 'R occlusion; G clamped roughness; B forwarded through mtl.metalness to HairCartoon shading',
                              'Tex3': 'RGB flow direction for anisotropic tangent and normal perturbation',
                              'Tex4': 'RGB multiplied by SpecularColor.rgb and SpecularParam.r'},
        'eye_cartoon.surf': {'Tex0': 'RGB albedo * BaseColor.rgb; opacity explicitly 1. Surface UI labels A as parallax intensity, not transparency.',
                             'Tex3': 'RGB static reflection sampled with UV0 and scaled by Intensity.g',
                             'Tex4': 'View-normal matcap UV; not mesh-UV base colour'},
        'stocking.surf': {'Tex0': 'RGB albedo * StockingColor.rgb; A opacity',
                         'Tex2': 'R occlusion; G roughness; A contributes thickness; metalness field repurposed as skin roughness',
                         'Tex3': 'R pattern sampled at UV0 * tilling (220 here), passed to custom lighting via emissive'},
    }
    for param, meaning in overrides[surface].items():
        result[param]['hlsl_semantic'] = meaning
    return result


def split_glb(blob):
    if len(blob) < 28 or struct.unpack_from('<III', blob) != (0x46546c67, 2, len(blob)):
        raise ValueError('invalid GLB header')
    n, kind = struct.unpack_from('<II', blob, 12)
    if kind != 0x4e4f534a or n % 4 or 28+n > len(blob):
        raise ValueError('invalid GLB JSON chunk')
    doc = json.loads(blob[20:20+n])
    m, kind = struct.unpack_from('<II', blob, 20+n)
    if kind != 0x004e4942 or m % 4 or 28+n+m != len(blob):
        raise ValueError('invalid GLB BIN chunk')
    return doc, bytearray(blob[28+n:])


def pack_glb(doc, binary):
    doc['buffers'] = [{'byteLength': len(binary)}]
    j = json.dumps(doc, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')
    j += b' '*(-len(j) % 4)
    b = bytes(binary) + b'\0'*(-len(binary) % 4)
    return struct.pack('<IIIII', 0x46546c67, 2, 28+len(j)+len(b), len(j), 0x4e4f534a)+j+struct.pack('<II', len(b), 0x004e4942)+b


def encode_reference(model, bindings, materials, textures, joint_locals=None):
    """Embed only proven colour maps; never connect normal/mask images as colour."""
    raw, _, bind = encode_glb(model, 'Elsa / ailisha_yangcheng / source bind pose', skin=True,
                              joint_locals=joint_locals)
    doc, binary = split_glb(raw)
    doc.update(images=[], textures=[], materials=[],
               samplers=[{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}],
               extensionsUsed=['KHR_materials_unlit'])
    texture_indices = {}
    for material in materials:
        logical = material['params']['Tex0']
        if not logical and material['technique'].get('TechName', '').endswith('::TNoShader'):
            doc['materials'].append({'name': f"{material['slot']}: {material['name']} (unresolved TNoShader)",
                'pbrMetallicRoughness': {'baseColorFactor': [0.5, 0.5, 0.5, 1.0], 'metallicFactor': 0, 'roughnessFactor': 1},
                'extensions': {'KHR_materials_unlit': {}}, 'alphaMode': 'OPAQUE', 'doubleSided': True,
                'extras': {'sourceMaterial': material, 'scope': 'Source has no texture and a TNoShader technique; '
                    'whether the original draws this submesh is unverified. Grey marks it as unresolved.'}})
            continue
        if logical not in texture_indices:
            record = textures[logical]
            blob = Path(record['gltf_png']).read_bytes()
            if blob[:8] != b'\x89PNG\r\n\x1a\n' or digest(blob) != record['gltf_png_sha256']:
                raise ValueError('colour PNG differs from conversion provenance')
            while len(binary) % 4:
                binary.append(0)
            view = {'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(blob)}
            binary.extend(blob)
            doc['bufferViews'].append(view)
            idx = len(doc['images'])
            doc['images'].append({'name': Path(logical).stem, 'mimeType': 'image/png',
                                  'bufferView': len(doc['bufferViews'])-1,
                                  'extras': {'sourcePath': logical, 'sourceKtxSha256': record['source_sha256'],
                                             'pngSha256': record['gltf_png_sha256'],
                                             'colourPolicy': record['colour_policy']}})
            doc['textures'].append({'source': idx, 'sampler': 0})
            texture_indices[logical] = idx
        effect = material['technique']['Type'] == 'Effect'
        eye = material['name'] == 'eye'
        # This export is a portable albedo reference, with explicit conservative
        # alpha/culling policies. Numeric NeoX render-state enum mapping is not
        # claimed; source values are retained for an eventual engine port.
        alpha = 'BLEND' if effect else ('OPAQUE' if eye else 'MASK')
        factor = [1.0]*4
        if material['name'] == 'siwa' and 'StockingColor' in material['params']:
            factor = [float(v) for v in material['params']['StockingColor'].split(',')]
        m = {'name': f"{material['slot']}: {material['name']} (colour reference)",
             'pbrMetallicRoughness': {'baseColorTexture': {'index': texture_indices[logical], 'texCoord': 0},
                                      'baseColorFactor': factor, 'metallicFactor': 0, 'roughnessFactor': 1},
             'extensions': {'KHR_materials_unlit': {}}, 'alphaMode': alpha, 'doubleSided': True,
             'extras': {'sourceMaterial': material, 'scope': 'Unlit base-colour reference; no original lighting.',
                        'alphaPolicy': 'Eye opaque from HLSL; other surfaces MASK at authored AlphaRef/255; overlays conventional straight-alpha BLEND. Enum correspondence unverified.',
                        'cullingPolicy': 'doubleSided for source winding inspection; original CullMode 2 is retained but not interpreted.'}}
        if alpha == 'MASK':
            m['alphaCutoff'] = int(material['render_states']['AlphaRef'])/255.0
        doc['materials'].append(m)
    for row, prim in zip(bindings, doc['meshes'][0]['primitives']):
        prim['material'] = row['material_slot']
        prim['extras'].update(sourceSubmeshName=row['name'], materialBindingEvidence='GIM MtlIdx plus independent AABB')
    doc['extras']['missing'] = ['animation clips and physics', 'NeoX lighting/toon/outlines and tone adjustments',
                              'normal maps, mask maps, skin LUT, hair anisotropy/highlights, eye matcap/highlights',
                              'stocking view-dependent skin/fabric compositing', 'exact render-state enum and backend orientation verification']
    doc['extras']['colourScope'] = 'Original Tex0 colour sampling only; unlit reference, not source game appearance.'
    doc['extras']['uvPolicy'] = 'UV0 and UV1 floats and decoded image row order preserved; no flip or axis conversion.'
    return pack_glb(doc, binary), doc, bind


def run(apk, out):
    with apk.open('rb') as f:
        apk_sha = hashlib.file_digest(f, 'sha256').hexdigest()
    if apk_sha != APK_SHA256:
        raise ValueError('APK differs from investigated source')
    catalogue = read_catalogue(apk)
    sources = {}
    for suffix in SOURCE_HASHES:
        path = out/'source'/f'elsa-{suffix}.{suffix}'
        source = extract(apk, catalogue, MODEL_ROOT+'.'+suffix, path, apk_sha)
        if source['sha256'] != SOURCE_HASHES[suffix]:
            raise ValueError('named model source hash mismatch')
        sources[suffix] = source
    shader_dir = out/'shader-evidence'
    shaders = [extract(apk, catalogue, p, shader_dir/Path(p).name, apk_sha) for p in SHADERS]
    # This descriptor's filename is unresolved; its verified content selects
    # DefaultVF -> model_default.hlsl. Preserve archive identity without inventing a path.
    cfg_path = shader_dir/'compositor-config-index-1241.xml'
    cfg = extract_npk_entry(apk, 'assets/res/shader.npk', 1241, cfg_path)
    if cfg['sha256'] != 'bb8067e2bcf29cc22d62521f85a0bfe2413f84984a7e181c7396d21f1984c972':
        raise ValueError('shader compositor descriptor changed')
    shaders.append({**cfg, 'apk_sha256': apk_sha, 'sample_path': str(cfg_path.resolve()), 'logical_path': None})
    assert_shader_evidence(shader_dir)
    model = parse_model(Path(sources['mesh']['sample_path']).read_bytes())
    materials = parse_materials(Path(sources['mtg']['sample_path']).read_bytes())
    bindings = bind_materials(model, Path(sources['gim']['sample_path']).read_bytes(), materials)
    usage = []
    for material in materials:
        semantics = shader_semantics(material, shader_dir)
        for param, logical in material['params'].items():
            if not param.startswith('Tex'):
                continue
            usage.append({'material_slot': material['slot'], 'material_name': material['name'],
                          'parameter': param, 'logical_path': logical, 'semantic_evidence': semantics[param],
                          'exported_as_colour': param == 'Tex0'})
    texture_sources, inventory = [], []
    for logical in sorted({u['logical_path'] for u in usage}):
        archive = str(Path(logical).with_suffix('.ktx')).replace('\\', '/')
        path = out/'textures'/Path(archive).name
        source = extract(apk, catalogue, archive, path, apk_sha)
        meta = parse_ktx(path.read_bytes())
        uses = [u for u in usage if u['logical_path'] == logical]
        row = {'logical_path': logical, 'archive_path': archive, 'source': source, 'ktx': meta, 'uses': uses}
        inventory.append(row)
        if any(u['exported_as_colour'] for u in uses):
            texture_sources.append({**source, 'material_logical_path': logical})
    p = out/'texture-provenance.json'
    write_json(p, texture_sources)
    converted = convert([Path(r['sample_path']) for r in texture_sources], out/'colour-png', DEFAULT_DECODER,
                        provenance_path=p, inspector=DEFAULT_INSPECTOR)
    textures = {}
    for t in converted['textures']:
        r = t['outputs'][0]
        png = Path(r['png'])
        if not png.is_absolute():
            png = ROOT/png
        policy = 'sRGB KTX decoded to PNG; glTF baseColorTexture uses sRGB RGB and linear alpha'
        if t['texture']['profile'] == 'linear':
            # glTF base-colour RGB is always sRGB. Preserve the source decoder PNG
            # and explicitly encode its linear RGB in a separate derived image.
            import numpy as np
            from PIL import Image
            pixels = np.array(Image.open(png).convert('RGBA'))
            x = pixels[:, :, :3].astype(np.float64)/255
            encoded = np.where(x <= .0031308, x*12.92, 1.055*np.power(x, 1/2.4)-.055)
            pixels[:, :, :3] = np.clip(np.rint(encoded*255), 0, 255).astype('uint8')
            png = png.with_name(png.stem+'.gltf-srgb.png')
            Image.fromarray(pixels).save(png)
            policy = 'Derived PNG: source linear RGB encoded to sRGB for glTF colour sampling; alpha unchanged'
        textures[t['provenance']['material_logical_path']] = {
            'source_sha256': t['source_sha256'], 'gltf_png': str(png.resolve()), 'gltf_png_sha256': digest(png.read_bytes()),
            'colour_policy': policy, 'decoder_record': t}
    glb, doc, bind = encode_reference(model, bindings, materials, textures)
    output = out/'elsa-yangcheng.colour-reference.glb'
    output.write_bytes(glb)
    report = {'apk_sha256': apk_sha, 'sources': sources, 'shader_sources': shaders,
              'vertex_count': model['vertex_count'], 'triangle_count': model['triangle_count'],
              'bones': len(model['bones']), 'source_coverage_bytes': model['coverage_bytes'],
              'max_weight_sum_error': model['max_weight_sum_error'], 'bind_validation': bind,
              'material_bindings': bindings, 'material_slots': materials, 'texture_inventory': inventory,
              'character_local_unique_textures': sum(r['logical_path'].startswith('character/') for r in inventory),
              'total_unique_textures': len(inventory), 'decoded_colour_textures': textures,
              'output': str(output.resolve()), 'glb_bytes': len(glb), 'glb_sha256': digest(glb),
              'limitations': doc['extras']['missing'], 'source_ranges': model['ranges']}
    write_json(out/'export-report.json', report)
    write_json(out/'gltf.json', doc)
    write_json(out/'bone-map.json', {
        'mesh_sha256': model['sha256'], 'glb_sha256': digest(glb),
        'matrix_layout': 'column-major 4x4; source global bind; GLB nodes contain parent-local bind',
        'animation_track_mapping': 'UNRESOLVED: do not equate ACL track ordinal with mesh joint ordinal',
        'bones': [{'mesh_joint_index': i, 'gltf_node_index': i+1, 'name': bone['name'],
                   'parent_mesh_joint_index': bone['parent'], 'source_global_bind': bone['matrix_raw'],
                   'gltf_local_bind': doc['nodes'][i+1]['matrix']}
                  for i, bone in enumerate(model['bones'])]})
    return {k: report[k] for k in ['output', 'glb_bytes', 'glb_sha256', 'vertex_count', 'triangle_count', 'bones',
                                  'character_local_unique_textures', 'total_unique_textures']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    ap.add_argument('--out', type=Path, default=ROOT/'analysis/elsa-model')
    args = ap.parse_args()
    print(json.dumps(run(args.apk.resolve(), args.out.resolve()), indent=2))
