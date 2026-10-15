"""Import the pinned theatre cube transport into an isolated UE asset namespace.

Does not assign lighting or modify any map. Check native imported dimensions,
format and mip preservation before using this authored probe in a material.
"""
import hashlib
import json
from pathlib import Path
import time
import traceback

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/battle-visual/reflection/boss_theatre'
OUT = ROOT / 'analysis/unreal/battle-reference/source-reflection-import.json'


def run():
    report = json.loads((BASE / 'dds.json').read_text('utf8'))
    source = Path(report['dds'])
    if source.resolve() != BASE / 'reflectionprobe_0.dds' or hashlib.sha256(source.read_bytes()).hexdigest() != report['ddsSha256']:
        raise ValueError('Pinned source DDS changed')
    folder = '/Game/Recovered/SourceStages/Reflection/v_' + report['ddsSha256'][:16]
    path = folder + '/T_TheatreProbe'
    texture = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
    if texture:
        if u.EditorAssetLibrary.get_metadata_tag(texture, 'HczsSourceDDS') != report['ddsSha256']:
            raise RuntimeError('Cube namespace contains unowned data')
    else:
        request = u.AssetImportTask()
        for field, value in dict(filename=str(source), destination_path=folder,
            destination_name='T_TheatreProbe', automated=True, replace_existing=False, save=False).items():
            request.set_editor_property(field, value)
        factory = u.TextureFactory()
        factory.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
        request.set_editor_property('factory', factory)
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([request])
        imported = request.get_objects()
        if len(imported) != 1 or not isinstance(imported[0], u.TextureCube):
            raise RuntimeError('DDS did not import as one TextureCube')
        texture = imported[0]
    texture.set_editor_property('srgb', False)
    texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_HDR)
    texture.set_editor_property('mip_gen_settings', u.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    texture.set_editor_property('never_stream', True)
    u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourceDDS', report['ddsSha256'])
    if not u.EditorAssetLibrary.save_loaded_asset(texture, False):
        raise RuntimeError('Cube asset save failed')
    asset_data = u.AssetRegistryHelpers.create_asset_data(texture)
    tags = {key: str(asset_data.get_tag_value(key)) for key in ('Dimensions', 'Format', 'NumMips')}
    size = texture.blueprint_get_built_texture_size()
    dimensions = [int(size.x), int(size.y), int(size.z)]
    if dimensions != [report['size'], report['size'], 6]:
        raise RuntimeError('Native cube dimensions differ from the source')
    result = dict(asset=texture.get_path_name(), sourceDdsSha256=report['ddsSha256'],
        importedType=texture.get_class().get_name(), srgb=texture.get_editor_property('srgb'),
        mipGenSettings=str(texture.get_editor_property('mip_gen_settings')),
        expectedSourceSize=report['size'], expectedSourceMips=report['mipCount'],
        sourceDdsHashValidated=True, lightingApplied=False,
        builtTextureSize=dimensions, assetRegistryTags=tags, nativeGpuMipCountVerified=False,
        limitation='Asset import only. No map modified; native GPU mip count, orientation and shader equivalence not established.')
    OUT.write_text(json.dumps(result, indent=2), 'utf8')


try:
    previous_error = OUT.with_suffix('.error.txt')
    if previous_error.exists():
        previous_error.rename(OUT.with_name('source-reflection-import.error-' + str(time.time_ns()) + '.txt'))
    if OUT.exists():
        OUT.rename(OUT.with_name('source-reflection-import.previous-' + str(time.time_ns()) + '.json'))
    run()
except Exception:
    OUT.with_suffix('.error.txt').write_text(traceback.format_exc(), 'utf8')
    raise
