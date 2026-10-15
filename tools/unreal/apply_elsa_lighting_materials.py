"""Give an Elsa actor independent UE lighting-preview material overrides.

Call apply_elsa_lighting_materials(actor) in the editor after loading the new
lighting-preview map. This module never loads/saves a level, launches UE, or
changes the original skeletal mesh/materials/textures. The result is UE Default
Lit input verification, not a reconstruction of the NeoX shading models.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "analysis/elsa-hall/elsa-hall-idle.colour-reference.glb"
SOURCE_SHA256 = "823397c87ae22bbdaa1fc20b07352da0b2b3a252d0f755fb1998dd5d2578b193"
DEST = "/Game/Recovered/Elsa/LightingPreview"
REPORT = ROOT / "analysis/unreal/elsa-material/lighting-preview-result.json"
SCHEMA = "hczs-elsa-ue-lit-input-preview-v1"
NAMES = ("hair_yinying", "yifu", "siwa", "hair", "body", "eye", "eye_yinying", "head", "eye_nei")

# Deliberately temporary lighting-inspection settings. The original per-pixel
# roughness, skin LUT, stocking density and anisotropic hair are separate ports.
ROUGHNESS = {"yifu": .62, "siwa": .75, "hair": .55, "body": .65, "eye": .20, "head": .65, "eye_nei": .65}
SPECULAR = {"yifu": .28, "siwa": .20, "hair": .30, "body": .22, "eye": .15, "head": .22, "eye_nei": .22}


def build_plan():
    payload = SOURCE.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError("Reviewed original-colour Elsa GLB changed")
    if payload[:4] != b"glTF" or struct.unpack_from("<II", payload, 4) != (2, len(payload)):
        raise ValueError("Invalid source GLB envelope")
    size, kind = struct.unpack_from("<II", payload, 12)
    if kind != 0x4E4F534A or size > len(payload) - 20:
        raise ValueError("Invalid source GLB JSON")
    doc = json.loads(payload[20:20 + size])
    if len(doc["materials"]) != 9 or len(doc["images"]) != 7:
        raise ValueError("Source material/colour inventory changed")
    rows = []
    for slot, material in enumerate(doc["materials"]):
        original = material["extras"]["sourceMaterial"]
        if original["slot"] != slot or original["name"] != NAMES[slot]:
            raise ValueError("Source material slot identity changed")
        pbr = material["pbrMetallicRoughness"]
        image = doc["images"][doc["textures"][pbr["baseColorTexture"]["index"]]["source"]]
        overlay = slot in (0, 6)
        rows.append({
            "source_slot": slot, "name": NAMES[slot],
            "source_material": original,
            "source_colour": image["extras"],
            "texture": "/Game/Recovered/Elsa/" + image["name"],
            "tint": pbr["baseColorFactor"],
            "blend": material["alphaMode"],
            "alpha_cutoff": material.get("alphaCutoff", 0),
            "two_sided": material["doubleSided"],
            "preview_shading_model": "Unlit original-colour overlay" if overlay else "UE Default Lit",
            "roughness": None if overlay else ROUGHNESS[NAMES[slot]],
            "specular": None if overlay else SPECULAR[NAMES[slot]],
            "metallic": None if overlay else 0,
            "emissive_fill": None if overlay else .035,
            "normal_connected": False,
            "source_shadow_map_disabled": original.get("macros", {}).get("DISABLE_SHADOW_MAP") == "TRUE",
        })
    return {"schema": SCHEMA, "source_glb_sha256": SOURCE_SHA256, "slots": rows,
            "source_maps_preserved": True,
            "normal_policy": "Retain imported vertex normals; no normal maps before source/UE TBN comparison",
            "original_neox_shading_restored": False}


def _recipe_digest(row):
    return hashlib.sha256(json.dumps({"schema": SCHEMA, "slot": row}, sort_keys=True).encode("utf8")).hexdigest()


def _build_material(unreal, row, texture):
    editing = unreal.MaterialEditingLibrary
    name = "M_ElsaPreview_%02d_%s" % (row["source_slot"], row["name"])
    package = DEST + "/" + name
    recipe = _recipe_digest(row)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        material = unreal.load_asset(package)
        if (not isinstance(material, unreal.Material)
                or unreal.EditorAssetLibrary.get_metadata_tag(material, "HczsPreviewRecipeSHA256") != recipe):
            raise RuntimeError("Existing material is not this reviewed preview recipe: " + package)
        return material, False
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST, unreal.Material, unreal.MaterialFactoryNew())
    if not material:
        raise RuntimeError("Cannot create independent Elsa preview material")
    overlay = row["blend"] == "BLEND"
    material.set_editor_property("blend_mode", {
        "BLEND": unreal.BlendMode.BLEND_TRANSLUCENT,
        "MASK": unreal.BlendMode.BLEND_MASKED,
        "OPAQUE": unreal.BlendMode.BLEND_OPAQUE,
    }[row["blend"]])
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT if overlay else unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    material.set_editor_property("two_sided", row["two_sided"])
    material.set_editor_property("opacity_mask_clip_value", row["alpha_cutoff"])
    editing.set_base_material_usage(material, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH, True)

    def node(kind, x, y, **properties):
        result = editing.create_material_expression(material, kind, x, y)
        if not result:
            raise RuntimeError("Cannot create material expression")
        for key, value in properties.items():
            result.set_editor_property(key, value)
        return result

    def link(source, output, target, input_name):
        if not editing.connect_material_expressions(source, output, target, input_name):
            raise RuntimeError("Material expression connection failed: " + input_name)

    def property_link(expression, output, property_id):
        if not editing.connect_material_property(expression, output, property_id):
            raise RuntimeError("Material property connection failed: " + str(property_id))

    sample = node(unreal.MaterialExpressionTextureSampleParameter2D, -900, -150,
                  parameter_name="OriginalBaseColor", texture=texture,
                  sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    tint = node(unreal.MaterialExpressionVectorParameter, -900, 150,
                parameter_name="OriginalColourReferenceTint", default_value=unreal.LinearColor(*row["tint"]))
    colour = node(unreal.MaterialExpressionMultiply, -600, -120)
    link(sample, "RGB", colour, "A")
    link(tint, "RGB", colour, "B")
    property_link(colour, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR if overlay else unreal.MaterialProperty.MP_BASE_COLOR)
    if row["blend"] == "BLEND":
        property_link(sample, "A", unreal.MaterialProperty.MP_OPACITY)
    elif row["blend"] == "MASK":
        property_link(sample, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    if not overlay:
        for y, parameter, value, property_id in (
            (150, "PreviewRoughness", row["roughness"], unreal.MaterialProperty.MP_ROUGHNESS),
            (250, "PreviewSpecular", row["specular"], unreal.MaterialProperty.MP_SPECULAR),
            (350, "PreviewMetallic", 0, unreal.MaterialProperty.MP_METALLIC),
        ):
            scalar = node(unreal.MaterialExpressionScalarParameter, -350, y,
                          parameter_name=parameter, default_value=value)
            property_link(scalar, "", property_id)
        fill = node(unreal.MaterialExpressionScalarParameter, -650, 500,
                    parameter_name="PreviewEmissiveFill", default_value=row["emissive_fill"])
        fill_colour = node(unreal.MaterialExpressionMultiply, -350, -120)
        link(colour, "", fill_colour, "A")
        link(fill, "", fill_colour, "B")
        property_link(fill_colour, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    errors = list(editing.recompile_material(material))
    if errors:
        raise RuntimeError("Elsa preview shader compile errors: " + repr(errors))
    unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsPreviewRecipeSHA256", recipe)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsSourceGLBSHA256", SOURCE_SHA256)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "HczsShadingScope", "UE input lighting preview; original NeoX algorithms not restored")
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("Cannot save independent lighting-preview material")
    return material, True


def apply_elsa_lighting_materials(actor, normal_strength=0.0):
    """Create nine separate assets and override this actor; caller saves its map.

    normal_strength is intentionally zero-only until the original normal/TBN
    relationship is verified. Enabling guessed green-channel inversion would
    hide an untested coordinate conversion.
    """
    import unreal
    if not math.isfinite(normal_strength) or normal_strength != 0:
        raise ValueError("Source/UE tangent basis is not verified; normal_strength must remain zero")
    if not actor or actor.get_actor_label() != "HCZS_elsa":
        raise ValueError("Expected the independently placed HCZS_elsa actor")
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    mesh = unreal.load_asset("/Game/Recovered/Elsa/elsa")
    if not component or not mesh or component.get_num_bones() != 180 or component.get_num_materials() != 9:
        raise RuntimeError("Expected actual imported Elsa 180-bone/9-slot actor")
    if component.get_skinned_asset() != mesh:
        raise RuntimeError("Actor does not use the reviewed Elsa mesh")
    mesh_materials_before = [m.get_editor_property("material_interface").get_path_name() for m in mesh.get_editor_property("materials")]
    plan = build_plan()
    originals, textures = {}, {}
    # Validate every source slot and texture before producing any override.
    for component_slot in range(9):
        original = component.get_material(component_slot)
        source_slot = None
        for row in plan["slots"]:
            source_name = "%d__%s__colour_reference_" % (row["source_slot"], row["name"])
            preview_name = "M_ElsaPreview_%02d_%s" % (row["source_slot"], row["name"])
            if original and original.get_name() in (source_name, preview_name):
                source_slot = row["source_slot"]
                break
        if source_slot is None or source_slot in originals:
            raise RuntimeError("Component material mapping changed at slot " + str(component_slot))
        originals[source_slot] = (component_slot, original.get_path_name())
    for row in plan["slots"]:
        texture = unreal.load_asset(row["texture"])
        if not isinstance(texture, unreal.Texture2D) or not texture.get_editor_property("srgb"):
            raise RuntimeError("Expected original GLB sRGB-encoded colour texture: " + row["texture"])
        textures[row["source_slot"]] = texture
    result = {**plan, "engine_version": unreal.SystemLibrary.get_engine_version(),
              "actor": actor.get_path_name(), "mesh": mesh.get_path_name(), "results": [], "passed": False,
              "level_saved_by_this_script": False, "evidence_kind": "UE Python material compile and property readback; not REA execution evidence"}
    for row in plan["slots"]:
        material, created = _build_material(unreal, row, textures[row["source_slot"]])
        component_slot, old_path = originals[row["source_slot"]]
        component.set_material(component_slot, material)
        if component.get_material(component_slot) != material:
            raise RuntimeError("Component material override readback failed")
        result["results"].append({"source_slot": row["source_slot"], "component_slot": component_slot,
                                  "original_component_material": old_path, "preview_material": material.get_path_name(),
                                  "created": created, "graph_nodes": unreal.MaterialEditingLibrary.get_num_material_expressions(material),
                                  "shading_model": str(material.get_editor_property("shading_model")),
                                  "blend_mode": str(material.get_editor_property("blend_mode")),
                                  "two_sided": material.get_editor_property("two_sided"),
                                  "alpha_cutoff": material.get_editor_property("opacity_mask_clip_value")})
    mesh_materials_after = [m.get_editor_property("material_interface").get_path_name() for m in mesh.get_editor_property("materials")]
    if mesh_materials_before != mesh_materials_after or hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("Source mesh material assignment or GLB changed")
    result["original_mesh_materials_unchanged"] = True
    result["passed"] = True
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    unreal.log("HCZS Elsa independent lighting-preview materials applied: " + str(REPORT))
    return result


if __name__ == "__main__":
    print(json.dumps(build_plan(), ensure_ascii=False, indent=2))
