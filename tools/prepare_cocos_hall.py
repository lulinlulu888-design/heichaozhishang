"""Stage source-verified hall assets for the shared Cocos client; no APK mutation."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from export_elsa_model import split_glb, pack_glb

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'legacy/cocos-poc/assets/resources/recovered/hall'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def read_json(path):
    return json.loads(path.read_text('utf8'))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')


def texture_meta(path):
    """Let Creator generate texture data, preserving any existing import identity."""
    meta = path.with_suffix(path.suffix+'.meta')
    if meta.exists():
        return
    write_json(meta, dict(ver='1.0.27', importer='image', imported=False,
        uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'hczs/'+path.relative_to(ROOT).as_posix())),
        files=[], subMetas={}, userData=dict(type='texture', fixAlphaTransparencyArtifacts=False)))


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    records = []

    def stage(source, target, expected=None, rewrite=None):
        source = ROOT/source
        blob = source.read_bytes()
        sha = digest(blob)
        if expected and sha != expected:
            raise ValueError('Verified source changed: '+str(source))
        output = rewrite(blob) if rewrite else blob
        dest = DEST/target
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(output)
        if dest.suffix == '.png':
            texture_meta(dest)
        records.append(dict(source=source.relative_to(ROOT).as_posix(), source_sha256=sha,
            output=dest.relative_to(ROOT).as_posix(), output_sha256=digest(output),
            changed=output != blob))
        return output

    source = ROOT/'analysis/hall/midgard_home_3d/scene.glb'
    report = read_json(source.with_name('export.json'))
    source_bytes = source.read_bytes()
    if digest(source_bytes) != report['sha256']:
        raise ValueError('Hall GLB changed')
    doc, binary = split_glb(source_bytes)
    uuids, opaque, hidden, players = {}, [], [], []
    for index, node in enumerate(doc['nodes']):
        original = node.get('extras', {}).get('sourceInstance', {})
        if 'mesh' not in node:
            continue
        node.setdefault('extras', {})['sourceNodeName'] = node.get('name')
        node['name'] = f'HallSource_{index}'
        identity = original.get('UUID')
        if identity:
            if identity in uuids:
                raise ValueError('Duplicate source instance UUID')
            uuids[identity] = node
        if original.get('Name') == 'player_position':
            players.append(dict(matrix=node['matrix'], scale=.86))
        if original.get('FilePathIndex') == '25':
            hidden.append(node['name'])
        for slot, primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
            material = doc['materials'][primitive['material']]
            cull_back = 'CullMode="2"' in material.get('extras', {}).get('sourceMaterialXML', '')
            if cull_back:
                material['doubleSided'] = False
            if material.get('alphaMode', 'OPAQUE') == 'OPAQUE':
                opaque.append(dict(nodeName=node['name'], slot=slot, cullBack=cull_back))
    if len(players) != 1:
        raise ValueError('Original player marker is not unique')
    staged = pack_glb(doc, binary)
    stage(source.relative_to(ROOT), 'scene/scene.glb', report['sha256'], lambda _: staged)
    scene_data = dict(schema=1, cameras=doc['extras']['sourceCameras'],
        player=players[0], hiddenNodes=hidden, opaque=opaque,
        source_sha256=report['sha256'], staged_sha256=digest(staged),
        adaptations=['Unique node names for Cocos; source names preserved in extras',
                     'CullMode 2 mapped to back-face culling, matching the existing Three reference',
                     'Scale .86 follows the already verified hall reconstruction'])
    scene_data['characterMaterials'] = {}

    for directory, basename, target in [
        ('export', 'shiranui-idle.colour-reference.glb', 'actor/actor.glb'),
        ('export-weapon', 'shiranuiweapon-idle.colour-reference.glb', 'weapon/weapon.glb'),
    ]:
        base = ROOT/'analysis/characters/shiranui'/directory
        actor_report = read_json(base/'export-report.json')
        actor_blob = stage((base/basename).relative_to(ROOT), target, actor_report['sha256'])
        actor_doc, _ = split_glb(actor_blob)
        mesh_nodes = [n for n in actor_doc['nodes'] if 'mesh' in n]
        if len(mesh_nodes) != 1:
            raise ValueError('Hall character must have one source mesh node')
        rows = []
        for slot, primitive in enumerate(actor_doc['meshes'][mesh_nodes[0]['mesh']]['primitives']):
            material = actor_doc['materials'][primitive['material']]
            mode = material.get('alphaMode', 'OPAQUE')
            if mode == 'BLEND':
                continue
            if mode not in ('OPAQUE', 'MASK'):
                raise ValueError('Unsupported character alpha mode')
            rows.append(dict(slot=slot, alphaMode=mode, alphaCutoff=material.get('alphaCutoff', .5)))
        scene_data['characterMaterials'][target.split('/')[0]] = rows
    write_json(DEST/'scene-data.json', scene_data)

    lightbase = ROOT/'analysis/hall/lighting'
    lighting = read_json(lightbase/'lighting.json')
    if lighting['scene_glb_sha256'] != report['sha256']:
        raise ValueError('Lightmaps target another hall export')
    for texture in lighting['textures']:
        stage((lightbase/texture['file']).relative_to(ROOT), texture['file'], texture['sha256'])
        texture['resource'] = 'recovered/hall/'+Path(texture['file']).stem
    for row in lighting['bindings']:
        node = uuids[row['uuid']]
        if node['mesh'] != row['mesh']:
            raise ValueError('Lightmap mesh identity changed')
        primitives = doc['meshes'][node['mesh']]['primitives']
        if len(primitives) != 1 or row['primitive'] != 0:
            raise ValueError('Unsupported multi-primitive lightmap')
        if doc['accessors'][primitives[0]['attributes']['TEXCOORD_1']]['count'] != row['uv_count']:
            raise ValueError('Source UV count changed')
        row['nodeName'] = node['name']
        row['cullBack'] = not doc['materials'][primitives[0]['material']].get('doubleSided', False)
    write_json(DEST/'lighting.json', lighting)

    fxbase = ROOT/'analysis/characters/shiranui/effects/render-inputs'
    flame = read_json(fxbase/'manifest.json')
    stage((fxbase/'flame-01.glb').relative_to(ROOT), 'flame/geometry/flame.glb', flame['geometry_sha256'])
    for index, texture in enumerate(flame['textures']):
        output = texture['outputs'][0]
        stage(Path(output['png']), f'flame/texture-{index}.png', output['png_sha256'])
    stage((fxbase/'manifest.json').relative_to(ROOT), 'flame/manifest.json')
    stage((fxbase/'attachment.json').relative_to(ROOT), 'flame/attachment.json')
    for template, target in [('cocos-hall-lightmap.effect', 'lightmap.effect'),
                             ('cocos-shiranui-flame.effect', 'flame/flame.effect')]:
        source_template = ROOT/'tools/templates'/template
        if not source_template.is_file():
            raise ValueError('Missing renderer template: '+template)
        stage(source_template.relative_to(ROOT), target)
    for template, target in [('cocos-hall-scene-view.ts','HallSceneView.ts'),
                             ('cocos-hall-lighting.ts','HallLighting.ts'),
                             ('cocos-shiranui-flames.ts','ShiranuiFlames.ts')]:
        shutil.copyfile(ROOT/'tools/templates'/template, ROOT/'legacy/cocos-poc/assets'/target)
    write_json(DEST/'provenance.json', dict(schema=1, records=records,
        counts=dict(lightmaps=len(lighting['textures']), light_instances=len(lighting['bindings']),
                    environment_instances=len(uuids), opaque_slots=len(opaque)),
        limitation='Shared-client resource staging; not visual, native, or original-client acceptance'))
    print(json.dumps(dict(files=len(records), light_instances=len(lighting['bindings']),
                         opaque_slots=len(opaque), scene_sha256=digest(staged))))


if __name__ == '__main__':
    main()
