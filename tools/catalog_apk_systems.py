"""Rebuild the APK's system catalogue from retained, source-bound indexes.

This inventories all script paths and UI namespaces; it does not execute the
APK or claim that a matching filename proves a feature's behavior is restored.
No Markdown, extracted asset, save, database, or Unreal project is modified.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_APK = "aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4"
SOURCE_FILES = {
    "scripts": "analysis/assets/decoded/script/index.json",
    "packs": "analysis/assets/npk_catalogue.json",
    "apk_inventory": "analysis/assets/inventory.json",
    "integrity": "analysis/goal-alignment/integrity.json",
}


def read_source(relative):
    raw = (ROOT / relative).read_bytes()
    return json.loads(raw), {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    data, sources = {}, {}
    for name, path in SOURCE_FILES.items():
        data[name], sources[name] = read_source(path)
    if data["integrity"]["apk_sha256"] != EXPECTED_APK:
        raise ValueError("The retained source integrity record belongs to a different APK")
    scripts = data["scripts"]
    packages, ui, cdata = defaultdict(list), defaultdict(list), []
    for entry in scripts:
        path = entry["filename"].replace("\\", "/")
        decoded_sha256 = entry.get("decoded_sha256")
        if not decoded_sha256:
            decoded_path = (ROOT / entry["output"]).resolve()
            if not decoded_path.is_relative_to(ROOT / "analysis/assets/decoded/script"):
                raise ValueError("Decoded source escapes its retained script directory")
            decoded_sha256 = hashlib.sha256(decoded_path.read_bytes()).hexdigest()
        row = {
            "module_index": entry["index"], "source_path": path,
            "marshal_path": entry["output"].replace("\\", "/"),
            "decoded_sha256": decoded_sha256,
            "payload_sha256": entry["payload_sha256"],
        }
        packages[path.split("/")[0]].append(row)
        if path.startswith("ui/"):
            ui[path.split("/")[1]].append(row)
        if path.startswith("common/cdata/"):
            cdata.append(row)
    for rows in (*packages.values(), *ui.values(), cdata):
        rows.sort(key=lambda row: (row["source_path"], row["module_index"]))
    # Keep every namespace, including unimplemented and unfamiliar systems.
    report = {
        "schema": "hczs-apk-system-catalogue-v1", "apk_sha256": EXPECTED_APK,
        "evidence_kind": "Ordinary-tool metadata survey of retained APK indexes",
        "original_apk_executed": False,
        "source_pins": sources,
        "counts": {
            "apk_zip_entries": data["apk_inventory"]["member_count"],
            "npk_archives": len(data["packs"]),
            "npk_index_entries": sum(pack["count"] for pack in data["packs"]),
            "decoded_script_entries": len(scripts),
            "unique_script_paths": len(set(row["filename"] for row in scripts)),
            "cdata_script_entries": len(cdata),
            "ui_script_entries": sum(map(len, ui.values())),
            "ui_system_folders": sum(name.startswith("ui_") for name in ui),
        },
        "npk_archives": [{"member": pack["member"], "entries": pack["count"]} for pack in data["packs"]],
        "loose_resources": data["apk_inventory"]["extensions"],
        "script_packages": {key: {"count": len(rows), "modules": rows} for key, rows in sorted(packages.items())},
        "ui_systems": {key: {"count": len(rows), "modules": rows} for key, rows in sorted(ui.items())},
        "configuration_modules": cdata,
        "limitations": [
            "Counts describe index entries, not distinct models, heroes, complete features, or recovery percentages.",
            "Matching names establish candidate source locations; behavior still needs bytecode and resource tracing.",
            "Decoded script records are not full source decompilation or original runtime verification.",
            "The APK's offline inventory cannot prove that all historical hot-update content is present.",
        ],
    }
    target = ROOT / "analysis/apk-systems/catalog.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"output": target.relative_to(ROOT).as_posix(), **report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
