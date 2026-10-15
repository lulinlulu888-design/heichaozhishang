"""Create a separate source-SH comparison map; never replace the playable map.

Uses raw hall sky coefficients through the verified native packer. Runtime
probe mixing and NeoX BRDF parity remain unverified; this is an isolated test.
"""
import hashlib
import json
import sys
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_hall_environment_lighting import build, pack_complete_sh

SOURCE = '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview'
TARGET = '/Game/Recovered/Hall/Maps/L_ElsaHallSourceSHComparisonV2'
DEST = '/Game/Recovered/Elsa/SourceSHComparisonV2'
OUT = ROOT / 'analysis/unreal/hall-lighting/environment'


def main():
    build()
    if unreal.EditorAssetLibrary.does_asset_exist(TARGET):
        raise RuntimeError('Comparison map exists; preserve it instead of overwriting')
    source_file = ROOT / 'clients/unreal5 5.8/Content/Recovered/Hall/Maps/L_ElsaHallFxPreview.umap'
    before = hashlib.sha256(source_file.read_bytes()).hexdigest()
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(SOURCE):
        raise RuntimeError('Cannot load comparison source')
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    hero = next(a for a in actors.get_all_level_actors() if a.get_actor_label() == 'HCZS_elsa')
    component = hero.get_component_by_class(unreal.SkeletalMeshComponent)
    if component.get_num_materials() != 9:
        raise RuntimeError('Unexpected Elsa material slots')
    inputs = json.loads((OUT / 'source-inputs.json').read_text('utf8'))
    packed = pack_complete_sh(inputs['skyBoxSHRaw'])
    editing = unreal.MaterialEditingLibrary
    results = []
    for slot in range(9):
        original = component.get_material(slot)
        if not original.get_path_name().startswith('/Game/Recovered/Elsa/LightingPreview/'):
            raise RuntimeError('Unexpected hero material; retain user changes')
        if original.get_editor_property('shading_model') == unreal.MaterialShadingModel.MSM_UNLIT:
            continue  # Original transparent hair/eye AO overlays.
        path = DEST + '/M_SourceSH_' + str(slot)
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            raise RuntimeError('Existing comparison material retained: ' + path)
        material = unreal.EditorAssetLibrary.duplicate_asset(original.get_path_name(), path)
        expressions = list(editing.get_material_expressions(material))
        sample = next(e for e in expressions if isinstance(e, unreal.MaterialExpressionTextureSampleParameter2D)
                      and str(e.get_editor_property('parameter_name')) == 'OriginalBaseColor')
        tint = next(e for e in expressions if isinstance(e, unreal.MaterialExpressionVectorParameter)
                    and str(e.get_editor_property('parameter_name')) == 'OriginalColourReferenceTint')
        def node(cls, **properties):
            result = editing.create_material_expression(material, cls)
            for key, value in properties.items():
                result.set_editor_property(key, value)
            return result
        def link(a, output, b, name):
            if not editing.connect_material_expressions(a, output, b, name):
                raise RuntimeError('Failed material link ' + name)
        # Inverse of the current scene adapter: UE=(source.x,-source.z,source.y).
        # This is the imported scene convention, not proof of original projection.
        code = 'float3 n = normalize(float3(N.x,N.z,-N.y));\n'
        code += 'float4 a=float4(n,1); float4 b=n.xyzz*n.yzzx;\n'
        code += 'float3 sh=float3(dot(C0,a),dot(C1,a),dot(C2,a));\n'
        code += 'sh+=float3(dot(C3,b),dot(C4,b),dot(C5,b));\n'
        code += 'sh+=C6.rgb*(n.x*n.x-n.y*n.y); return clamp(sh,0.0,10.0);'
        custom = node(unreal.MaterialExpressionCustom, code=code,
                      output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
                      description='Source sky SH comparison; runtime blending not verified')
        names = ['N'] + ['C'+str(i) for i in range(7)]
        custom_inputs = []
        for name in names:
            entry = unreal.CustomInput()
            entry.set_editor_property('input_name', name)
            custom_inputs.append(entry)
        custom.set_editor_property('inputs', custom_inputs)
        normal = node(unreal.MaterialExpressionVertexNormalWS)
        link(normal, '', custom, 'N')
        for i, row in enumerate(packed):
            value = node(unreal.MaterialExpressionVectorParameter, parameter_name='SourceSH'+str(i),
                         default_value=unreal.LinearColor(*row))
            link(value, 'RGBA', custom, 'C'+str(i))
        colour = node(unreal.MaterialExpressionMultiply)
        link(sample, 'RGB', colour, 'A')
        link(tint, 'RGB', colour, 'B')
        ambient = node(unreal.MaterialExpressionMultiply)
        link(colour, '', ambient, 'A')
        link(custom, '', ambient, 'B')
        if not editing.connect_material_property(ambient, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR):
            raise RuntimeError('Failed environment output')
        errors = list(editing.recompile_material(material))
        if errors:
            raise RuntimeError(str(errors))
        unreal.EditorAssetLibrary.set_metadata_tag(material, 'HczsEnvironmentScope', 'Raw sky SH comparison; incomplete NeoX shading')
        if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
            raise RuntimeError('Cannot save comparison material')
        component.set_material(slot, material)
        results.append({'slot': slot, 'original': original.get_path_name(), 'comparison': path})
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, TARGET):
        raise RuntimeError('Cannot save comparison map')
    if hashlib.sha256(source_file.read_bytes()).hexdigest() != before:
        raise RuntimeError('Playable source map changed')
    (OUT / 'ue-comparison.json').write_text(json.dumps({
        'map': TARGET, 'sourceMapHashUnchanged': before, 'materials': results,
        'renderVerified': False, 'originalParityVerified': False,
    }, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
