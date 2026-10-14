"""Trace card-action/client battle boundaries without executing APK bytecode.

Reuses the hash-checked marshal reader and corroborated partial opcode map.
This is an evidence renderer/import inventory, not a Python VM or decompiler.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static
from extract_npk import jsonable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "analysis/card-action"
DEFAULT_MODULES = [0, 36, 126, 618, 1113, 1259, 1317, 2058, 2350, 2697, 4153, 4453,
                   4762, 4942, 5455, 5485, 5631, 6198, 6221, 6224, 6601,
                   6786, 7088, 7693, 8213, 8874, 9137, 9330, 9641]
GUARDS = {
    0: "53ceb7b10ceb4159d0a468c5faa75bb352b1d2444d2f5cd406dc5d1cea5308dc",
    618: "4c56f3a17723f1fd70fcadb687039af93c781882d7c4f0b02e5c6366bebba3d8",
    1259: "1fdc7beb3c857faf061bdb76894d7badc0a3c1376321c9d232f1bf62705bf27e",
    1317: "f90cbbf489ecd3d9626a527fe6d4bd9869f0465410c59da8d4e2c5d9934266f1",
    2350: "5c156352bd613575e566420dca9ce04cf74c937a598e9f565eb5e1ff01fe70fa",
    2697: "6b3931b986758dfef8dbce9d84b7c9bf7b451ceb567d5a3eaab7748785d5779c",
    4153: "729277c7b95b7df13aedf87ddda4922aa3255a5dd7d77a96f706534ab8474937",
    4453: "b36d09e2b15537edd39e025faeee5114048fce2431c5ea8a6a9e761403df6dd9",
    4942: "e2911c234556cc11d601bbe566bad7da58253e91171b05ef6e1930ff2dea07c1",
    5455: "50900f11c2a737b582c90fe9e7b37577782d62e4a3c366fadc275fb417b3b61e",
    5485: "1d7d3a6f523292558ea6f37e68d6b569caa65f883b07aa88d016e0d005cf1378",
    5631: "2d975621955eb6b6c983fd599a448c0aa3ef824a34f2b3b8a122cc5e396ea845",
    6198: "a7030162e6d8b39ac2b90a56bba52b0259f1912d66cd956d9432d4e1ee745252",
    6221: "e09e9130987752b7bd2f875e86b620cb6af290cf4fd291be1bd4b932031f2b9f",
    6224: "2dd6c63498657b4be579e667be35510b277dd98ce1c34a9645a911dbae410a67",
    6601: "d73deedc1743db25d656d04347e6c693ba84ece718659bcdb895f03094f8d365",
    6786: "d06a46e6bf9cd7d7455936562b7e0d9b0133940eb5a5d4e7075921067f5a7aa4",
    9137: "76523206f60bf128cab471310a44f63b15f69cd65b967475fedb0a88f7cd4cd2",
}
SELECTED = {
    0: [[26]], 618: [[], [24, 0], [24, 2], [24, 3], [26, 0]],
    1259: [[]], 1317: [[6, 2], [6, 3]], 2350: [[5, 2], [15, 2]],
    2697: [[12, 12], [12, 51]],
    4153: [[15], [15, 5], [15, 6], [15, 7], [15, 16], [15, 17]],
    4453: [[5, 10], [5, 16], [5, 17], [5, 18]], 4942: [[8, 2]],
    5455: [[7, 5], [7, 13]], 5485: [[13, 1], [13, 2], [13, 19], [13, 20], [13, 22]],
    5631: [[], [4]], 6198: [[4], [4, 139]], 6221: [[]], 6224: [[]],
    6601: [[22, 4], [24, 3]], 6786: [[3, 1], [3, 2], [3, 5]],
    9137: [[], [9, 0], [9, 1], [9, 9], [9, 10], [9, 13]],
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def module_key(filename):
    name = filename.replace("\\", "/").removesuffix(".py")
    if name.endswith("/__init__"):
        name = name[:-9]
    return name.replace("/", ".")


def action_map(code):
    """Recognize only the observed map literal of class symbols to string keys.

    No symbol resolution, class construction, imports or arbitrary instructions
    are executed. Each entry must be exactly LOAD_NAME/LOAD_CONST/STORE_MAP.
    """
    items = list(static.instructions(code))
    end = next(n for n, i in enumerate(items) if i["opname"] == "STORE_NAME" and i.get("operand") == "RAW_ACTION_MAP")
    starts = [n for n, i in enumerate(items[:end]) if i["opname"] == "BUILD_MAP"]
    if len(starts) != 1:
        raise ValueError("unexpected action-map literal layout")
    start = starts[0]
    body = items[start + 1:end]
    if len(body) % 3:
        raise ValueError("action-map entries are not fixed triples")
    entries = []
    for n in range(0, len(body), 3):
        symbol, key, store = body[n:n + 3]
        if [symbol["opname"], key["opname"], store["opname"]] != ["LOAD_NAME", "LOAD_CONST", "STORE_MAP"]:
            raise ValueError("nonliteral action-map entry")
        if not isinstance(symbol.get("operand"), str) or not isinstance(key.get("operand"), str):
            raise ValueError("action-map key/symbol is not text")
        entries.append({"name": key["operand"], "class_symbol": symbol["operand"],
                        "offset_range_end_exclusive": [symbol["offset"], store["end_exclusive"]]})
    if len(entries) != items[start]["argument"] or len({v['name'] for v in entries}) != len(entries):
        raise ValueError("action-map size/unique-name check failed")
    return {"source": "6198:4", "store_offset": items[end]["offset"],
            "entry_count": len(entries), "entries": entries,
            "scope": "raw presentation action names; not RPC numeric IDs or server combat rules"}


def provider_boundary(inventory):
    terms = {"SServiceCardActionSL", "CServiceCardActionSL", "BaseServiceCardActionSL",
             "SServiceCardActionChooseTargetSL", "CServiceCardActionChooseTargetSL", "StorylineSkillContext"}
    hits = []
    for line in (static.SCRIPT / "symbols.jsonl").read_text("utf8").splitlines():
        symbol = json.loads(line)
        matched = sorted(terms.intersection(symbol["names"] + symbol["strings"] + symbol["functions"]))
        if matched:
            hits.append({"index": symbol["index"], "filename": symbol["filename"], "terms": matched})
    requested = ["ServerUtils", "storyline.StorylineBattleContext", "storyline.Storyline.Node",
                 "storyline.Storyline.NodePort", "storyline.Storyline.NodeMeta", "storyline.Meta.TypeMeta"]
    files = {module_key(r["filename"]): r["index"] for r in inventory}
    members = json.loads((ROOT / "analysis/assets/members.json").read_text("utf8"))
    filelist = json.loads((ROOT / "analysis/assets/filelist_verification.json").read_text("utf8"))
    return {"coverage": {"script_entries": len(inventory), "unique_filenames": len(files),
                         "new_search": "six class/context identifiers; not a repeated diyActionData/native-name search"},
            "class_or_context_reference_modules": hits,
            "nonclient_import_exact_inventory_matches": {name: files.get(name) for name in requested},
            "additional_pyc_members": [x for x in members if x["name"].endswith(".pyc")],
            "npk_members": [x["name"] for x in members if x["name"].endswith(".npk")],
            "shipped_filelist": {"sha256": filelist["manifest_sha256"], "counts": filelist["counts"]},
            "limitations": ["Names can be synthesized or supplied by native registration/dynamic imports.",
                "Neither this inventory nor a matching shipped filelist proves online-patch completeness.",
                "No cardAction constructor or DIY-list-to-diyActionData provider has been established.",
                "No known combat replay payload was supplied; resource inventory does not prove one absent."]}


def presentation_contract():
    return {
        "format": "hczs-client-presentation-boundary-v1",
        "evidence_kind": "static application-level calls and assignments; not observed traffic or native wire framing",
        "outbound": [
            {"source": "5455:7.5", "range": [34, 67], "method": "requestPlayACard", "arguments": {"cID": "cardID argument", "tID": "targetID argument"}},
            {"source": "5455:7.13", "range": [0, 19], "method": "avtRequestEndRound", "arguments": {}},
        ],
        "inbound": {"source": "4153:15", "range": [180, 213], "decorator": "rpc_method(CLIENT_STUB, (List('a'),))",
                    "method": "onPushActions", "implementation": "4153:15.16 -> 4153:15.17 -> 2697:12.51"},
        "raw_action_shape": {"source": "6786:3.5", "item": "(actionName, actionData)",
            "begin_names": ["SkillUseBegin", "SkillEachStateBegin", "TargetBegin"],
            "end_names": ["SkillUseEnd", "SkillEachStateEnd", "TargetEnd"],
            "behavior": "begin creates/pushes a nested list, end pops without appending itself; final stack size must be one",
            "limits": "Observed parser does not match closing marker type to opening marker type. Merge/postprocess/custom modifications remain separate steps."},
        "hp_change": {"action": "HpChange", "class": "HpAction", "map_source": "6198:4 [0xb1,0xb8)",
            "consumer": "2350:5.2 -> 5485:13.22", "target": "actionData['target'] passed to Battle.getEntity",
            "call": "toEnt.onChangeHp(**Args)", "call_offset": 52,
            "state_assignment": {"source": "5485:13.22", "range": [78, 87], "expression": "self.hp = kwargs.get('finalValue')"},
            "reads": ["lastActionShield", "deltaValue", "finalValue", "skillInfo", "srcEntityID", "HeavyAttack"],
            "limit": "deltaValue controls presentation; this consumer does not calculate damage, clamp HP or consume shields"},
        "shield_change": {"action": "ShieldChange", "consumer": "2350:15.2",
            "state_assignment": "5485:13.19/13.20 [0,9): self.shield = curValue",
            "reads": ["target", "skillInfo", "deltaValue", "finalValue", "isAutoReduce", "srcEntityID", "damageShowTags"],
            "limit": "Supplied finalValue is authoritative for this display object; no shield absorption formula recovered here"},
        "card_sync": {"source": "4453:5.10/5.18; 9137:9.0/9.1/9.13",
            "input_paths": ["battleInfo.team1", "battleInfo.team2"],
            "piles": ["handPile", "drawPile", "discardPile", "exhaustedPile", "powerUsedPile"],
            "constructor": "ClientCard(cardInfo['cardID'], cardInfo['cardTypeID'], cardInfo['charID'])",
            "updates": "cardInfo.update(input); setattr(self,k,v) for each received field",
            "limit": "ClientCard directly subclasses object and is not the missing server cardAction class"},
        "two_phase_refresh": {"enqueue": "4153:15.5 generates local ClientUpdateBattleProperties action",
            "on_receive": "1317:6.2 -> 4153:15.6 updates pre-calculation/data card piles",
            "on_play": "1317:6.3 -> 4153:15.7 updates view card piles and visible state",
            "queue": "2697:12.51 invokes onReceive then enqueues action to normal or UI track"},
        "unresolved": ["DIY list -> cardAction.diyActionData", "cardAction/getRpgValue provider",
            "server validation/energy costs/RNG/draw order/turn scheduling", "beHurt and shield/HP settlement",
            "native RPC wire and actual captured battle messages", "action merge/render timing and complete client replay"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", type=int, nargs="*", default=DEFAULT_MODULES)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((static.SCRIPT / "index.json").read_text("utf8"))
    module_ids = {module_key(row["filename"]): row["index"] for row in inventory}
    for index, digest in GUARDS.items():
        if inventory[index]["decoded_sha256"] != digest:
            raise ValueError(f"module {index} changed; manually review semantic claims")
    manifests, import_edges, sources = [], [], []
    for index in args.modules:
        row = inventory[index]
        module = static.read_module(row)
        result = static.export(row)
        lines = [f"APK assets/script.npk index={index}; NPK offset={row['offset']}",
                 f"module={row['filename']}; marshal sha256={row['decoded_sha256']}"]
        for (path, code), rendered in zip(static.walk_codes(module), result["code_objects"]):
            rendered["flags"] = code["flags"]
            # Avoid duplicating complete nested code objects in constants.
            rendered["constants"] = [
                {"code_name": v["name"].decode("utf8")} if isinstance(v, dict) and v.get("type") == "code" else jsonable(v)
                for v in code["consts"]]
            lines += [f"\n### {rendered['name']} path={list(path)} line={code['firstlineno']}",
                      f"args/locals={rendered['varnames']!r}", f"names={rendered['names']!r}",
                      f"constants={rendered['constants']!r}"]
            for item in rendered["instructions"]:
                if item["opcode"] == 0x8D:
                    # Corroborated with shipped json.loads [26] offset 0x106 and
                    # CPython 2.7.18 Lib/json/__init__.py:317, cls(..., **kw).
                    item["opname"] = "CALL_FUNCTION_KW"
                lines.append(f"{item['offset']:05x} {item['opname']:24} {str(item['argument']):6} {item.get('operand', '')!r}")
                if item["opname"] == "IMPORT_NAME":
                    requested = item.get("operand")
                    import_edges.append({"module_index": index, "constant_path": list(path),
                                         "function": rendered["name"], "instruction": item,
                                         "requested": requested,
                                         "exact_inventory_match": module_ids.get(requested),
                                         "limitation": "Absolute-name inventory match only; does not emulate relative imports or native module registration."})
            if list(path) in SELECTED.get(index, []):
                sources.append({"source": {"apk_member": "assets/script.npk", **row}, **rendered})
            if index == 6198 and path == (4,):
                write_json(OUTPUT / "action-map.json", action_map(code))
        stem = f"{index:05d}_" + row["filename"].replace("\\", "__")
        write_json(OUTPUT / (stem + ".json"), result)
        (OUTPUT / (stem + ".partial-dis.txt")).write_text("\n".join(lines) + "\n", encoding="utf8")
        manifests.append({**row, "code_objects": len(result["code_objects"]), "evidence_stem": stem})
    write_json(OUTPUT / "module-sources.json", manifests)
    write_json(OUTPUT / "import-edges.json", {"coverage": args.modules, "inventory_modules": len(inventory), "edges": import_edges})
    write_json(OUTPUT / "function-sources.json", sources)
    write_json(OUTPUT / "provider-boundary.json", provider_boundary(inventory))
    write_json(OUTPUT / "client-presentation-contract.json", presentation_contract())
    write_json(OUTPUT / "input-fingerprints.json", [
        {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in [static.SCRIPT / "index.json", static.SCRIPT / "symbols.jsonl",
                     ROOT / "analysis/assets/members.json", ROOT / "analysis/assets/filelist_verification.json"]])
    write_json(OUTPUT / "opcode-corroboration.json", {
        "opcode": "0x8d", "meaning": "CALL_FUNCTION_KW", "reference": "0:26 at 0x106",
        "argument": 256, "stack_shape": "cls, 'encoding', encoding, kw -> cls(encoding=encoding, **kw)",
        "official_source": "https://github.com/python/cpython/blob/v2.7.18/Lib/json/__init__.py#L317",
        "limit": "Analyst corroboration with shipped standard-library code; not a native dispatch-table recovery.",
        "shared_opcode_tools_modified": False})
    print(json.dumps({"modules": len(manifests), "code_objects": sum(x['code_objects'] for x in manifests), "imports": len(import_edges)}))


if __name__ == "__main__":
    main()
