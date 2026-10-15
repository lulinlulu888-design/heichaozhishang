"""Import hash-checked original entrance meshes/lancer3 materials, without level edits.

Use run(apply=True) in UE5.8. This does not claim SFX scheduling, direction,
particle emission or original blend/pipeline equivalence.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools/unreal')]
from export_elsa_model import split_glb
from import_recovered_assets import make_pipeline
from repair_battle_visual_materials import node, link, prop, source_colour_emissive

BASE = ROOT / 'analysis/battle-visual/entrance-fx'
DEST = '/Game/Recovered/Battle/Entrance/SourceModels'
OWNER = 'HczsEntranceFxSourceRecipe'
BUILD = 'HczsEntranceFxBuild'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plan():
    files = ['playback-recipe.json', 'sourcepins.json', 'material-inputs.json']
    hashes = {name: sha((BASE / name).read_bytes()) for name in files}
    recipes = {name: json.loads((BASE / name).read_text('utf8')) for name in files}
    pins = recipes['sourcepins.json']
    if pins['apkSha256'] != 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4':
        raise ValueError('Wrong source APK identity')
    for logical, source in pins['sources'].items():
        path = Path(source['sample_path']).resolve()
        if not path.is_relative_to(BASE.resolve()) or sha(path.read_bytes()) != pins['pins'][logical]:
            raise ValueError('Changed source: ' + logical)
    geometry = {m['name']: m for m in recipes['playback-recipe.json']['models']}
    materials = recipes['material-inputs.json']
    if materials['schema'] != 'hczs-elsa-entrance-fx-material-inputs-v1' or len(geometry) != 3:
        raise ValueError('Unexpected entrance closure')
    for row in materials['materials']:
        source = geometry[row['name']]
        glb = Path(row['glb']).resolve()
        if not glb.is_relative_to(BASE.resolve()) or sha(glb.read_bytes()) != source['sha256'] or source['sha256'] != row['glbSha256']:
            raise ValueError('Changed geometry')
        doc, _ = split_glb(glb.read_bytes())
        if doc.get('skins') or len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1:
            raise ValueError('Unexpected geometry structure')
        if not all(v['byteIdentical'] for v in source['verification']):
            raise ValueError('Source array verification failed')
        for tex in row['textures']:
            path = Path(tex['file']).resolve()
            if not path.is_relative_to(BASE.resolve()) or tex['srgb'] or sha(path.read_bytes()) != tex['sha256']:
                raise ValueError('Changed/nonlinear texture handoff')
    return dict(recipeSha256=sha(json.dumps(hashes, sort_keys=True).encode()), sourceHashes=hashes,
                materials=materials['materials'], destination=DEST)


def run(*, apply=False):
    value = plan()
    if not apply:
        return value
    import unreal as u
    if not u.SystemLibrary.get_engine_version().startswith('5.8.') or Path(u.Paths.project_dir()).resolve() != (ROOT / 'clients/unreal5 5.8').resolve():
        raise RuntimeError('Use the Hczs UE5.8 project')
    library = u.EditorAssetLibrary
    identity = value['recipeSha256']

    def owned(asset):
        if not asset or not asset.get_path_name().startswith(DEST + '/') or library.get_metadata_tag(asset, OWNER) != identity:
            raise RuntimeError('Foreign/mismatched asset retained')
        return asset

    def mark(asset):
        library.set_metadata_tag(asset, OWNER, identity)
        return asset

    def save(asset):
        if not library.save_loaded_asset(owned(asset), only_if_is_dirty=False):
            raise RuntimeError('Asset save failed: ' + asset.get_path_name())

    for path in library.list_assets(DEST, True, False):
        owned(u.load_asset(path))
    result = dict(passed=False, recipeSha256=identity, meshes=[], materials=[],
                  mapsChanged=False, originalAssetsChanged=False, sfxPlaybackIntegrated=False,
                  limitations=['UE translucent Unlit/exposure adapter; original render blend not verified',
                               'SFX curve timing, ARGB ordering, TrackType/DirType and particle emission remain unresolved'])
    for row in value['materials']:
        name = row['name']
        mesh_path = DEST + '/SM_' + name
        mesh = owned(u.load_asset(mesh_path)) if library.does_asset_exist(mesh_path) else None
        if not mesh:
            before = set(library.list_assets(DEST, True, False))
            pipeline, overrides = make_pipeline(u, {'import_operation': 'asset'})
            args = u.ImportAssetParameters()
            for key, val in [('is_automated', True), ('replace_existing', False), ('override_pipelines', overrides)]:
                args.set_editor_property(key, val)
            status = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
                DEST, u.InterchangeManager.create_source_data(row['glb']), args)
            if not (status[0] if isinstance(status, tuple) else status):
                raise RuntimeError('Entrance mesh import failed')
            created = [mark(u.load_asset(p)) for p in sorted(set(library.list_assets(DEST, True, False)) - before)]
            meshes = [a for a in created if isinstance(a, u.StaticMesh)]
            if len(meshes) != 1:
                raise RuntimeError('Unexpected imported mesh count')
            for asset in created:
                save(asset)
            mesh = meshes[0]
            if not library.rename_asset(mesh.get_path_name(), mesh_path):
                raise RuntimeError('Entrance mesh rename failed')
        if not isinstance(mesh, u.StaticMesh) or len(mesh.get_editor_property('static_materials')) != 1:
            raise RuntimeError('Mesh type/slot mismatch')
        material_path = DEST + '/M_' + name
        material = owned(u.load_asset(material_path)) if library.does_asset_exist(material_path) else None
        if not material:
            material = mark(u.AssetToolsHelpers.get_asset_tools().create_asset('M_' + name, DEST, u.Material, u.MaterialFactoryNew()))
        textures = {}
        for tex in row['textures']:
            texture_name = 'T_' + name + '_' + tex['name']
            texture_path = DEST + '/' + texture_name
            texture = owned(u.load_asset(texture_path)) if library.does_asset_exist(texture_path) else None
            if not texture:
                task = u.AssetImportTask()
                for key, val in [('filename', tex['file']), ('destination_path', DEST), ('destination_name', texture_name),
                                 ('automated', True), ('replace_existing', False), ('save', False), ('async_', False)]:
                    task.set_editor_property(key, val)
                u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                objects = task.get_objects()
                if len(objects) != 1 or not isinstance(objects[0], u.Texture2D):
                    raise RuntimeError('Entrance texture import failed')
                texture = mark(objects[0])
            for key, val in [('srgb', False), ('compression_settings', u.TextureCompressionSettings.TC_DEFAULT),
                             ('address_x', u.TextureAddress.TA_WRAP), ('address_y', u.TextureAddress.TA_WRAP),
                             ('filter', u.TextureFilter.TF_BILINEAR)]:
                texture.set_editor_property(key, val)
            save(texture)
            textures[tex['input']] = texture
        if library.get_metadata_tag(material, BUILD) != 'complete':
            u.MaterialEditingLibrary.delete_all_material_expressions(material)
            material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
            material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
            material.set_editor_property('two_sided', True)
            expression = node(u, material, u.MaterialExpressionCustom, 0, 0, code=row['code'],
                              output_type=u.CustomMaterialOutputType.CMOT_FLOAT4,
                              description='Original entrance lancer3 single-flow / linear texture inputs')
            custom_inputs = []
            for key in row['inputs']:
                inp = u.CustomInput(); inp.set_editor_property('input_name', key); custom_inputs.append(inp)
            expression.set_editor_property('inputs', custom_inputs)
            uv = node(u, material, u.MaterialExpressionTextureCoordinate, -500, 0, coordinate_index=0)
            link(u, uv, '', expression, 'UV')
            for index, (key, default) in enumerate(row['dynamicDefaults'].items()):
                if key == 'SourceTint':
                    parameter = node(u, material, u.MaterialExpressionVectorParameter, -500, 100,
                                     parameter_name=key, default_value=u.LinearColor(*default, 1))
                    link(u, parameter, 'RGB', expression, key)
                else:
                    parameter = node(u, material, u.MaterialExpressionScalarParameter, -800, 100 + index * 100,
                                     parameter_name=key, default_value=default)
                    link(u, parameter, '', expression, key)
            for index, (key, texture) in enumerate(textures.items()):
                parameter = node(u, material, u.MaterialExpressionTextureObjectParameter, -1100, 400 + index * 100,
                                 parameter_name='Source' + key, texture=texture,
                                 sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                link(u, parameter, '', expression, key)
            rgb = node(u, material, u.MaterialExpressionComponentMask, 200, 0, r=True, g=True, b=True, a=False)
            alpha = node(u, material, u.MaterialExpressionComponentMask, 200, 200, r=False, g=False, b=False, a=True)
            link(u, expression, '', rgb, ''); link(u, expression, '', alpha, '')
            source_colour_emissive(u, material, rgb, '')
            prop(u, alpha, '', u.MaterialProperty.MP_OPACITY)
            errors = u.MaterialEditingLibrary.recompile_material(material)
            if errors is None:
                raise RuntimeError('Entrance shader compiler returned no diagnostic result')
            if errors:
                raise RuntimeError('Entrance shader compilation failed: ' + repr(errors))
            library.set_metadata_tag(material, BUILD, 'complete')
            save(material)
        mesh.set_material(0, material)
        save(mesh)
        result['meshes'].append(mesh.get_path_name())
        result['materials'].append(dict(path=material.get_path_name(), textures=[a.get_path_name() for a in textures.values()],
                                        customCodeSha256=sha(row['code'].encode())))
    u.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
    for row in value['materials']:
        material = owned(u.load_asset(DEST + '/M_' + row['name']))
        for tex in row['textures']:
            texture = owned(u.load_asset(DEST + '/T_' + row['name'] + '_' + tex['name']))
            if texture.get_editor_property('srgb') or [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()] != [tex['width'], tex['height']]:
                raise RuntimeError('Saved texture colour/size readback differs')
        if material.get_editor_property('blend_mode') != u.BlendMode.BLEND_TRANSLUCENT:
            raise RuntimeError('Saved material adapter differs')
    result.update(passed=True, engine=u.SystemLibrary.get_engine_version(), shaderCompilationRequested=True)
    (BASE / 'ue-import.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    u.log('HCZS source entrance model/material import passed')
    return result


def verify_saved():
    """Fresh-process readback, without importing or assigning anything."""
    import unreal as u
    value = plan()
    library = u.EditorAssetLibrary
    records = []
    geometry = {m['name']: m for m in json.loads((BASE / 'playback-recipe.json').read_text('utf8'))['models']}
    for row in value['materials']:
        mesh = u.load_asset(DEST + '/SM_' + row['name'])
        material = u.load_asset(DEST + '/M_' + row['name'])
        for asset in (mesh, material):
            if not asset or library.get_metadata_tag(asset, OWNER) != value['recipeSha256']:
                raise RuntimeError('Saved source ownership mismatch')
        if not isinstance(mesh, u.StaticMesh) or len(mesh.get_editor_property('static_materials')) != 1 or mesh.get_material(0) != material:
            raise RuntimeError('Saved mesh material slot differs')
        if library.get_metadata_tag(material, BUILD) != 'complete':
            raise RuntimeError('Material build incomplete')
        scalars = {str(n) for n in u.MaterialEditingLibrary.get_scalar_parameter_names(material)}
        if scalars != set(row['dynamicDefaults']) - {'SourceTint'}:
            raise RuntimeError('Saved runtime scalar inventory differs')
        for key, expected in row['dynamicDefaults'].items():
            if key == 'SourceTint':
                actual = u.MaterialEditingLibrary.get_material_default_vector_parameter_value(material, key)
                if max(abs(a-b) for a,b in zip((actual.r,actual.g,actual.b), expected)) > 1e-6:
                    raise RuntimeError('Saved raw source tint differs')
            elif abs(u.MaterialEditingLibrary.get_material_default_scalar_parameter_value(material, key) - expected) > 1e-6:
                raise RuntimeError('Saved runtime scalar differs')
        for tex in row['textures']:
            texture = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(material, 'Source' + tex['input'])
            expected = DEST + '/T_' + row['name'] + '_' + tex['name']
            if (not texture or texture.get_path_name().split('.')[0] != expected
                    or library.get_metadata_tag(texture, OWNER) != value['recipeSha256']
                    or texture.get_editor_property('srgb')
                    or [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()] != [tex['width'], tex['height']]):
                raise RuntimeError('Saved original linear sampler binding differs')
        bounds = mesh.get_bounds()
        source_bounds = geometry[row['name']]['sourceBounds']
        origin, extent = bounds.origin, bounds.box_extent
        actual_min = [origin.x-extent.x,origin.y-extent.y,origin.z-extent.z]
        actual_max = [origin.x+extent.x,origin.y+extent.y,origin.z+extent.z]
        expected_min = [source_bounds['min'][i]*100 for i in (0,2,1)]
        expected_max = [source_bounds['max'][i]*100 for i in (0,2,1)]
        if max(abs(a-b) for a,b in zip(actual_min+actual_max,expected_min+expected_max)) > .02:
            raise RuntimeError('Imported source geometry bounds/axis/scale differ')
        records.append(dict(name=row['name'], mesh=mesh.get_path_name(), material=material.get_path_name(),
                            boundsMin=actual_min, boundsMax=actual_max, scalarParameters=sorted(scalars)))
    report = dict(passed=True, mode='fresh-process-saved-entrance-assets-readback',
                  recipeSha256=value['recipeSha256'], records=records,
                  assetsMutated=False, sfxPlaybackIntegrated=False, visibleFrameVerified=False)
    (BASE / 'ue-readback.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    u.log('HCZS saved entrance model/material readback passed')
    return report
