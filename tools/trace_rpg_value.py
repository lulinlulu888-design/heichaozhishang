"""Bounded RPG consumer audit and first-encounter parameter matrix.

Reads marshal as ordinary data only. Reference functions below are independent
manual translations, not execution/eval/import of original game bytecode.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static
from trace_first_encounter import extra_index

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/rpg-value"
GUARDS = {
    296: "c4c17c0ea6978bb79d210fa114ba7a9dd7e94547a1a158378024a986677fc8ad",
    618: "4c56f3a17723f1fd70fcadb687039af93c781882d7c4f0b02e5c6366bebba3d8",
    1280: "8e0bd362e3fd2c5a8a024d44a06fd2a035b762855da6d78cffb229c90f4c3288",
    3207: "521ab2d66e5036cd647e84de3fa119a1ddfc0fa2c6a03aa7abf50d76734dcec3",
    3391: "c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09",
    3510: "114173991c7458dc152e5d410f6f485b771af7ebdf1da5965b794b237751a5d0",
    3598: "9cb09b5d52c7b29288ea2b2f60aff7ae3bd240d29326d377d7fdc42c5985d45b",
    7554: "5ad78dc543e9a48f4365739497f8916b4604b4c6eec2ce4a7fdd8a33e2d59ab2",
    8010: "70e12558e90078b6d7f73c27a8b9755d68a45f98330052ced1e5d4bfa2487326",
    8903: "be8c1ea4abc43f7dab5e38187e6ac286f2f338aef1581313eb99d099dbea090c",
    9137: "76523206f60bf128cab471310a44f63b15f69cd65b967475fedb0a88f7cd4cd2",
    9176: "fc9d2d84bc2d3b79636c1b774292c2c69f91fb07a57556d43db0cba2655b8c64",
    9333: "fc547f5c9239e1119840cb6fd3e155278b0e7311665eb74f40ceafc1929218a9",
}
SELECT = {
    296: [(20, 6)], 618: [(24, 0), (24, 2), (24, 3), (26, 0)],
    3207: [(6,), (26,), (28,)], 3510: [(i,) for i in range(29, 40)],
    3598: [(10, 6)], 7554: [(5, 13), (5, 14)],
    8010: [(353, 1), (355, 1), (357,), (358,)], 9137: [(9, 8)],
    9176: [(42,), (43,), (44,), (178,), (180,), (277,), (278,)],
}
CARD_IDS = {110001, 110009, 210003, 410101, 410102}
ENEMY_SKILLS = {990, 991, 992}
FIELD_TERMS = {"RPG_FORMULA", "RPG_DEFAULT_FORMULA", "rpgFormula", "rpgDefaultFormula"}
HELPER_TERMS = {"getCommonRpgFormulaValues", "getRpgActionInfoFromData"}


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def common_formula_reference(formula, coefficients, property_values, reads):
    """Manual 3510:39 translation for finite synthetic small-number vectors.

    property_values supplies the results of external getRpgPropByKey calls. A
    missing key fails; this helper does not invent the owner's attribute state.
    """
    if not formula:
        return 0
    properties = [s.strip() for s in formula.split(",")]
    factors = [int(float(s.strip())) for s in coefficients.split(",")]
    if len(properties) != len(factors):
        raise AssertionError("formula/coefficient count differs")
    result = 0
    for prop, factor in zip(properties, factors):
        reads.append(prop)
        result += property_values[prop] * factor / 100.0
    return result


def reference_vectors():
    cases = [
        (None, None, {}, 0, None),
        ("", "invalid coefficient ignored", {}, 0, None),
        ("PropAtk", "75.9", {"PropAtk": 10}, 7.5, None),
        ("PropAtk", "-75.9", {"PropAtk": 10}, -7.5, None),
        ("PropAtk, PropAtk", "25.9,25.9", {"PropAtk": 3}, 1.5, None),
        ("PropAtk", None, {"PropAtk": 10}, None, "AttributeError"),
        ("PropAtk", "", {"PropAtk": 10}, None, "ValueError"),
        ("PropAtk,PropHp", "50", {"PropAtk": 10}, None, "AssertionError"),
    ]
    vectors = []
    for formula, coefficients, props, expected, expected_error in cases:
        reads = []
        try:
            result = common_formula_reference(formula, coefficients, props, reads)
            if expected_error or result != expected:
                raise ValueError("reference vector mismatch")
            outcome = {"value": result, "numeric_type": type(result).__name__}
        except (AttributeError, ValueError, AssertionError) as exc:
            if type(exc).__name__ != expected_error:
                raise
            outcome = {"exception": type(exc).__name__}
        vectors.append({"formula": formula, "coefficients": coefficients,
                        "explicit_property_results": props, "property_reads": reads, "outcome": outcome})
    return {"kind": "independent manual translation, not original-runtime differential test",
            "source": "3510:39; hash-guarded module and full instructions included",
            "limits": ["Only synthetic small finite values; not a new cross-platform numeric core.",
                       "This function is not proven to be the provider of cardAction.getRpgValue."],
            "vectors": vectors}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {r["index"]: r for r in json.loads((static.SCRIPT / "index.json").read_text(encoding="utf8"))}
    sources, selected_functions = [], []
    for index, digest in GUARDS.items():
        row = rows[index]
        if row["decoded_sha256"] != digest:
            raise ValueError(f"module {index} source version changed")
        module = static.read_module(row)
        sources.append({"apk_member": "assets/script.npk", **row})
        if index not in SELECT:
            continue
        result = static.export(row)
        result["code_objects"] = [c for c in result["code_objects"] if tuple(c["constant_path"]) in SELECT[index]]
        if len(result["code_objects"]) != len(SELECT[index]):
            raise ValueError("selected function is missing")
        write(f"{index:05d}_instructions.json", result)
        lines = [f"{row['filename']}; NPK offset={row['offset']}; SHA256={digest}"]
        for c in result["code_objects"]:
            selected_functions.append({"module_index": index, "npk_offset": row["offset"], **c})
            lines += [f"\n### {c['name']} {c['constant_path']} sha256={c['bytecode_sha256']}", f"locals={c['varnames']}"]
            lines += [f"{i['offset']:05x} {i['opname']:24} {str(i['argument']):5} {i.get('operand', '')!r}" for i in c["instructions"]]
        (OUT / f"{index:05d}_partial-dis.txt").write_text("\n".join(lines) + "\n", encoding="utf8")

    # Exactly the new field/helper identifiers, using the existing symbol index;
    # do not repeat the old getRpgValue or native-name scan.
    symbol_path = static.SCRIPT / "symbols.jsonl"
    symbols = [json.loads(line) for line in symbol_path.read_text(encoding="utf8").splitlines()]
    field_hits, helper_hits = [], []
    for row in symbols:
        if "\\cdata\\" in row["filename"]:
            continue
        haystack = set(row["names"]) | set(row["strings"]) | set(row["functions"])
        fields, helpers = sorted(FIELD_TERMS & haystack), sorted(HELPER_TERMS & haystack)
        if fields:
            field_hits.append({"index": row["index"], "filename": row["filename"], "terms": fields})
        if helpers:
            helper_hits.append({"index": row["index"], "filename": row["filename"], "terms": helpers})
    if {r["index"] for r in field_hits} != {3207, 3510, 3598, 9137, 9176} or {r["index"] for r in helper_hits} != {3207, 3510, 3598}:
        raise ValueError("consumer scope changed; review newly discovered modules")
    write("bounded-consumer-audit.json", {
        "symbol_index_sha256": hashlib.sha256(symbol_path.read_bytes()).hexdigest(),
        "indexed_modules": len(symbols), "scope": "exact field/helper identifiers in existing non-cdata symbol index",
        "field_terms": sorted(FIELD_TERMS), "helper_terms": sorted(HELPER_TERMS),
        "field_hits": field_hits, "helper_hits": helper_hits,
        "limits": "Static names/short string literals only. Does not rule out dynamic calls, hidden payloads or native registrations.",
        "no_new_getRpgValue_or_native_scan": True,
    })

    cards = static.export_table(3391, CARD_IDS)
    skill_ids = {r["fields"]["SKILL_ID"] for r in cards["rows"]} | ENEMY_SKILLS
    state_index = extra_index(8903, skill_ids)
    state_ids = {state_id for entry in state_index["requested"].values() for state_id in entry["value"]}
    states = static.export_table(8903, state_ids)
    skills = static.export_table(9333, skill_ids)
    write("cards.json", cards)
    write("skills.json", skills)
    write("skill-states.json", states)
    write("state-index.json", state_index)
    write("ap-description.json", static.export_table(1280, {1}))
    state_rows = {r["id"]: r for r in states["rows"]}

    def state_record(state_id):
        row = state_rows[state_id]
        f = row["fields"]
        graph_name = f["STORYLINE_NAME"]
        graph_requires_rpg = graph_name != "SkillState_getCard"
        if graph_name not in {"SkillState_getCard", "SkillState_CauseDamage", "SkillState_MonsterCauseDamage", "SkillState_AddShield"}:
            raise ValueError("unreviewed graph in parameter matrix")
        keys = ["OwnerIndex", "RPG_FORMULA", "RPG_DEFAULT_FORMULA", "STORYLINE_NAME", "STORYLINE_PARAM", "DATA"]
        return {"id": state_id, "fields_present": {k: f[k] for k in keys if k in f},
                "formula_missing": "RPG_FORMULA" not in f,
                "coefficient_missing": "RPG_DEFAULT_FORMULA" not in f,
                "field_sources": {k: row["field_sources"][k] for k in keys if k in f},
                "graph_requires_rpg": graph_requires_rpg,
                "getRpgValue_result": {"status": "unresolved_provider" if graph_requires_rpg else "not_requested_by_this_graph", "value": None}}

    matrix = []
    for row in cards["rows"]:
        f = row["fields"]
        sid = f["SKILL_ID"]
        matrix.append({"card_id": row["id"], "skill_id": sid,
            "display_formula": f.get("RPG_FORMULA"), "display_coefficients": f.get("RPG_DEFAULT_FORMULA"),
            "raw_diy_parameter_names": f.get("SKILL_DIY_PARAMETER"), "raw_diy_values": f.get("SKILL_DIY_VALUE"),
            "state_index_order_not_proven_runtime_order": state_index["requested"][str(sid)]["value"],
            "states": [state_record(x) for x in state_index["requested"][str(sid)]["value"]],
            "limit": "No automatic zip-to-runtime-DIY or coefficient precedence is claimed."})
    enemies = [{"skill_id": sid, "states": [state_record(x) for x in state_index["requested"][str(sid)]["value"]]} for sid in sorted(ENEMY_SKILLS)]
    write("first-encounter-parameters.json", {"players": matrix, "enemy": enemies,
        "not_final_damage": True, "missing_fields_not_zero": True})
    write("reference-vectors.json", reference_vectors())

    prior = {}
    for name in ["analysis/battle-rules/boundary-references.json", "analysis/card-action/provider-boundary.json", "analysis/card-action/input-fingerprints.json", "analysis/skill-graph/03109_graph.json", "analysis/skill-graph/00296_instructions.json"]:
        path = ROOT / name
        prior[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write("provider-status.json", {
        "actual_call": "context.cardAction.getRpgValue(target)", "target_default": "context.owner iff node.target is None",
        "actual_call_anchor": "296:20.6 [0x0,0x38)",
        "object_injection": "618:24.0 receives cardAction; 618:24.2 writes it into context",
        "common_helper": "3510:39 getCommonRpgFormulaValues",
        "proven_helper_callers": ["3207:6 BuffDataTools.getBuffDescriptList", "3598:10.6 RelicGetRpgDamage.Start"],
        "missing_edge": "No observed call connecting cardAction.getRpgValue to getCommonRpgFormulaValues",
        "native_location": "unproven; no new anchor to distinguish native implementation from absent server modules or another payload",
        "reused_prior_evidence_sha256": prior,
        "next_step": "Obtain a new server/patch/runtime artifact or explicitly choose a separately labelled reconstruction policy. Repeating the same name scan cannot validate zero fallback.",
    })
    write("function-sources.json", selected_functions)
    write("sources.json", sources)
    print(f"Verified {len(sources)} modules; exported {len(selected_functions)} functions, {len(matrix)} cards, {len(enemies)} enemy skills and 8 reference cases")


if __name__ == "__main__":
    main()
