"""Import preserved APK arrow pixels and a separate UE UI shader adaptation.

Ordinary --validate-only does not launch UE. Full Editor import requires the
explicit -HczsImportTargetArrow flag or main(apply=True) in a connected editor;
no level or existing presentation is changed.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'analysis/battle-ui/target-arrow/manifest.json'
DEST = '/Game/Recovered/Battle/UI/Targeting'
REPORT = ROOT / 'analysis/unreal/battle-ui/target-arrow-import.json'
PINS = {
    'arrowhead': '38069ca08a4e4b1af41c825ae0f72af727e944b52e68793a61205bd4eabd2b2e',
    'arrowflow': '53ffee932f4bc573fe47296067bca2ddceddd12242807a7c22b1ddb7d50fb0d5',
    'arrowbg': 'a7d5f8afd099321a9c68e3008014feda62d10c07aead18d80e89bd121c42ea5b',
}
NAMES = {'arrowhead': 'T_ArrowHead', 'arrowflow': 'T_ArrowFlow', 'arrowbg': 'T_ArrowBackground'}
SIZES = {'arrowhead': [256, 128], 'arrowflow': [64, 512], 'arrowbg': [64, 512]}


def verified_inputs():
    source = json.loads(SOURCE.read_text(encoding='utf8'))
    rows = {}
    for row in source['textures']:
        key = Path(row['source']).stem
        if key not in PINS or key in rows or len(row['outputs']) != 1:
            raise ValueError('Unexpected source arrow input')
        output = row['outputs'][0]
        filename = (ROOT / output['png']).resolve()
        if not filename.is_relative_to(ROOT):
            raise ValueError('Source arrow path is outside the project: ' + key)
        pixels = filename.read_bytes()
        if hashlib.sha256(pixels).hexdigest() != PINS[key]:
            raise ValueError('Original arrow pixels changed: ' + key)
        size = list(struct.unpack('>II', pixels[16:24]))
        if pixels[:8] != b'\x89PNG\r\n\x1a\n' or size != SIZES[key] or size != [output['width'], output['height']]:
            raise ValueError('Original arrow dimensions changed: ' + key)
        packed = (ROOT / row['source']).resolve()
        if not packed.is_relative_to(ROOT) or hashlib.sha256(packed.read_bytes()).hexdigest() != row['source_sha256']:
            raise ValueError('Original ASTC input changed: ' + key)
        rows[key] = {'path': filename, 'sha256': PINS[key], 'size': size,
                     'logicalPath': row['provenance']['logical_path'], 'npkIndex': row['provenance']['index']}
    if set(rows) != set(PINS):
        raise ValueError('Source arrow input is incomplete')
    return rows


def main(*, apply=False):
    rows = verified_inputs()
    if '--validate-only' in sys.argv:
        print(json.dumps({'passed': True, 'textures': len(rows), 'mutatedAssets': False,
                          'sourcePixelHashes': PINS, 'scope': 'Source input validation only; not UE import or rendering'}))
        return
    import unreal
    if apply is not True and '-hczsimporttargetarrow' not in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Full Editor import requires main(apply=True) or explicit -HczsImportTargetArrow')
    finish_compilation = getattr(getattr(unreal, 'AutomationUtilsBlueprintLibrary', None),
                                 'finish_all_asset_compilation', None)
    if not callable(finish_compilation):
        raise RuntimeError('This editor needs AutomationUtils.finish_all_asset_compilation before texture import')
    textures = {}
    resumed_textures = []
    for key, row in rows.items():
        package = DEST + '/' + NAMES[key]
        obj = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
        if obj:
            if obj.get_class().get_name() != 'Texture2D':
                raise RuntimeError('Existing non-texture asset retained: ' + package)
            source_tag = unreal.EditorAssetLibrary.get_metadata_tag(obj, 'HczsSourceSHA256')
            if source_tag and source_tag != row['sha256']:
                raise RuntimeError('Existing asset retained because source differs: ' + package)
            if not source_tag:
                # A failed first import may leave an unsaved Texture2D before metadata
                # was assigned. Resume only its exact hash-verified source file.
                import_data = obj.get_editor_property('asset_import_data')
                filenames = list(import_data.extract_filenames()) if import_data else []
                if len(filenames) != 1 or Path(filenames[0]).resolve() != row['path']:
                    raise RuntimeError('Unmarked existing texture has a different import source: ' + package)
                resumed_textures.append(key)
        else:
            task = unreal.AssetImportTask()
            for name, value in [('filename', str(row['path'])), ('destination_path', DEST),
                                ('destination_name', NAMES[key]), ('automated', True),
                                ('replace_existing', False), ('save', False)]:
                task.set_editor_property(name, value)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            objects = [value for value in task.get_objects() if value.get_class().get_name() == 'Texture2D']
            if len(objects) != 1:
                raise RuntimeError('Arrow texture import failed: ' + key)
            obj = objects[0]
        for name, value in [('lod_group', unreal.TextureGroup.TEXTUREGROUP_UI),
                            ('compression_settings', unreal.TextureCompressionSettings.TC_EDITOR_ICON),
                            ('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                            ('lod_bias', 0), ('max_texture_size', 0), ('srgb', False),
                            ('filter', unreal.TextureFilter.TF_BILINEAR),
                            ('address_x', unreal.TextureAddress.TA_CLAMP), ('address_y', unreal.TextureAddress.TA_CLAMP)]:
            if obj.get_editor_property(name) != value:
                obj.set_editor_property(name, value)
        textures[key] = obj
    # UE 5.8 Texture2D::GetSizeX/Y return placeholder dimensions during async
    # compilation. Drain engine compilation and render commands, never sleep.
    finish_compilation()
    for key, obj in textures.items():
        actual_size = [obj.blueprint_get_size_x(), obj.blueprint_get_size_y()]
        if actual_size != rows[key]['size']:
            raise RuntimeError(f'Compiled source arrow dimensions differ: {key}: {actual_size} != {rows[key]["size"]}')
        unreal.EditorAssetLibrary.set_metadata_tag(obj, 'HczsSourceSHA256', rows[key]['sha256'])
        if not unreal.EditorAssetLibrary.save_loaded_asset(obj, only_if_is_dirty=False):
            raise RuntimeError('Cannot save source arrow texture: ' + key)
    recipe = {'version': 1, 'inputs': PINS, 'flowUV': '(u,frac(v-Time))',
              'color': 'flow*flow.a+background*(1-flow.a)', 'blend': 'UE-UI-additive',
              'originalRuntimeEquivalent': False}
    recipe_sha = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode('utf8')).hexdigest()
    package = DEST + '/M_SourceArrowRibbon'
    material = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if material:
        if material.get_class().get_name() != 'Material' or unreal.EditorAssetLibrary.get_metadata_tag(material, 'HczsRecipeSHA256') != recipe_sha:
            raise RuntimeError('Existing arrow material retained because recipe differs')
    else:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_SourceArrowRibbon', DEST, unreal.Material, unreal.MaterialFactoryNew())
        if not material:
            raise RuntimeError('Cannot create arrow material')
        material.set_editor_property('material_domain', unreal.MaterialDomain.MD_UI)
        material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_ADDITIVE)
        material.set_editor_property('two_sided', True)
        edit = unreal.MaterialEditingLibrary
        def node(cls, x, y):
            return edit.create_material_expression(material, cls, x, y)
        def link(a, output, b, input_name):
            if not edit.connect_material_expressions(a, output, b, input_name):
                raise RuntimeError('Cannot connect source shader expression ' + input_name)
        coord = node(unreal.MaterialExpressionTextureCoordinate, -900, 0)
        u = node(unreal.MaterialExpressionComponentMask, -700, -140)
        u.set_editor_property('r', True); u.set_editor_property('g', False)
        v = node(unreal.MaterialExpressionComponentMask, -700, 20)
        v.set_editor_property('r', False); v.set_editor_property('g', True)
        link(coord, '', u, ''); link(coord, '', v, '')
        time = node(unreal.MaterialExpressionTime, -900, 200)
        sub = node(unreal.MaterialExpressionSubtract, -500, 30)
        link(v, '', sub, 'A'); link(time, '', sub, 'B')
        frac = node(unreal.MaterialExpressionFrac, -340, 30); link(sub, '', frac, '')
        uv = node(unreal.MaterialExpressionAppendVector, -180, -120)
        link(u, '', uv, 'A'); link(frac, '', uv, 'B')
        flow = node(unreal.MaterialExpressionTextureSample, 0, -120)
        flow.set_editor_property('texture', textures['arrowflow'])
        flow.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(uv, '', flow, 'UVs')
        bg = node(unreal.MaterialExpressionTextureSample, 0, 170)
        bg.set_editor_property('texture', textures['arrowbg'])
        bg.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(coord, '', bg, 'UVs')
        color = node(unreal.MaterialExpressionLinearInterpolate, 350, -70)
        alpha = node(unreal.MaterialExpressionLinearInterpolate, 350, 140)
        link(bg, 'RGB', color, 'A'); link(flow, 'RGB', color, 'B'); link(flow, 'A', color, 'Alpha')
        link(bg, 'A', alpha, 'A'); link(flow, 'A', alpha, 'B'); link(flow, 'A', alpha, 'Alpha')
        if not edit.connect_material_property(color, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR) or not edit.connect_material_property(alpha, '', unreal.MaterialProperty.MP_OPACITY):
            raise RuntimeError('Cannot connect source shader outputs')
        errors = edit.recompile_material(material)
        if errors is None or list(errors):
            raise RuntimeError('Arrow material compilation failed: ' + repr(errors))
        unreal.EditorAssetLibrary.set_metadata_tag(material, 'HczsRecipeSHA256', recipe_sha)
        if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
            raise RuntimeError('Cannot save arrow material')
    result = {'passed': True, 'engine': unreal.SystemLibrary.get_engine_version(),
              'recipeSha256': recipe_sha, 'recipe': recipe,
              'resumedPartialTextures': resumed_textures,
              'sourcePixels': {key: {k: v for k, v in row.items() if k != 'path'} for key, row in rows.items()},
              'textures': {key: obj.get_path_name() for key, obj in textures.items()},
              'material': material.get_path_name(), 'originalApkExecuted': False,
              'scope': 'Preserved APK pixels and source PS formula; UE shader/color/blend runtime still requires frame inspection'}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    unreal.log('HCZS source arrow import passed: ' + str(REPORT))
    return result


if __name__ == '__main__':
    main()
