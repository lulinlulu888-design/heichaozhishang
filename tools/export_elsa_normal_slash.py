"""Export the two source-pinned full-ring slash layers and their original recipe.

No NeoX/Unreal execution. The generic exact-AABB material binder is unchanged.
This exception is valid only for these two GIMs and this one shared mesh.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

from export_elsa_model import parse_materials, split_glb, pack_glb
from export_neox_gltf import encode_glb
from extract_texture_samples import APK_SHA256
from inspect_neox_model import ModelError, parse_model

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'
THEATRE = ROOT / 'analysis/battle-visual/prologue-theatre/source'
MESH = 'effects/modeleffect/char/001/daoguang_01.mesh'
MESH_SHA = '50613e1489873fa492f312d60fda63cda4e6605869c25a6d7308b3f6c9f51472'
VARIANTS = {
    'effects/modeleffect/char/001/daoguang_01_a.gim': {
        'gim': '483d2039f6a520acd065d7837bab80e4e34f00edbe0477c462c5f355d9b614e5',
        'mtg': '7c6117de08215f435cf0efb328ff5eae0882aa3b86a3d78a7abfc4e5123a1124',
        'half': 46.7992},
    'effects/modeleffect/char/001/new_daoguang_01.gim': {
        'gim': 'a9b9256e6b57a24b33653698b271dc3f870bc64e721efe5105ff1fca8a0c9ed6',
        'mtg': 'ab1fa830b794780a20fb96e071209deaf939f1b948e3feeadb5bcbccd0b4cacb',
        'half': 46.8},
}
SOURCE_PINS = {
    'character/player/ailisha/ailisha.gim': 'cec24d79e67c9bc86993d0ab4115f484d6e222f0954252d02d8505899d0eccf7',
    'character/player/ailisha/ailisha.ags': '12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729',
    'effects/player/001/fire_1.sfx': '9c1c7364da0a25cf371f59ffb31fb5ff22347472b52e7bed9f458a8167e5b441',
    'effects/player/001/new_daoguang_01.sfx': '095c60658874ef91dcf5f9c1f80a64ed86354d72e6b6ab703412790acf4646e4',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')


def bind_daoguang_full_ring(model, gim, materials):
    """Accept source-pinned conservative circle bounds, never arbitrary mismatches."""
    selected = next((v for v in VARIANTS.values() if v['gim'] == sha(gim)), None)
    if selected is None or model['sha256'] != MESH_SHA:
        raise ModelError('Not a source-pinned daoguang full-ring pair')
    tree = ET.fromstring(gim.decode('gb18030'))
    if tree.get('Mesh', '').replace('\\', '/') != MESH:
        raise ModelError('Full-ring explicit Mesh reference changed')
    if (model['vertex_count'], model['triangle_count'], model['submesh_count'], model['kind']) != (205, 320, 1, 0):
        raise ModelError('Full-ring geometry structure changed')
    children = list(tree.find('SubMesh'))
    if len(children) != 1 or children[0].tag != 'Sub0' or len(materials) != 1:
        raise ModelError('Full-ring material/submesh association changed')
    el, sub = children[0], model['submeshes'][0]
    if el.get('MtlIdx') != '0' or el.get('Name') != 'Cone001' or materials[0]['name'] != 'Cone001':
        raise ModelError('Full-ring sole material slot identity changed')
    center = [float(x) for x in el.attrib['BoundingCenter'].split(',')]
    half = [float(x) for x in el.attrib['BoundingHalf'].split(',')]
    if center != [0, 0, 0] or half != [selected['half'], 0, selected['half']]:
        raise ModelError('Source-pinned conservative bound changed')
    positions = model['positions']
    if any(p[1] != 0 or any(abs(p[k]) > half[k] + 1e-6 for k in range(3)) for p in positions):
        raise ModelError('Full-ring positions escape source conservative bound')
    radii = [math.hypot(p[0], p[2]) for p in positions]
    if abs(max(radii) - 46.799161610443754) > 1e-6:
        raise ModelError('Full-ring radial envelope changed')
    angles = [math.degrees(math.atan2(p[2], p[0])) for p in positions]
    angle_error = max(abs((a - 4.5) / 9 - round((a - 4.5) / 9)) * 9 for a in angles)
    if angle_error > 0.0002 or len({round(a, 3) for a in angles}) != 40:
        raise ModelError('Full-ring 4.5-degree offset / 9-degree sampling changed')
    if sub['vertex_start'] != 0 or sub['uv_count'] != 1 or len(sub['uvs'][0]) != 205:
        raise ModelError('Full-ring original UV/index partition changed')
    lo = [min(p[k] for p in positions) for k in range(3)]
    hi = [max(p[k] for p in positions) for k in range(3)]
    return [{'submesh_index': 0, 'name': 'Cone001', 'material_slot': 0,
             'material_name': 'Cone001', 'vertex_count': 205, 'triangle_count': 320,
             'bounds_max_error': max(abs(lo[k] + half[k]) for k in range(3)),
             'bounds_validation': {
                 'method': 'source-pinned explicit Mesh + sole Sub0/MtlIdx0 + conservative circular envelope',
                 'exactAabbMatch': False, 'sourceCenter': center, 'sourceHalf': half,
                 'meshAabb': {'min': lo, 'max': hi}, 'allVerticesContained': True,
                 'maxRadius': max(radii), 'angleOffsetDegrees': 4.5, 'angularStepDegrees': 9,
                 'maxAngularGridErrorDegrees': angle_error,
                 'radiusTimesCosHalfStep': max(radii) * math.cos(math.radians(4.5)),
                 'geometryRescaled': False, 'gimTransformPresent': False},
             'uv_ranges': [{'channel': 0, 'min': [min(u[k] for u in sub['uvs'][0]) for k in range(2)],
                            'max': [max(u[k] for u in sub['uvs'][0]) for k in range(2)]}]}]


def verify_glb_arrays(blob, source_raw, model):
    """Compare actual emitted bytes to independent source offsets, not float echoes."""
    doc, binary = split_glb(blob)
    primitive = doc['meshes'][0]['primitives'][0]
    ranges = {x['name']: x for x in model['ranges']}
    result = []
    for semantic, key, component, width in (
        ('POSITION', 'positions_float32', 5126, 3),
        ('NORMAL', 'normals_float32', 5126, 3),
        ('TEXCOORD_0', 'submesh_0_uv_0', 5126, 2),
        ('indices', 'triangle_indices_uint16', 5123, 1),
    ):
        index = primitive['indices'] if semantic == 'indices' else primitive['attributes'][semantic]
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        expected_count = 960 if semantic == 'indices' else 205
        expected_type = {1: 'SCALAR', 2: 'VEC2', 3: 'VEC3'}[width]
        if accessor['componentType'] != component or accessor['count'] != expected_count or accessor['type'] != expected_type:
            raise ModelError('Exported accessor layout changed: ' + semantic)
        if view.get('byteStride') or accessor.get('sparse') or accessor.get('normalized'):
            raise ModelError('Unexpected transformed accessor: ' + semantic)
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        span = ranges[key]
        original = source_raw[span['offset']:span['offset'] + span['size']]
        exported = binary[offset:offset + span['size']]
        if exported != original:
            raise ModelError('GLB array differs from exact source bytes: ' + semantic)
        result.append({'semantic': semantic, 'sourceOffset': span['offset'], 'bytes': span['size'],
                       'sourceSha256': sha(original), 'glbSha256': sha(exported), 'byteIdentical': True})
    if any(k in doc['nodes'][0] for k in ('matrix', 'rotation', 'translation', 'scale')):
        raise ModelError('Geometry export unexpectedly applied a node transform')
    return result


def xml_tree(raw):
    """Preserve every attribute, sibling order and source line, including unknown enums."""
    from xml.parsers import expat
    parser = expat.ParserCreate()
    stack, roots, elements = [], [], {}

    def start(tag, attrs):
        siblings = stack[-1]['children'] if stack else roots
        ordinal = 1 + sum(x['tag'] == tag for x in siblings)
        prefix = stack[-1]['xpath'] if stack else ''
        row = {'tag': tag, 'attributes': attrs, 'line': parser.CurrentLineNumber,
               'xpath': f'{prefix}/{tag}[{ordinal}]', 'children': []}
        siblings.append(row)
        elements[row['xpath']] = row
        stack.append(row)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _: stack.pop()
    # Decode once, normalizing CRCRLF only as the XML parser itself does.
    text = raw.decode('gb18030').replace('\r\r\n', '\n').replace('\r\n', '\n')
    parser.Parse(text, True)
    if len(roots) != 1:
        raise ValueError('Expected one source XML root')
    return roots[0], elements


def run(out):
    catalogue = json.loads((EFFECTS / 'bindings.json').read_text('utf8'))
    if catalogue['apkSha256'] != APK_SHA256:
        raise ValueError('Wrong effect source APK')
    sources = {x['source']['logical_path']: x['source'] for x in catalogue['files']}
    for path in THEATRE.glob('*.provenance.json'):
        source = json.loads(path.read_text('utf8'))
        if source.get('logical_path') in SOURCE_PINS:
            sources[source['logical_path']] = source
    ags = json.loads((ROOT / 'analysis/battle-visual/skill-animation/ailisha.ags.provenance.json').read_text('utf8'))
    sources[ags['logical_path']] = ags
    used = {}

    def read(logical, pin=None):
        source = sources[logical]
        raw = Path(source['sample_path']).read_bytes()
        digest = sha(raw)
        expected = pin or SOURCE_PINS.get(logical) or source['sha256']
        if source['apk_sha256'] != APK_SHA256 or digest != source['sha256'] or digest != expected:
            raise ValueError('Recovered source identity changed: ' + logical)
        used[logical] = source
        return raw

    raw_mesh = read(MESH, MESH_SHA)
    model = parse_model(raw_mesh)
    exported = []
    out.mkdir(parents=True, exist_ok=True)
    for logical, pins in VARIANTS.items():
        gim = read(logical, pins['gim'])
        mtg_path = logical[:-4] + '.mtg'
        mtg = read(mtg_path, pins['mtg'])
        materials = parse_materials(mtg, expected_slots=1)
        bindings = bind_daoguang_full_ring(model, gim, materials)
        name = Path(logical).stem
        blob, _, _ = encode_glb(model, name, skin=False)
        doc, binary = split_glb(blob)
        doc['materials'] = [{'name': name + '_source_slot_0', 'doubleSided': True,
                            'extras': {'originalMaterial': materials[0], 'shaderImplemented': False}}]
        doc['meshes'][0]['primitives'][0]['material'] = 0
        doc['extras'].update(sourceGim=logical, sourceMesh=MESH, sourceMaterialGroup=mtg_path,
                             sourceBoundsEvidence=bindings[0]['bounds_validation'])
        blob = pack_glb(doc, binary)
        equality = verify_glb_arrays(blob, raw_mesh, model)
        target = out / (name + '.glb')
        target.write_bytes(blob)
        exported.append({'gim': logical, 'mesh': MESH, 'materialGroup': mtg_path,
                         'glb': str(target.resolve()), 'sha256': sha(blob), 'bindings': bindings,
                         'materials': materials, 'arrayVerification': equality})

    ags_tree = ET.fromstring(read('character/player/ailisha/ailisha.ags').decode('gb18030'))
    track = ags_tree.find('./AnimationEventTracks/EventTrack_fire_1')
    event = next(x for x in track if x.get('Name') == 'fx_fire1')
    if float(event.attrib['TimeRatio']) != 0:
        raise ValueError('Original fire_1 event ratio changed')
    gim_tree = ET.fromstring(read('character/player/ailisha/ailisha.gim').decode('gb18030'))
    trigger = gim_tree.find('./Triggers/fire_1/fx_fire1/trigger')
    socket = next(x for x in gim_tree.find('Sockets') if x.get('Name') == trigger.get('SocketName'))
    outer_path = trigger.attrib['ObjectFileName'].replace('\\', '/')
    outer, outer_nodes = xml_tree(read(outer_path))
    emitter = next(x for x in outer_nodes.values() if x['tag'] == 'ParticleRes')
    child_path = emitter['attributes']['SfxName'].replace('\\', '/')
    child, child_nodes = xml_tree(read(child_path))
    delay = float(emitter['attributes']['FxStartTime'])
    if delay != 0.2 or child_path != 'effects/player/001/new_daoguang_01.sfx':
        raise ValueError('Original ordinary slash source chain changed')
    layers = []
    for node in child_nodes.values():
        if node['tag'] not in ('Model', 'Sprite', 'ParticleSystem'):
            continue
        parent_path = node['xpath'].rsplit('/', 1)[0]
        ancestors = []
        while parent_path:
            ancestor = child_nodes[parent_path]
            ancestors.insert(0, {'tag': ancestor['tag'], 'xpath': ancestor['xpath'],
                                 'line': ancestor['line'], 'attributes': ancestor['attributes'],
                                 'tracks': [x for x in ancestor['children'] if x['tag'].startswith('Track')]})
            parent_path = parent_path.rsplit('/', 1)[0]
        attrs = node['attributes']
        nominal_start = delay + sum(float(x['attributes'].get('FxStartTime', 0)) for x in ancestors)
        nominal_start += float(attrs.get('FxStartTime', 0))
        layer = {'node': node, 'ancestors': ancestors, 'enabledInSource': attrs.get('FxIgnore') == 'FALSE',
                 'nominalFirstEmissionStartSeconds': round(nominal_start, 6),
                 'sourceLifeSeconds': float(attrs.get('FxLifeSpan', 0)),
                 'timingScope': 'First EmitAtBegin child; parent lifetime clipping/emission scheduler not executed'}
        if node['tag'] == 'Model':
            model_path = attrs['ModelName'].replace('\\', '/')
            layer['geometry'] = next(x for x in exported if x['gim'] == model_path)
            layer['shaderCurves'] = []
            uniforms = next(x for x in node['children'] if x['tag'] == 'ShaderComponent')['children'][0]
            variables = next(x for x in uniforms['children'] if x['tag'] == 'Variables')
            for semantic in variables['children']:
                curve = next(x for x in uniforms['children'] if x['tag'] == semantic['attributes']['Value'])
                layer['shaderCurves'].append({'semantic': semantic['attributes'], 'curve': curve})
        layers.append(layer)

    references = []
    for row in exported:
        material = row['materials'][0]
        shader_path = material['technique']['TechName'].split('::')[0].replace('\\', '/')
        read(shader_path)
        references.append({'original': shader_path, 'kind': 'shader', 'source': used[shader_path]})
        for parameter, value in material['params'].items():
            if not parameter.startswith('Tex'):
                continue
            logical = value.replace('\\', '/')
            container = logical.rsplit('.', 1)[0] + '.ktx'
            read(container)
            references.append({'materialGroup': row['materialGroup'], 'parameter': parameter,
                               'original': logical, 'kind': 'texture', 'container': container,
                               'source': used[container]})
    for layer in layers:
        attrs = layer['node']['attributes']
        if attrs.get('Texture'):
            logical = attrs['Texture'].replace('\\', '/')
            container = logical.rsplit('.', 1)[0] + '.ktx'
            if container in sources:
                read(container)
                references.append({'layer': layer['node']['xpath'], 'original': logical,
                                   'kind': 'sprite-texture', 'container': container, 'source': used[container]})

    recipe = {
        'schemaVersion': 1, 'apkSha256': APK_SHA256, 'originalRuntimeExecuted': False,
        'event': {'animation': 'fire_1', 'event': dict(event.attrib), 'trigger': dict(trigger.attrib),
                  'agsSource': used['character/player/ailisha/ailisha.ags'],
                  'gimSource': used['character/player/ailisha/ailisha.gim'],
                  'socket': {'tag': socket.tag, 'attributes': dict(socket.attrib)},
                  'socketBindingCaveat': 'BindType=7 is retained as source enum; no unsupported bone-name substitution.'},
        'outerSfx': {'source': used[outer_path], 'tree': outer},
        'childSfx': {'source': used[child_path], 'tree': child},
        'emission': {'sourceNode': emitter, 'firstChildDelaySeconds': delay,
                     'sourceScaleMinMax': [float(emitter['attributes'][k]) for k in ('MinScale', 'MaxScale')],
                     'note': 'EmitAtBegin=TRUE; zero velocity/gravity/rotation-speed. Preserve source emission/life settings.'},
        'layers': layers, 'models': exported, 'sourceReferences': references,
        'sourceGeometry': {'vertices': 205, 'triangles': 320, 'fullMeshBytes': len(raw_mesh),
                           'parserCoverageBytes': model['coverage_bytes'], 'byteRanges': model['ranges']},
        'findings': {
            'observed': ['Both GIMs explicitly reference the identical shared daoguang_01.mesh.',
                         'GIM contains no model transform; source mesh Y=0, all original XYZ/UV/index bytes are retained.',
                         'GIM half widths 46.7992/46.8 enclose radius 46.799161610443754.',
                         '40 angular directions at 4.5+9*n degrees give axis extrema ~46.6548996.',
                         'The old exact-AABB assumption rejects this conservative circular bound; no corrupt decoded bytes observed.'],
            'inferred': ['The radial envelope is suitable for the source Y-axis rotations. Authoring intent/native culling was not executed.'],
            'forbiddenFixes': ['Do not rescale geometry to fill GIM bounds.', 'Do not substitute daoguang_half.',
                               'Do not relax generic bind_materials AABB checks.']},
        'limitations': [
            'GLB contains exact geometry plus original material metadata, not a NeoX shader implementation.',
            'TrackFixPoint.Forward, TrackRotate.CycleType, curve ChangeType/Interpolator and color ordering are retained verbatim; native semantics not newly verified here.',
            'Do not collapse nested transforms or treat raw curve Time as seconds without the runtime enum/time evidence.',
            'Nominal first-emission start is 0.20s for refraction and 0.25s for the luminous model. Parent dummy life is 0.50s while luminous layer ends nominally at child 0.55s; clipping/continuation requires runtime confirmation.',
            'Two meshes alone are not the whole slash: four enabled Sprite layers accompany them; the ParticleSystem is FxIgnore=TRUE.',
        ],
        'sources': list(used.values()),
    }
    write_json(out / 'playback-recipe.json', recipe)
    return {'out': str(out.resolve()), 'models': len(exported), 'byteIdenticalArrays': sum(len(x['arrayVerification']) for x in exported),
            'enabledLayers': sum(x['enabledInSource'] for x in layers), 'recipe': str((out / 'playback-recipe.json').resolve())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'analysis/battle-visual/normal-slash')
    args = parser.parse_args()
    print(json.dumps(run(args.out.resolve()), ensure_ascii=False, indent=2))
