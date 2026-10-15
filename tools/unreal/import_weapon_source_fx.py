"""Import a new prop1-local weapon overlay and its source lancer2 flow shader.

Run --plan with ordinary Python. In the UE5.8 editor, run(apply=True) writes only
/Game/Recovered/Battle/Weapon/SourceFx. No map, actor, original weapon, camera or
lighting is modified. Owned partial builds can be retried; unrelated assets
are rejected. Source translucency/HDR equivalence remains explicitly unverified.
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

BASE = ROOT / 'analysis/battle-visual/weapon/effect/prop1-local'
DEST = '/Game/Recovered/Battle/Weapon/SourceFx'
PROJECT = ROOT / 'clients/unreal5 5.8/Hczs.uproject'
TAG = 'HczsWeaponSourceFxRecipe'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_plan():
    report = json.loads((BASE / 'report.json').read_text('utf8'))
    if report['schema'] != 'hczs-source-weapon-overlay-v1' or report['passed'] is not True:
        raise ValueError('Source conversion did not pass')
    data = {k: v for k, v in report.items() if k != 'recipeSha256'}
    if sha(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()) != report['recipeSha256']:
        raise ValueError('Source recipe identity changed')
    for path, expected in report['sources'].items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Protected source changed: ' + path)
    glb = Path(report['glb'])
    if not glb.resolve().is_relative_to(BASE.resolve()) or sha(glb.read_bytes()) != report['glbSha256']:
        raise ValueError('Overlay source changed')
    doc, _ = split_glb(glb.read_bytes())
    if len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1 or doc.get('skins'):
        raise ValueError('Unexpected overlay topology')
    for row in report['material']['textures'].values():
        if sha(Path(row['file']).read_bytes()) != row['sha256'] or row['srgb']:
            raise ValueError('Source noise image changed')
    if sha(report['material']['hlsl'].encode()) != report['material']['hlslSha256']:
        raise ValueError('Source shader changed')
    if report['destination'] != {'mesh': DEST + '/SM_WeaponOverlay', 'material': DEST + '/M_WeaponFlow'}:
        raise ValueError('Unexpected destination')
    return report


def owned(u, asset, plan):
    if not asset or not asset.get_path_name().startswith(DEST + '/'):
        raise RuntimeError('Asset escaped the new effect namespace')
    if u.EditorAssetLibrary.get_metadata_tag(asset, TAG) != plan['recipeSha256']:
        raise RuntimeError('Refuse to modify unrelated asset: ' + asset.get_path_name())
    return asset


def mark(u, asset, plan):
    if not asset.get_path_name().startswith(DEST + '/'):
        raise RuntimeError('Importer returned an asset outside SourceFx')
    u.EditorAssetLibrary.set_metadata_tag(asset, TAG, plan['recipeSha256'])


def load_owned(u, path, kind, plan):
    if not u.EditorAssetLibrary.does_asset_exist(path):
        return None
    asset = owned(u, u.load_asset(path), plan)
    if not isinstance(asset, kind):
        raise RuntimeError('Wrong asset class: ' + path)
    return asset


def import_mesh(u, plan):
    path = plan['destination']['mesh']
    existing = load_owned(u, path, u.StaticMesh, plan)
    if existing:
        return existing
    before = set(u.EditorAssetLibrary.list_assets(DEST, True, False))
    pipeline, overrides = make_pipeline(u, {'import_operation': 'asset'})
    params = u.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    params.set_editor_property('replace_existing', False)
    params.set_editor_property('override_pipelines', overrides)
    result = u.InterchangeManager.get_interchange_manager_scripted().import_asset(
        DEST, u.InterchangeManager.create_source_data(plan['glb']), params)
    if not (result[0] if isinstance(result, tuple) else result):
        raise RuntimeError('Interchange rejected original overlay')
    after = set(u.EditorAssetLibrary.list_assets(DEST, True, False))
    objects = [u.load_asset(p) for p in sorted(after - before)]
    meshes = [a for a in objects if isinstance(a, u.StaticMesh)]
    if len(meshes) != 1:
        raise RuntimeError('Expected exactly one imported overlay mesh')
    for asset in objects:
        mark(u, asset, plan)
        if not u.EditorAssetLibrary.save_loaded_asset(asset, False):
            raise RuntimeError('Unable to save owned imported asset')
    mesh = meshes[0]
    if mesh.get_path_name().split('.')[0] != path:
        if u.EditorAssetLibrary.does_asset_exist(path):
            raise RuntimeError('Unexpected overlay destination collision')
        if not u.EditorAssetLibrary.rename_asset(mesh.get_path_name(), path):
            raise RuntimeError('Could not assign the agreed overlay asset name')
        mesh = u.load_asset(path)
    owned(u, mesh, plan)
    if len(mesh.get_editor_property('static_materials')) != 1:
        raise RuntimeError('Overlay material slot count differs from source')
    return mesh


def import_texture(u, plan, name, row):
    path = DEST + '/T_Weapon' + name
    texture = load_owned(u, path, u.Texture2D, plan)
    if texture is None:
        task = u.AssetImportTask()
        for key, value in {'filename': row['file'], 'destination_path': DEST,
                           'destination_name': 'T_Weapon' + name, 'automated': True,
                           'replace_existing': False, 'save': False}.items():
            task.set_editor_property(key, value)
        task.set_editor_property('async_', False)
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        objects = task.get_objects()
        if len(objects) != 1 or not isinstance(objects[0], u.Texture2D):
            raise RuntimeError('Expected one imported source noise texture')
        texture = objects[0]
        mark(u, texture, plan)
        if texture.get_path_name().split('.')[0] != path:
            if u.EditorAssetLibrary.does_asset_exist(path) or not u.EditorAssetLibrary.rename_asset(texture.get_path_name(), path):
                raise RuntimeError('Could not assign source noise texture name')
            texture = u.load_asset(path)
    # UE normal-map detection must not reinterpret the coloured/noise inputs.
    texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_DEFAULT)
    texture.set_editor_property('compression_no_alpha', False)
    texture.set_editor_property('virtual_texture_streaming', False)
    texture.set_editor_property('address_x', u.TextureAddress.TA_WRAP)
    texture.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
    texture.set_editor_property('filter', u.TextureFilter.TF_BILINEAR)
    texture.set_editor_property('srgb', False)  # Last: compression can reset this.
    if hasattr(texture, 'post_edit_change'):
        texture.post_edit_change()
    if texture.get_editor_property('srgb') or texture.get_editor_property('compression_settings') != u.TextureCompressionSettings.TC_DEFAULT:
        raise RuntimeError('Texture colour-space readback failed')
    u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourcePNG_SHA256', row['sha256'])
    if not u.EditorAssetLibrary.save_loaded_asset(texture, False):
        raise RuntimeError('Could not save new source texture')
    return texture


def material(u, plan, textures):
    path = plan['destination']['material']
    asset = load_owned(u, path, u.Material, plan)
    if asset is None:
        asset = u.AssetToolsHelpers.get_asset_tools().create_asset('M_WeaponFlow', DEST, u.Material, u.MaterialFactoryNew())
        if not asset:
            raise RuntimeError('Could not create source weapon material')
        mark(u, asset, plan)
    if u.EditorAssetLibrary.get_metadata_tag(asset, 'HczsWeaponBuildState') == 'complete':
        return asset
    u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsWeaponBuildState', 'building')
    u.MaterialEditingLibrary.delete_all_material_expressions(asset)
    asset.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    asset.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided', True)
    custom = node(u, asset, u.MaterialExpressionCustom, -150, 0,
                  code=plan['material']['hlsl'], output_type=u.CustomMaterialOutputType.CMOT_FLOAT4,
                  description='Original lancer2 SIMPLE colour and panner; UE translucency adapter')
    inputs = []
    for name in ('UV', 'EffectTime', 'Distortion', 'Flow'):
        entry = u.CustomInput()
        entry.set_editor_property('input_name', name)
        inputs.append(entry)
    custom.set_editor_property('inputs', inputs)
    uv = node(u, asset, u.MaterialExpressionTextureCoordinate, -650, -300, coordinate_index=0)
    clock = node(u, asset, u.MaterialExpressionScalarParameter, -650, -150,
                 parameter_name='EffectTime', default_value=0.0)
    link(u, uv, '', custom, 'UV')
    link(u, clock, '', custom, 'EffectTime')
    for i, name in enumerate(('Distortion', 'Flow')):
        tex = node(u, asset, u.MaterialExpressionTextureObjectParameter, -650, 150 * i,
                   parameter_name='Source' + name, texture=textures[name],
                   sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(u, tex, '', custom, name)
    rgb = node(u, asset, u.MaterialExpressionComponentMask, 120, -100, r=True, g=True, b=True, a=False)
    alpha = node(u, asset, u.MaterialExpressionComponentMask, 120, 150, r=False, g=False, b=False, a=True)
    link(u, custom, '', rgb, '')
    link(u, custom, '', alpha, '')
    source_colour_emissive(u, asset, rgb, '')
    prop(u, alpha, '', u.MaterialProperty.MP_OPACITY)
    errors = u.MaterialEditingLibrary.recompile_material(asset)
    if errors is None or list(errors):
        raise RuntimeError('Material compile diagnostics failed: ' + repr(errors))
    u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsWeaponHlslSHA256', plan['material']['hlslSha256'])
    u.EditorAssetLibrary.set_metadata_tag(asset, 'HczsWeaponBuildState', 'complete')
    if not u.EditorAssetLibrary.save_loaded_asset(asset, False):
        raise RuntimeError('Could not save new weapon material')
    return asset


def verify(u, plan):
    mesh = load_owned(u, plan['destination']['mesh'], u.StaticMesh, plan)
    mat = load_owned(u, plan['destination']['material'], u.Material, plan)
    if not mesh or not mat or len(mesh.get_editor_property('static_materials')) != 1:
        raise RuntimeError('Missing new overlay/material assets')
    if mesh.get_material(0) != mat:
        raise RuntimeError('Overlay is not assigned the new source material')
    if u.EditorAssetLibrary.get_metadata_tag(mat, 'HczsWeaponHlslSHA256') != plan['material']['hlslSha256']:
        raise RuntimeError('Shader ownership readback changed')
    if mat.get_editor_property('blend_mode') != u.BlendMode.BLEND_TRANSLUCENT:
        raise RuntimeError('Source alpha adapter changed')
    if 'EffectTime' not in [str(n) for n in u.MaterialEditingLibrary.get_scalar_parameter_names(mat)]:
        raise RuntimeError('Runtime EffectTime parameter missing')
    for name, row in plan['material']['textures'].items():
        tex = u.MaterialEditingLibrary.get_material_default_texture_parameter_value(mat, 'Source' + name)
        owned(u, tex, plan)
        if tex.get_editor_property('srgb') or u.EditorAssetLibrary.get_metadata_tag(tex, 'HczsSourcePNG_SHA256') != row['sha256']:
            raise RuntimeError('Incorrect source texture or implicit sRGB conversion')
    return {'mesh': mesh.get_path_name(), 'material': mat.get_path_name(), 'materialSlots': 1,
            'effectTimeParameter': 'EffectTime', 'nativeBlendEqualityVerified': False,
            'attachedToBattle': False, 'visibleFrameVerified': False}


def run(apply=False):
    import unreal as u
    plan = build_plan()
    result = {'passed': False, 'applied': apply, 'recipeSha256': plan['recipeSha256']}
    try:
        if Path(u.Paths.get_project_file_path()).resolve() != PROJECT.resolve() or not u.SystemLibrary.get_engine_version().startswith('5.8.'):
            raise RuntimeError('Use this project in UE5.8')
        # Check all pre-existing SourceFx objects before any mutations.
        for path in u.EditorAssetLibrary.list_assets(DEST, True, False):
            owned(u, u.load_asset(path), plan)
        if apply:
            mesh = import_mesh(u, plan)
            textures = {name: import_texture(u, plan, name, row) for name, row in plan['material']['textures'].items()}
            mat = material(u, plan, textures)
            mesh.set_material(0, mat)
            if not u.EditorAssetLibrary.save_loaded_asset(mesh, False):
                raise RuntimeError('Could not save the new overlay mesh')
        result.update(verify(u, plan), passed=True, cameraChanged=False, mapChanged=False, originalWeaponChanged=False)
        return result
    except Exception:
        result['error'] = traceback.format_exc()
        raise
    finally:
        (BASE / ('ue-import.json' if apply else 'ue-readback.json')).write_text(json.dumps(result, indent=2) + '\n', 'utf8')


if __name__ == '__main__':
    if '--plan' in sys.argv:
        p = build_plan()
        print(json.dumps({k: p[k] for k in ('glb', 'glbSha256', 'destination', 'geometry', 'ueAttachment')}, indent=2))
    else:
        import unreal
        print(json.dumps(run(apply='-HczsWeaponSourceFxApply' in unreal.SystemLibrary.get_command_line())))
