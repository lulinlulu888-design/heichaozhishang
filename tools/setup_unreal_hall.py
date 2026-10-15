"""Create a recoverable UE inspection map using only imported APK assets.

Keeps L_RecoveredHall intact; this placement is a reconstruction preview,
not a claim that original camera projection or NeoX materials are restored.
"""
import json
import math
import os
import sys
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[1]
BASE = "/Game/Recovered/Hall/Maps/L_RecoveredHall"
HERO = os.environ.get("HCZS_UE_HALL_HERO", "elsa")
SPECS = {
    "elsa": {"character_id":1, "entity_id":0, "parts":["elsa"],
             "map":"/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview", "report":"hall-elsa-aligned-preview.json",
             "folders":{"elsa":"/Game/Recovered/Elsa"}},
    "shiranui": {"character_id":33, "entity_id":71, "parts":["shiranui","shiranui_weapon"],
                 "map":"/Game/Recovered/Hall/Maps/L_ShiranuiHallPreview", "report":"hall-preview-final.json",
                 "folders":{"shiranui":"/Game/Recovered/Shiranui/shiranui",
                            "shiranui_weapon":"/Game/Recovered/Shiranui/shiranui_weapon"}},
}
if HERO not in SPECS:
    raise ValueError("Unsupported verified hall character")
SPEC = SPECS[HERO]
TARGET = SPEC["map"]
REPORT = ROOT / "analysis/unreal/plan" / SPEC["report"]

