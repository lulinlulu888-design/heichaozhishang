"""Import ten selected common icon variants; does not add fake UI state."""
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'analysis/assets/ai-icons/common/manifest.json'
PIN = 'deedd9c39d9bb62c6f8ec8a2a75159da3eedf9a34b9253897b3857f697fa3b13'
DEST = '/Game/Recovered/UI/IconLibrary/AI'
REPORT = ROOT / 'analysis/assets/ai-icons/common/ue-import-result.json'

def verified_file(filename, sha):
    path = (ROOT / filename).resolve()
    if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise ValueError('Icon source differs: ' + filename)
    return path

def main():
    import unreal
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise ValueError('Reviewed common icon manifest changed')
    manifest = json.loads(raw)
    if manifest['PNGMutation'] or manifest['runtimeMutation'] or len(manifest['icons']) != 10:
        raise ValueError('Common icon preservation policy differs')
    result = []
    for row in manifest['icons']:
        original = verified_file(row['sourcePNG'], row['sourcePNG_SHA256'])
        filename = verified_file(row['aiPNG'], row['aiPNG_SHA256'])
        raw_png = filename.read_bytes()
        if raw_png[:8] != b'\x89PNG\r\n\x1a\n' or raw_png[24:26] != b'\x08\x06' or list(struct.unpack('>II', raw_png[16:24])) != row['aiSize']:
            raise ValueError('RGBA8 dimensions differ')
        name = 'T_AI_' + row['name'].replace('-', '_') + '_v' + str(row['aiVersion'])
        package = DEST + '/' + name
        metadata = {'HczsSourceSHA256': row['aiPNG_SHA256'], 'HczsOriginalPNG_SHA256': row['sourcePNG_SHA256'],
                    'HczsAIManifestSHA256': PIN, 'HczsAIGenerated': 'true', 'HczsOriginalFrame': row['sourceFrame']}
        policy = {'lod_group': unreal.TextureGroup.TEXTUREGROUP_UI,
                  'compression_settings': unreal.TextureCompressionSettings.TC_EDITOR_ICON,
                  'mip_gen_settings': unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS,
                  'filter': unreal.TextureFilter.TF_BILINEAR, 'srgb': True, 'lod_bias': 0, 'max_texture_size': 512}
        texture = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
        if texture:
            if texture.get_class().get_name() != 'Texture2D' or any(unreal.EditorAssetLibrary.get_metadata_tag(texture, key) != value for key,value in metadata.items()) or any(texture.get_editor_property(key) != value for key,value in policy.items()):
                raise RuntimeError('Existing icon asset retained; identity differs: ' + package)
            action = 'reused'
        else:
            task = unreal.AssetImportTask()
            for key,value in {'filename': str(filename), 'destination_path': DEST, 'destination_name': name,
                              'automated': True, 'replace_existing': False, 'save': False}.items():
                task.set_editor_property(key, value)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            objects = [obj for obj in task.get_objects() if obj.get_class().get_name() == 'Texture2D']
            if len(objects) != 1 or objects[0].get_path_name().split('.')[0] != package:
                raise RuntimeError('Exact icon texture import failed')
            texture = objects[0]
            for key,value in policy.items(): texture.set_editor_property(key, value)
            for key,value in metadata.items(): unreal.EditorAssetLibrary.set_metadata_tag(texture, key, value)
            if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
                raise RuntimeError('Could not save icon texture')
            action = 'imported'
        if hashlib.sha256(original.read_bytes()).hexdigest() != row['sourcePNG_SHA256']:
            raise RuntimeError('Original image changed unexpectedly')
        result.append({'name': row['name'], 'asset': texture.get_path_name(), 'action': action,
                       'sourcePNG_SHA256': row['sourcePNG_SHA256'], 'aiPNG_SHA256': row['aiPNG_SHA256'],
                       'libraryOnly': row['libraryOnly'], 'sourceSize': row['sourceSize'], 'aiPNGSize': row['aiSize'],
                       'platformSize': [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()]})
    REPORT.write_text(json.dumps({'passed': True, 'engine': unreal.SystemLibrary.get_engine_version(), 'manifestSHA256': PIN,
                                  'textures': result, 'originalPixelsModified': False, 'generatedPixelsModified': False,
                                  'libraryOnlyIconsAreNotNewUIState': True},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    unreal.log('HCZS common icon library saved ' + str(REPORT))

if __name__ == '__main__':
    main()
