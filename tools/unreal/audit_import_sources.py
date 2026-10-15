"""Audit recovered GLB lineage and embedded image sizes without opening Unreal."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "analysis/unreal/import-inputs"
OUT = ROOT / "analysis/unreal/plan/source-audit.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(relative):
    return json.loads((ROOT / relative).read_text("utf8"))


def glb_inventory(path):
    data = path.read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<II", data, 4) != (2, len(data)):
        raise ValueError("Invalid GLB envelope")
    size, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("Missing GLB JSON chunk")
    doc = json.loads(data[20:20 + size])
    binary_at = 20 + size
    binary_size, binary_kind = struct.unpack_from("<II", data, binary_at)
    if binary_kind != 0x004E4942 or binary_at + 8 + binary_size != len(data):
        raise ValueError("Invalid embedded GLB BIN chunk")
    binary = data[binary_at + 8:]
    images = []
    for image in doc.get("images", []):
        view = doc["bufferViews"][image["bufferView"]]
        begin, length = view.get("byteOffset", 0), view["byteLength"]
        pixels = binary[begin:begin + length]
        if pixels[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Recovered handoff image is not embedded PNG")
        images.append(dict(name=image.get("name"), dimensions=list(struct.unpack_from(">II", pixels, 16)),
                           png_sha256=hashlib.sha256(pixels).hexdigest()))
    materials = [dict(name=m.get("name"), alpha_mode=m.get("alphaMode", "OPAQUE"),
                      unlit="KHR_materials_unlit" in m.get("extensions", {}),
                      double_sided=m.get("doubleSided", False)) for m in doc.get("materials", [])]
    accessors = doc["accessors"]
    primitives = [p for m in doc["meshes"] for p in m["primitives"]]
    return dict(
        sha256=hashlib.sha256(data).hexdigest(), vertices=sum(accessors[p["attributes"]["POSITION"]]["count"] for p in primitives),
        triangles=sum(accessors[p["indices"]]["count"] // 3 for p in primitives),
        meshes=len(doc["meshes"]), mesh_instances=sum("mesh" in n for n in doc["nodes"]),
        bones=[len(s["joints"]) for s in doc.get("skins", [])],
        animations=[dict(name=a.get("name"), channels=len(a["channels"])) for a in doc.get("animations", [])],
        images=images, materials=materials, extensions_used=doc.get("extensionsUsed", []),
    )


def verify_source(record):
    path = Path(record["sample_path"]).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or digest(path) != record["sha256"]:
        raise ValueError("Decoded APK source changed: " + str(path))
    return {k: record[k] for k in ("logical_path", "member", "index", "sha256", "apk_sha256") if k in record}


def main():
    manifest = load("analysis/unreal/import-inputs/manifest.json")
    inputs = {row["id"]: row for row in manifest["assets"]}
    audit = load("analysis/characters/shiranui/asset-audit.json")
    resolution = load("analysis/characters/shiranui/resolution-audit/report.json")
    hall_export = load("analysis/hall/midgard_home_3d/export.json")
    characters = []
    for identifier, folder, model_path in (
        ("shiranui", "export", "character/player/buzhihuo/buzhihuo_yangcheng.gim"),
        ("shiranui_weapon", "export-weapon", "character/player/buzhihuo/buzhihuo_weapon.gim"),
    ):
        row = inputs[identifier]
        glb = glb_inventory(BASE / row["file"])
        if glb["sha256"] != row["sha256"]:
            raise ValueError("Staged GLB hash mismatch")
        export_report = load("analysis/characters/shiranui/" + folder + "/export-report.json")
        sources = [verify_source(audit["sources"][model_path]), verify_source(audit["sources"][model_path[:-4] + ".mesh"])]
        image_hashes = {i["png_sha256"] for i in glb["images"]}
        texture_sources = []
        for texture_name, texture in export_report["textures"].items():
            png = Path(texture["gltf_png"])
            if digest(png) != texture["gltf_png_sha256"] or texture["gltf_png_sha256"] not in image_hashes:
                raise ValueError("Embedded image does not match converter output: " + texture_name)
            logical_ktx = str(Path(texture_name).with_suffix(".ktx")).replace("\\", "/")
            source = audit["sources"].get(logical_ktx)
            texture_sources.append(dict(original_texture_reference=texture_name,
                                        decoded_apk_source=verify_source(source) if source else None,
                                        original_png_dimensions=list(struct.unpack_from(">II", png.read_bytes(), 16)),
                                        colour_policy=texture["colour_policy"]))
        for animation in export_report["animations"]:
            sources.append(verify_source(animation["source"]))
        characters.append(dict(id=identifier, glb=glb, apk_sources=sources, textures=texture_sources,
                               source_reference_skin=export_report["reference_skin"], shader_limits=export_report["limits"]))
    hall = glb_inventory(BASE / inputs["hall_scene"]["file"])
    if hall["sha256"] != inputs["hall_scene"]["sha256"]:
        raise ValueError("Hall GLB hash mismatch")
    source_scope = {k: v for k, v in hall_export["scope"].items() if k != "sourceCameras"}
    result = dict(
        schema="hczs-unreal-source-audit-v1", evidence_kind="Ordinary static tool evidence; no new REA Evidence ID or original-client execution",
        apk_sha256=audit["apk_sha256"],
        geometry_origin="Decoded APK NeoX .gim/.mesh via common tools/recover_shiranui_hall.py + tools/export_shiranui_hall.py; not Cocos build output",
        source_bytes_changed=False, characters=characters,
        hall=dict(glb=hall, source_scope=source_scope, decoded_source_hashes=hall_export["sources"],
                  shader_status="glTF colour-reference materials; original NeoX lightmap, toon/emission and SFX need separate UE implementation"),
        shiranui_available_models=[{k: m[k] for k in ("id", "path", "vertices", "triangles", "bones")} for m in resolution["models"]],
        lod_statement="Selected row 530 is the highest geometry among these four recovered models; original runtime LOD selection is unobserved",
        validation=dict(byte_hashes_and_embedded_image_sizes_verified=True,
                        geometry_source_position_error_reported=resolution["exports"][0]["max_position_error"],
                        unreal_import_executed=False, visual_materials_verified=False),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(json.dumps(dict(passed=True, output=str(OUT), shiranui_vertices=characters[0]["glb"]["vertices"],
                          shiranui_triangles=characters[0]["glb"]["triangles"],
                          original_images=len(characters[0]["glb"]["images"]), unreal_import_executed=False)))


if __name__ == "__main__":
    main()
