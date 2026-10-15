"""Prepare the original home-scene FX sources, without executing game or UE.

The original effect tree remains authoritative. Runtime adaptations are kept
separate from source fields, especially for unknown native blend enums/tracks.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import lookup_logical, read_catalogue

OUT = ROOT / "analysis/unreal/hall-fx"
SCENE_PATH = "scene/midgard_home_3d/midgard_home_3d.scn"
SCENE_SHA = "2eda711687e3461c1021be8bab3c339fc025fe5fc05ce8f0d0bc90932289c58b"
REA_IDS = ["ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220",
           "ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree(element):
    return {"tag": element.tag, "attributes": dict(element.attrib),
            "children": [tree(child) for child in element]}


def vec(value):
    values = [float(v) for v in value.split(",")]
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Nonfinite source vector")
    return values


def main():
    apk = ROOT / "heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk"
    if sha(apk) != APK_SHA256:
        raise ValueError("APK identity changed")
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    sources, resources, texture_paths = {}, {}, {}

    def source(logical):
        logical = logical.replace("\\", "/")
        if logical not in sources:
            dest = OUT / "source" / (hashlib.sha256(logical.encode()).hexdigest()[:20] + Path(logical).suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            info = extract(apk, catalogue, logical, dest, APK_SHA256)
            sources[logical] = {"logical": logical, "path": str(dest.resolve()),
                                "sha256": sha(dest), "provenance": info}
        return Path(sources[logical]["path"])

    scene_file = source(SCENE_PATH)
    if sha(scene_file) != SCENE_SHA:
        raise ValueError("Reviewed source home scene changed")
    scene = ET.fromstring(scene_file.read_bytes())
    all_files = scene.find(".//AllFiles")
    files = {entry.tag.split("_", 1)[1]: entry.attrib for entry in all_files}
    instances = []
    for item in scene.findall(".//Fxes/sfx"):
        source_file = files[item.get("FilePathIndex")]
        path_values = [v.replace("\\", "/") for v in source_file.values() if v.lower().endswith(".sfx")]
        if len(path_values) != 1:
            raise ValueError("Expected unique scene SFX file attribute")
        instances.append({"attributes": item.attrib, "sfx": path_values[0]})
    if len(instances) != 9:
        raise ValueError("Reviewed source SFX instance count changed")
    queue = list(dict.fromkeys(row["sfx"] for row in instances))
    queue.append("effects/scene/zhujuejia_prop/fengling_benti.sfx")
    effects = []
    while queue:
        logical = queue.pop(0)
        if any(row["logical"] == logical for row in effects):
            continue
        if len(effects) >= 32:
            raise ValueError("FX traversal bound exceeded")
        fx = ET.fromstring(source(logical).read_bytes().decode("gb18030"))
        rendered = []
        def walk(element, ancestry, ignored=False):
            ignored = ignored or element.get("FxIgnore") == "TRUE"
            if element.tag in ("Sprite", "Model", "ParticleSystem", "ParticleRes"):
                rendered.append({"kind": element.tag, "ignored": ignored,
                                 "attributes": element.attrib,
                                 "ancestors": ancestry, "tree": tree(element)})
            next_ancestry = ancestry + [{"tag": element.tag, "attributes": element.attrib,
                                        "tracks": [tree(e) for e in element if e.tag.startswith("Track")]}]
            for child in element:
                walk(child, next_ancestry, ignored)
        walk(fx, [])
        effects.append({"logical": logical, "source": sources[logical], "tree": tree(fx),
                        "rendered_nodes": rendered})
        for e in fx.iter():
            for value in e.attrib.values():
                ref = value.replace("\\", "/")
                if not ref.lower().endswith((".gim", ".sfx", ".tga", ".dds", ".png", ".fx")):
                    continue
                if ref in resources:
                    continue
                choices = [ref]
                if Path(ref).suffix.lower() in (".tga", ".dds", ".png"):
                    choices.append(str(Path(ref).with_suffix(".ktx")).replace("\\", "/"))
                available = [(p, lookup_logical(catalogue, p)) for p in choices]
                nonempty = [(p, rows) for p, rows in available if rows]
                record = {"logical": ref, "candidates": [{"path": p, "matches": len(rows)} for p, rows in available]}
                if not nonempty:
                    record.update(status="missing-within-explicit-path-candidates")
                elif len(nonempty[0][1]) != 1:
                    record.update(status="ambiguous")
                else:
                    selected = nonempty[0][0]
                    record.update(status="present", selected=selected, source=sources.get(selected))
                    file = source(selected)
                    record["source"] = sources[selected]
                    if selected.endswith(".ktx"):
                        texture_paths[ref] = file
                    elif selected.endswith(".gim"):
                        gim = ET.fromstring(file.read_bytes())
                        record["gim_tree"] = tree(gim)
                        for suffix in (".mesh", ".mtg", ".gisacl"):
                            sibling = selected[:-4] + suffix
                            match = lookup_logical(catalogue, sibling)
                            record.setdefault("siblings", []).append({"logical": sibling, "matches": len(match),
                                "purpose": "explicit sibling convention; animation name resolution not established"})
                    elif selected.endswith(".sfx"):
                        queue.append(selected)
                resources[ref] = record
    textures = []
    for logical, file in sorted(texture_paths.items()):
        key = hashlib.sha256(logical.encode()).hexdigest()[:20]
        decoded = convert([file], OUT / "decoded" / key, DEFAULT_DECODER, inspector=DEFAULT_INSPECTOR)
        meta = decoded["textures"][0]
        if len(meta["outputs"]) != 1:
            raise ValueError("Expected one 2D FX texture")
        raw_png = ROOT / meta["outputs"][0]["png"]
        png = OUT / "textures" / (Path(logical).stem + "_" + key[:6] + ".png")
        png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw_png, png)
        pixels = Image.open(png).convert("RGBA")
        textures.append({"logical": logical, "png": str(png.resolve()), "png_sha256": sha(png),
                         "selected": resources[logical]["selected"], "source_sha256": sha(file),
                         "size": list(pixels.size), "alpha_range": list(pixels.getchannel("A").getextrema()),
                         "decode": meta})
    sheet = Image.new("RGB", (700, 400), (24, 28, 40))
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(textures):
        image = Image.open(row["png"]).convert("RGBA")
        image.thumbnail((145, 140))
        column, line = index % 4, index // 4
        sheet.paste(image, (column*175+(175-image.width)//2, line*200+20), image)
        draw.text((column*175+6, line*200+165), Path(row["logical"]).stem, fill=(225,225,235))
    sheet.save(OUT / "contact-sheet.png")
    sunlight = next(e for e in effects if e["logical"] == "effects/scene/zhujuejia_yangguang.sfx")
    particle = next(e for e in sunlight["rendered_nodes"] if e["kind"] == "ParticleSystem")
    instance = next(e for e in instances if e["sfx"] == sunlight["logical"])
    position, offset, scale = (vec(instance["attributes"]["Position"]),
                               vec(particle["attributes"]["PosOffset"]), vec(instance["attributes"]["Scale"]))
    emission = [position[i] + offset[i] * scale[i] for i in range(3)]
    # The current aligned UE map has a single world-Y reflection after
    # Interchange's source Y-up to UE Z-up conversion.
    adapted_position = [emission[0]*100, -emission[2]*100, emission[1]*100]
    preview = {"scope": "source sunlight particle input for a temporary runtime adaptation",
               "sfx": sunlight["logical"], "attributes": particle["attributes"], "tree": particle["tree"],
               "source_instance": instance["attributes"], "source_emitter_position": emission,
               "aligned_ue_position_cm": adapted_position,
               "position_policy": "scene scale + source local offset, then (X,-Z,Y)*100 for current aligned map; native projection unverified",
               "notes": ["Do not use Shiranui fan effects for Elsa",
                         "Native EmissionType=4 geometry and reversed min/max velocity remain unresolved",
                         "BlendMode=2/8 values preserved, no equivalence to UE blend mode asserted",
                         "Source color list appears ARGB; runtime reconstruction uses explicitly recorded adaptation",
                         "Use original textures, source rate/lifetime/color keys; label any substitute emission geometry or interpolation"]}
    report = {"schemaVersion": 1, "apk_sha256": APK_SHA256, "scene_sha256": SCENE_SHA,
              "evidence_kind": "ordinary source extraction/XML parsing/ASTC decoding, not new REA Evidence or original execution",
              "rea_context_evidence_ids": REA_IDS, "instances": instances, "effects": effects,
              "resources": list(resources.values()), "textures": textures, "sources": list(sources.values()),
              "sunlight_preview": preview,
              "summary": {"scene_instances": len(instances), "effect_files": len(effects),
                          "model_nodes": sum(n["kind"] == "Model" for e in effects for n in e["rendered_nodes"]),
                          "sprite_nodes": sum(n["kind"] == "Sprite" for e in effects for n in e["rendered_nodes"]),
                          "particle_system_nodes": sum(n["kind"] == "ParticleSystem" for e in effects for n in e["rendered_nodes"]),
                          "decoded_textures": len(textures)},
              "limitations": ["Source loop/track/lifecycle enums preserved but not executed",
                              "Animated leaf models need source skeleton/ACL conversion; static geometry cannot establish motion",
                              "Source sprites need native direction/axis-angle/blend semantics validation",
                              "No UE asset imported or map changed by this tool",
                              "Sunlight particle is the source asset candidate; runtime application is not yet verified"]}
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), "utf8")
    (OUT / "sunlight-preview.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2, allow_nan=False), "utf8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
