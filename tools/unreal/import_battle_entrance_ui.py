"""Import source entrance UI textures into a dedicated, ownership-checked folder.

Ordinary Python only validates/prints a plan. Explicit run(apply=True) inside UE
imports textures and a dedicated runtime timeline DataAsset; it never edits a
level, widget, material, or existing presentation asset.
Original per-node animation/shader limitations stay in playback-recipe.json.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'analysis/battle-ui/entrance/playback-recipe.json'
DEST = '/Game/Recovered/Battle/Entrance/UI'
REPORT = ROOT / 'analysis/unreal/battle-entrance-ui/import-report.json'
APK_SHA = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
OWNER = 'hczs-source-battle-entrance-ui-v1'
OWN_CARD_IN = ROOT / 'analysis/battle-ui/hud-in/own-card-area-in.json'
OWN_CARD_SHA = '81273767f5d227e90ca1d8bdc07a0bf08100485c35833898afe24efbd51536f9'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(filename, expected_sha):
    path = (ROOT / filename).resolve()
    if not path.is_relative_to((ROOT / 'analysis/battle-ui/entrance').resolve()):
        raise ValueError('Entrance input outside its prepared directory')
    data = path.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError('Source input changed: ' + str(path))
    return path, data


def plan():
    recipe = json.loads(SOURCE.read_text('utf8'))
    if recipe['schema'] != 'hczs-battle-entrance-ui-v1':
        raise ValueError('Unexpected entrance schema')
    if recipe['sourceApkSha256'] != APK_SHA or recipe['destination'] != DEST:
        raise ValueError('Source APK/destination mismatch')
    identity = dict(recipe)
    expected = identity.pop('recipeSha256')
    if sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()) != expected:
        raise ValueError('Prepared entrance recipe changed')
    if recipe['unresolvedDirectImages']:
        raise ValueError('Entrance direct images remain unresolved')
    for name, layout in recipe['layouts'].items():
        source = layout['source']
        checked_file('analysis/battle-ui/entrance/csb/' + name + '.csb', source['sha256'])
        for track in layout['timeline']['timelines']:
            if not track['targetNodeNames']:
                raise ValueError('Unbound source animation target')
    rows, names = [], set()
    for row in recipe['sprites']:
        name = 'T_Entrance_' + row['name']
        if not re.fullmatch(r'[A-Za-z0-9_]+', name) or name in names:
            raise ValueError('Invalid/duplicate asset name')
        names.add(name)
        path, raw = checked_file(row['png'], row['sha256'])
        if raw[:8] != b'\x89PNG\r\n\x1a\n' or list(struct.unpack('>II', raw[16:24])) != row['size']:
            raise ValueError('Original PNG dimensions changed')
        rows.append({'spriteId': row['name'], 'name': name, 'png': str(path),
                     'sha256': row['sha256'], 'size': row['size'],
                     'sourceResource': row['source_frame'], 'package': DEST + '/' + name})
    if len(rows) != 52:
        raise ValueError('Unexpected source texture inventory')
    return {'recipeSha256': expected, 'textures': rows, 'destination': DEST,
            'sourceRecipe': str(SOURCE), 'sourceApkSha256': APK_SHA,
            'limitations': recipe['limitations'], 'mutatedAssets': False}


def runtime_clip(recipe, name, animation):
    layout = recipe['layouts'][name]
    interval = next(a for a in layout['timeline']['animations'] if a['name'] == animation)
    nodes = []
    indices = {}
    for original in layout['nodes']:
        node = dict(original)
        parents = node.pop('parents')
        node['parent'] = indices[parents[-1]['actionTag']] if parents else -1
        indices[node['action_tag']] = len(nodes)
        limitations = []
        if any(t['action_tag'] == node['action_tag'] and t['property'].startswith('Splendor_')
               for t in layout['timeline']['timelines']):
            limitations.append('source-custom-shader-not-rendered')
        if node.get('blend_func') == [1, 1]:
            limitations.append('source-additive-blend-not-rendered')
        if node['classname'] == 'Particle':
            limitations.append('source-particle-not-rendered')
        node['unsupported'] = limitations
        nodes.append(node)
    return dict(schema='hczs-source-ui-timeline-v1', fps=60,
                speed=layout['timeline']['speed'], startFrame=interval['start'], endFrame=interval['end'],
                easingPolicy='cocos2d-x-3.17.2', nodes=nodes, tracks=layout['timeline']['timelines'])


def run(*, apply=False):
    result = plan()
    if apply is not True:
        return result
    import unreal
    assetlib = unreal.EditorAssetLibrary
    finish = getattr(getattr(unreal, 'AutomationUtilsBlueprintLibrary', None), 'finish_all_asset_compilation', None)
    if not callable(finish):
        raise RuntimeError('AutomationUtils.finish_all_asset_compilation required')
    texture_objects, resumed = {}, []
    # Preflight every existing package before any creation/mutation.
    for row in result['textures']:
        package = row['package']
        if not assetlib.does_asset_exist(package):
            continue
        obj = unreal.load_asset(package)
        if not obj or obj.get_class().get_name() != 'Texture2D':
            raise RuntimeError('Existing non-texture asset retained: ' + package)
        owner = assetlib.get_metadata_tag(obj, 'HczsOwner')
        source_sha = assetlib.get_metadata_tag(obj, 'HczsSourceSHA256')
        if owner not in ('', OWNER) or source_sha not in ('', row['sha256']):
            raise RuntimeError('Existing differently owned/source asset retained: ' + package)
        if not owner or not source_sha:
            import_data = obj.get_editor_property('asset_import_data')
            files = list(import_data.extract_filenames()) if import_data else []
            if len(files) != 1 or Path(files[0]).resolve() != Path(row['png']).resolve():
                raise RuntimeError('Unmarked asset has different import source: ' + package)
            resumed.append(package)
        texture_objects[row['spriteId']] = obj
    for row in result['textures']:
        obj = texture_objects.get(row['spriteId'])
        if obj is None:
            task = unreal.AssetImportTask()
            for key, value in [('filename', row['png']), ('destination_path', DEST),
                               ('destination_name', row['name']), ('automated', True),
                               ('async_', False), ('replace_existing', False), ('save', False)]:
                task.set_editor_property(key, value)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            values = [v for v in task.get_objects() if v.get_class().get_name() == 'Texture2D']
            if len(values) != 1 or values[0].get_path_name().split('.')[0] != row['package']:
                raise RuntimeError('Unexpected source entrance texture import result')
            obj = values[0]
            texture_objects[row['spriteId']] = obj
        for key, value in [('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI),
                           ('compression_settings', unreal.TextureCompressionSettings.TC_EDITOR_ICON),
                           ('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                           ('lod_bias', 0), ('max_texture_size', 0), ('srgb', True),
                           ('filter', unreal.TextureFilter.TF_BILINEAR),
                           ('address_x', unreal.TextureAddress.TA_CLAMP), ('address_y', unreal.TextureAddress.TA_CLAMP)]:
            if obj.get_editor_property(key) != value:
                obj.set_editor_property(key, value)
        assetlib.set_metadata_tag(obj, 'HczsOwner', OWNER)
        assetlib.set_metadata_tag(obj, 'HczsSourceSHA256', row['sha256'])
        assetlib.set_metadata_tag(obj, 'HczsSourceResource', row['sourceResource'])
    finish()
    for row in result['textures']:
        obj = texture_objects[row['spriteId']]
        if [obj.blueprint_get_size_x(), obj.blueprint_get_size_y()] != row['size']:
            raise RuntimeError('Compiled dimensions changed: ' + row['name'])
        if not assetlib.save_loaded_asset(obj, only_if_is_dirty=False):
            raise RuntimeError('Could not save source UI texture: ' + row['name'])
        row['objectPath'] = obj.get_path_name()
    # Separate presentation asset: never overwrite the existing battle HUD.
    recipe = json.loads(SOURCE.read_text('utf8'))
    clips = {name: runtime_clip(recipe, name, animation) for name, animation in
             [('elite', 'In'), ('boss', 'in'), ('hud', 'In')]}
    own_card = json.loads(OWN_CARD_IN.read_text('utf8'))
    if own_card['sourceSha256'] != OWN_CARD_SHA or own_card['clip']['schema'] != 'hczs-source-ui-timeline-v1':
        raise RuntimeError('Prepared OwnCardArea In clip changed; rerun tools/prepare_battle_hud_in.py')
    clips['ownCardAreaIn'] = own_card['clip']
    payload = dict(schema='hczs-source-battle-opening-v1', sourceRecipeSha256=result['recipeSha256'],
                   clips=clips, hudInTrigger=own_card['trigger'],
                   selection=dict(encounterId='tutorial-5000', enemyId='991', difficultyType=1,
                                  branch='elite', source='monster_table991 + CMonster.IsElite + MonsterType.Elite=1'),
                   limitations=recipe['limitations'])
    cls = unreal.load_class(None, '/Script/Hczs.HczsBattlePresentationAsset')
    if not cls: raise RuntimeError('Hczs presentation class unavailable')
    package = DEST + '/BattleEntrancePresentation'
    asset = unreal.load_asset(package) if assetlib.does_asset_exist(package) else None
    if asset:
        if asset.get_class().get_name() != 'HczsBattlePresentationAsset' or assetlib.get_metadata_tag(asset, 'HczsOwner') != OWNER:
            raise RuntimeError('Foreign opening presentation retained')
    else:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class', cls)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('BattleEntrancePresentation', DEST,
                                                                      cls, factory)
    if not asset:
        raise RuntimeError('Opening DataAsset creation failed')
    asset.set_editor_property('LayoutJson', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    asset.set_editor_property('SourceManifestSha256', result['recipeSha256'])
    asset.set_editor_property('Sprites', texture_objects)
    assetlib.set_metadata_tag(asset, 'HczsOwner', OWNER)
    assetlib.set_metadata_tag(asset, 'HczsSourceSHA256', result['recipeSha256'])
    if not assetlib.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Opening DataAsset save failed')
    result['presentationAsset'] = asset.get_path_name()
    result.update(passed=True, mutatedAssets=True, resumedPartialImports=resumed,
                  engine=unreal.SystemLibrary.get_engine_version(),
                  originalApkExecuted=False, runtimeAnimationVerified=False)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    unreal.log('HCZS entrance texture import completed: ' + str(REPORT))
    return result


if __name__ == '__main__':
    value = run()
    print(json.dumps({'passed': True, 'textures': len(value['textures']),
                      'mutatedAssets': value['mutatedAssets'], 'recipeSha256': value['recipeSha256']}))
