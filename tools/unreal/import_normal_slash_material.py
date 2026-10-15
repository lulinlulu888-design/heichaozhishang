"""Import the source luminous normal-slash model and shader, without a scene edit.

Ordinary Python --plan validates the frozen offline handoff. UE5.8 run(apply=True)
creates only owned /Game/Recovered/Battle/NormalSlash assets. Refraction, sprites,
SFX scheduling/placement are deliberately not implemented by this material tool.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tools/unreal')]
from export_elsa_model import split_glb
from import_recovered_assets import make_pipeline
from repair_battle_visual_materials import node, link, prop, source_colour_emissive

BASE = ROOT / 'analysis/battle-visual/normal-slash/material-inputs'
DEST = '/Game/Recovered/Battle/NormalSlash'
PROJECT = ROOT / 'clients/unreal5 5.8/Hczs.uproject'
TAG = 'HczsNormalSlashRecipe'
BUILD_TAG = 'HczsNormalSlashBuildState'
TEXTURE_NAMES = {name: 'T_NormalSlash' + name for name in ('Flow1', 'Flow2', 'Distortion', 'Dissolve')}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_plan():
    plan = json.loads((BASE / 'report.json').read_text('utf8'))
    unsigned = {k: v for k, v in plan.items() if k != 'recipeSha256'}
    if (plan['schema'] != 'hczs-normal-slash-material-v1' or plan['passed'] is not True
            or sha(json.dumps(unsigned, sort_keys=True, separators=(',', ':')).encode()) != plan['recipeSha256']):
        raise ValueError('Source handoff identity invalid')
    for path, expected in plan['sources'].items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Pinned source changed: ' + path)
    if sha(Path(plan['playbackRecipe']).read_bytes()) != plan['playbackRecipeSha256']:
        raise ValueError('Source SFX recipe changed')
    path = Path(plan['glb']).resolve()
    if not path.is_relative_to(BASE.resolve()) or sha(path.read_bytes()) != plan['glbSha256']:
        raise ValueError('Prepared geometry changed')
    doc, _ = split_glb(path.read_bytes())
    if len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1 or doc.get('skins'):
        raise ValueError('Unexpected geometry inventory')
    for row in plan['material']['textures'].values():
        if sha(Path(row['file']).read_bytes()) != row['sha256'] or row['srgb']:
            raise ValueError('Source texture handoff changed')
    if sha(plan['material']['hlsl'].encode()) != plan['material']['hlslSha256']:
        raise ValueError('Source shader handoff changed')
    if plan['destination'] != {'mesh': DEST + '/SM_NormalSlashLuminous', 'material': DEST + '/M_NormalSlashLuminous'}:
        raise ValueError('Unexpected new asset destination')
    return plan


class OwnedAssets:
    def __init__(self, u, plan):
        self.u, self.plan = u, plan

    def assert_owned(self, asset):
        u = self.u
        if (not asset or not asset.get_path_name().startswith(DEST + '/')
                or u.EditorAssetLibrary.get_metadata_tag(asset, TAG) != self.plan['recipeSha256']):
            raise RuntimeError('Refuse unrelated/missing normal-slash asset: ' + str(asset))
        return asset

    def mark(self, asset):
        if not asset or not asset.get_path_name().startswith(DEST + '/'):
            raise RuntimeError('Importer escaped the isolated normal-slash namespace')
        self.u.EditorAssetLibrary.set_metadata_tag(asset, TAG, self.plan['recipeSha256'])
        return asset

    def load(self, path, cls):
        if not self.u.EditorAssetLibrary.does_asset_exist(path):
            return None
        asset = self.assert_owned(self.u.load_asset(path))
        if not isinstance(asset, cls):
            raise RuntimeError('Wrong asset type: ' + path)
        return asset

    def save(self, asset):
        self.assert_owned(asset)
        if not self.u.EditorAssetLibrary.save_loaded_asset(asset, False):
            raise RuntimeError('Could not save owned asset: ' + asset.get_path_name())

    def rename(self, asset, path):
        if asset.get_path_name().split('.')[0] == path:
            return asset
        if self.u.EditorAssetLibrary.does_asset_exist(path):
            raise RuntimeError('New asset name collision: ' + path)
        if not self.u.EditorAssetLibrary.rename_asset(asset.get_path_name(), path):
            raise RuntimeError('Unable to rename new source asset: ' + path)
        return self.assert_owned(self.u.load_asset(path))

    def mesh(self):
        u, plan = self.u, self.plan
        path = plan['destination']['mesh']
        mesh = self.load(path, u.StaticMesh)
        if mesh:
            return mesh
        before = set(u.EditorAssetLibrary.list_assets(DEST, True, False))
        pipeline, overrides = make_pipeline(u, {'import_operation': 'asset'})
        params = u.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', False)
        params.set_editor_property('override_pipelines', overrides)
        status = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
            DEST, u.InterchangeManager.create_source_data(plan['glb']), params)
        if not (status[0] if isinstance(status, tuple) else status):
            raise RuntimeError('Source normal-slash mesh import rejected')
        paths = set(u.EditorAssetLibrary.list_assets(DEST, True, False)) - before
        objects = [u.load_asset(p) for p in sorted(paths)]
        meshes = [a for a in objects if isinstance(a, u.StaticMesh)]
        if len(meshes) != 1:
            raise RuntimeError('Expected one original luminous model')
        for asset in objects:
            self.save(self.mark(asset))
        mesh = self.rename(meshes[0], path)
        if len(mesh.get_editor_property('static_materials')) != 1:
            raise RuntimeError('Source material partition changed')
        return mesh

    def texture(self, name, row):
        u = self.u
        path = DEST + '/' + TEXTURE_NAMES[name]
        texture = self.load(path, u.Texture2D)
        if texture is None:
            task = u.AssetImportTask()
            for key, value in {'filename': row['file'], 'destination_path': DEST,
                               'destination_name': TEXTURE_NAMES[name], 'automated': True,
                               'replace_existing': False, 'save': False, 'async_': False}.items():
                task.set_editor_property(key, value)
            u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            objects = task.get_objects()
            if len(objects) != 1 or not isinstance(objects[0], u.Texture2D):
                raise RuntimeError('Expected one original slash texture: ' + name)
            texture = self.rename(self.mark(objects[0]), path)
        texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_DEFAULT)
        texture.set_editor_property('compression_no_alpha', False)
        texture.set_editor_property('virtual_texture_streaming', False)
        texture.set_editor_property('address_x', u.TextureAddress.TA_WRAP)
        texture.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
        texture.set_editor_property('filter', u.TextureFilter.TF_BILINEAR)
        texture.set_editor_property('srgb', False)
        if hasattr(texture, 'post_edit_change'):
            texture.post_edit_change()
        if texture.get_editor_property('srgb') or texture.get_editor_property('compression_settings') != u.TextureCompressionSettings.TC_DEFAULT:
            raise RuntimeError('Texture implicit colour conversion remains active')
        u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsNormalSlashPNG', row['sha256'])
        self.save(texture)
        return texture


def build_material(io, textures):
    u, plan = io.u, io.plan
    asset = io.load(plan['destination']['material'], u.Material)
    if asset is None:
        asset = io.mark(u.AssetToolsHelpers.get_asset_tools().create_asset(
            'M_NormalSlashLuminous', DEST, u.Material, u.MaterialFactoryNew()))
    if u.EditorAssetLibrary.get_metadata_tag(asset, BUILD_TAG) == 'complete':
        return asset
    u.EditorAssetLibrary.set_metadata_tag(asset, BUILD_TAG, 'building')
    u.MaterialEditingLibrary.delete_all_material_expressions(asset)
    asset.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    asset.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', True)
    expression = node(u, asset, u.MaterialExpressionCustom, 0, 0,
        code=plan['material']['hlsl'], output_type=u.CustomMaterialOutputType.CMOT_FLOAT4,
        description='Source lancer2 TWO_FLOAT+DISSOLVE_EFFECT/SIMPLE; no bloom_factor main colour gain')
    names = ['UV'] + list(plan['material']['scalars']) + list(plan['material']['vectors']) + list(textures)
    inputs = []
    for name in names:
        value = u.CustomInput()
        value.set_editor_property('input_name', name)
        inputs.append(value)
    expression.set_editor_property('inputs', inputs)
    uv = node(u, asset, u.MaterialExpressionTextureCoordinate, -500, -400, coordinate_index=0)
    link(u, uv, '', expression, 'UV')
    for i, (name, default) in enumerate(plan['material']['scalars'].items()):
        value = node(u, asset, u.MaterialExpressionScalarParameter, -800, -250 + i * 100,
                     parameter_name=name, default_value=float(default))
        link(u, value, '', expression, name)
    for i, (name, default) in enumerate(plan['material']['vectors'].items()):
        value = node(u, asset, u.MaterialExpressionVectorParameter, -800, 200 + i * 130,
                     parameter_name=name, default_value=u.LinearColor(*default))
        link(u, value, 'RGB', expression, name)
    for i, (name, texture) in enumerate(textures.items()):
        value = node(u, asset, u.MaterialExpressionTextureObjectParameter, -1200, i * 150,
                     parameter_name='SourceTexture' + name, texture=texture,
                     sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(u, value, '', expression, name)
    rgb = node(u, asset, u.MaterialExpressionComponentMask, 200, -100, r=True, g=True, b=True, a=False)
    alpha = node(u, asset, u.MaterialExpressionComponentMask, 200, 150, r=False, g=False, b=False, a=True)
    link(u, expression, '', rgb, '')
    link(u, expression, '', alpha, '')
    source_colour_emissive(u, asset, rgb, '')
    prop(u, alpha, '', u.MaterialProperty.MP_OPACITY)
    errors = u.MaterialEditingLibrary.recompile_material(asset)
    if errors is None or list(errors):
        raise RuntimeError('Normal-slash source shader compile failed: ' + repr(errors))
    u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsNormalSlashHLSL', plan['material']['hlslSha256'])
    u.EditorAssetLibrary.set_metadata_tag(asset, BUILD_TAG, 'complete')
    io.save(asset)
    return asset


def verify(io):
    u, plan = io.u, io.plan
    mesh = io.load(plan['destination']['mesh'], u.StaticMesh)
    material = io.load(plan['destination']['material'], u.Material)
    if not mesh or not material or len(mesh.get_editor_property('static_materials')) != 1 or mesh.get_material(0) != material:
        raise RuntimeError('Expected original mesh and derived material assignment')
    if u.EditorAssetLibrary.get_metadata_tag(material, 'HczsNormalSlashHLSL') != plan['material']['hlslSha256']:
        raise RuntimeError('Derived shader recipe mismatch')
    if material.get_editor_property('blend_mode') != u.BlendMode.BLEND_TRANSLUCENT:
        raise RuntimeError('Unexpected source alpha adaptation')
    scalar_names = {str(n) for n in u.MaterialEditingLibrary.get_scalar_parameter_names(material)}
    if scalar_names != set(plan['material']['scalars']):
        raise RuntimeError('Runtime scalar parameters incomplete')
    for name, expected in plan['material']['scalars'].items():
        value = u.MaterialEditingLibrary.get_material_default_scalar_parameter_value(material, name)
        if abs(value - expected) > 1e-6:
            raise RuntimeError('Runtime scalar default changed: ' + name)
    for name, expected in plan['material']['vectors'].items():
        value = u.MaterialEditingLibrary.get_material_default_vector_parameter_value(material, name)
        if max(abs(a - b) for a, b in zip((value.r, value.g, value.b, value.a), expected)) > 1e-6:
            raise RuntimeError('Source raw colour default changed: ' + name)
    for name, row in plan['material']['textures'].items():
        texture = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(material, 'SourceTexture' + name)
        io.assert_owned(texture)
        if texture.get_editor_property('srgb') or u.EditorAssetLibrary.get_metadata_tag(texture, 'HczsNormalSlashPNG') != row['sha256']:
            raise RuntimeError('Wrong source texture or duplicate sRGB conversion')
    return {'mesh': mesh.get_path_name(), 'material': material.get_path_name(),
            'scalars': plan['material']['scalars'], 'vectors': plan['material']['vectors'],
            'separateUnimplementedLayers': plan['separateUnimplementedLayers'],
            'attachedToBattle': False, 'visibleFrameVerified': False}


def run(apply=False):
    import unreal as u
    plan = build_plan()
    report = {'passed': False, 'applied': apply, 'recipeSha256': plan['recipeSha256']}
    try:
        if Path(u.Paths.get_project_file_path()).resolve() != PROJECT.resolve() or not u.SystemLibrary.get_engine_version().startswith('5.8.'):
            raise RuntimeError('Use this project in UE5.8')
        io = OwnedAssets(u, plan)
        for path in u.EditorAssetLibrary.list_assets(DEST, True, False):
            io.assert_owned(u.load_asset(path))
        if apply:
            mesh = io.mesh()
            textures = {name: io.texture(name, row) for name, row in plan['material']['textures'].items()}
            material = build_material(io, textures)
            mesh.set_material(0, material)
            io.save(mesh)
        report.update(verify(io), passed=True, cameraChanged=False, mapChanged=False, existingAssetsChanged=False)
        return report
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (BASE / ('ue-import.json' if apply else 'ue-readback.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf8')


if __name__ == '__main__':
    if '--plan' in sys.argv:
        plan = build_plan()
        print(json.dumps({k: plan[k] for k in ('glb', 'glbSha256', 'destination')}
                         | {'textures': len(plan['material']['textures']), 'scalars': plan['material']['scalars'],
                            'unimplementedLayers': len(plan['separateUnimplementedLayers'])}, indent=2))
    else:
        import unreal
        print(json.dumps(run(apply='-HczsNormalSlashApply' in unreal.SystemLibrary.get_command_line())))
