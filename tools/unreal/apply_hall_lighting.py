"""Port the APK hall's ten encoded irradiance maps into a separate UE map.

Ordinary Python writes a verified plan. Set HCZS_UE_HALL_LIGHTING_APPLY=1
inside Unreal's Python runtime to import new textures/materials and clone the
aligned Elsa preview. No existing source map, mesh, material, or hero is edited.
This is the recovered diffuse lightmap formula, not native BRDF/dynamic-light
parity. Multi-primitive bindings remain deferred rather than guessed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "analysis/unreal/import-inputs"
OUTPUT = ROOT / "analysis/unreal/hall-lighting"
SOURCE_MAP = "/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview"
TARGET_MAP = os.environ.get("HCZS_UE_HALL_LIGHTING_TARGET", "/Game/Recovered/Hall/Maps/L_ElsaHallLightingPreview")
ASSET_ROOT = "/Game/Recovered/Hall/Lighting/SourceDiffuseV1"
FORMULA_TAG = "DefaultVF UE4_lm encode_type=4 source diffuse-v1"
UV_CODE = "return UV * ScaleOffset.xy + ScaleOffset.zw;"
# These two packages were saved by the verified full-editor run immediately
# before its map-switch GC failure. They predate recipe metadata; only these
# exact bytes may use the legacy resume path, never an arbitrary existing mat.
LEGACY_MASTER_SHA256 = {
    "BLEND": "2b390e48f6298e3151bdcad736f92ae320be9cb1db757c91c767e6c19ce75b20",
    "OPAQUE": "6c516aabaae9c4707f349f7f9faf064f91d2d3a7392ff2e41ecb480b2745cf5f",
}
LEGACY_LIGHTING_SHA256 = "5bdb2bce8ddbc699609cb88f1f6123434c1edc85170693878a6b1501cc246fa2"
SHADER_CODE = """float3 encodedLight = LightmapColor * LightmapScale + LightmapAdd;
float logL = dot(float3(0.299, 0.587, 0.114), encodedLight);
float luminance = (exp2(logL * 16.0 - 8.0) - 0.00390625) * 0.6;
return encodedLight * (luminance / max(logL, 0.00001));"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(text, count):
    values = [float(x) for x in text.split(",")]
    if len(values) < count or not all(math.isfinite(x) for x in values):
        raise ValueError("Nonfinite or incomplete source vector")
    return values[:count]


def report(name, value):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), "utf8")


