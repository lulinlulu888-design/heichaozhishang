"""Build the original mainline dungeon panel draw data for UE.

Reads the shipped MainLineDungeonPanel CSB graph as data. Chat, boss areas,
the progress counter and the call button stay out of this page: their runtime
state is not restored. Challenge 3997 supplies the two placeholder strings.
"""
import hashlib
import json
import plistlib
from collections import Counter, deque
from pathlib import Path

from audit_hall_ui_dependencies import nodes, ui_path
from audit_worldline_ui_dependencies import WorldlineReader, digest, strings
from decode_ktx import DEFAULT_DECODER, convert
from export_elsa_model import extract
from extract_npk import Marshal2
from extract_texture_samples import APK_SHA256
from neox_resource_paths import lookup_logical, read_catalogue
from prepare_unreal_hall_ui import geometry, multiply, rgba, transform, verified
from recover_hall_ui_sprites import crop_frame

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/unreal/mainline-dungeon-ui'
DEP = OUT / 'dependencies'
PIXELS = OUT / 'sprites'
ENTRY = 'uires/MainLlineDungeonPanel/MainLineDungeonPanel_ext.csb'
# Panel, info area, info popup and number area. Boss autos stay out.
AUTO_INDICES = (5474, 1496, 3788, 9410)
SKIP_PROJECTS = {'ChatNode', 'progressNode', 'BossDungeonInfo', 'BossBlessBtnArea', 'BossTitleBtnArea'}
SKIP_NODES = {'BtnCall'}
CHALLENGES = ROOT / 'analysis/mainline-dungeon/data/challenges.json'
CHALLENGE_SHA = 'faa114ed68d88252a154bb63f5538090844ac34bcfd1cd62620ec149a3465809'


def exclusion(node):
    name = node.get('name') or ''
    if name in SKIP_PROJECTS:
        return 'chat-boss-or-progress-runtime-not-restored'
    if name in SKIP_NODES:
        return 'call-completion-flow-not-restored'
    if node.get('classname') == 'Particle':
        return 'original-particle-not-converted'
    return None


def script_refs(index):
    result = []
    for number in AUTO_INDICES:
        row = index[number]
        path = ROOT / row['output']
        if digest(path) != row['decoded_sha256']:
            raise ValueError('Decoded script hash changed: ' + str(number))
        refs = sorted({item for item in strings(Marshal2(path.read_bytes()).obj())
                       if item.endswith(('.csb', '.plist', '.png', '.ttf'))})
        result.append(dict(index=number, filename=row['filename'], sha256=digest(path), resourceStrings=refs))
    if ENTRY not in result[0]['resourceStrings']:
        raise ValueError('Panel auto script no longer binds the dungeon entry')
    return result


