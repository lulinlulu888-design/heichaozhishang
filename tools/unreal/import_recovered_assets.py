"""Verified-input UE 5.8 Interchange import; run planning with ordinary Python.

Apply only inside Unreal's Python runtime with HCZS_UE_IMPORT_APPLY=1. Defaults
to importing the recovered hall scene and two Shiranui skeletal meshes. Source
GLBs and handoff metadata remain byte-identical. A new hall map keeps imported
instance transforms; it does not claim restored NeoX materials or lighting.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "analysis/unreal/import-inputs"
REPORT_DIR = ROOT / "analysis/unreal/plan"
CORE_IDS = ("hall_scene", "shiranui", "shiranui_weapon")
HALL_MAP = "/Game/Recovered/Hall/Maps/L_RecoveredHall"
GLTF_PIPELINE = "/Interchange/Pipelines/DefaultGLTFPipeline.DefaultGLTFPipeline"
SCENE_PIPELINE = "/Interchange/Pipelines/DefaultSceneLevelPipeline.DefaultSceneLevelPipeline"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def contained(base, relative):
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("Input path escapes its declared root: " + relative)
    return path


def read_glb(data):
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Invalid GLB magic")
    version, length, size, kind = struct.unpack_from("<IIII", data, 4)
    if version != 2 or length != len(data) or kind != 0x4E4F534A or size > length - 20:
        raise ValueError("Invalid GLB envelope")
    return json.loads(data[20:20 + size])


def glb_summary(doc):
    primitives = [p for m in doc.get("meshes", []) for p in m["primitives"]]
    accessors = doc["accessors"]
    return dict(
        meshes=len(doc.get("meshes", [])),
        mesh_instances=sum("mesh" in n for n in doc.get("nodes", [])),
        vertices=sum(accessors[p["attributes"]["POSITION"]]["count"] for p in primitives),
        triangles=sum(accessors[p["indices"]]["count"] // 3 for p in primitives),
        nodes=len(doc.get("nodes", [])), skins=len(doc.get("skins", [])),
        bones=[len(s["joints"]) for s in doc.get("skins", [])],
        animations=[dict(name=a.get("name"), channels=len(a["channels"]))
                    for a in doc.get("animations", [])],
        images=len(doc.get("images", [])), extensions=doc.get("extensionsUsed", []),
    )


def build_plan(selected=CORE_IDS):
    """Check both source and staged copy before any editor mutation."""
    manifest_bytes = (BASE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["schema"] != "hczs-unreal-import-inputs-v1":
        raise ValueError("Unsupported handoff schema")
    rows = {a["id"]: a for a in manifest["assets"]}
    if len(rows) != len(manifest["assets"]):
        raise ValueError("Duplicate asset IDs")
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Empty or duplicate import selection")
    plan_rows = []
    for identifier in selected:
        a = rows[identifier]
        if not a["import_enabled"] or a["kind"] == "metadata":
            raise ValueError("Metadata cannot be imported as an engine asset: " + identifier)
        source = contained(ROOT, a["source_file"])
        staged = contained(BASE, a["file"])
        data, original = staged.read_bytes(), source.read_bytes()
        if len(data) != a["bytes"] or not (sha256(data) == sha256(original) == a["sha256"] == a["source_sha256"]):
            raise ValueError("Source or copy hash mismatch: " + identifier)
        destination = a["import_path"]
        if not destination.startswith("/Game/Recovered/") or ".." in destination or ":" in destination:
            raise ValueError("Destination outside recovered content: " + identifier)
        row = {k: a[k] for k in ("id", "kind", "sha256", "bytes", "import_path")}
        row["filename"] = staged.as_posix()
        if a["kind"].startswith("gltf_"):
            doc = read_glb(data)
            summary = glb_summary(doc)
            if summary != a["geometry"]:
                raise ValueError("GLB inventory mismatch: " + identifier)
            # Self-contained GLBs must not read arbitrary external file URIs.
            for entry in doc.get("buffers", []) + doc.get("images", []):
                if entry.get("uri") and not entry["uri"].startswith("data:"):
                    raise ValueError("External GLB URI is not approved: " + identifier)
            row["expected"] = summary
            row["import_operation"] = "scene" if a["kind"] == "gltf_scene" else "asset"
        elif a["kind"] == "texture":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or list(struct.unpack_from(">II", data, 16)) != a["dimensions"]:
                raise ValueError("PNG inventory mismatch: " + identifier)
            row["expected"] = {"dimensions": a["dimensions"]}
            row["import_operation"] = "texture"
        else:
            raise ValueError("Unsupported enabled import kind: " + a["kind"])
        plan_rows.append(row)
    return dict(
        schema="hczs-unreal-interchange-import-v1", manifest_sha256=sha256(manifest_bytes),
        assets=plan_rows, hall_map=HALL_MAP,
        coordinate_policy=dict(axis_mapping="(x,y,z) -> (x,z,y)", importer_scale=100,
                               additional_import_offset_uniform_scale=1.0,
                               physical_original_units_verified=False, source_bytes_changed=False),
        validation=dict(input_hashes_and_inventory_verified=True, editor_import_executed=False,
                        materials_visually_verified=False, animation_pose_visually_verified=False,
                        native_platforms_verified=False),
    )


def write_report(name, report):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = os.environ.get("HCZS_UE_REPORT_SUFFIX", "")
    if suffix:
        if len(suffix)>64 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in suffix):
            raise ValueError("Invalid report suffix")
        stem = Path(name)
        name = stem.stem+"-"+suffix+stem.suffix
    target = REPORT_DIR / name
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    return target


def object_summary(obj):
    row = dict(path=obj.get_path_name(), name=obj.get_name(), class_name=obj.get_class().get_name())
    if row["class_name"] == "AnimSequence":
        row["play_length_seconds"] = obj.get_play_length()
    return row


def asset_inventory(unreal, destination):
    paths = unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False)
    objects = [unreal.EditorAssetLibrary.load_asset(path) for path in paths]
    return [object_summary(obj) for obj in objects if obj is not None]


def make_pipeline(unreal, row):
    """Create transient settings, never change the installed engine's assets."""
    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.set_editor_property("import_offset_uniform_scale", 1.0)
    pipeline.set_editor_property("import_offset_translation", unreal.Vector(0, 0, 0))
    pipeline.set_editor_property("import_offset_rotation", unreal.Rotator(0, 0, 0))
    pipeline.set_editor_property("use_source_name_for_asset", True)
    pipeline.set_editor_property("asset_type_sub_folders", False)
    pipeline.set_editor_property("scene_name_sub_folder", False)
    # GLTF already declares colour/normal/data texture usage. Pixel-based normal
    # guessing misclassified the original purple Cube colour texture as a normal
    # map, changing compression and sRGB. Keep semantic normal-map handling in
    # Interchange, but disable the post-import colour heuristic for recovered GLBs.
    material_pipeline = pipeline.get_editor_property("material_pipeline")
    texture_pipeline = material_pipeline.get_editor_property("texture_pipeline")
    texture_pipeline.set_editor_property("detect_normal_map_texture", False)
    common = pipeline.get_editor_property("common_meshes_properties")
    common.set_editor_property("bake_meshes", False)
    common.set_editor_property("recompute_normals", False)
    common.set_editor_property("recompute_tangents", True)  # Recovered GLBs have no tangent stream.
    common.set_editor_property("keep_sections_separate", True)
    common.set_editor_property("use_full_precision_u_vs", True)
    meshes = pipeline.get_editor_property("mesh_pipeline")
    meshes.set_editor_property("build_nanite", False)
    meshes.set_editor_property("create_physics_asset", False)
    meshes.set_editor_property("combine_static_meshes_behavior", unreal.InterchangeCombineStaticMeshesBehavior.DO_NOT_COMBINE)
    animations = pipeline.get_editor_property("animation_pipeline")
    animations.set_editor_property("import_animations", True)
    animations.set_editor_property("import_bone_tracks", True)
    animations.set_editor_property("use30_hz_to_bake_bone_animation", False)
    animations.set_editor_property("custom_bone_animation_sample_rate", 0)
    paths = [unreal.SoftObjectPath(pipeline.get_path_name()), unreal.SoftObjectPath(GLTF_PIPELINE)]
    if row["import_operation"] == "scene":
        paths.append(unreal.SoftObjectPath(SCENE_PIPELINE))
    return pipeline, paths