def main():
    if unreal.EditorAssetLibrary.does_asset_exist(TARGET):
        raise RuntimeError("Preview map already exists; retain it rather than overwrite edits")
    if not unreal.EditorAssetLibrary.duplicate_asset(BASE, TARGET):
        raise RuntimeError("Cannot duplicate recovered map")
    world = unreal.EditorLoadingAndSavingUtils.load_map(TARGET)
    if not world:
        raise RuntimeError("Cannot load preview map")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    sys.path.insert(0, str(ROOT / "tools/unreal"))
    from import_recovered_assets import read_glb
    doc = read_glb((ROOT / "analysis/unreal/import-inputs/scene/hall.glb").read_bytes())
    helpers = {n["name"] for n in doc["nodes"]
               if n.get("extras", {}).get("sourceInstance", {}).get("FilePathIndex") == "25"}
    hidden = []
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label() in helpers:
            actor.set_actor_hidden_in_game(True)
            actor.set_is_temporarily_hidden_in_editor(True)
            hidden.append(actor.get_actor_label())
    if set(hidden) != helpers:
        raise RuntimeError("Source marker actor mapping incomplete: " + str(helpers-set(hidden)))
    layout = json.loads((ROOT / "analysis/unreal/import-inputs/scene/layout.json").read_text("utf8"))
    marker = next(m for m in layout["player_markers"] if m["name"] == "player_position")
    m = marker["matrix"]
    position = unreal.Vector(m[12]*100, m[14]*100, m[13]*100)
    rotation = unreal.Rotator(pitch=0, yaw=math.degrees(math.atan2(m[2], m[0])), roll=0)
    sys.path.insert(0, str(ROOT / "tools"))
    from trace_first_encounter import literal_table
    entity = literal_table(1955, {SPEC["entity_id"]})["rows"][0]["fields"]
    if entity["ANIM_STATES_HOME_STAND_IDLE"] != "home_stand_idle_1":
        raise RuntimeError("Entity hall animation selection changed")
    hall_scale = entity["SCALE_IN_HALL"]
    result = {"character_id":SPEC["character_id"], "entity_id":SPEC["entity_id"], "map": TARGET, "source_map_preserved": BASE, "actors": [],
              "camera_policy": "inspection look-at; original projection unverified",
              "source_marker_matrix": m, "character_scale": hall_scale,
              "original_materials_verified": False, "original_camera_verified": False, "hidden_marker_labels": hidden}
    for name in SPEC["parts"]:
        folder = SPEC["folders"][name]
        objects = [unreal.load_asset(path) for path in unreal.EditorAssetLibrary.list_assets(folder, True, False)]
        meshes = [obj for obj in objects if obj and obj.get_class().get_name() == "SkeletalMesh"]
        animations = [obj for obj in objects if obj and obj.get_class().get_name() == "AnimSequence"]
        if len(meshes)!=1 or len(animations)!=1:
            raise RuntimeError("Expected one source mesh and exact hall-idle sequence in "+folder)
        mesh, animation = meshes[0], animations[0]
        actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, position, rotation)
        actor.set_actor_label("HCZS_"+name)
        actor.set_actor_scale3d(unreal.Vector(*hall_scale))
        component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
        component.set_skeletal_mesh_asset(mesh)
        component.override_animation_data(animation, True, True, 0, 1)
        component.set_update_animation_in_editor(True)
        component.set_editor_property("cast_shadow", False)
        result["actors"].append({"path": actor.get_path_name(), "mesh":mesh.get_path_name(),
                                "animation":animation.get_path_name(), "bone_count":component.get_num_bones()})
    # One shared reflection reconciles raw NeoX coordinates with the source
    # camera's handedness. This is a reversible visual adaptation, not a claim
    # about the original native renderer's complete projection convention.
    roots = [a for a in actors.get_all_level_actors() if not a.get_attach_parent_actor()]
    pivot = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0,0,0))
    pivot.set_actor_label("HCZSCoordinateAdapter")
    pivot.get_component_by_class(unreal.SceneComponent).set_mobility(unreal.ComponentMobility.STATIC)
    for root in roots:
        root.attach_to_actor(pivot, "", unreal.AttachmentRule.KEEP_WORLD,
                             unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        if root.get_attach_parent_actor() != pivot:
            raise RuntimeError("Could not attach coordinate-adaptation root: "+root.get_actor_label())
    pivot.set_actor_scale3d(unreal.Vector(1,-1,1))
    result["source_coordinate_adaptation"] = "one world Y reflection after Interchange; pending native projection validation"
    target = unreal.Vector(position.x, -position.y, position.z+800)
    source_camera = next(c for c in layout["cameras"] if c["Name"] == "camera_1")
    camera_matrix = [float(x) for x in source_camera["Transform"].split(",")]
    forward = unreal.Vector(camera_matrix[8], -camera_matrix[10], camera_matrix[9])
    forward.normalize()
    camera_position = target-forward*6000
    camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_position, target)
    camera = actors.spawn_actor_from_class(unreal.CameraActor, camera_position, camera_rotation)
    camera.set_actor_label("HCZSInspectionCamera")
    camera.set_editor_property("tags", ["HCZSInspectionCamera"])
    camera_component = camera.get_component_by_class(unreal.CameraComponent)
    horizontal_fov = math.degrees(2*math.atan(math.tan(math.radians(18)/2)*(16/9)))
    camera_component.set_editor_property("field_of_view", horizontal_fov)
    camera_component.set_editor_property("aspect_ratio", 16/9)
    camera_component.set_editor_property("constrain_aspect_ratio", True)
    mode = unreal.load_class(None, "/Script/Hczs.HczsRecoveredHallMode")
    if mode:
        world.get_world_settings().set_editor_property("default_game_mode", mode)
    result["game_mode_applied"] = bool(mode)
    # Inspection lighting only; the APK's baked-light shader is still a separate task.
    light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0,0,2000), unreal.Rotator(pitch=-45,yaw=-30,roll=0))
    light.set_actor_label("HCZSInspectionLight")
    light.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("intensity", 2)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, TARGET):
        raise RuntimeError("Preview map save failed")
    result["saved"] = True
    result["level_actor_count"] = len(actors.get_all_level_actors())
    result["camera"] = {"position":[camera_position.x,camera_position.y,camera_position.z],
                       "rotation":[camera_rotation.pitch,camera_rotation.yaw,camera_rotation.roll], "horizontal_fov":horizontal_fov, "vertical_fov":18}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    unreal.log("HCZS recovered hall preview saved: "+str(REPORT))

if __name__ == "__main__":
    main()
