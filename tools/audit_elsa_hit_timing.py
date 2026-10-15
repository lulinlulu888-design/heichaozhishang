"""Bounded source audit of Elsa's authored hit events, without executing the APK.

Reuses decoded/hash-bound source artifacts and LLVM transcripts. Reads seven
animation records and selected Python code objects; writes machine evidence
only. Neither UE, a database, nor a game process is opened or changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import inspect_battle_rules as static
from inspect_neox_animation import parse_library
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/battle-visual/elsa-hit-timing"
APK_SHA = "aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4"
NATIVE_SHA = "54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef"
AGS_SHA = "12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729"
LIB_SHA = "2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41"
WANTED = (110001, 110009, 210003, 410101, 410102)
MODULE_SHA = {
    2072: "288b1b4884b54fbe3128b60d8d57c140853a208dbaa469a11bbd29617c985d57",
    4497: "a9bf15904e005cbf39cbb0b858197335a600232fd7e6bbe361d6855fee157167",
    6558: "eae0f934c892527b48ed37eb643176f9cd84a7ab1fc0c25c74dd2518a13f621c",
    7810: "ec6a6f5a74108d1648fe876c934737c6fc7530e2aa30aa129053f43d7fd36816",
    6025: "df90d450758a3ecec46195d5c7cceff3dba28848199b179920c4642f513be964",
    8905: "4fc2aeb4db4cbd72897546beca0bfab6442623a415b9f6f80471727a003b6030",
    4254: "8f9571a9d857300addae02f0f614709411ec400a73ad1f84bbb195e351d3bbb6",
    1723: "d97e3ef54b421e93bf91fafd02df81ee12cd5eecc434ca271d2146a7bc0caca2",
    7522: "f8af793a018d8780e938f232e8df3a6373141c2206932c2abf4a4dc1fd90c43a",
    9615: "dcce7b74f4cadfec8743071696ad1f36d86fa89ddc9ced5c36ccfb4c6715eadc",
    5888: "1c02a407d9f1d55653f1abe6a822dc1b2cc5588f5fdd39507b194f155f4b54fc",
    938: "01c26477645f03ac60471077907131ff680dd2c800fde0269a7d5632fc710f75",
    2350: "5c156352bd613575e566420dca9ce04cf74c937a598e9f565eb5e1ff01fe70fa",
    5485: "1d7d3a6f523292558ea6f37e68d6b569caa65f883b07aa88d016e0d005cf1378",
    3031: "f5a752800432e2a80dd737098cd72d018b82f59f28b647af16af45d504b41c61",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(path, expected=None):
    path = ROOT / path
    actual = digest(path)
    if expected is not None and actual != expected:
        raise ValueError(f"Source identity mismatch: {path}")
    return path, {"path": path.relative_to(ROOT).as_posix(), "sha256": actual}


def load(path, expected=None):
    path, identity = checked(path, expected)
    return json.loads(path.read_text("utf8")), identity


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def declarations(module):
    """Recognize straight-line literal declarations only; no bytecode execution.

    Supports the shipped design files' constants/lists/maps and literal aliases.
    Imports, calls, branches, computed expressions and duplicate names fail.
    """
    stack, bindings = [], {}
    for item in static.instructions(module):
        op, value = item["opname"], item.get("operand")
        if op == "LOAD_CONST":
            if isinstance(value, dict) and "code_name" in value:
                raise ValueError("Code object is not a literal declaration")
            stack.append(value)
        elif op == "LOAD_NAME":
            if value not in bindings:
                raise ValueError(f"Unresolved literal alias: {value}")
            stack.append(bindings[value])
        elif op in ("BUILD_LIST", "BUILD_TUPLE"):
            n = item["argument"]
            values = stack[-n:] if n else []
            if n:
                del stack[-n:]
            stack.append(tuple(values) if op == "BUILD_TUPLE" else values)
        elif op == "BUILD_MAP":
            stack.append({})
        elif op == "STORE_MAP":
            key, data = stack.pop(), stack.pop()
            if key in stack[-1]:
                raise ValueError("Duplicate literal map key")
            stack[-1][key] = data
        elif op == "STORE_NAME":
            if value in bindings:
                raise ValueError("Duplicate literal declaration")
            bindings[value] = stack.pop()
        elif op == "RETURN_VALUE":
            stack.pop()
            if stack:
                raise ValueError("Unconsumed literal stack")
        else:
            raise ValueError(f"Unsupported declaration operation {op} at {item['offset']}")
    return bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-apk", action="store_true", help="Additionally hash the original APK (read-only)")
    args = parser.parse_args()
    if args.verify_apk:
        apks = list(ROOT.glob("*.apk"))
        if len(apks) != 1 or digest(apks[0]) != APK_SHA:
            raise ValueError("Original APK identity mismatch/ambiguous input")

    sources, objects, modules = [], {}, {}
    index = {r["index"]: r for r in json.loads((static.SCRIPT / "index.json").read_text("utf8"))}
    selections = {
        2072: ("getAnimationListInTimelineData", "getSkillDurationAndReactTimeList", "isEventTriggerReactSkill", "getUltimateSkillData"),
        4497: ("play", "_prepareReactData", "createSkillTrack", "createReactTrack", "casterAnimEvent", "getReactWaitDuration", "getReactCount", "getSkillReactTimeList"),
        6558: ("isReactAction",),
        7810: ("doInit", "play", "getDuration"),
        6025: ("_enterLogic", "_playNext", "playSingleAnimation", "_realPlayAnimation", "getAnimReactCount", "endPlayerFocus", "onEventAnimEnd", "reEnter"),
        8905: ("getAnimationLength", "getAnimationEventTime", "playViewAnimation"),
        4254: ("_initModelInfo", "getAnimationEventTimeMilliseconds", "playAnimation"),
        1723: ("<module>",), 7522: ("<module>",), 9615: ("<module>",),
        2350: ("play",), 5485: ("onChangeHp", "_playImpactAnim"), 3031: ("switchState",),
    }
    for mid, sha in MODULE_SHA.items():
        row = index[mid]
        if row["decoded_sha256"] != sha:
            raise ValueError(f"Changed script inventory identity: {mid}")
        modules[mid] = static.read_module(row)
        sources.append({"kind": "decoded-script", "moduleIndex": mid, **row})
        if mid not in selections:
            continue
        exported = static.export(row, selections[mid])
        # Names such as play are reused by multiple classes. Keep exact scope.
        if mid in (7810, 6025, 2350):
            scopes = (14, 16) if mid == 6025 else (5,) if mid == 2350 else (14,)
            exported["code_objects"] = [o for o in exported["code_objects"] if o["constant_path"][0] in scopes]
        save(OUT / f"{mid}-source.json", exported)
        for obj in exported["code_objects"]:
            objects[(mid, obj["name"])] = obj

    def anchor(mid, name, start, end):
        obj = objects[(mid, name)]
        ops = [i for i in obj["instructions"] if start <= i["offset"] < end]
        if not ops or ops[0]["offset"] != start or ops[-1]["end_exclusive"] != end:
            raise ValueError(f"Anchor is not an instruction-aligned range: {mid} {name}")
        return {"moduleIndex": mid, "function": name, "constantPath": obj["constant_path"],
                "bytecodeSha256": obj["bytecode_sha256"], "start": start, "endExclusive": end,
                "sourceFile": f"analysis/battle-visual/elsa-hit-timing/{mid}-source.json"}

    random = declarations(modules[1723])["data"][0]
    replacement = declarations(modules[7522])["data"]
    focus = declarations(modules[9615])["blinkData"]
    blink_ops = list(static.instructions(modules[938]))
    blink_assignments = [(blink_ops[i-1], op) for i, op in enumerate(blink_ops)
                         if op.get("operand") == "PlayerBlinkPauseTime" and op["opname"] == "STORE_NAME"]
    if len(blink_assignments) != 1 or blink_assignments[0][0]["opname"] != "LOAD_CONST":
        raise ValueError("Blink pause is not a unique scalar declaration")
    blink = blink_assignments[0][0]["operand"]
    if blink != 0.15 or replacement or random[0] != [["ATK_1", "ATK_2", "ATK_3", "ATK_4", "ATK_5", "ATK_7"], 0]:
        raise ValueError("Observed Elsa animation-selection preconditions changed")

    mapping, identity = load("analysis/battle-visual/skill-animation/mapping.json")
    sources.append(identity)
    if mapping["apk_sha256"] != APK_SHA or mapping["entity_id"] != 0:
        raise ValueError("Mapping does not identify the source Elsa entity")
    entities, identity = load("analysis/resource-mapping/entity-table-selected.json", mapping["entity_json_sha256"])
    sources.append(identity)
    entity = next(r for r in entities["rows"] if r["id"] == 0)
    static.read_module(index[entities["source"]["index"]])
    timelines = literal_table(6655)
    selected_timeline = [r for r in timelines["rows"] if r["fields"].get("OwnerSkill") in WANTED]
    if selected_timeline != [r["timeline"] for r in mapping["links"]]:
        raise ValueError("Recovered timeline mapping differs from freshly recognized source rows")
    skills, identity = load("analysis/first-encounter/skills.json")
    sources.append(identity)
    states, identity = load("analysis/first-encounter/skill-states.json")
    sources.append(identity)
    for table in (skills, states):
        original = literal_table(table["source"]["index"], selected={r["id"] for r in table["rows"]})
        if original["rows"] != table["rows"]:
            raise ValueError("Skill/state rows differ from current original source")
    ult = literal_table(5888)
    if any(r["id"] in WANTED for r in ult["rows"]):
        raise ValueError("Selected source skill now uses native event-step reaction mode")

    ags_path, identity = checked("analysis/battle-visual/skill-animation/ailisha.ags", AGS_SHA)
    sources.append(identity)
    ags_source, identity = load("analysis/battle-visual/skill-animation/ailisha.ags.provenance.json")
    sources.append(identity)
    if ags_source["sha256"] != AGS_SHA or ags_source["apk_sha256"] != APK_SHA:
        raise ValueError("Event-track extraction provenance mismatch")
    raw_xml = ags_path.read_bytes()
    tracks = ET.fromstring(raw_xml).find("AnimationEventTracks")
    if tracks is None or tracks.attrib.get("Version") != "2":
        raise ValueError("Authored track format changed")
    lib_path, identity = checked("analysis/animation/recovered/ailisha.gisacl", LIB_SHA)
    sources.append(identity)
    library_raw = lib_path.read_bytes()
    library = parse_library(library_raw)
    types = list(dict.fromkeys([t for link in mapping["links"] for t in link["animation_types"]] + random[0][0]))
    clip_names = list(dict.fromkeys(entity["fields"]["ANIM_STATES_" + t] for t in types))
    clips = {}
    for name in clip_names:
        record = next(r for r in library["clips"] if r["name"] == name)
        duration_offset = record["offset"] + 0x44c
        duration_ms = struct.unpack_from("<f", library_raw, duration_offset)[0]
        if not math.isfinite(duration_ms) or duration_ms <= 0:
            raise ValueError("Invalid authored record duration")
        track = tracks.find("EventTrack_" + name)
        if track is None:
            raise ValueError("Selected clip lacks original event track")
        clip_start = raw_xml.index(("<EventTrack_" + name + ">").encode())
        clip_end = raw_xml.index(("</EventTrack_" + name + ">").encode(), clip_start)
        events = []
        for event in track:
            literal = event.attrib["TimeRatio"]
            ratio = float(literal)
            if not math.isfinite(ratio) or not 0 <= ratio <= 1:
                raise ValueError("Authored event outside clip")
            # Matches the observed ARM float32 multiplication, not observed runtime.
            time_ms = f32(f32(ratio) * duration_ms)
            if event.attrib["Name"] in ("attack", "jump_next", "end"):
                # Attributes span several lines in the source XML.
                offsets = []
                for match in re.finditer(rb"<Event\s[^>]+/>", raw_xml[clip_start:clip_end]):
                    if (f'Name="{event.attrib["Name"]}"'.encode() in match[0]
                            and f'TimeRatio="{literal}"'.encode() in match[0]):
                        offsets.append([clip_start + match.start(), clip_start + match.end()])
                if len(offsets) != 1:
                    raise ValueError("Event source span is ambiguous")
                events.append({"name": event.attrib["Name"], "ratioLiteral": literal, "normalizedClipProgress": ratio,
                               "nativeF32DerivedMilliseconds": time_ms, "derivedSeconds": time_ms / 1000.0,
                               "xmlByteSpan": offsets[0]})
        if sum(e["name"] == "attack" for e in events) != 1:
            raise ValueError("Expected exactly one authored attack event in the selected clip")
        acl = mapping["clips"].get(name)
        if acl and abs(acl["duration_seconds"] * 1000 - duration_ms) >= 0.001:
            raise ValueError("Independent ACL/record duration mismatch")
        clips[name] = {"durationMilliseconds": duration_ms, "durationSeconds": duration_ms / 1000,
                       "durationFieldOffset": duration_offset, "libraryRecordIndex": record["index"],
                       "aclDurationSeconds": acl["duration_seconds"] if acl else None,
                       "events": events}

    native_path, identity = checked("analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so", NATIVE_SHA)
    sources.append(identity)
    native_transcripts = []
    for report_name in ("loader-chain", "storage-chain", "query-chain"):
        report, identity = load(f"analysis/battle-visual/enemy-timing/{report_name}.json")
        sources.append(identity)
        if report["native_sha256"] != NATIVE_SHA:
            raise ValueError("Native transcript identity mismatch")
        for item in report["exports"]:
            _, transcript_identity = checked(item["path"].replace("\\", "/"), item["sha256"])
            native_transcripts.append({**transcript_identity, "command": item.get("command")})

    resolved = []
    for link in mapping["links"]:
        row, animation_types = link["timeline"], link["animation_types"]
        skill_id = row["fields"]["OwnerSkill"]
        if row["fields"]["TIME"] != 0 or row["fields"]["TYPE"] != 0:
            raise ValueError("Selected animation timeline start/type changed")
        name = next(r for r in skills["rows"] if r["id"] == skill_id)["fields"]["NAME"]
        stage_rows = sorted((r for r in states["rows"] if r["fields"]["OwnerSkill"] == skill_id),
                            key=lambda r: r["fields"]["OwnerIndex"])
        damage_rows = [r for r in stage_rows if r["fields"]["STORYLINE_NAME"] == "SkillState_CauseDamage"]
        random_types = random[0][0] if len(animation_types) == 1 and animation_types[0] in random[0][0] else []
        selected_names = [entity["fields"]["ANIM_STATES_" + t] for t in animation_types]
        # This is a static conditional schedule, not a captured push-action stream.
        count = len(damage_rows)
        cumulative, hit_events = 0.0, []
        for ordinal in range(count):
            clip = selected_names[ordinal % len(selected_names)]
            attack = next(e for e in clips[clip]["events"] if e["name"] == "attack")
            blink_pair = 2 * blink if animation_types[ordinal % len(animation_types)] in focus.get(0, []) else 0.0
            cumulative += blink_pair
            hit_events.append({"ordinal": ordinal, "stageId": damage_rows[ordinal]["id"],
                               "clip": clip, "clipOrdinal": ordinal,
                               "eventName": "attack", "clipProgress": attack["normalizedClipProgress"],
                               "clipLocalSeconds": attack["derivedSeconds"],
                               "helperDerivedSecondsFromTimelineStart": cumulative + attack["derivedSeconds"],
                               "helperFocusPauseSecondsBeforeClip": blink_pair,
                               "observedRuntimeSeconds": None})
            cumulative += clips[clip]["durationSeconds"]
        resolved.append({"skillId": skill_id, "name": name, "timelineRow": row,
                         "configuredAnimationTypes": animation_types, "configuredClips": selected_names,
                         "nativeEventStepReactionMode": False,
                         "reactionMode": "wait-for-first-attack-time; later stage minDuration=successive attack-time difference",
                         "sourceDamageStateRows": damage_rows, "otherSourceStateRows": [r for r in stage_rows if r not in damage_rows],
                         "conditionalReactionCount": count,
                         "conditionalReactionCountScope": "Expected only if each source damage stage yields a non-caster Hp/Shield react action. Actual pushed actions are authoritative.",
                         "randomAnimationTypes": random_types,
                         "randomClips": [entity["fields"]["ANIM_STATES_" + t] for t in random_types],
                         "deterministicExample": not bool(random_types), "hitEventsForConfiguredClips": hit_events,
                         "sourceFullSkillRuntimeVerified": False})

    chains = [
        {"claim": "TYPE creates the action class; TIME schedules its parallel-track start. All five selected TIME=0/TYPE=SkillPlayAnimationAction rows start animation, not hit.",
         "anchors": [anchor(4497, "createSkillTrack", 155, 205)]},
        {"claim": "A reaction is a Hp/Shield action on a non-caster target; _reactCount increments at most once per skill stage. It is not animation-list length.",
         "anchors": [anchor(6558, "isReactAction", 0, 50), anchor(4497, "_prepareReactData", 353, 414), anchor(4497, "getReactCount", 0, 16)]},
        {"claim": "SkillHelper reads attack/attack_1..attack_20 and adds prior complete clip lengths; blink clips add two PlayerBlinkPauseTime terms to its computed schedule.",
         "anchors": [anchor(2072, "getSkillDurationAndReactTimeList", 68, 141), anchor(2072, "getSkillDurationAndReactTimeList", 153, 222),
                     anchor(2072, "getSkillDurationAndReactTimeList", 222, 344), anchor(2072, "getSkillDurationAndReactTimeList", 426, 436)]},
        {"claim": "Selected skills are absent from the 92-row ultimate table; their reactions use an initial wait then stage spacing, rather than attack-event step mode.",
         "anchors": [anchor(2072, "isEventTriggerReactSkill", 0, 16), anchor(4497, "createReactTrack", 16, 86),
                     anchor(4497, "createReactTrack", 191, 253), anchor(4497, "getReactWaitDuration", 0, 37)]},
        {"claim": "Multi-clip SkillState advances by getAnimReactCount (at least 1). end event invokes _playNext; jump_next changes only the endPlayerFocus delay in the selected function.",
         "anchors": [anchor(6025, "playSingleAnimation", 155, 194), anchor(6025, "_realPlayAnimation", 46, 155),
                     anchor(6025, "_realPlayAnimation", 265, 337), anchor(6025, "onEventAnimEnd", 0, 24)]},
        {"claim": "Entity0 single ATK_1 selection may random.choice any of six source attack types. The three-entry 410101 list does not enter this branch; replacement data is empty.",
         "anchors": [anchor(2072, "getAnimationListInTimelineData", 123, 240)]},
        {"claim": "Model uses cached native event milliseconds. CompAnimation divides by 1000; Model.playAnimation uses native raw duration, startTime and speed arguments.",
         "anchors": [anchor(8905, "getAnimationEventTime", 43, 91), anchor(4254, "playAnimation", 56, 79),
                     anchor(4254, "playAnimation", 269, 322), anchor(4254, "playAnimation", 353, 384)]},
        {"claim": "HpAction calls onChangeHp. Negative delta invokes _playImpactAnim; when canShowOnHitAnim allows, it switches to HIT. Same-state FSM switch invokes reEnter; HitState.reEnter calls _enterLogic, which replays hit animation and clears/replaces its end timer. A later hit need not wait for the former hit clip to end.",
         "anchors": [anchor(2350, "play", 40, 56), anchor(5485, "onChangeHp", 162, 187),
                     anchor(5485, "_playImpactAnim", 24, 70), anchor(3031, "switchState", 96, 109),
                     anchor(6025, "reEnter", 0, 17), anchor(6025, "_enterLogic", 117, 170)]},
    ]
    # Native addresses are observed LLVM locations, not recovered original names.
    native_chain = [
        {"address": "0x995d54", "meaning": "construct event container using selected animation duration+0x48c"},
        {"address": "0xaef108", "meaning": "version<=1 takes Time; version>1 takes TimeRatio path"},
        {"address": "0xaef1dc", "meaning": "version2 reads TimeRatio float"},
        {"address": "0xaef1fa", "meaning": "vmul.f32 ratio * container duration"},
        {"address": "0xaef208", "meaning": "stores computed event time float"},
        {"address": "0x990128", "meaning": "RGIS fixed record+0x44c copied to animation+0x48c without conversion"},
        {"address": "0xa4c160", "meaning": "event time accessor returns stored float; no further duration multiplication"},
    ]
    report = {
        "schemaVersion": 1, "mode": "elsa-authored-hit-timing-static-audit", "sourceApkSha256": APK_SHA,
        "sourceApkHashedThisRun": args.verify_apk, "originalApkExecuted": False,
        "ueModified": False, "authority": "shipped-artifact-static", "evidenceKind": "Hash-verified XML, fixed binary records, partial Python disassembly and retained LLVM transcripts; not runtime observation",
        "sources": sources, "scriptChains": chains, "nativeChain": native_chain,
        "nativeTranscripts": native_transcripts, "originalEventTrackSource": ags_source,
        "clips": clips, "skills": resolved,
        "blinkPauseSource": {"moduleIndex": 938, "seconds": blink, "declaration": blink_assignments[0]},
        "implementation": {
            "eventDefinition": ["skillId", "requestId", "actionIndex", "reactionOrdinal", "clipName", "clipOrdinal", "eventName", "normalizedClipProgress"],
            "progressClock": "Use current actual animation playback position divided by that matching imported clip's length. Source ratio is preferable to a universal wall-clock timer or .5 threshold.",
            "fullSequence": "410101 with two confirmed reaction stages plays fire_1_1 then fire_1_3; the third configured fire_2 is not a third damage event merely because it appears in ANIMATION_LIST.",
            "confirmedReactionGate": "Require matching authoritative receipt and per-ordinal source attack progress reached. Preserve exactly-once intent and reaction guards. Never predict HP, death or result.",
            "lateReceipt": "Source does not prove how the new Node adapter should handle late receipt. Choose and test hold-at-impact/reconciliation explicitly; do not claim original timing equivalence.",
            "randomChoiceScope": "A deterministic fire_1 adapter uses its authored ratio but is a subset of the original six-clip random selection. Random selection must be stored once per intent so retries cannot change it.",
            "heavyFocusScope": "crit_1 .281831 is clip-local. Original SkillState delays _realPlayAnimation by .15 for blink; helper computes an additional .30 scheduling term. Do not add either to UE clip-normalized hit progress unless the corresponding focus mechanic is reconstructed.",
        },
        "knownDifferences": ["Previous UE .5 ConfirmedHitProgress was an adapter constant, not a source value.", "Current new Node 1v1 receipt domain is not the original RPC/SkillEachState/Target action stream."],
        "unknowns": ["Original APK wall-clock execution and final native cache values were not observed.", "Original native scheduler, all playback speed/focus/video/transition combinations are not executed here.", "Actual original pushed Hp/Shield stage count can differ from static damage-row count due to targeting/other conditions.", "Retained XML loader static path does not prove that no later loader overrides the cache.", "REA native read_bytes unavailable on this host: unconfigured Ghidra/IDA, Hopper unsupported, Ghidra Windows profile rejects ARM ELF. Existing ordinary LLVM evidence remains separately classified."],
        "rea": {"originalInventoryEvidence": "ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220", "inventoryEvidenceScope": "APK identity/inventory only; does not establish timing", "newNativeEvidenceAvailable": False},
        "auditPassed": True, "auditMeaning": "Declared static evidence identities and source schedules are internally consistent; this is not original runtime/playability equivalence.",
    }
    save(OUT / "source-audit.json", report)
    print(json.dumps({"output": str(OUT / "source-audit.json"), "auditPassed": True,
                      "skills": len(resolved), "clips": len(clips), "originalApkExecuted": False,
                      "sourceApkHashedThisRun": args.verify_apk}, ensure_ascii=True))


if __name__ == "__main__":
    main()
