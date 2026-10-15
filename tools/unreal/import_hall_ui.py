"""Import verified original hall UI images/fonts and a runtime layout DataAsset.

No existing map, model or user save is edited. Repeated imports reuse only assets
with matching source metadata. Runtime drawing intentionally does not fabricate
original account, unlock, notification or economy state.
"""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'analysis/unreal/hall-ui/layout.json'
DEST = '/Game/Recovered/Hall/UI'
REPORT = ROOT / 'analysis/unreal/hall-ui/import-result.json'
PINNED_LAYOUT = '815367f3f73b4580d88d94e24ec36ea9128b2110f7a8eb4054a54f01f30e643d'


def verified_file(filename, expected):
    path = Path(filename).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Source file outside project')
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('UI source hash changed: '+str(path))
    return path


def import_one(row, kind):
    field, sha_field = ('png','pngSha256') if kind == 'Texture2D' else ('ttf','sha256')
    path = verified_file(row[field], row[sha_field])
    name = ('T_' if kind == 'Texture2D' else 'FF_') + row['id']
    folder = DEST+('/Sprites' if kind == 'Texture2D' else '/Fonts')
    package = folder+'/'+name
    old = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if old:
        if old.get_class().get_name() != kind or unreal.EditorAssetLibrary.get_metadata_tag(old,'HczsSourceSHA256') != row[sha_field]:
            raise RuntimeError('Existing UI asset has different source identity: '+package)
        return old
    task = unreal.AssetImportTask()
    task.set_editor_property('filename', str(path))
    task.set_editor_property('destination_path', folder)
    task.set_editor_property('destination_name', name)
    task.set_editor_property('automated', True)
    task.set_editor_property('replace_existing', False)
    task.set_editor_property('save', False)
    if kind == 'FontFace':
        factory = unreal.FontFileImportFactory()
        factory.set_editor_property('batch_create_font_asset', unreal.BatchCreateFontAsset.NO)
        task.set_editor_property('factory', factory)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects = [o for o in task.get_objects() if o.get_class().get_name() == kind]
    if len(objects) != 1:
        raise RuntimeError('Expected one imported '+kind+': '+str(path))
    obj = objects[0]
    if kind == 'Texture2D':
        obj.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI)
        obj.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        obj.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        obj.set_editor_property('lod_bias', 0)
        obj.set_editor_property('max_texture_size', 0)
        obj.set_editor_property('srgb', True)
        obj.set_editor_property('filter', unreal.TextureFilter.TF_BILINEAR)
        actual = [obj.blueprint_get_size_x(),obj.blueprint_get_size_y()]
        if actual != row['size']:
            raise RuntimeError('Imported image dimensions changed')
    unreal.EditorAssetLibrary.set_metadata_tag(obj, 'HczsSourceSHA256', row[sha_field])
    if not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError('Cannot save imported UI asset')
    return obj


def main():
    if '-run=' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Original FontFace import requires the full Slate editor; use -ExecutePythonScript, not -run=pythonscript')
    raw = INPUT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINNED_LAYOUT:
        raise ValueError('Reviewed layout changed; revalidate source policy first')
    layout = json.loads(raw)
    if layout['schemaVersion'] != 1 or layout['canvas']['drawOrigin'] != 'top-left':
        raise ValueError('Unknown layout convention')
    items = layout['previewDrawItems']
    nodes = {n['id']: n for n in layout['nodes']}
    for item in items:
        item['clipGeometry'] = [nodes[node_id]['clipGeometry'] for node_id in item.get('clipNodeIds', [])]
        for clip in item['clipGeometry']:
            if len(clip.get('corners', [])) != 4:
                raise RuntimeError('Source clip is not a verified quadrilateral')
    sprite_ids = {i['spriteId'] for i in items if i['kind'] == 'sprite'}
    font_ids = {i['fontId'] for i in items if i['kind'] == 'text'}
    sprites = {r['id']:import_one(r,'Texture2D') for r in layout['sprites'] if r['id'] in sprite_ids}
    fonts = {r['id']:import_one(r,'FontFace') for r in layout['fonts'] if r['id'] in font_ids}
    if set(sprites) != sprite_ids or set(fonts) != font_ids:
        raise RuntimeError('Required source resources missing')
    cls = unreal.load_class(None, '/Script/Hczs.HczsHallLayoutAsset')
    if not cls:
        raise RuntimeError('Build HczsEditor before UI import')
    package = DEST+'/HallLayout'
    asset = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if asset:
        if asset.get_editor_property('SourceLayoutSha256') != digest:
            raise RuntimeError('Existing layout retained; source hash differs')
    else:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class',cls)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('HallLayout',DEST,cls,factory)
    if not asset:
        raise RuntimeError('Cannot create layout asset')
    asset.set_editor_property('SourceLayoutSha256',digest)
    asset.set_editor_property('LayoutJson',json.dumps({'schemaVersion':1,'canvas':layout['canvas'],'items':items},ensure_ascii=False))
    asset.set_editor_property('Sprites',sprites)
    asset.set_editor_property('Fonts',fonts)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Cannot save layout DataAsset')
    reloaded = unreal.load_asset(package)
    if len(reloaded.get_editor_property('Sprites')) != len(sprites) or len(reloaded.get_editor_property('Fonts')) != len(fonts):
        raise RuntimeError('Saved asset reference count mismatch')
    result = {'passed':True,'engine':unreal.SystemLibrary.get_engine_version(),'layout_sha256':digest,
              'asset':asset.get_path_name(),'draw_items':len(items),'textures':len(sprites),'font_faces':len(fonts),
              'items_with_panel_clip':sum(bool(i['clipGeometry']) for i in items),
              'source_images':{k:{'asset':v.get_path_name(),'size':[v.blueprint_get_size_x(),v.blueprint_get_size_y()]} for k,v in sprites.items()},
              'layout_scope':'reviewed static-source subset; original runtime state not restored',
              'scale9_policy':'one footer image scaled uniformly; native cap-inset semantics unresolved',
              'material_and_gameplay_verified':False}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    unreal.log('HCZS original UI import saved '+str(REPORT))


if __name__ == '__main__':
    main()