def apply_plan(plan):
    import unreal
    required = ("InterchangeManager", "ImportAssetParameters", "InterchangeGenericAssetsPipeline",
                "EditorAssetLibrary", "EditorActorSubsystem", "EditorLoadingAndSavingUtils")
    missing = [name for name in required if not hasattr(unreal, name)]
    if missing:
        raise RuntimeError("Required UE Python API unavailable: " + ", ".join(missing))
    report = dict(plan)
    report["validation"] = dict(plan["validation"])
    report["engine_version"] = unreal.SystemLibrary.get_engine_version()
    report["results"] = []
    replacing = os.environ.get("HCZS_UE_IMPORT_REPLACE") == "1"
    manager = unreal.InterchangeManager.get_interchange_manager_scripted()
    if not manager:
        raise RuntimeError("Interchange manager unavailable")
    # Fail before importing anything if a selected destination is populated.
    for row in plan["assets"]:
        if not replacing and unreal.EditorAssetLibrary.list_assets(row["import_path"], recursive=True, include_folder=False):
            raise RuntimeError("Destination already contains assets; explicit HCZS_UE_IMPORT_REPLACE=1 required: " + row["import_path"])
    if any(r["import_operation"] == "scene" for r in plan["assets"]):
        if unreal.EditorAssetLibrary.does_asset_exist(HALL_MAP):
            raise RuntimeError("Existing hall map is retained. Import into a new map path or inspect it manually: " + HALL_MAP)
    try:
        for row in plan["assets"]:
            result = {"id": row["id"], "source_sha256": row["sha256"], "import_operation": row["import_operation"]}
            if row["import_operation"] == "texture":
                task = unreal.AssetImportTask()
                for prop, value in dict(filename=row["filename"], destination_path=row["import_path"],
                                        destination_name=row["id"], automated=True, replace_existing=replacing,
                                        save=True, async_=False).items():
                    if prop != "async_":
                        task.set_editor_property(prop, value)
                task.set_editor_property("async", False)
                unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                imported = task.get_objects()
                result["import_returned_success"] = bool(imported)
            else:
                source_data = unreal.InterchangeManager.create_source_data(row["filename"])
                if not source_data or not manager.can_translate_source_data(source_data, row["import_operation"] == "scene"):
                    raise RuntimeError("Interchange cannot translate verified source: " + row["id"])
                params = unreal.ImportAssetParameters()
                params.set_editor_property("is_automated", True)
                params.set_editor_property("replace_existing", replacing)
                pipeline, paths = make_pipeline(unreal, row)
                params.set_editor_property("override_pipelines", paths)
                if row["import_operation"] == "scene":
                    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
                    if not world:
                        raise RuntimeError("Could not create dedicated blank hall map")
                    levels = unreal.EditorLevelUtils.get_levels(world)
                    if not levels:
                        raise RuntimeError("Blank hall map has no persistent level")
                    params.set_editor_property("import_level", levels[0])
                    succeeded = manager.import_scene(row["import_path"], source_data, params)
                    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
                    actors = actor_subsystem.get_all_level_actors()
                    result["actors"] = [object_summary(actor) for actor in actors]
                    result["actor_count"] = len(actors)
                    if not succeeded:
                        raise RuntimeError("Interchange scene import returned failure: " + row["id"])
                    if not unreal.EditorLoadingAndSavingUtils.save_map(world, HALL_MAP):
                        raise RuntimeError("Hall scene imported but map save failed")
                    result["saved_map"] = HALL_MAP
                    result["import_returned_success"] = True
                else:
                    response = manager.import_asset(row["import_path"], source_data, params)
                    # UE 5.8 exposes OutImportedObjects; previous versions return bool.
                    succeeded = response[0] if isinstance(response, tuple) else response
                    result["import_returned_success"] = bool(succeeded)
                    if not succeeded:
                        raise RuntimeError("Interchange asset import returned failure: " + row["id"])
            inventory = asset_inventory(unreal, row["import_path"])
            result["assets"] = inventory
            result["classes"] = dict(Counter(a["class_name"] for a in inventory))
            classes = result["classes"]
            if row["kind"] == "gltf_skeletal_mesh" and not (classes.get("SkeletalMesh") and classes.get("Skeleton") and classes.get("AnimSequence")):
                raise RuntimeError("Skeletal import did not create mesh, skeleton and animation: " + row["id"])
            if row["kind"] in ("gltf_scene", "gltf_static_mesh") and not classes.get("StaticMesh"):
                raise RuntimeError("Static import produced no StaticMesh: " + row["id"])
            if row["kind"] == "texture" and not classes.get("Texture2D"):
                raise RuntimeError("Texture import produced no Texture2D: " + row["id"])
            for asset in inventory:
                if not unreal.EditorAssetLibrary.save_asset(asset["path"], only_if_is_dirty=False):
                    raise RuntimeError("Imported asset save failed: " + asset["path"])
            report["results"].append(result)
            write_report("import-result.json", report)
        # Re-read originals as a postcondition. Editor import never edits the handoff.
        build_plan(tuple(row["id"] for row in plan["assets"]))
        report["validation"]["editor_import_executed"] = True
        report["passed"] = True
    except Exception:
        report["passed"] = False
        report["error"] = traceback.format_exc()
        write_report("import-result.json", report)
        raise
    write_report("import-result.json", report)
    unreal.log("HCZS verified recovered import completed: " + str(REPORT_DIR / "import-result.json"))
    return report


def main():
    selected = tuple(x.strip() for x in os.environ.get("HCZS_UE_IMPORT_IDS", ",".join(CORE_IDS)).split(",") if x.strip())
    plan = build_plan(selected)
    plan_path = write_report("import-plan.json", plan)
    if os.environ.get("HCZS_UE_IMPORT_APPLY") == "1":
        apply_plan(plan)
    else:
        print(json.dumps(dict(passed=True, selected=[r["id"] for r in plan["assets"]],
                              plan_file=str(plan_path), editor_import_executed=False)))


if __name__ == "__main__":
    main()