def build_plan():
    if not TARGET_MAP.startswith("/Game/Recovered/Hall/Maps/L_ElsaHall") or ".." in TARGET_MAP:
        raise ValueError("Target must be an independent Elsa hall map")
    if TARGET_MAP == SOURCE_MAP:
        raise ValueError("Source inspection map must remain unchanged")
    lighting_file = INPUT / "lighting/lighting.json"
    original_file = ROOT / "analysis/hall/lighting/lighting.json"
    if digest(lighting_file) != digest(original_file):
        raise ValueError("Staged lighting metadata differs from recovered source")
    lighting = json.loads(lighting_file.read_text("utf8"))
    if lighting["schema"] != 1 or len(lighting["textures"]) != 10:
        raise ValueError("Unreviewed hall lighting table")
    source_glb = INPUT / "scene/hall.glb"
    if digest(source_glb) != lighting["scene_glb_sha256"]:
        raise ValueError("Hall GLB does not match reviewed lightmap bindings")
    data = source_glb.read_bytes()
    doc = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
    source_shader = ROOT / "analysis/hall/lighting/source/default_functions.hlsl"
    shader = source_shader.read_text("utf8")
    if not all(x in shader for x in ("LogBlackPoint = 0.00390625", "ConstDirectional = 0.6", "LogL * 16 - 8")):
        raise ValueError("Reviewed irradiance decoder changed")
    images = []
    for index, row in enumerate(lighting["textures"]):
        path = INPUT / "lighting" / row["file"]
        original = ROOT / "analysis/hall/lighting" / row["file"]
        if digest(path) != row["sha256"] or digest(original) != row["sha256"]:
            raise ValueError("Original lightmap bytes changed: " + row["file"])
        if row["ktx"]["profile"] != "linear" or row["ktx"]["orientation_changed"]:
            raise ValueError("Unexpected lightmap colour space/orientation")
        images.append(dict(index=index, filename=path.as_posix(), sha256=row["sha256"],
                           dimensions=[row["ktx"]["width"], row["ktx"]["height"]],
                           logical_source=row["logical"], name=f"T_SourceHallLM_{index}"))
    nodes = {n["extras"]["sourceInstance"]["UUID"]: n for n in doc["nodes"] if "mesh" in n}
    bindings = []
    for row in lighting["bindings"]:
        node = nodes[row["uuid"]]
        if node["name"] != row["name"] or node["mesh"] != row["mesh"]:
            raise ValueError("Source instance identity mismatch")
        primitives = doc["meshes"][row["mesh"]]["primitives"]
        if len(primitives) != 1 or "TEXCOORD_1" not in primitives[0]["attributes"]:
            raise ValueError("Ambiguous source lightmap primitive")
        material = doc["materials"][primitives[0]["material"]]
        pbr = material["pbrMetallicRoughness"]
        if pbr.get("baseColorFactor", [1, 1, 1, 1]) != [1, 1, 1, 1]:
            raise ValueError("Unexpected diffuse colour factor")
        tex = pbr["baseColorTexture"]
        if tex.get("texCoord", 0) != 0 or tex.get("extensions"):
            raise ValueError("Unreviewed diffuse UV transform")
        texture_index = doc["textures"][tex["index"]]["source"]
        params = row["parameters"]
        if params["UE4_lm"] != "true" or params["encode_type"] != "4":
            raise ValueError("Unreviewed original lightmap encoding")
        uv_scale, uv_offset = vector(params["uv_scale"], 2), vector(params["uv_ofs"], 2)
        alpha = material.get("alphaMode", "OPAQUE")
        if alpha not in ("OPAQUE", "BLEND") or not material.get("doubleSided"):
            raise ValueError("Unreviewed original diffuse render mode")
        bindings.append(dict(name=row["name"], uuid=row["uuid"], source_mesh=row["mesh"],
                             uv_count=row["uv_count"], texture_index=int(params["texture_index"]),
                             diffuse_asset=f"/Game/Recovered/Hall/Environment/hall_texture_{texture_index}.hall_texture_{texture_index}",
                             uv_scale_offset=uv_scale + uv_offset,
                             lightmap_scale=vector(params["lightmap_scale"], 3),
                             lightmap_add=vector(params["lightmap_add"], 3),
                             alpha_mode=alpha,
                             material_name="MI_HallLM_" + row["uuid"].replace("-", "")))
    if len(bindings) != 66 or len({r["name"] for r in bindings}) != 66:
        raise ValueError("Hall lighting binding inventory changed")
    return dict(schema="hczs-ue-hall-source-diffuse-lighting-v1", source_map=SOURCE_MAP,
                target_map=TARGET_MAP, asset_root=ASSET_ROOT, images=images, bindings=bindings,
                lighting_metadata_sha256=digest(lighting_file), source_glb_sha256=digest(source_glb),
                source_decoder_sha256=digest(source_shader), source_apk_sha256=lighting["apk_sha256"],
                deferred_bindings=lighting["unresolved"], original_light_count=len(lighting["lights"]),
                original_lights_applied=False,
                limitations=["Only diffuse irradiance decoding, not original BRDF, normal maps or realtime light-channel semantics",
                             "Eleven ambiguous multi-primitive instances retain existing colour-reference materials",
                             "Scene camera/native projection and original tone mapping remain unverified",
                             "Source directional lightmap contribution is not reconstructed",
                             "Editor render and packaged/mobile validation are separate checks"])


def new_asset(unreal, name, folder, cls, factory):
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if not asset:
        raise RuntimeError("Cannot create new asset: " + folder + "/" + name)
    return asset


def package_file(package, extension):
    import unreal
    content = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())).resolve()
    if not package.startswith("/Game/"):
        raise ValueError("Package is outside project content")
    path = (content / (package[6:] + extension)).resolve()
    if not path.is_relative_to(content):
        raise ValueError("Package file escapes project content")
    return path


