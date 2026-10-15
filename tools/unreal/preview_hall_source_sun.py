"""Single source-directed sun comparison for mobile's one-sun-per-channel path."""
import hashlib
import json
from pathlib import Path
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/unreal/hall-lighting/environment'
SOURCE = '/Game/Recovered/Hall/Maps/L_ElsaHallSourceSHComparisonV2'
TARGET = '/Game/Recovered/Hall/Maps/L_ElsaHallSourceSunComparison'


def main():
    if u.EditorAssetLibrary.does_asset_exist(TARGET):
        raise RuntimeError('Retain existing source sun comparison')
    source_file = ROOT / 'clients/unreal5 5.8/Content' / (SOURCE.removeprefix('/Game/') + '.umap')
    before = hashlib.sha256(source_file.read_bytes()).hexdigest()
    report = json.loads((OUT/'source-inputs.json').read_text('utf8'))
    main = [r for r in report['lights'] if r['attributes'].get('MainLight') == 'true'
            and r['attributes']['Enable'] == 'true']
    if len(main) != 1 or main[0]['attributes']['Type'] != '3' or len(main[0]['diffuseKeys']) != 1:
        raise RuntimeError('Unexpected source sun selection')
    light = main[0]
    x,y,z = [float(v) for v in light['attributes']['Direction'].split(',')]
    direction = u.Vector(x,-z,y)
    direction.normalize()
    colour = [float(v) for v in light['diffuseKeys'][0]['Color'].split(',')]
    if not u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(SOURCE):
        raise RuntimeError('Cannot load source SH map')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    disabled = []
    for actor in actors.get_all_level_actors():
        for component in actor.get_components_by_class(u.DirectionalLightComponent):
            component.set_visibility(False)
            disabled.append(actor.get_actor_label())
    sun = actors.spawn_actor_from_class(u.DirectionalLight,u.Vector(0,0,2000),u.MathLibrary.make_rot_from_x(direction))
    sun.set_actor_label('HCZSSourceSunComparison')
    component = sun.get_component_by_class(u.DirectionalLightComponent)
    component.set_mobility(u.ComponentMobility.MOVABLE)
    component.set_editor_property('intensity',float(light['attributes']['Intensity']))
    component.set_light_color(u.LinearColor(colour[0],colour[1],colour[2],1))
    component.set_editor_property('cast_shadows',True)
    component.set_editor_property('forward_shading_priority',10)
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not u.EditorLoadingAndSavingUtils.save_map(world,TARGET):
        raise RuntimeError('Cannot save sun comparison')
    if hashlib.sha256(source_file.read_bytes()).hexdigest() != before:
        raise RuntimeError('Source map modified')
    (OUT/'source-sun-comparison.json').write_text(json.dumps({
        'map':TARGET,'sourceMapSha256':before,'disabledDirectionalLights':disabled,
        'sourceSun':light,'ueRayDirection':[direction.x,direction.y,direction.z],
        'scope':'Source direction/colour/intensity numbers in UE units; native radiometric equivalence unverified',
        'renderVerified':False,
    },indent=2),'utf8')


if __name__ == '__main__':
    main()
