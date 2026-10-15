"""Show the existing imported Elsa hall in the real Unreal Editor."""
import json
import os
from pathlib import Path
import unreal

# -ExecutePythonScript normally exits the editor when the script returns.
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
ROOT = Path(__file__).resolve().parents[1]
MAP = os.environ.get("HCZS_UE_OPEN_MAP", "/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview")
if MAP not in ("/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview", "/Game/Recovered/Hall/Maps/L_ElsaHallLightingPreview", "/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview"):
    raise RuntimeError('Unknown Elsa hall map')
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world or world.get_path_name().split(".")[0] != MAP:
    world = None
    world = unreal.EditorLoadingAndSavingUtils.load_map(MAP)
if not world:
    raise RuntimeError("Verified imported Elsa map could not load")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
camera = next((a for a in actors if str(a.get_actor_label()) == "HCZSInspectionCamera"), None)
elsa = next((a for a in actors if str(a.get_actor_label()) == "HCZS_elsa"), None)
if not camera or not elsa:
    raise RuntimeError("Imported Elsa or preview camera missing")
unreal.EditorLevelLibrary.pilot_level_actor(camera)
component = elsa.get_component_by_class(unreal.SkeletalMeshComponent)
component.set_update_animation_in_editor(True)
unreal.EditorAssetLibrary.sync_browser_to_objects(["/Game/Recovered/Elsa/elsa.elsa"])
result = {"project":unreal.Paths.get_project_file_path(), "engine":unreal.SystemLibrary.get_engine_version(),
          "world":world.get_path_name(), "actor_count":len(actors),
          "camera_pilot_called":True, "elsa_actor":elsa.get_path_name(), "elsa_bones":component.get_num_bones(),
          "asset_browser_sync_called":True, "asset_import_repeated":False}
(ROOT/"analysis/unreal/plan/editor-open-elsa.json").write_text(json.dumps(result,indent=2),encoding="utf8")
unreal.log("HCZS: existing Elsa project/map opened in full editor")
