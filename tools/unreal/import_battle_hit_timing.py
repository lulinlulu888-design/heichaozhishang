"""Import/verify source-authored hit ratios on the existing battle DataAsset.

Ordinary Python --plan stages a hash-bound manifest. Full Editor invocation is
read-only unless its command line has -HczsBattleHitTimingApply. This tool never
launches UE, alters meshes/maps, or writes shared engine/source assets.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "clients/unreal5 5.8"
BASE = ROOT / "analysis/unreal/battle-hit-timing"
SOURCE = ROOT / "analysis/battle-visual/elsa-hit-timing/source-audit.json"
ASSET = "/Game/Recovered/Battle/BattleSceneAssets"
AGS_SHA = "12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729"
EXPECTED = {"fire_1": 0.230700, "crit_1": 0.281831, "fire_1_1": 0.350154, "fire_1_3": 0.409156}
CARDS = {"110001": ["fire_1"], "110009": ["crit_1"], "210003": ["fire_1"],
         "410101": ["fire_1_1", "fire_1_3"], "410102": ["fire_1"]}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def publish(name, value):
    BASE.mkdir(parents=True, exist_ok=True)
    destination = BASE / name
    if destination.exists():
        previous = destination.read_bytes()
        archive = BASE / "attempts" / (destination.stem + "-" + sha(previous)[:20] + ".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists() and archive.read_bytes() != previous:
            raise ValueError("Evidence archive hash collision")
        if not archive.exists():
            archive.write_bytes(previous)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", "utf8")


def plan():
    raw = SOURCE.read_bytes()
    source = json.loads(raw)
    if (source["mode"] != "elsa-authored-hit-timing-static-audit" or source["auditPassed"] is not True
            or source["originalApkExecuted"] is not False or source["originalEventTrackSource"]["sha256"] != AGS_SHA):
        raise ValueError("Need successful source-bound static timing audit")
    for entry in source["sources"]:
        filename = entry.get("path", entry.get("output"))
        if not filename:
            raise ValueError("Source audit identity has no file")
        target = (ROOT / filename).resolve()
        if not target.is_relative_to(ROOT.resolve()):
            raise ValueError("Source audit path outside project")
        if sha(target.read_bytes()) != entry.get("sha256", entry.get("decoded_sha256")):
            raise ValueError("Source audit file changed: " + filename)
    rows = {}
    for name, ratio in EXPECTED.items():
        clip = source["clips"][name]
        events = [e for e in clip["events"] if e["name"] == "attack"]
        if len(events) != 1 or events[0]["normalizedClipProgress"] != ratio:
            raise ValueError("Reviewed selected source hit ratio changed")
        event = events[0]
        rows[name] = dict(progress=ratio, duration_seconds=clip["durationSeconds"],
                          event_name="attack", ratio_literal=event["ratioLiteral"], xml_byte_span=event["xmlByteSpan"])
    for skill in source["skills"]:
        if [e["clip"] for e in skill["hitEventsForConfiguredClips"]] != CARDS[str(skill["skillId"])]:
            raise ValueError("Reviewed card-stage mapping changed")
    manifest = dict(schema="hczs-battle-hit-events-v1", data_asset=ASSET, source_audit_sha256=sha(raw),
                    source_audit=SOURCE.relative_to(ROOT).as_posix(), event_track_sha256=AGS_SHA,
                    player_hit_events=rows, card_animation_queues=CARDS,
                    original_apk_executed=False, original_full_timing_equivalence=False,
                    policy="Fixed selected clips use original clip-local attack events. Late authority holds at actual impact pose; per-ordinal reactions may restart HIT. No predicted HP/death/result.")
    publish("manifest.json", manifest)
    return manifest


def verify_manifest():
    raw = (BASE / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    if (manifest["schema"] != "hczs-battle-hit-events-v1" or manifest["data_asset"] != ASSET
            or manifest["card_animation_queues"] != CARDS or manifest["event_track_sha256"] != AGS_SHA):
        raise ValueError("Unexpected hit-event manifest")
    if sha(SOURCE.read_bytes()) != manifest["source_audit_sha256"]:
        raise ValueError("Source timing audit changed after planning")
    source = json.loads(SOURCE.read_bytes())
    for identity in source["sources"]:
        filename = identity.get("path", identity.get("output"))
        target = (ROOT / filename).resolve()
        if not target.is_relative_to(ROOT.resolve()) or sha(target.read_bytes()) != identity.get("sha256", identity.get("decoded_sha256")):
            raise ValueError("Pinned source changed before native import")
    if set(manifest["player_hit_events"]) != set(EXPECTED):
        raise ValueError("Unexpected source event table key")
    for clip, value in manifest["player_hit_events"].items():
        original = source["clips"][clip]
        event = next(e for e in original["events"] if e["name"] == "attack")
        expected = dict(progress=EXPECTED[clip], duration_seconds=original["durationSeconds"],
                        event_name="attack", ratio_literal=event["ratioLiteral"], xml_byte_span=event["xmlByteSpan"])
        if value != expected:
            raise ValueError("Manifest scalar/source projection mismatch: " + clip)
    return manifest, sha(raw)


def native():
    import unreal
    report = dict(schema="hczs-battle-hit-events-native-v1", passed=False,
                  read_only=True, original_apk_executed=False, original_full_timing_equivalence=False)
    try:
        manifest, manifest_sha = verify_manifest()
        applying = "-HczsBattleHitTimingApply" in unreal.SystemLibrary.get_command_line()
        report.update(read_only=not applying, manifest_sha256=manifest_sha, data_asset=ASSET)
        scene = unreal.load_asset(ASSET)
        if not scene or scene.get_class().get_name() != "HczsBattleSceneAssets":
            raise ValueError("Existing typed battle scene DataAsset missing")
        queues = {str(k): list(v.get_editor_property("Clips"))
                  for k, v in scene.get_editor_property("CardAnimationQueues").items()}
        if queues != CARDS:
            raise ValueError("Actual card animation queues differ from reviewed selected clips")
        animations = {str(k): v for k, v in scene.get_editor_property("PlayerAnimations").items()}
        imported = {}
        for clip, entry in manifest["player_hit_events"].items():
            animation = animations.get(clip)
            length = animation.get_play_length() if isinstance(animation, unreal.AnimSequence) else None
            if (length is None or not math.isfinite(length) or abs(length - entry["duration_seconds"]) > .002):
                raise ValueError("Actual imported clip/source duration mismatch: " + clip)
            imported[clip] = dict(path=animation.get_path_name(), duration_seconds=length)
        report["actual_imported_animations"] = imported
        if applying:
            # Exact dedicated DataAsset files only. No directory-wide copy/delete.
            disk = PROJECT / "Content/Recovered/Battle/BattleSceneAssets.uasset"
            if not disk.is_file():
                raise ValueError("Cannot snapshot existing saved DataAsset")
            previous_sha = sha(disk.read_bytes())
            backup_dir = BASE / "backups" / previous_sha
            backup_dir.mkdir(parents=True, exist_ok=True)
            report["backups"] = []
            for extension in (".uasset", ".uexp", ".ubulk"):
                file = disk.with_suffix(extension)
                if not file.exists():
                    continue
                backup = backup_dir / file.name
                if backup.exists() and backup.read_bytes() != file.read_bytes():
                    raise ValueError("Existing asset backup differs")
                if not backup.exists():
                    shutil.copy2(file, backup)
                report["backups"].append(dict(path=backup.relative_to(ROOT).as_posix(), sha256=sha(backup.read_bytes())))
            values = {}
            for clip, entry in manifest["player_hit_events"].items():
                value = unreal.HczsBattleSourceHit()
                for key, data in dict(NormalizedProgress=entry["progress"], SourceDurationSeconds=entry["duration_seconds"],
                                      EventName=entry["event_name"], RatioLiteral=entry["ratio_literal"]).items():
                    value.set_editor_property(key, data)
                values[clip] = value
            scene.set_editor_property("PlayerHitEvents", values)
            scene.set_editor_property("SourceHitTimingSHA256", manifest_sha)
        actual = scene.get_editor_property("PlayerHitEvents")
        if set(str(k) for k in actual) != set(EXPECTED):
            raise ValueError("Native hit-event table keys differ")
        report["events"] = {}
        for clip, entry in manifest["player_hit_events"].items():
            value = actual[clip]
            fields = dict(progress=value.get_editor_property("NormalizedProgress"),
                          duration_seconds=value.get_editor_property("SourceDurationSeconds"),
                          event_name=str(value.get_editor_property("EventName")), ratio_literal=str(value.get_editor_property("RatioLiteral")))
            if (abs(fields["progress"] - entry["progress"]) > 1e-7 or
                    abs(fields["duration_seconds"] - entry["duration_seconds"]) > 1e-6 or
                    fields["event_name"] != entry["event_name"] or fields["ratio_literal"] != entry["ratio_literal"]):
                raise ValueError("Native hit-event scalar/string readback differs: " + clip)
            report["events"][clip] = fields
        if str(scene.get_editor_property("SourceHitTimingSHA256")) != manifest_sha:
            raise ValueError("Native source manifest SHA differs")
        if applying and not unreal.EditorAssetLibrary.save_loaded_asset(scene, False):
            raise ValueError("Typed hit-event DataAsset save failed")
        report["passed"] = True
        report["scope"] = "Actual source ratios and matching imported clip lengths on one dedicated DataAsset; visual/native game runtime acceptance remains separate."
    except Exception as error:
        report["error"] = str(error)
        report["traceback"] = traceback.format_exc()
        unreal.log_error(report["traceback"])
    finally:
        publish("native-apply.json" if not report["read_only"] else "native-readback.json", report)
        unreal.log("HCZS source hit-event import: " + json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        manifest = plan()
        print(json.dumps(dict(manifest=str(BASE / "manifest.json"), clips=len(manifest["player_hit_events"]),
                              source_audit_sha256=manifest["source_audit_sha256"], original_apk_executed=False)))
    else:
        native()
