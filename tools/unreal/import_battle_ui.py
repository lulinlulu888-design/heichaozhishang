"""Import source-verified battle UI textures/font and bind the C++ DataAsset.

Run with the full Unreal Editor -ExecutePythonScript after building HczsEditor.
No level, material, save, APK, or original extraction output is modified.
"""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'analysis/unreal/battle-ui/manifest.json'
DEST = '/Game/Recovered/Battle/UI'
REPORT = ROOT / 'analysis/unreal/battle-ui/import-result.json'
PINNED_MANIFEST = '04dd19e25a8f8842bd9566879d7654dd5ed1de9a6050d540641d45ecc49c0f77'


def verified(filename, digest):
    path = (ROOT / filename.replace('\\', '/')).resolve()
    if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Battle presentation source changed: ' + filename)
    return path


def apply_card_sampling(row, obj):
    """Hand cards are drawn at ~0.3-0.7x their source size and rotated; without
    mips Slate's bilinear sampling skips texels and the edges stair-step."""
    if not row['id'].startswith('card-'):
        return False
    changed = False
    for key, value in [('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE),
                       ('never_stream', True)]:
        if obj.get_editor_property(key) != value:
            obj.set_editor_property(key, value)
            changed = True
    if changed and not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError('Cannot save card texture sampling policy')
    return changed


def import_one(row, kind):
    field, sha_field = ('png', 'pngSha256') if kind == 'Texture2D' else ('ttf', 'sha256')
    filename = verified(row[field], row[sha_field])
    name = ('T_' if kind == 'Texture2D' else 'FF_') + row['id'].replace('-', '_')
    folder = DEST + ('/Sprites' if kind == 'Texture2D' else '/Fonts')
    package = folder + '/' + name
    old = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if old:
        if old.get_class().get_name() != kind or unreal.EditorAssetLibrary.get_metadata_tag(old, 'HczsSourceSHA256') != row[sha_field]:
            raise RuntimeError('Existing asset retained: source differs at ' + package)
        if kind == 'Texture2D':
            apply_card_sampling(row, old)
        return old
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(filename)), ('destination_path', folder),
                       ('destination_name', name), ('automated', True),
                       ('replace_existing', False), ('save', False)]:
        task.set_editor_property(key, value)
    if kind == 'FontFace':
        factory = unreal.FontFileImportFactory()
        factory.set_editor_property('batch_create_font_asset', unreal.BatchCreateFontAsset.NO)
        task.set_editor_property('factory', factory)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects = [obj for obj in task.get_objects() if obj.get_class().get_name() == kind]
    if len(objects) != 1:
        raise RuntimeError('Import did not create exactly one ' + kind)
    obj = objects[0]
    if kind == 'Texture2D':
        for key, value in [('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI),
                           ('compression_settings', unreal.TextureCompressionSettings.TC_EDITOR_ICON),
                           ('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                           ('lod_bias', 0), ('max_texture_size', 0), ('srgb', True),
                           ('filter', unreal.TextureFilter.TF_BILINEAR)]:
            obj.set_editor_property(key, value)
        if [obj.blueprint_get_size_x(), obj.blueprint_get_size_y()] != row['size']:
            raise RuntimeError('Source sprite dimensions changed in import')
        apply_card_sampling(row, obj)
    unreal.EditorAssetLibrary.set_metadata_tag(obj, 'HczsSourceSHA256', row[sha_field])
    if not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError('Cannot save imported battle presentation asset')
    return obj


def main():
    if '-run=' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('FontFace import requires Slate; use full editor -ExecutePythonScript')
    raw = INPUT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINNED_MANIFEST:
        raise ValueError('Reviewed battle presentation manifest changed')
    source = json.loads(raw)
    if source['schemaVersion'] != 1:
        raise ValueError('Unknown battle presentation schema')
    for filename, expected in source['sourcePins'].items():
        verified(filename, expected)
    sprites = {row['id']: import_one(row, 'Texture2D') for row in source['sprites']}
    font = import_one(source['font'], 'FontFace')
    cls = unreal.load_class(None, '/Script/Hczs.HczsBattlePresentationAsset')
    if not cls:
        raise RuntimeError('Build HczsEditor before battle UI import')
    package = DEST + '/BattlePresentation'
    asset = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if not asset:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class', cls)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('BattlePresentation', DEST, cls, factory)
    if not asset:
        raise RuntimeError('Cannot create battle presentation DataAsset')
    asset.set_editor_property('SourceManifestSha256', digest)
    asset.set_editor_property('LayoutJson', json.dumps(source['runtime'], ensure_ascii=False))
    asset.set_editor_property('Sprites', sprites)
    asset.set_editor_property('ChineseFont', font)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Cannot save battle presentation DataAsset')
    reloaded = unreal.load_asset(package)
    if len(reloaded.get_editor_property('Sprites')) != len(sprites) or not reloaded.get_editor_property('ChineseFont'):
        raise RuntimeError('Saved presentation reference readback failed')
    result = {'passed': True, 'engine': unreal.SystemLibrary.get_engine_version(),
              'manifest_sha256': digest, 'asset': asset.get_path_name(),
              'textures': len(sprites), 'font_faces': 1,
              'sprites': {key: obj.get_path_name() for key, obj in sprites.items()},
              'scope': 'Original APK pixels, static card arc, reconstructed UE screen layout; gameplay state comes from Node API'}
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    unreal.log('HCZS battle presentation import passed: ' + str(REPORT))
    if '-unattended' in unreal.SystemLibrary.get_command_line().lower():
        unreal.SystemLibrary.execute_console_command(None, 'QUIT_EDITOR')


if __name__ == '__main__':
    main()
