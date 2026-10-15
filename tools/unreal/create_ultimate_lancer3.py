"""Build source-derived moon-blade materials in an isolated namespace."""
import hashlib
import json
from pathlib import Path
import sys
import traceback
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from repair_battle_visual_materials import node, link, prop, create_material, save_material
BASE = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'
DEST = '/Game/Recovered/Battle/ElsaUltimateEffects/MaterialsDynamic'


def main():
    import unreal as u
    raw = (BASE / 'lancer3-recipe.json').read_bytes()
    recipe = json.loads(raw)
    plan = {'destination': DEST, 'recipe_sha256': hashlib.sha256(raw).hexdigest()}
    apply = '-HczsUltimateMaterialsApply' in u.SystemLibrary.get_command_line()
    results = []
    for row in recipe['materials']:
        name = 'M_' + Path(row['gim']).stem
        if not apply:
            material = u.load_asset(DEST + '/' + name)
            if not material or u.EditorAssetLibrary.get_metadata_tag(material, 'HczsBattleVisualRecipeSHA256') != plan['recipe_sha256'] or u.EditorAssetLibrary.get_metadata_tag(material, 'HczsBattleVisualBuildState') != 'complete':
                raise ValueError('Saved material recipe mismatch')
        else:
            material, build = create_material(u, plan, name, 'BLEND')
            if build:
                expression = node(u, material, u.MaterialExpressionCustom, 0, 0, code=row['code'],
                                  output_type=u.CustomMaterialOutputType.CMOT_FLOAT4, description='APK lancer3 dissolve-only branch')
                names = ['UV', 'Time', 'SourceAlpha', 'Color', 'Noise', 'Dissolve', 'SourceTint', 'SourceDissolve', 'SourceStrength']
                inputs = []
                for pin in names:
                    inp = u.CustomInput(); inp.set_editor_property('input_name', pin); inputs.append(inp)
                expression.set_editor_property('inputs', inputs)
                uv = node(u, material, u.MaterialExpressionTextureCoordinate, -700, 0, coordinate_index=0)
                time = node(u, material, u.MaterialExpressionScalarParameter, -700, 100, parameter_name='EffectTime', default_value=0)
                alpha = node(u, material, u.MaterialExpressionScalarParameter, -700, 200, parameter_name='SourceAlpha', default_value=1)
                for source, pin in [(uv, 'UV'), (time, 'Time'), (alpha, 'SourceAlpha')]: link(u, source, '', expression, pin)
                defaults = row['dynamicDefaults']
                tint = node(u, material, u.MaterialExpressionVectorParameter, -1000, 100,
                            parameter_name='SourceTint', default_value=u.LinearColor(*defaults['SourceTint'], 1))
                link(u, tint, 'RGB', expression, 'SourceTint')
                for pin in ('SourceDissolve', 'SourceStrength'):
                    value = node(u, material, u.MaterialExpressionScalarParameter, -1000, 250,
                                 parameter_name=pin, default_value=defaults[pin])
                    link(u, value, '', expression, pin)
                for index, tex in enumerate(row['textures']):
                    if hashlib.sha256(Path(tex['png']).read_bytes()).hexdigest() != tex['sha256']:
                        raise ValueError('Decoded source texture changed')
                    texture_name = 'T_' + name[2:] + '_' + tex['input']
                    path = DEST + '/' + texture_name
                    if u.EditorAssetLibrary.does_asset_exist(path):
                        texture = u.load_asset(path)
                        if u.EditorAssetLibrary.get_metadata_tag(texture, 'HczsSourcePNG') != tex['sha256']:
                            raise ValueError('Refuse unrelated texture overwrite')
                    else:
                        task = u.AssetImportTask()
                        for key, value in {'filename': tex['png'], 'destination_path': DEST, 'destination_name': texture_name,
                                           'automated': True, 'replace_existing': False, 'save': False}.items(): task.set_editor_property(key, value)
                        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                        objects = task.get_objects()
                        if len(objects) != 1 or not isinstance(objects[0], u.Texture2D): raise ValueError('Texture import failed')
                        texture = objects[0]
                        u.EditorAssetLibrary.set_metadata_tag(texture, 'HczsSourcePNG', tex['sha256'])
                    texture.set_editor_property('srgb', tex['srgb'])
                    texture.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_DEFAULT)
                    if not u.EditorAssetLibrary.save_loaded_asset(texture, False): raise ValueError('Texture save failed')
                    sample = node(u, material, u.MaterialExpressionTextureObjectParameter, -700, 400 + index * 150,
                                  parameter_name='Source' + tex['input'], texture=texture,
                                  sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR if tex['srgb'] else u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                    link(u, sample, '', expression, tex['input'])
                rgb = node(u, material, u.MaterialExpressionComponentMask, 250, 0, r=True, g=True, b=True, a=False)
                opacity = node(u, material, u.MaterialExpressionComponentMask, 250, 200, r=False, g=False, b=False, a=True)
                link(u, expression, '', rgb, ''); link(u, expression, '', opacity, '')
                prop(u, rgb, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
                prop(u, opacity, '', u.MaterialProperty.MP_OPACITY)
                save_material(u, material, plan)
        results.append({'source': row['gim'], 'material': material.get_path_name()})
    return {'passed': True, 'applied': apply, 'materials': results, 'visualVerified': False, 'effectPlaybackIntegrated': False}


if __name__ == '__main__':
    import unreal
    apply = '-HczsUltimateMaterialsApply' in unreal.SystemLibrary.get_command_line()
    out = BASE / ('ue-materials.json' if apply else 'ue-materials-readback.json')
    try: result = main()
    except Exception:
        out.write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}, indent=2), 'utf8'); raise
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(result))
