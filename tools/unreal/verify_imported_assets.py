"""Read back imported assets in Unreal; retain visual fidelity as unverified."""
from collections import Counter
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_recovered_assets import BASE, CORE_IDS, HALL_MAP, build_plan, read_glb, write_report


def main():
    import unreal
    selected = tuple(x.strip() for x in os.environ.get("HCZS_UE_IMPORT_IDS", ",".join(CORE_IDS)).split(",") if x.strip())
    plan = build_plan(selected)
    result = dict(schema="hczs-unreal-import-readback-v1", engine_version=unreal.SystemLibrary.get_engine_version(),
                  assets=[], failures=[], validation=dict(engine_asset_readback_executed=True,
                  source_inputs_byte_identical=True, visual_materials_verified=False,
                  animation_pose_verified=False, native_platforms_verified=False))
    meshes = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    for row in plan["assets"]:
        paths = unreal.EditorAssetLibrary.list_assets(row["import_path"], recursive=True, include_folder=False)
        entry = dict(id=row["id"], source_sha256=row["sha256"], objects=[])
        for path in paths:
            obj = unreal.EditorAssetLibrary.load_asset(path)
            if not obj:
                result["failures"].append("Cannot reload " + path)
                continue
            item = dict(path=obj.get_path_name(), name=obj.get_name(), class_name=obj.get_class().get_name())
            if item["class_name"] == "SkeletalMesh":
                # Transient component reads the actual UE reference skeleton.
                component = unreal.SkeletalMeshComponent()
                component.set_skeletal_mesh_asset(obj)
                item["bone_count"] = component.get_num_bones()
                item["bone_names"] = [str(component.get_bone_name(i)) for i in range(item["bone_count"])]
                item["lod0_render_vertices"] = meshes.get_num_verts(obj, 0)
                item["lod0_sections"] = meshes.get_num_sections(obj, 0)
                skeleton = obj.get_editor_property("skeleton")
                item["skeleton"] = skeleton.get_path_name() if skeleton else None
                expected = row["expected"]["bones"][0]
                item["source_bone_count"] = expected
                if item["bone_count"] < expected:
                    result["failures"].append(row["id"] + ": reference skeleton lost bones")
                if item["lod0_render_vertices"] <= 0 or not skeleton:
                    result["failures"].append(row["id"] + ": missing geometry or skeleton")
            elif item["class_name"] == "AnimSequence":
                item["play_length_seconds"] = obj.get_play_length()
                skeleton = obj.get_editor_property("skeleton")
                item["skeleton"] = skeleton.get_path_name() if skeleton else None
                item["source_animation_names"] = [a["name"] for a in row["expected"]["animations"]]
                if item["play_length_seconds"] <= 0 or not skeleton:
                    result["failures"].append(row["id"] + ": empty animation or missing animation skeleton")
            elif item["class_name"] == "Texture2D":
                item["runtime_dimensions"] = [obj.blueprint_get_size_x(), obj.blueprint_get_size_y()]
                item["s_rgb"] = obj.get_editor_property("srgb")
                item["lod_bias"] = obj.get_editor_property("lod_bias")
                item["max_texture_size"] = obj.get_editor_property("max_texture_size")
            entry["objects"].append(item)
        entry["classes"] = dict(Counter(o["class_name"] for o in entry["objects"]))
        if row["kind"] == "gltf_skeletal_mesh" and not (entry["classes"].get("SkeletalMesh") and entry["classes"].get("AnimSequence")):
            result["failures"].append(row["id"] + ": skeletal mesh and animation assets not both present")
        if row["kind"] == "gltf_scene":
            entry["hall_map_exists"] = unreal.EditorAssetLibrary.does_asset_exist(HALL_MAP)
            if not entry["classes"].get("StaticMesh") or not entry["hall_map_exists"]:
                result["failures"].append("Recovered hall meshes or saved map missing")
        result["assets"].append(entry)
    result["passed"] = not result["failures"]
    path = write_report("import-readback.json", result)
    unreal.log("HCZS imported assets readback: " + str(path))
    if not result["passed"]:
        raise RuntimeError("; ".join(result["failures"]))


if __name__ == "__main__":
    main()