def challenge_copy():
    report = json.loads(CHALLENGES.read_text('utf8'))
    if report['source']['decoded_sha256'] != CHALLENGE_SHA:
        raise ValueError('Challenge table identity changed')
    row = next(item for item in report['rows'] if item['id'] == 3997)
    fields = row['fields']
    if fields['ChallengeSpecialName'] != '序章' or not fields['ChallengeDesc']:
        raise ValueError('Challenge 3997 display fields changed')
    return fields['ChallengeSpecialName'], fields['ChallengeDesc'], fields['ChapterName']


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('Unexpected original APK bytes')
    catalogue = read_catalogue(apk)
    index = {row['index']: row for row in json.loads((ROOT / 'analysis/assets/decoded/script/index.json').read_text('utf8'))}
    refs = script_refs(index)
    special, description, chapter = challenge_copy()
    DEP.mkdir(parents=True, exist_ok=True)
    queue, visited, layouts, edges, resources = deque([ENTRY]), set(), [], [], []
    while queue:
        logical = queue.popleft()
        if logical in visited:
            continue
        if len(visited) >= 64:
            raise ValueError('Dungeon UI graph budget exceeded')
        visited.add(logical)
        matches = lookup_logical(catalogue, logical)
        if len(matches) != 1:
            layouts.append(dict(path=logical, status='unresolved', matches=len(matches)))
            continue
        target = DEP / 'source' / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        source = extract(apk, catalogue, logical, target, APK_SHA256)
        reader = WorldlineReader(target.read_bytes(), preserve_unknown=True)
        root = reader.scalar('I', 0)
        version = reader.string(reader.field(root, 0))
        if version != '2.1.0.0':
            raise ValueError('Unsupported shipped CSB version: ' + str(version))
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        layouts.append(dict(path=logical, source=source, tree=tree, version=version, node_count=len(reader.seen)))
        for node in nodes(tree):
            if node.get('name') in SKIP_PROJECTS | SKIP_NODES:
                continue
            if node.get('project_path'):
                child = ui_path(node['project_path'])
                edges.append(dict(parent=logical, node=node['name'], child=child))
                queue.append(child)
            for field in ('resource', 'pressed_resource', 'disabled_resource', 'background_resource', 'font_resource'):
                resource = node.get(field)
                if not resource or not resource.get('path'):
                    continue
                resolved = ui_path(resource.get('plist') or resource['path'])
                hits = lookup_logical(catalogue, resolved)
                resources.append(dict(layout=logical, node=node['name'], field=field, reference=resource,
                    lookup_path=resolved, kind='atlas-frame' if resource.get('plist') else 'file', matches=len(hits)))
    atlases = {}
    for resource in resources:
        logical = resource['lookup_path']
        if not logical.endswith('.plist') or resource['matches'] != 1 or logical in atlases:
            continue
        target = DEP / 'source' / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        source = extract(apk, catalogue, logical, target, APK_SHA256)
        atlas = plistlib.loads(target.read_bytes())
        if not isinstance(atlas, dict) or not isinstance(atlas.get('frames'), dict):
            continue
        texture = atlas.get('metadata', {}).get('textureFileName')
        atlases[logical] = dict(source=source, frames=atlas['frames'], texture_path=ui_path(texture) if texture else None)
        if resource['kind'] == 'atlas-frame':
            resource['frame_present'] = resource['reference']['path'] in atlas['frames']
    for resource in resources:
        if resource['kind'] == 'atlas-frame' and 'frame_present' not in resource:
            atlas = atlases.get(resource['lookup_path'])
            resource['frame_present'] = bool(atlas and resource['reference']['path'] in atlas['frames'])
    PIXELS.mkdir(parents=True, exist_ok=True)
    frames, files, fonts = [], [], []
    for logical, record in atlases.items():
        texture_logical = record['texture_path'].removesuffix('.png') + '.pkm'
        directory = PIXELS / Path(logical).stem
        directory.mkdir(parents=True, exist_ok=True)
        texture = directory / 'atlas.ktx'
        extract(apk, catalogue, texture_logical, texture, APK_SHA256)
        decoded = convert([texture], directory / 'decoded', DEFAULT_DECODER)
        outputs = decoded['textures'][0]['outputs']
        if len(outputs) != 1:
            raise ValueError('Expected one atlas image')
        from PIL import Image
        image = Image.open(ROOT / outputs[0]['png']).convert('RGBA')
        wanted = {item['reference']['path'] for item in resources
                  if item['lookup_path'] == logical and item.get('frame_present')}
        for key in sorted(wanted):
            pixels = crop_frame(image, record['frames'][key])
            name = hashlib.sha256((logical + '\0' + key).encode()).hexdigest()[:24]
            target = directory / (name + '.png')
            pixels.save(target)
            frames.append(dict(plist=logical, source_frame=key, frame=record['frames'][key],
                png=str(target.relative_to(ROOT)), size=list(pixels.size), sha256=digest(target)))
    file_refs = sorted({item['lookup_path'] for item in resources if item['kind'] == 'file' and item['lookup_path'].endswith(('.png', '.ttf'))})
    for logical in file_refs:
        if logical.endswith('.ttf'):
            target = PIXELS / 'fonts' / (hashlib.sha256(logical.encode()).hexdigest()[:24] + '.ttf')
            target.parent.mkdir(parents=True, exist_ok=True)
            source = extract(apk, catalogue, logical, target, APK_SHA256)
            fonts.append(dict(logical_path=logical, path=str(target.relative_to(ROOT)), sha256=digest(target), source=source))
            continue
        name = logical.removeprefix('uires/')
        memberships = [key for key, record in atlases.items() if name in record['frames']]
        if len(memberships) == 1:
            continue
        if memberships:
            raise ValueError('Ambiguous dungeon atlas frame: ' + name)
        packed = logical.removesuffix('.png') + '.pkm'
        direct, candidates = lookup_logical(catalogue, logical), lookup_logical(catalogue, packed)
        directory = PIXELS / 'standalone' / hashlib.sha256(logical.encode()).hexdigest()[:24]
        directory.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        if len(direct) == 1:
            target = directory / 'original.png'
            source = extract(apk, catalogue, logical, target, APK_SHA256)
            png, resolution = target, 'direct-original-png'
        elif not direct and len(candidates) == 1:
            target = directory / 'original.ktx'
            source = extract(apk, catalogue, packed, target, APK_SHA256)
            decoded = convert([target], directory / 'decoded', DEFAULT_DECODER)
            outputs = decoded['textures'][0]['outputs']
            if len(outputs) != 1:
                raise ValueError('Expected one standalone image')
            png, resolution = ROOT / outputs[0]['png'], 'original-loader-png-to-pkm-substitution'
        else:
            continue
        image = Image.open(png).convert('RGBA')
        files.append(dict(logical_path=logical, source=source, png=str(png.relative_to(ROOT)),
                          size=list(image.size), sha256=digest(png), resolution=resolution))
    trees = {row['path']: row['tree'] for row in layouts if 'tree' in row}
    sprites, sprite_map, font_rows, font_map = [], {}, [], {}
    for row in frames:
        png = verified(row['png'], row['sha256'])
        item = dict(id=png.stem, plist=row['plist'], sourceFrame=row['source_frame'], png=str(png),
                    pngSha256=row['sha256'], size=row['size'])
        sprites.append(item)
        sprite_map[(row['plist'], row['source_frame'])] = item
    for row in files:
        png = verified(row['png'], row['sha256'])
        item = dict(id='standalone_' + digest(png)[:24], logicalPath=row['logical_path'], png=str(png),
                    pngSha256=row['sha256'], size=row['size'], resolution=row['resolution'])
        sprites.append(item)
        sprite_map[(None, row['logical_path'])] = item
    for row in fonts:
        path = verified(row['path'], row['sha256'])
        item = dict(id=path.stem, logicalPath=row['logical_path'], ttf=str(path), sha256=row['sha256'])
        font_rows.append(item)
        font_map[row['logical_path']] = item

    def convert_page(entry):
        draw_nodes, items, controls, gaps = [], [], [], []

        def visit(node, layout, parent, world, visible, opacity, path, clip_ids, reason=None, stack=()):
            if len(draw_nodes) > 800 or len(stack) > 16:
                raise ValueError('Dungeon expansion bounds exceeded')
            name = node.get('name') or '<opaque>'
            full = path + [name]
            node_id = 'n' + str(len(draw_nodes)).zfill(4)
            local_reason = reason or exclusion(node)
            meta = {key: value for key, value in node.items() if key != 'children'}
            meta.update(id=node_id, parentId=parent, layout=layout, instancePath='/'.join(full), previewExcludedReason=local_reason)
            draw_nodes.append(meta)
            if local_reason or node.get('options_status'):
                gaps.append(dict(kind=local_reason or 'opaque-options', nodeId=node_id, name=name))
                return
            world = multiply(world, transform(node))
            visible = visible and node['visible']
            opacity *= node['alpha'] / 255
            size = list(node.get('size') or [0, 0])
            clips = list(clip_ids)
            if node.get('clip_enabled'):
                meta['clipGeometry'] = geometry(world, size)
                clips.append(node_id)
            children = sorted(enumerate(node['children']), key=lambda pair: (pair[1].get('z_order', 0), pair[0]))
            for _, child in children:
                if child.get('z_order', 0) < 0:
                    visit(child, layout, node_id, world, visible, opacity, full, clips, local_reason, stack)
            ref = node.get('resource') or node.get('background_resource')
            if ref and ref.get('path'):
                sprite = sprite_map.get((ui_path(ref['plist']), ref['path'])) if ref.get('plist') else sprite_map.get((None, ui_path(ref['path'])))
                if not sprite:
                    gaps.append(dict(kind='missing-image', nodeId=node_id, resource=ref))
                else:
                    size = [size[index] or sprite['size'][index] for index in range(2)]
                    item = dict(id=node_id + '-sprite', nodeId=node_id, kind='sprite', nodeName=name, layout=layout,
                        instancePath='/'.join(full), size=size, visible=visible, opacity=opacity, geometry=geometry(world, size),
                        color=rgba(node.get('color_argb')), clipNodeIds=clips, previewExcludedReason=None,
                        spriteId=sprite['id'], flipX=node.get('flip_x', False), flipY=node.get('flip_y', False))
                    items.append(item)
                    leaf = Path(layout).name
                    if node['classname'] == 'Button' and leaf == 'DungeonInfoArea_ext.csb' and name == 'BtnGo':
                        controls.append(dict(action='explore', size=size, geometry=item['geometry'], enabled=True,
                            authority='original-BtnGo-hitbox; local-tutorial-5000-adaptation'))
                    if node['classname'] == 'Button' and leaf == 'Topbar_left_ext.csb' and name == 'btn_back':
                        controls.append(dict(action='back', size=size, geometry=item['geometry'], enabled=True,
                            authority='original-source-hitbox; local-leave-dungeon'))
            if node.get('text'):
                font_ref = node.get('font_resource') or {}
                font = font_map.get(ui_path(font_ref['path'])) if font_ref.get('path') else None
                if node['classname'] not in ('Text', 'Button') or not font:
                    gaps.append(dict(kind='text-font', nodeId=node_id, text=node['text']))
                else:
                    text, authority = node['text'], 'authored-static-string'
                    if name == 'TxtChallenNum':
                        text, authority = special, 'challenge-3997-ChallengeSpecialName'
                    elif name == 'TxtDesc':
                        text, authority = description, 'challenge-3997-ChallengeDesc'
                    elif Path(layout).name == 'Topbar_left_ext.csb' and name == 'title':
                        text, authority = chapter, 'challenge-3997-ChapterName'
                    item = dict(id=node_id + '-text', nodeId=node_id, kind='text', nodeName=name, layout=layout,
                        instancePath='/'.join(full), size=size, visible=visible, opacity=opacity, geometry=geometry(world, size),
                        color=rgba(node.get('text_color_argb') or node.get('color_argb')), clipNodeIds=clips,
                        previewExcludedReason=None if text not in ('Button', 'button') else 'button-authoring-placeholder',
                        text=text, authoredText=node['text'], fontId=font['id'], fontSize=node.get('font_size', 0),
                        horizontalAlignment=1 if node['classname'] == 'Button' else node.get('h_alignment', 0),
                        verticalAlignment=1 if node['classname'] == 'Button' else node.get('v_alignment', 0),
                        textAuthority=authority, wrap=name == 'TxtDesc')
                    items.append(item)
            if node.get('project_path'):
                child = ui_path(node['project_path'])
                if child not in trees:
                    raise ValueError('Missing original ProjectNode: ' + child)
                visit(trees[child], child, node_id, world, visible, opacity, full + ['@' + Path(child).stem], clips, local_reason, stack + (layout,))
            for _, child in children:
                if child.get('z_order', 0) >= 0:
                    visit(child, layout, node_id, world, visible, opacity, full, clips, local_reason, stack)

        visit(trees[entry], entry, None, [1, 0, 0, 1, 0, 0], True, 1, [], [])
        index_by_id = {node['id']: node for node in draw_nodes}
        for item in items:
            item['clipGeometry'] = [index_by_id[key]['clipGeometry'] for key in item['clipNodeIds']]
        return dict(nodes=len(draw_nodes), items=[item for item in items if item['visible'] and item['opacity'] > 0 and not item['previewExcludedReason']],
                    controls=controls, gaps=gaps)

    page = convert_page(ENTRY)
    if not any(item.get('nodeName') == 'TxtChallenNum' and item.get('text') == special for item in page['items']):
        raise ValueError('序章 label was not bound')
    if not any(item.get('text') == description for item in page['items']):
        raise ValueError('Challenge description was not bound')
    result = dict(schemaVersion=1, canvas=dict(width=1280, height=720, drawOrigin='top-left'), apkSha256=APK_SHA256,
        entry=ENTRY, challengeId=3997, page=page, sprites=sprites, fonts=font_rows,
        scriptReferences=[dict(index=row['index'], filename=row['filename'], sha256=row['sha256']) for row in refs],
        limitations=['Chat, boss areas, number progress and the call button are omitted',
            'TxtChallenNum and TxtDesc use challenge 3997 fields; the setter body is outside the exported panel instructions',
            '3998 stays locked until 3997 has a successTime record; this page does not start battle 1703'])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'layout.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    summary = dict(layoutSha256=digest(OUT / 'layout.json'), layouts=len(layouts), drawItems=len(page['items']),
        controls=page['controls'], sprites=len(sprites), fonts=len(font_rows), gaps=len(page['gaps']),
        kinds=dict(Counter(item['kind'] for item in page['items'])))
    (OUT / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
