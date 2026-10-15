"""Import five reviewed AI hall icons into an independent opt-in UE layout.

Run in the full Editor with -ExecutePythonScript. Outside UE, --validate-only
checks input hashes and the geometry recipe without editing PNGs or assets.
Existing assets are reused only if their complete own recipe matches exactly.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_LAYOUT = ROOT / "analysis/unreal/hall-ui/layout.json"
PROVENANCE = ROOT / "analysis/unreal/hall-ui/ai-icons/provenance.json"
AUDIT = ROOT / "analysis/unreal/hall-ui/ai-icons/audit.json"
REPORT = ROOT / "analysis/unreal/hall-ui/ai-icons/ue-import-result.json"
PLAN_REPORT = ROOT / "analysis/unreal/hall-ui/ai-icons/ue-input-plan.json"
BASE_ASSET = "/Game/Recovered/Hall/UI/HallLayout"
DEST = "/Game/Recovered/Hall/UI/AI"
LAYOUT_ASSET = DEST + "/HallLayoutHD"
RECIPE_VERSION = "hczs-hall-ai-icons-v1"
PINNED_SOURCE_LAYOUT = "815367f3f73b4580d88d94e24ec36ea9128b2110f7a8eb4054a54f01f30e643d"
PINNED_PROVENANCE = "135143e724c2b7c4b1f0a511b96c9d83771c600a3cdbad5769eea04d01a5c510"
PINNED_AUDIT = "e0f269815ce6d06ded2fffd4b3b8e860c7290d32f207c3071d6a96f58585aacf"
SELECTION = {"event": 2, "welfare": 2, "friends": 2, "mail": 1, "community": 1}
REVIEWED_INSTANCE_PREFIXES = ("Layer/Main/RightTop/SysBtn/",)
LABEL_STYLE_OVERRIDES = {}
OPTICAL_BOUNDS_POLICY = None
EXTERNAL_TEXTURE_REFERENCES = {}
TEXTURE_POLICY = {
    "lod_group": "TEXTUREGROUP_UI",
    "compression_settings": "TC_EDITOR_ICON",
    "mip_gen_settings": "TMGS_NO_MIPMAPS",
    "filter": "TF_BILINEAR",
    "srgb": True,
    "lod_bias": 0,
    "max_texture_size": 512,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verified_file(filename: str | Path, expected: str) -> Path:
    path = Path(filename).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Input outside repository: " + str(path))
    if digest(path.read_bytes()) != expected:
        raise ValueError("Input SHA256 differs: " + str(path))
    return path


def png_header(path: Path) -> dict:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("Not a PNG: " + str(path))
    width, height, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
    if bit_depth != 8 or color_type != 6:
        raise ValueError("Expected 8-bit RGBA PNG: " + str(path))
    return {"size": [width, height], "bitDepth": bit_depth, "colorType": color_type}


def point(matrix: list, x: float, y: float) -> list:
    a, b, c, d, tx, ty = matrix
    return [a * x + c * y + tx, b * x + d * y + ty]


def transformed_geometry(item: dict, adjustment: dict) -> dict:
    geometry = copy.deepcopy(item["geometry"])
    a, b, c, d, tx, ty = geometry["matrix"]
    width, height = item["size"]
    sx, sy = adjustment["fullCanvasScaleXY"]
    ox, oy = adjustment["fullCanvasOffsetXY"]
    values = [a, b, c, d, tx, ty, width, height, sx, sy, ox, oy]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise ValueError("Nonfinite geometry")
    if width <= 0 or height <= 0 or not (0.5 <= sx <= 2.5 and 0.5 <= sy <= 2.5):
        raise ValueError("Unexpected source geometry or AI alignment scale")
    matrix = [a * sx, b * sx, c * sy, d * sy,
              tx + a * width * ox + c * height * oy,
              ty + b * width * ox + d * height * oy]
    corners = [point(matrix, x, y) for x, y in [(0, 0), (width, 0), (width, height), (0, height)]]
    xs, ys = [p[0] for p in corners], [p[1] for p in corners]
    geometry.update(matrix=matrix, corners=corners,
                    bounds=[min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)])
    return geometry


def alignment_error(item: dict, new_geometry: dict, source_box: list, generated_box: list) -> float:
    width, height = item["size"]
    old_matrix, new_matrix = item["geometry"]["matrix"], new_geometry["matrix"]
    corner_indices = [(0, 1), (2, 1), (2, 3), (0, 3)]
    errors = []
    for xi, yi in corner_indices:
        old = point(old_matrix, source_box[xi] * width, source_box[yi] * height)
        new = point(new_matrix, generated_box[xi] * width, generated_box[yi] * height)
        errors.append(math.dist(old, new))
    return max(errors)


def load_plan() -> dict:
    verified_file(SOURCE_LAYOUT, PINNED_SOURCE_LAYOUT)
    verified_file(PROVENANCE, PINNED_PROVENANCE)
    verified_file(AUDIT, PINNED_AUDIT)
    layout = json.loads(SOURCE_LAYOUT.read_text(encoding="utf-8"))
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if audit["provenanceSha256"] != PINNED_PROVENANCE or audit["pngMutation"] or audit["ueAssetMutation"]:
        raise ValueError("Audit source identity or read-only policy differs")
    if provenance["originalLayoutSha256"] != PINNED_SOURCE_LAYOUT:
        raise ValueError("AI provenance refers to another source layout")
    if layout["schemaVersion"] != 1 or layout["canvas"]["drawOrigin"] != "top-left":
        raise ValueError("Unknown source coordinate convention")
    if set(SELECTION) != {icon["name"] for icon in provenance["icons"]}:
        raise ValueError("Expected the five reviewed icons only")
    selections = []
    for name, version in SELECTION.items():
        icon = next(icon for icon in provenance["icons"] if icon["name"] == name)
        variant = next(variant for variant in icon["variants"] if variant["version"] == version)
        audited = next(icon for icon in audit["icons"] if icon["name"] == name)
        reviewed = next(variant for variant in audited["variants"] if variant["version"] == version)
        source = icon["source"]
        source_path = verified_file(source["png"], source["pngSha256"])
        ai_path = verified_file(variant["path"], variant["sha256"])
        if reviewed["sha256"] != variant["sha256"] or audited["source"]["sha256"] != source["pngSha256"]:
            raise ValueError("Audit input hash differs: " + name)
        header = png_header(ai_path)
        if header["size"] != reviewed["size"]:
            raise ValueError("Audited PNG size differs: " + name)
        items = [item for item in layout["previewDrawItems"]
                 if item["kind"] == "sprite" and item["spriteId"] == source["spriteId"]]
        if len(items) != 1:
            raise ValueError("Expected exactly one reviewed top-bar sprite: " + name)
        item = items[0]
        if not any(item["instancePath"].startswith(prefix) for prefix in REVIEWED_INSTANCE_PREFIXES) or item["flipX"] or item["flipY"]:
            raise ValueError("Unexpected reviewed sprite transform: " + name)
        adjustment = reviewed["adaptation"]
        if adjustment["method"] != "review-only-source-alpha128-alignment":
            raise ValueError("Unexpected alignment recipe")
        reference_box = audited["source"]["alpha128BBoxNormalized"]
        if OPTICAL_BOUNDS_POLICY and name in OPTICAL_BOUNDS_POLICY["names"]:
            width, height = item["size"]
            x0, y0, x1, y1 = reference_box
            body_width, body_height = (x1 - x0) * width, (y1 - y0) * height
            scale = min(math.sqrt(OPTICAL_BOUNDS_POLICY["targetBBoxArea"] / (body_width * body_height)),
                        OPTICAL_BOUNDS_POLICY["maxEdge"] / max(body_width, body_height))
            target_width, target_height = body_width * scale, body_height * scale
            reference_box = [0.5 - target_width / width / 2, 0.5 - target_height / height / 2,
                             0.5 + target_width / width / 2, 0.5 + target_height / height / 2]
            gx0, gy0, gx1, gy1 = reviewed["alpha128BBoxNormalized"]
            sx, sy = (reference_box[2] - reference_box[0]) / (gx1 - gx0), (reference_box[3] - reference_box[1]) / (gy1 - gy0)
            adjustment = {**adjustment, "fullCanvasScaleXY": [sx, sy],
                          "fullCanvasOffsetXY": [reference_box[0] - gx0 * sx, reference_box[1] - gy0 * sy],
                          "groupOpticalPolicy": OPTICAL_BOUNDS_POLICY,
                          "targetBodySizeDesignPixels": [target_width, target_height],
                          "targetBBoxNormalized": reference_box}
        new_geometry = transformed_geometry(item, adjustment)
        error = alignment_error(item, new_geometry,
                                reference_box,
                                reviewed["alpha128BBoxNormalized"])
        if error > 1e-8:
            raise ValueError("AI padding alignment differs: " + name)
        selections.append({
            "name": name, "label": icon["label"], "version": version,
            "spriteId": source["spriteId"], "drawItemId": item["id"],
            "sourcePNG": str(source_path), "sourcePNG_SHA256": source["pngSha256"],
            "sourceFrame": source["sourceFrame"], "sourceAPK_SHA256": source["apkSha256"],
            "aiPNG": str(ai_path), "aiPNG_SHA256": variant["sha256"],
            "aiSourceSize": header["size"], "texturePolicy": TEXTURE_POLICY,
            "alignment": adjustment, "originalSize": item["size"],
            "originalGeometry": item["geometry"], "alignedGeometry": new_geometry,
            "opaqueBBoxAlignmentErrorPixels": error,
        })
    return {"schemaVersion": 1, "recipeVersion": RECIPE_VERSION,
            "sourceLayoutSHA256": PINNED_SOURCE_LAYOUT, "provenanceSHA256": PINNED_PROVENANCE,
            "auditSHA256": PINNED_AUDIT, "selections": selections,
            "pngMutation": False, "originalLayoutMutation": False,
            "geometryPolicy": "full original widget size; affine padding adjustment; no pixel crop or alpha rewrite"}


def metadata_matches(unreal, asset, recipe_sha: str, expected: dict) -> None:
    if unreal.EditorAssetLibrary.get_metadata_tag(asset, "HczsAIRecipeSHA256") != recipe_sha:
        raise RuntimeError("Existing AI asset has another recipe; not overwritten: " + asset.get_path_name())
    for key, value in expected.items():
        if unreal.EditorAssetLibrary.get_metadata_tag(asset, key) != value:
            raise RuntimeError("Existing AI asset source differs for " + key + ": " + asset.get_path_name())


def set_metadata(unreal, asset, recipe: dict, identity: dict) -> None:
    unreal.EditorAssetLibrary.set_metadata_tag(asset, "HczsAIRecipeSHA256", digest(canonical(recipe).encode("utf-8")))
    unreal.EditorAssetLibrary.set_metadata_tag(asset, "HczsAIRecipe", canonical(recipe))
    for key, value in identity.items():
        unreal.EditorAssetLibrary.set_metadata_tag(asset, key, value)


def texture_settings(unreal) -> dict:
    return {
        "lod_group": unreal.TextureGroup.TEXTUREGROUP_UI,
        "compression_settings": unreal.TextureCompressionSettings.TC_EDITOR_ICON,
        "mip_gen_settings": unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS,
        "filter": unreal.TextureFilter.TF_BILINEAR,
        "srgb": True, "lod_bias": 0, "max_texture_size": 512,
    }


def import_texture(unreal, row: dict, project_content: Path) -> tuple:
    if row['name'] in EXTERNAL_TEXTURE_REFERENCES:
        package = EXTERNAL_TEXTURE_REFERENCES[row['name']]
        texture = unreal.load_asset(package)
        if not texture or texture.get_class().get_name() != 'Texture2D':
            raise RuntimeError('Reviewed shared icon texture is missing: ' + package)
        if unreal.EditorAssetLibrary.get_metadata_tag(texture, 'HczsSourceSHA256') != row['aiPNG_SHA256']:
            raise RuntimeError('Shared icon texture image identity differs: ' + package)
        if any(texture.get_editor_property(key) != value for key, value in texture_settings(unreal).items()):
            raise RuntimeError('Shared icon texture sampling policy differs: ' + package)
        return texture, 'reused-reviewed-library'
    recipe = {"recipeVersion": RECIPE_VERSION, "sourceLayoutSHA256": PINNED_SOURCE_LAYOUT,
              "provenanceSHA256": PINNED_PROVENANCE, "selection": row}
    sha = digest(canonical(recipe).encode("utf-8"))
    folder = DEST + "/Sprites"
    name = f"T_AI_{row['name']}_v{row['version']}"
    package = folder + "/" + name
    identity = {"HczsAIGenerated": "true", "HczsAIRecipeVersion": RECIPE_VERSION,
                "HczsSourceLayoutSHA256": PINNED_SOURCE_LAYOUT,
                "HczsOriginalSpriteID": row["spriteId"],
                "HczsOriginalPNG_SHA256": row["sourcePNG_SHA256"],
                "HczsSourceSHA256": row["aiPNG_SHA256"],
                "HczsAIInputPNG_SHA256": row["aiPNG_SHA256"]}
    policy = texture_settings(unreal)
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        texture = unreal.load_asset(package)
        if not texture or texture.get_class().get_name() != "Texture2D":
            raise RuntimeError("Existing AI texture is another asset class")
        metadata_matches(unreal, texture, sha, identity)
        if any(texture.get_editor_property(key) != value for key, value in policy.items()):
            raise RuntimeError("Existing AI texture policy differs; not overwritten: " + package)
        return texture, "reused"
    physical_path = asset_file(project_content, package)
    if physical_path.exists():
        raise RuntimeError("Unregistered existing package retained: " + str(physical_path))
    task = unreal.AssetImportTask()
    for key, value in {"filename": row["aiPNG"], "destination_path": folder,
                       "destination_name": name, "automated": True,
                       "replace_existing": False, "save": False}.items():
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    textures = [asset for asset in task.get_objects() if asset.get_class().get_name() == "Texture2D"]
    if len(textures) != 1 or textures[0].get_path_name().split(".")[0] != package:
        raise RuntimeError("Expected exact one new AI texture at " + package)
    texture = textures[0]
    for key, value in policy.items():
        texture.set_editor_property(key, value)
    set_metadata(unreal, texture, recipe, identity)
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
        raise RuntimeError("Failed to save AI texture")
    return texture, "imported"


def asset_file(project_content: Path, package: str) -> Path:
    if not package.startswith("/Game/"):
        raise ValueError("Expected project asset package")
    path = (project_content / (package[len("/Game/"):] + ".uasset")).resolve()
    if not path.is_relative_to(project_content):
        raise ValueError("Package resolves outside active project Content")
    return path


def run_editor(plan: dict) -> dict:
    import unreal

    if "-run=" in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError("Use full Editor -ExecutePythonScript, not a Python commandlet")
    engine = unreal.SystemLibrary.get_engine_version()
    if not engine.startswith("5.8."):
        raise RuntimeError("Reviewed client uses UE 5.8; current engine is " + engine)
    project_content = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())).resolve()
    if not project_content.is_relative_to(ROOT):
        raise RuntimeError("Active project Content is outside hczs")
    base = unreal.load_asset(BASE_ASSET)
    if not base or base.get_class().get_name() != "HczsHallLayoutAsset":
        raise RuntimeError("Build HczsEditor and import original HallLayout first")
    if base.get_editor_property("SourceLayoutSha256") != PINNED_SOURCE_LAYOUT:
        raise RuntimeError("Original source layout identity differs")
    base_file = asset_file(project_content, BASE_ASSET)
    before_file_sha = digest(base_file.read_bytes())
    base_json = base.get_editor_property("LayoutJson")
    base_sprites = dict(base.get_editor_property("Sprites"))
    base_fonts = dict(base.get_editor_property("Fonts"))
    if len(base_sprites) != 37 or len(base_fonts) != 2:
        raise RuntimeError("Expected original 37 sprite / 2 font references")
    layout = json.loads(base_json)
    if layout.get("schemaVersion") != 1 or len(layout.get("items", [])) != 84:
        raise RuntimeError("Unexpected original runtime layout")
    transforms = []
    for row in plan["selections"]:
        targets = [item for item in layout["items"] if item.get("spriteId") == row["spriteId"]]
        if len(targets) != 1 or targets[0]["id"] != row["drawItemId"]:
            raise RuntimeError("Base asset differs from reviewed top-bar item")
        item = targets[0]
        if item["size"] != row["originalSize"] or item["geometry"] != row["originalGeometry"]:
            raise RuntimeError("Base top-bar geometry differs from source review")
        item["geometry"] = copy.deepcopy(row["alignedGeometry"])
        item["aiVariant"] = {"name": row["name"], "version": row["version"],
                             "sha256": row["aiPNG_SHA256"], "originalPNG_SHA256": row["sourcePNG_SHA256"]}
        transforms.append({"drawItemId": item["id"], "spriteId": row["spriteId"],
                           "before": row["originalGeometry"]["matrix"], "after": item["geometry"]["matrix"],
                           "sizeUnchanged": item["size"] == row["originalSize"],
                           "opaqueBBoxAlignmentErrorPixels": row["opaqueBBoxAlignmentErrorPixels"]})
    layout["aiIconPolicy"] = {"recipeVersion": RECIPE_VERSION, "optInPreview": True,
                              "aiGenerated": True, "recoveredOriginalHighResolutionDetail": False,
                              "sourceLayoutSHA256": PINNED_SOURCE_LAYOUT}
    styled_labels = []
    for label, properties in LABEL_STYLE_OVERRIDES.items():
        matches = [item for item in layout["items"] if item.get("kind") == "text"
                   and item.get("text") == label
                   and item.get("instancePath", "").startswith("Layer/Main/RightTop/SysBtn/")]
        if len(matches) != 1 or set(properties) - {"outlineEnabled", "outlineSize", "shadowEnabled"}:
            raise RuntimeError("Unreviewed label style override: " + label)
        matches[0].update(properties)
        styled_labels.append({"label": label, "drawItemId": matches[0]["id"], "properties": properties})
    if styled_labels:
        layout["aiIconPolicy"]["labelStyleOverrides"] = styled_labels
    hd_json = canonical(layout)
    recipe = {**plan, "baseRuntimeJSON_SHA256": digest(base_json.encode("utf-8")),
              "hdRuntimeJSON_SHA256": digest(hd_json.encode("utf-8")),
              "baseSprites": {key: value.get_path_name() for key, value in base_sprites.items()},
              "baseFonts": {key: value.get_path_name() for key, value in base_fonts.items()}}
    recipe_sha = digest(canonical(recipe).encode("utf-8"))
    identity = {"HczsAIGenerated": "true", "HczsAIRecipeVersion": RECIPE_VERSION,
                "HczsSourceLayoutSHA256": PINNED_SOURCE_LAYOUT,
                "HczsBaseRuntimeJSON_SHA256": recipe["baseRuntimeJSON_SHA256"],
                "HczsAIRuntimeJSON_SHA256": recipe["hdRuntimeJSON_SHA256"]}
    old = unreal.load_asset(LAYOUT_ASSET) if unreal.EditorAssetLibrary.does_asset_exist(LAYOUT_ASSET) else None
    if old:
        if old.get_class().get_name() != "HczsHallLayoutAsset":
            raise RuntimeError("Existing HD layout class differs")
        metadata_matches(unreal, old, recipe_sha, identity)
        if old.get_editor_property("LayoutJson") != hd_json:
            raise RuntimeError("Existing HD layout JSON differs; not overwritten")
    elif asset_file(project_content, LAYOUT_ASSET).exists():
        raise RuntimeError("Unregistered HD package retained")
    sprites = dict(base_sprites)
    imported = []
    for row in plan["selections"]:
        texture, action = import_texture(unreal, row, project_content)
        sprites[row["spriteId"]] = texture
        imported.append({"name": row["name"], "variant": row["version"], "action": action,
                         "asset": texture.get_path_name(), "sourcePNG": row["aiPNG"],
                         "sourceSHA256": row["aiPNG_SHA256"], "sourceSize": row["aiSourceSize"],
                         "reportedPlatformSize": [texture.blueprint_get_size_x(), texture.blueprint_get_size_y()],
                         "maxTextureSize": texture.get_editor_property("max_texture_size")})
    if old:
        asset = old
        saved_sprites = dict(asset.get_editor_property("Sprites"))
        saved_fonts = dict(asset.get_editor_property("Fonts"))
        if saved_sprites != sprites or saved_fonts != base_fonts or asset.get_editor_property("SourceLayoutSha256") != PINNED_SOURCE_LAYOUT:
            raise RuntimeError("Existing HD references differ; not overwritten")
        action = "reused"
    else:
        asset = unreal.EditorAssetLibrary.duplicate_asset(BASE_ASSET, LAYOUT_ASSET)
        if not asset:
            raise RuntimeError("Could not duplicate original layout to independent HD asset")
        asset.set_editor_property("LayoutJson", hd_json)
        asset.set_editor_property("Sprites", sprites)
        asset.set_editor_property("Fonts", base_fonts)
        asset.set_editor_property("SourceLayoutSha256", PINNED_SOURCE_LAYOUT)
        set_metadata(unreal, asset, recipe, identity)
        if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
            raise RuntimeError("Could not save independent HD layout")
        action = "created"
    saved = unreal.load_asset(LAYOUT_ASSET)
    if saved.get_editor_property("LayoutJson") != hd_json or dict(saved.get_editor_property("Sprites")) != sprites or dict(saved.get_editor_property("Fonts")) != base_fonts:
        raise RuntimeError("Saved HD asset readback differs")
    if base.get_editor_property("LayoutJson") != base_json or dict(base.get_editor_property("Sprites")) != base_sprites or dict(base.get_editor_property("Fonts")) != base_fonts:
        raise RuntimeError("Original in-memory layout changed unexpectedly")
    after_file_sha = digest(base_file.read_bytes())
    if after_file_sha != before_file_sha:
        raise RuntimeError("Original on-disk layout changed unexpectedly")
    return {"passed": True, "engine": engine, "projectContentDirectory": str(project_content),
            "layoutAsset": saved.get_path_name(), "layoutAction": action,
            "recipeVersion": RECIPE_VERSION, "recipeSHA256": recipe_sha,
            "sourceLayoutSHA256": PINNED_SOURCE_LAYOUT,
            "baseRuntimeJSON_SHA256": recipe["baseRuntimeJSON_SHA256"],
            "hdRuntimeJSON_SHA256": recipe["hdRuntimeJSON_SHA256"],
            "originalAssetFileSHA256Before": before_file_sha,
            "originalAssetFileSHA256After": after_file_sha, "originalLayoutUnchanged": True,
            "textures": imported, "drawItemTransforms": transforms,
            "labelStyleOverrides": styled_labels,
            "spriteReferences": len(sprites), "aiReplacedReferences": len(imported),
            "originalRetainedReferences": len(sprites) - len(imported), "fontReferencesRetained": len(base_fonts),
            "generatedPNGPixelsModified": False, "visualQualityVerified": False,
            "limitations": ["Opt-in AI display variants, not recovered original high resolution art.",
                            "Alpha128 alignment only; scattered low-alpha pixels are retained.",
                            "No gameplay or packaged-platform verification is claimed."]}


def main() -> None:
    try:
        plan = load_plan()
        if "--validate-only" in sys.argv:
            PLAN_REPORT.write_text(json.dumps({"passed": True, **plan}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"passed": True, "plan": str(PLAN_REPORT), "selectedIcons": len(plan["selections"]),
                              "maxAlignmentErrorPixels": max(row["opaqueBBoxAlignmentErrorPixels"] for row in plan["selections"]),
                              "pngMutation": False, "ueAssetMutation": False}, ensure_ascii=False))
            return
        result = run_editor(plan)
    except Exception as error:
        REPORT.write_text(json.dumps({"passed": False, "error": str(error), "recipeVersion": RECIPE_VERSION,
                                      "sourceAssetsIntentionallyModified": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    import unreal
    unreal.log("HCZS AI hall icon import saved " + str(REPORT))


if __name__ == "__main__":
    main()