def master_recipe(plan, alpha_mode):
    payload = dict(schema=plan["schema"], lighting_sha256=plan["lighting_metadata_sha256"],
                   glb_sha256=plan["source_glb_sha256"], source_decoder_sha256=plan["source_decoder_sha256"],
                   image_sha256=[x["sha256"] for x in plan["images"]], shader=SHADER_CODE,
                   uv_shader=UV_CODE, alpha_mode=alpha_mode, expression_count=9, uv_channel=1)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def apply(plan):
    import unreal
    library = unreal.MaterialEditingLibrary
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    mesh_subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    result = {k: v for k, v in plan.items() if k not in ("images", "bindings")}
    result.update(passed=False, textures=[], materials=[], bindings=[], engine_version=unreal.SystemLibrary.get_engine_version())
    try:
        if "-run=" in unreal.SystemLibrary.get_command_line().lower():
            raise RuntimeError("Full Unreal Editor -ExecutePythonScript is required; StaticMeshEditorSubsystem is unavailable in commandlets")
        if not actor_subsystem or not mesh_subsystem:
            raise RuntimeError("Full Unreal Editor actor/static-mesh subsystems are required")
        if unreal.EditorAssetLibrary.does_asset_exist(TARGET_MAP):
            raise RuntimeError("Target map already exists; retained without overwriting edits")
        source_file, target_file = package_file(SOURCE_MAP, ".umap"), package_file(TARGET_MAP, ".umap")
        source_map_sha256 = digest(source_file)
        if target_file.exists():
            raise RuntimeError("Target map file already exists; retained without overwriting")
        # A failed first run may already have saved textures. Resume only exact
        # source hashes at the ten generated paths, never a whole folder or an
        # unknown material asset. Nothing from the original import is deleted.
        expected_textures = {ASSET_ROOT + "/Textures/" + row["name"] + "." + row["name"]: row
                             for row in plan["images"]}
        existing_textures = {}
        existing_masters = {}
        expected_masters = {ASSET_ROOT + "/Materials/M_SourceHallDiffuseLM_" + mode + ".M_SourceHallDiffuseLM_" + mode: mode
                            for mode in ("OPAQUE", "BLEND")}
        for path in unreal.EditorAssetLibrary.list_assets(ASSET_ROOT, True, False):
            asset = unreal.load_asset(path)
            canonical = asset.get_path_name() if asset else str(path)
            row = expected_textures.get(canonical)
            alpha_mode = expected_masters.get(canonical)
            if alpha_mode and isinstance(asset, unreal.Material):
                if unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsLightmapFormula") != FORMULA_TAG:
                    raise RuntimeError("Existing master has no verified source formula ownership: " + canonical)
                recipe = unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsHallLightingRecipeSHA256")
                if recipe:
                    if recipe != master_recipe(plan, alpha_mode):
                        raise RuntimeError("Existing master recipe/source inputs differ: " + canonical)
                else:
                    asset_file = package_file(canonical.split(".")[0], ".uasset")
                    if (plan["lighting_metadata_sha256"] != LEGACY_LIGHTING_SHA256 or
                            digest(asset_file) != LEGACY_MASTER_SHA256[alpha_mode]):
                        raise RuntimeError("Unrecognized legacy master retained without modification: " + canonical)
                expressions = list(library.get_material_expressions(asset))
                if library.get_num_material_expressions(asset) != 9 or len(expressions) != 9:
                    raise RuntimeError("Existing source master expression count differs: " + canonical)
                codes = sorted(e.get_editor_property("code") for e in expressions if isinstance(e, unreal.MaterialExpressionCustom))
                if codes != sorted([SHADER_CODE, UV_CODE]):
                    raise RuntimeError("Existing master decoder/UV shader differs: " + canonical)
                uv_nodes = [e for e in expressions if isinstance(e, unreal.MaterialExpressionTextureCoordinate)]
                if len(uv_nodes) != 1 or uv_nodes[0].get_editor_property("coordinate_index") != 1:
                    raise RuntimeError("Existing source master UV channel differs: " + canonical)
                expected_blend = unreal.BlendMode.BLEND_TRANSLUCENT if alpha_mode == "BLEND" else unreal.BlendMode.BLEND_OPAQUE
                if (asset.get_editor_property("shading_model") != unreal.MaterialShadingModel.MSM_UNLIT or
                        asset.get_editor_property("blend_mode") != expected_blend or not asset.get_editor_property("two_sided")):
                    raise RuntimeError("Existing source master render state differs: " + canonical)
                existing_masters[alpha_mode] = asset
                continue
            if not row or not isinstance(asset, unreal.Texture2D):
                raise RuntimeError("Unknown pre-existing lighting asset retained without modification: " + canonical)
            if unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsSourceSHA256") != row["sha256"]:
                raise RuntimeError("Existing lightmap source hash differs: " + canonical)
            expected_settings = dict(srgb=False, compression_settings=unreal.TextureCompressionSettings.TC_HDR,
                                     mip_gen_settings=unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS,
                                     filter=unreal.TextureFilter.TF_BILINEAR, address_x=unreal.TextureAddress.TA_CLAMP,
                                     address_y=unreal.TextureAddress.TA_CLAMP, never_stream=True, lod_bias=0, max_texture_size=0)
            for key, expected in expected_settings.items():
                if asset.get_editor_property(key) != expected:
                    raise RuntimeError("Existing owned lightmap setting differs; retained without overriding: " + canonical + ":" + key)
            existing_textures[row["index"]] = asset
        world = unreal.EditorLoadingAndSavingUtils.load_map(SOURCE_MAP)
        if not world:
            raise RuntimeError("Aligned Elsa source map unavailable")
        by_label = {}
        for actor in actor_subsystem.get_all_level_actors():
            by_label.setdefault(actor.get_actor_label(), []).append(actor)
        # Validate all mappings before creating assets or modifying a clone.
        for row in plan["bindings"]:
            candidates = by_label.get(row["name"], [])
            if len(candidates) != 1:
                raise RuntimeError("Ambiguous UE actor label: " + row["name"])
            component = candidates[0].get_component_by_class(unreal.StaticMeshComponent)
            if not component:
                raise RuntimeError("Source actor has no StaticMeshComponent: " + row["name"])
            mesh = component.get_editor_property("static_mesh")
            if not mesh or mesh.get_num_sections(0) != 1 or component.get_num_materials() != 1:
                raise RuntimeError("UE section identity differs: " + row["name"])
            channels = mesh_subsystem.get_num_uv_channels(mesh, 0)
            if channels < 2:
                raise RuntimeError("Source UV1 unavailable: " + row["name"])
            build = mesh_subsystem.get_lod_build_settings(mesh, 0)
            generated = build.get_editor_property("generate_lightmap_u_vs")
            destination = build.get_editor_property("dst_lightmap_index")
            if generated and destination == 1:
                raise RuntimeError("UE generated lightmap UVs replaced source UV1: " + row["name"])
            old_material = component.get_material(0)
            base_texture = unreal.load_asset(row["diffuse_asset"])
            if not base_texture or not isinstance(old_material, unreal.MaterialInstanceConstant):
                raise RuntimeError("Source diffuse texture/material unavailable: " + row["name"])
            actual_texture = library.get_material_instance_texture_parameter_value(old_material, "BaseColorTexture")
            if actual_texture != base_texture:
                raise RuntimeError("GLB image-to-UE material mapping differs: " + row["name"])
            if not base_texture.get_editor_property("srgb"):
                raise RuntimeError("Diffuse texture is not sRGB: " + row["name"])
            row["verified_mesh"] = mesh.get_path_name()
            row["verified_original_material"] = old_material.get_path_name()
            row["ue_uv_channels"] = channels
        textures = []
        for row in plan["images"]:
            if row["index"] in existing_textures:
                texture = existing_textures[row["index"]]
                textures.append(texture)
                result["textures"].append(dict(path=texture.get_path_name(), source_sha256=row["sha256"],
                                               srgb=texture.get_editor_property("srgb"), dimensions=row["dimensions"],
                                               reused_verified_source_texture=True,
                                               codec="float HDR, linear; no mipmaps, clamp bilinear"))
                continue
            task = unreal.AssetImportTask()
            for key, value in dict(filename=row["filename"], destination_path=ASSET_ROOT + "/Textures",
                                   destination_name=row["name"], automated=True, replace_existing=False, save=False).items():
                task.set_editor_property(key, value)
            task.set_editor_property("bAsync", False)
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            imported = task.get_objects()
            if len(imported) != 1 or not isinstance(imported[0], unreal.Texture2D):
                raise RuntimeError("Source lightmap import failed: " + row["name"])
            texture = imported[0]
            texture.set_editor_property("srgb", False)
            texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_HDR)
            texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            texture.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
            texture.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            texture.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
            texture.set_editor_property("never_stream", True)
            texture.set_editor_property("lod_bias", 0)
            texture.set_editor_property("max_texture_size", 0)
            unreal.EditorAssetLibrary.set_metadata_tag(texture, "HczsSourceSHA256", row["sha256"])
            if not unreal.EditorAssetLibrary.save_loaded_asset(texture, False):
                raise RuntimeError("Cannot save lightmap texture")
            textures.append(texture)
            result["textures"].append(dict(path=texture.get_path_name(), source_sha256=row["sha256"],
                                           srgb=texture.get_editor_property("srgb"), dimensions=row["dimensions"],
                                           codec="float HDR, linear; no mipmaps, clamp bilinear"))

        def expression(material, cls, x=0, y=0, **properties):
            obj = library.create_material_expression(material, cls, x, y)
            if not obj:
                raise RuntimeError("Cannot create material expression " + str(cls))
            for key, value in properties.items():
                obj.set_editor_property(key, value)
            return obj

        def connect(from_node, from_output, to_node, to_input):
            if not library.connect_material_expressions(from_node, from_output, to_node, to_input):
                raise RuntimeError("Material expression connection failed: " + to_input)

        def custom(material, names, code, output_type, x=0, y=0):
            inputs = []
            for name in names:
                value = unreal.CustomInput()
                value.set_editor_property("input_name", name)
                inputs.append(value)
            return expression(material, unreal.MaterialExpressionCustom, x, y,
                              inputs=inputs, code=code, output_type=output_type)

        masters = {}
        for alpha_mode in sorted({r["alpha_mode"] for r in plan["bindings"]}):
            if alpha_mode in existing_masters:
                material = existing_masters[alpha_mode]
                masters[alpha_mode] = material
                result["materials"].append(dict(path=material.get_path_name(), alpha_mode=alpha_mode,
                                                source_formula=SHADER_CODE, uv_channel=1, expression_count=9,
                                                source_inputs_recipe_sha256=master_recipe(plan, alpha_mode),
                                                reused_verified_owned_master=True))
                continue
            name = "M_SourceHallDiffuseLM_" + alpha_mode
            material = new_asset(unreal, name, ASSET_ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
            material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
            material.set_editor_property("two_sided", True)
            material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT if alpha_mode == "BLEND" else unreal.BlendMode.BLEND_OPAQUE)
            diffuse = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -750, -100,
                                 parameter_name="SourceDiffuse", texture=unreal.load_asset(plan["bindings"][0]["diffuse_asset"]),
                                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
            uv = expression(material, unreal.MaterialExpressionTextureCoordinate, -1100, 220, coordinate_index=1)
            transform = expression(material, unreal.MaterialExpressionVectorParameter, -1100, 420,
                                   parameter_name="LMUVScaleOffset", default_value=unreal.LinearColor(1, 1, 0, 0))
            transformed = custom(material, ["UV", "ScaleOffset"], UV_CODE,
                                 unreal.CustomMaterialOutputType.CMOT_FLOAT2, -820, 240)
            connect(uv, "", transformed, "UV")
            connect(transform, "RGBA", transformed, "ScaleOffset")
            lightmap = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, -540, 210,
                                  parameter_name="SourceLightmap", texture=textures[0],
                                  sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
            # MaterialEditingLibrary applies MaterialGraphNode's shortened pin
            # names: C++ Coordinates is exposed to this API as UVs.
            connect(transformed, "", lightmap, "UVs")
            scale = expression(material, unreal.MaterialExpressionVectorParameter, -540, 450,
                               parameter_name="LMScale", default_value=unreal.LinearColor(1, 1, 1, 0))
            add = expression(material, unreal.MaterialExpressionVectorParameter, -540, 650,
                             parameter_name="LMAdd", default_value=unreal.LinearColor(0, 0, 0, 0))
            decode = custom(material, ["LightmapColor", "LightmapScale", "LightmapAdd"], SHADER_CODE,
                            unreal.CustomMaterialOutputType.CMOT_FLOAT3, -230, 250)
            connect(lightmap, "RGB", decode, "LightmapColor")
            connect(scale, "RGB", decode, "LightmapScale")
            connect(add, "RGB", decode, "LightmapAdd")
            multiply = expression(material, unreal.MaterialExpressionMultiply, 70, 0)
            connect(diffuse, "RGB", multiply, "A")
            connect(decode, "", multiply, "B")
            if not library.connect_material_property(multiply, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR):
                raise RuntimeError("Cannot connect recovered diffuse irradiance")
            if alpha_mode == "BLEND" and not library.connect_material_property(diffuse, "A", unreal.MaterialProperty.MP_OPACITY):
                raise RuntimeError("Cannot preserve source texture alpha")
            unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsLightmapFormula", FORMULA_TAG)
            unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsHallLightingRecipeSHA256", master_recipe(plan, alpha_mode))
            unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsLightingMetadataSHA256", plan["lighting_metadata_sha256"])
            library.layout_material_expressions(material)
            library.recompile_material(material)
            if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
                raise RuntimeError("Cannot save hall lighting master material")
            masters[alpha_mode] = material
            result["materials"].append(dict(path=material.get_path_name(), alpha_mode=alpha_mode,
                                            source_formula=SHADER_CODE, uv_channel=1, expression_count=9,
                                            source_inputs_recipe_sha256=master_recipe(plan, alpha_mode)))
        # Retain the already-loaded source world, and use native SaveMap SaveAs
        # once at the end. A Python-held old world/actor reference cannot survive
        # Editor load_map safely: it causes World Memory Leaks on map teardown.
        # Native FileHelpers::SaveWorld duplicates an on-disk source internally
        # without this editor map switch, preserving its serialized file.
        for row in plan["bindings"]:
            material = new_asset(unreal, row["material_name"], ASSET_ROOT + "/Instances",
                                 unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
            library.set_material_instance_parent(material, masters[row["alpha_mode"]])
            values = {"SourceDiffuse": unreal.load_asset(row["diffuse_asset"]), "SourceLightmap": textures[row["texture_index"]]}
            for name, texture in values.items():
                # UE5.8 setters leave their bool return false even after setting.
                # Validate the actual parameter, not that misleading return.
                library.set_material_instance_texture_parameter_value(material, name, texture)
                if library.get_material_instance_texture_parameter_value(material, name) != texture:
                    raise RuntimeError("Cannot set hall lighting texture parameter")
            for name, values in (("LMUVScaleOffset", row["uv_scale_offset"]),
                                 ("LMScale", row["lightmap_scale"] + [0]), ("LMAdd", row["lightmap_add"] + [0])):
                library.set_material_instance_vector_parameter_value(material, name, unreal.LinearColor(*values))
                actual = library.get_material_instance_vector_parameter_value(material, name)
                if any(abs(a-b) > 1e-5*(1+abs(b)) for a,b in zip((actual.r,actual.g,actual.b,actual.a),values)):
                    raise RuntimeError("Cannot set original lightmap vector parameter")
            unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsSourceInstanceUUID", row["uuid"])
            library.update_material_instance(material)
            if not unreal.EditorAssetLibrary.save_loaded_asset(material, False):
                raise RuntimeError("Cannot save hall source lightmap instance")
            component = by_label[row["name"]][0].get_component_by_class(unreal.StaticMeshComponent)
            component.set_material(0, material)
            if component.get_material(0) != material:
                raise RuntimeError("Clone material override readback failed")
            result["bindings"].append(dict(row, material=material.get_path_name()))
        report("apply-progress.json", dict(result, stage="before-native-save-as", source_map_sha256_before=source_map_sha256))
        if not unreal.EditorLoadingAndSavingUtils.save_map(world, TARGET_MAP):
            raise RuntimeError("Cannot save independent lighting preview map")
        if digest(source_file) != source_map_sha256:
            raise RuntimeError("Source map package changed during SaveAs")
        if not target_file.is_file() or target_file.stat().st_size == 0:
            raise RuntimeError("Native SaveAs did not create a target map package")
        saved_target = unreal.load_asset(TARGET_MAP)
        if (not saved_target or saved_target.get_class().get_name() != "World" or
                saved_target.get_path_name().split(".")[0] != TARGET_MAP):
            raise RuntimeError("Saved target World identity readback failed")
        result.update(passed=True, imported_texture_count=len(textures), bound_instances=len(result["bindings"]),
                      original_map_unchanged=True, hero_materials_unchanged=True,
                      source_map_sha256_before=source_map_sha256, source_map_sha256_after=digest(source_file),
                      target_map_sha256=digest(target_file), target_world=saved_target.get_path_name(),
                      save_policy="native SaveMap SaveAs, no Python editor map switch",
                      gpu_visual_parity_verified=False, packaged_platforms_verified=False)
        report("apply-result.json", result)
        unreal.log("HCZS source hall diffuse lightmap port saved: " + TARGET_MAP)
    except Exception:
        result["error"] = traceback.format_exc()
        report("apply-result.json", result)
        raise


def main():
    plan = build_plan()
    report("plan.json", plan)
    if os.environ.get("HCZS_UE_HALL_LIGHTING_APPLY") == "1":
        apply(plan)
    else:
        print(json.dumps(dict(passed=True, maps=10, bindings=len(plan["bindings"]),
                              deferred=len(plan["deferred_bindings"]), applied=False, target=TARGET_MAP)))


if __name__ == "__main__":
    main()
