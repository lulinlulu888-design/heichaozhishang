"""Original sunlight image/keys with a bounded, explicitly temporary UE actor.

Call apply_hall_sunlight(world) after loading a new independent Elsa lighting
map. The caller saves that map. This module does not launch or reload Unreal.
Ordinary Python can generate and validate the plan without touching UE assets.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "analysis/unreal/hall-fx/report.json"
OUT = ROOT / "analysis/unreal/hall-fx"
DEST = "/Game/Recovered/Hall/FX/SunlightPreviewV1"
RECIPE = "hczs-source-sunlight-bounded-preview-v1"
PNG_SHA = "913f29e7de4b5a8d0626a0b2865ae0b4e981be4d3b6b63ba8c4c038083c669b4"
SFX_SHA = "fbb9e96970e2bdaa9532b525a8ef19fea7eea8986d4b0ffa668fddf714c9f735"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_plan():
    report = json.loads(INPUT.read_text("utf8"))
    texture = next(row for row in report["textures"] if row["logical"] == "effects/tex/glow/dian_yun.tga")
    path = Path(texture["png"]).resolve()
    if not path.is_relative_to(ROOT) or digest(path) != PNG_SHA or texture["png_sha256"] != PNG_SHA:
        raise ValueError("Reviewed original sunlight pixels changed")
    effect = next(row for row in report["effects"] if row["logical"] == "effects/scene/zhujuejia_yangguang.sfx")
    source = Path(effect["source"]["path"])
    if not source.resolve().is_relative_to(ROOT) or digest(source) != SFX_SHA:
        raise ValueError("Reviewed sunlight SFX changed")
    particle = next(row for row in effect["rendered_nodes"] if row["kind"] == "ParticleSystem")
    a = particle["attributes"]
    if (a["ParticlesPerSecond"], a["MinSpriteLifespan"], a["MaxSpriteLifespan"]) != ("10.000", "1.500", "2.000"):
        raise ValueError("Reviewed sunlight rate/lifetime changed")
    color = next(row for row in particle["tree"]["children"] if row["tag"] == "ColorFramePar")
    times, colors = [], []
    for key in color["children"]:
        times.append(float(key["attributes"]["Time"]))
        values = [int(v) for v in key["attributes"]["Value"].split(",")]
        if len(values) != 4 or not all(0 <= v <= 255 for v in values):
            raise ValueError("Invalid source ARGB value")
        colors.append(values)
    if times != [0, .1761, .3472, .4967, .6794, .8289, 1] or colors != [
        [0,255,195,86], [37,255,205,81], [41,255,194,82], [52,255,222,117],
        [30,255,190,101], [37,255,215,97], [0,255,191,83]]:
        raise ValueError("Reviewed source particle keyframes changed")
    source_position = report["sunlight_preview"]["aligned_ue_position_cm"]
    if len(source_position) != 3 or not all(math.isfinite(v) for v in source_position):
        raise ValueError("Invalid source-derived emitter position")
    scale = float(report["sunlight_preview"]["source_instance"]["Scale"].split(",")[0])
    result = {"schema": RECIPE, "texture": texture, "source_effect_sha256": SFX_SHA,
              "source_color_times": times, "source_colors_argb": colors,
              "source_position_cm": source_position, "source_particle_attributes": a,
              "particle_limit": 20, "particles_per_second": 10, "lifespan_range": [1.5, 2],
              "radius_cm": [.2 * .5 * scale * 100, .6 * .5 * scale * 100],
              "preview_intensity": 4,
              "adaptations": {
                  "geometry": "twenty pooled engine planes, source dian_yun pixels; camera-facing",
                  "placement": "retain source position; preview actor recentered to the current inspection camera left-center",
                  "volume": "world-axis box half extents 420,100,350 cm; native EmissionType=4 unresolved",
                  "velocity": "temporary gentle drift x=-4..4,y=-3..3,z=3..8 cm/s; native reversed min/max not silently exchanged",
                  "interpolation": "linear normalized lifetime interpolation of seven source ARGB keys",
                  "colour": "ARGB interpreted as A,R,G,B, RGB bytes normalized directly to UE linear; original ColorType/global color composition unresolved",
                  "material": "UE Unlit/Additive, original linear texture RGB and alpha, opacity=textureA*keyA, emission=textureRGB*keyRGB*4",
                  "step": "delta bounded at .25 seconds; no catchup emission burst on long stalls",
              }, "original_neox_fx_verified": False}
    result["recipe_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode("utf8")).hexdigest()
    return result


def _texture(unreal, plan):
    package = DEST + "/T_OriginalSunlightDust"
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        asset = unreal.load_asset(package)
        if not isinstance(asset, unreal.Texture2D) or unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsSourceSHA256") != PNG_SHA:
            raise RuntimeError("Existing sunlight texture has another source identity")
        return asset
    task = unreal.AssetImportTask()
    for key, value in {"filename": plan["texture"]["png"], "destination_path": DEST,
                       "destination_name": "T_OriginalSunlightDust", "automated": True,
                       "replace_existing": False, "save": False}.items():
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    assets = [a for a in task.get_objects() if isinstance(a, unreal.Texture2D)]
    if len(assets) != 1:
        raise RuntimeError("Expected one original dust texture")
    asset = assets[0]
    if [asset.blueprint_get_size_x(),asset.blueprint_get_size_y()] != [128,128]:
        raise RuntimeError("Original sunlight texture dimensions changed")
    asset.set_editor_property("srgb", False)  # Source KTX ASTC is explicitly linear.
    asset.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    asset.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    asset.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
    asset.set_editor_property("lod_bias", 0)
    unreal.EditorAssetLibrary.set_metadata_tag(asset, "HczsSourceSHA256", PNG_SHA)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError("Sunlight texture save failed")
    return asset


def _material(unreal, plan, texture):
    package = DEST + "/M_OriginalSunlightDustPreview"
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        asset = unreal.load_asset(package)
        if not isinstance(asset, unreal.Material) or unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsPreviewRecipeSHA256") != plan["recipe_sha256"]:
            raise RuntimeError("Existing sunlight material has another recipe identity")
        return asset
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_OriginalSunlightDustPreview", DEST,
                    unreal.Material, unreal.MaterialFactoryNew())
    if not material:
        raise RuntimeError("Sunlight material creation failed")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("disable_depth_test", True)  # Source EnableZBuffer=FALSE.
    edit = unreal.MaterialEditingLibrary
    def node(kind, x, y, **properties):
        value = edit.create_material_expression(material, kind, x, y)
        if not value:
            raise RuntimeError("Sunlight material expression creation failed")
        for key, prop in properties.items():
            value.set_editor_property(key, prop)
        return value
    def connect(source, output, target, input_name):
        if not edit.connect_material_expressions(source, output, target, input_name):
            raise RuntimeError("Sunlight material link failed: " + input_name)
    image = node(unreal.MaterialExpressionTextureSampleParameter2D, -650, -150,
                 parameter_name="OriginalSunlightTexture", texture=texture,
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    color = node(unreal.MaterialExpressionVectorParameter, -650, 100,
                 parameter_name="SourceParticleColor", default_value=unreal.LinearColor(1,.8,.3,.2))
    brightness = node(unreal.MaterialExpressionScalarParameter, -300, 250,
                 parameter_name="PreviewIntensity", default_value=plan["preview_intensity"])
    rgb = node(unreal.MaterialExpressionMultiply, -300, -150)
    emission = node(unreal.MaterialExpressionMultiply, 0, -150)
    alpha = node(unreal.MaterialExpressionMultiply, -250, 100)
    connect(image, "RGB", rgb, "A"); connect(color, "RGB", rgb, "B")
    connect(rgb, "", emission, "A"); connect(brightness, "", emission, "B")
    connect(image, "A", alpha, "A"); connect(color, "A", alpha, "B")
    if not edit.connect_material_property(emission, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        raise RuntimeError("Sunlight emission property link failed")
    if not edit.connect_material_property(alpha, "", unreal.MaterialProperty.MP_OPACITY):
        raise RuntimeError("Sunlight opacity property link failed")
    errors = list(edit.recompile_material(material))
    if errors:
        raise RuntimeError("Sunlight shader errors: " + repr(errors))
    unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsPreviewRecipeSHA256", plan["recipe_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsShadingScope", "original sunlight pixels, temporary UE additive composition")
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("Sunlight material save failed")
    return material


def apply_hall_sunlight(world):
    """Add/reuse one source-texture preview actor in the independent active map."""
    import unreal
    if not world or world.get_path_name().split(".")[0] in (
        "/Game/Recovered/Hall/Maps/L_RecoveredHall", "/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview"):
        raise RuntimeError("Sunlight preview requires an independent map; retain source/aligned map")
    plan = build_plan()
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    active_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if active_world != world:
        raise RuntimeError("Sunlight caller world is not the active editor world")
    level_actors = list(actors.get_all_level_actors())
    cameras = [a for a in level_actors if "HCZSInspectionCamera" in [str(t) for t in a.get_editor_property("tags")]]
    elsa = [a for a in level_actors if a.get_actor_label() == "HCZS_elsa"]
    if len(cameras) != 1 or len(elsa) != 1:
        raise RuntimeError("Expected one source Elsa and one stable inspection camera")
    camera = cameras[0]
    component = camera.get_component_by_class(unreal.CameraComponent)
    if not component:
        raise RuntimeError("Inspection camera has no CameraComponent")
    origin = component.get_world_location()
    forward = component.get_forward_vector()
    right = component.get_right_vector()
    up = component.get_up_vector()
    hero = elsa[0].get_actor_location()
    offset = hero - origin
    distance = offset.x*forward.x + offset.y*forward.y + offset.z*forward.z
    if not 1000 <= distance <= 20000:
        raise RuntimeError("Unsupported inspection camera distance")
    adapted = origin + forward * distance + right * -520 + up * 160
    cls = unreal.load_class(None, "/Script/Hczs.HczsHallSunlightActor")
    if not cls:
        raise RuntimeError("Compile HczsEditor with HczsHallSunlightActor before import")
    existing = [a for a in level_actors if a.get_actor_label() == "HCZSOriginalSunlightPreview"]
    if len(existing) > 1 or (existing and existing[0].get_class() != cls):
        raise RuntimeError("Sunlight actor identity conflict")
    texture = _texture(unreal, plan)
    material = _material(unreal, plan, texture)
    actor = existing[0] if existing else actors.spawn_actor_from_class(cls, adapted, unreal.Rotator(pitch=0,yaw=0,roll=0))
    if not actor:
        raise RuntimeError("Cannot spawn sunlight actor")
    actor.set_actor_label("HCZSOriginalSunlightPreview")
    actor.set_actor_location(adapted, False, True)
    if actor.get_attach_parent_actor():
        raise RuntimeError("Sunlight actor must not inherit a second source-coordinate reflection")
    colors = [unreal.LinearColor(r/255,g/255,b/255,a/255) for a,r,g,b in plan["source_colors_argb"]]
    properties = {"ParticleMaterial":material,
                  "OriginalEmitterPosition":unreal.Vector(*plan["source_position_cm"]),
                  "PreviewHalfExtents":unreal.Vector(420,100,350),
                  "ParticlesPerSecond":10.0, "MinimumLifespan":1.5, "MaximumLifespan":2.0,
                  "MinimumRadiusCm":plan["radius_cm"][0], "MaximumRadiusCm":plan["radius_cm"][1],
                  "PreviewIntensity":plan["preview_intensity"], "SourceColorTimes":plan["source_color_times"],
                  "SourceParticleColors":colors, "SourceEffectSha256":SFX_SHA}
    for key, value in properties.items():
        actor.set_editor_property(key, value)
    if len(actor.get_components_by_class(unreal.StaticMeshComponent)) != 20:
        raise RuntimeError("Sunlight pool component count changed")
    actual_position = actor.get_actor_location()
    result = {"passed":True, "map":world.get_path_name(), "actor":actor.get_path_name(),
              "source_position_cm":plan["source_position_cm"],
              "actual_preview_position_cm":[actual_position.x,actual_position.y,actual_position.z],
              "camera_path":camera.get_path_name(), "camera_distance_cm":distance,
              "half_extents_cm":[420,100,350], "particle_component_count":20,
              "material":material.get_path_name(), "texture":texture.get_path_name(),
              "source_colour_key_count":len(actor.get_editor_property("SourceColorTimes")),
              "recipe":plan, "map_saved_by_caller":False,
              "runtime_display_verified":False, "original_fx_equivalence_verified":False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"apply-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),"utf8")
    unreal.log("HCZS: source sunlight actor installed with 20 bounded components; caller must save map and verify visible motion")
    return result


def main():
    plan = build_plan()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"runtime-plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False),"utf8")
    print(json.dumps({"passed":True,"plan_only":True,"source_texture":plan["texture"]["png"],
                      "particle_limit":20,"source_colour_keys":7}))


if __name__ == "__main__":
    main()
