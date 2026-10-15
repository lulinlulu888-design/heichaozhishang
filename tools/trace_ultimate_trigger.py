"""Recover ultimate-card trigger evidence from hash-checked APK marshal data.

Only literal tables and partial static instructions are read. No APK bytecode,
game process, service, save, or business code is executed or changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import inspect_battle_rules as static
from extract_game_data import export_table
from trace_first_encounter import extra_index, literal_table


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "analysis/battle-rules/ultimate-trigger.json"
GUARDS = {
    3391: "c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09",
    3510: "114173991c7458dc152e5d410f6f485b771af7ebdf1da5965b794b237751a5d0",
    4105: "230956d4a7d2068f340490aa50a47d2f2323954307416d0f4a16add7b04432ab",
    5888: "1c02a407d9f1d55653f1abe6a822dc1b2cc5588f5fdd39507b194f155f4b54fc",
    6221: "e09e9130987752b7bd2f875e86b620cb6af290cf4fd291be1bd4b932031f2b9f",
    6655: "4f1659eb95b471280d008da89c3e7d93aca93f40f7c045ef6f763e73d19a1b48",
    8903: "be8c1ea4abc43f7dab5e38187e6ac286f2f338aef1581313eb99d099dbea090c",
    9333: "fc547f5c9239e1119840cb6fd3e155278b0e7311665eb74f40ceafc1929218a9",
}


def table_fields(table, row_id):
    return next(row["fields"] for row in table["rows"] if row["id"] == row_id)


def named_table_rows(index, names):
    # The extractor's early row filter uses raw marshal byte keys; filter decoded
    # textual keys only after its literal-only export has validated the table.
    result = export_table(index)
    result["rows"] = [row for row in result["rows"] if row["id"] in names]
    if {row["id"] for row in result["rows"]} != names:
        raise ValueError(f"Missing text-keyed rows in table {index}")
    return result


def source_code(inventory, index, names, paths=None):
    result = static.export(inventory[index], names)
    if paths is not None:
        result["code_objects"] = [code for code in result["code_objects"] if code["constant_path"] in paths]
    return result


def gate_disabled(course_rows, battle_id, round_number):
    """Explicit static-path interpretation of 5947:9, not APK execution."""
    for row in course_rows:
        fields = row["fields"]
        if fields["FirstBattleID"] == battle_id and fields.get("DisableSpecialSkill") is not None:
            enabled_round = fields.get("EnableSpecialSkillRound")
            return enabled_round is None or round_number < enabled_round
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inventory = json.loads((static.SCRIPT / "index.json").read_text("utf-8"))
    for index, digest in GUARDS.items():
        if inventory[index]["decoded_sha256"] != digest:
            raise ValueError(f"Source {index} changed; review the semantic assertions")

    tables = {
        "trigger_tip": named_table_rows(3935, {"BATTLE_ULT_TIPS"}),
        "round_tip": export_table(6578, {1004}),
        "keywords": export_table(6593, {53, 61, 63}),
        "courses": export_table(4105),
        "story_entry": export_table(1303, {3998}),
        "current_city_encounter": literal_table(6500, {10405}),
        "elsa_card": export_table(3391, {410104}),
        "elsa_skill": export_table(9333, {410104}),
        "elsa_special_link_and_legacy_fields": export_table(2302, {1}),
        "elsa_build": export_table(9561, {1, 2, 3, 4}),
        "elsa_video": export_table(5888, {410104}),
    }
    reverse_indexes = {}
    for label, index in [("states", 8903), ("timelines", 6655)]:
        reverse = extra_index(index, {410104})
        selected = set(reverse["requested"]["410104"]["value"])
        tables[label] = literal_table(index, selected)
        if any(row["fields"]["OwnerSkill"] != 410104 for row in tables[label]["rows"]):
            raise ValueError("Ultimate reverse-index ownership mismatch")
        reverse_indexes[label] = reverse

    card = table_fields(tables["elsa_card"], 410104)
    skill = table_fields(tables["elsa_skill"], 410104)
    states = sorted(tables["states"]["rows"], key=lambda row: row["fields"]["OwnerIndex"])
    damage = [row for row in states if row["fields"]["STORYLINE_NAME"] == "SkillState_CauseDamage"]
    factors = [int(row["fields"]["RPG_DEFAULT_FORMULA"]) for row in damage]
    if factors != [15, 15, 30, 30, 30, 60, 60, 60] or len(states) != 9:
        raise ValueError("Ultimate effect sequence changed")
    if any(row["fields"]["RPG_FORMULA"] != "PropAtk" or row["fields"]["DAMAGE_TYPE"] != 1
           or row["fields"]["SKILL_STATE_TARGET_TYPE"] != 16 for row in damage):
        raise ValueError("Ultimate formula/type/target changed")
    if card["COST"] != 0 or card["CARD_TYPE"] != 7 or card["SKILL_ID"] != 410104:
        raise ValueError("Ultimate card identity changed")
    if not (card["CARD_DISAPPEAR"] and card["NOT_FREEZE"]) or skill["SKILL_TARGET_TYPE"] != 1:
        raise ValueError("Ultimate lifecycle/selection changed")

    codes = {
        "points_and_per_round_limit": source_code(inventory, 3510, ["getCardIncreaseSpecialSKillNum", "isSpecialSkillCardReachLimit"]),
        "card_and_target_enums": source_code(inventory, 6221, ["CardTypeEnum", "SkillTargetType"]),
        "tutorial_gate": source_code(inventory, 5947, ["isDisableSpecialSkill"]),
        "card_point_prediction": source_code(inventory, 9176, ["canAddSpecialEnergy", "getIsSpecialSkillCard"]),
        "received_slots": source_code(inventory, 8434, ["getBattleSpecialSkillEnergySlot", "getCharSpecialSkillCardID"]),
        "slot_refresh": source_code(inventory, 5455, ["onSpecialSkillEnergySlotChange"]),
        "autofight_count": source_code(inventory, 9364, ["_getFullSpecialSkillValue"]),
        "generation_nodes": source_code(inventory, 7693, ["Start"], [[215, 6], [496, 5]]),
        "draw_from_air": source_code(inventory, 5026, ["getIsSingleSpecialSkillCardShow", "onReceive", "play"], [[11, 1], [11, 3], [11, 4]]),
    }
    top = list(static.instructions(static.read_module(inventory[6221])))
    end = next(i for i, item in enumerate(top) if item.get("operand") == "MAX_SPECIAL_SKILL_ONE_CHAR_ONE_ROUND")
    if top[end - 1].get("operand") != 3:
        raise ValueError("Per-character per-round generation limit changed")
    codes["round_limit_literal"] = {"source": inventory[6221], "constant_path": [], "instructions": top[end - 1:end + 1]}
    graphs = {}
    for label, index in [("damage", 4168), ("energyadd", 9093)]:
        graphs[label] = {"source": inventory[index], **static.literal_story_graph(static.read_module(inventory[index]))}

    search_terms = {"addSpecialSkillEnergySlot", "specialSkillEnergySlot", "haveGetSpecialSkillCardInRound", "specialSkillponit"}
    references = []
    for line in (static.SCRIPT / "symbols.jsonl").read_text("utf-8").splitlines():
        item = json.loads(line)
        hits = sorted(search_terms.intersection(item["names"] + item["strings"] + item["functions"]))
        if hits:
            references.append({"index": item["index"], "filename": item["filename"], "terms": hits,
                               "definition_names": sorted(search_terms.intersection(item["functions"]))})

    course_rows = tables["courses"]["rows"]
    gates = [{"battleId": battle, "round": round_number,
              "disabled": gate_disabled(course_rows, battle, round_number)}
             for battle, round_number in [(5000, 1), (5000, 2), (1703, 1), (1703, 2), (10405, 1)]]
    assert [gate["disabled"] for gate in gates] == [True, True, True, False, False]
    result = {
        "schemaVersion": 1,
        "evidenceKind": "Hash-checked APK static literals/instructions; no original runtime or traffic observed",
        "tables": tables, "code": codes, "reverseIndexes": reverse_indexes, "graphs": graphs,
        "observedRules": {
            "trigger": {"consecutivePointsFromSameCharacter": 3, "maximumGeneratedPerCharacterPerRound": 3,
                        "evidence": ["3935:BATTLE_ULT_TIPS", "6578:1004", "6221:<module>:976..982", "9364:14.19"]},
            "pointRule": {"explicitOverrideField": "card_table.SPECIALSKILL_POINT", "overridePrecedesTypeCheck": True,
                          "otherwiseUltimateType7": 0, "otherwiseMismatchingCharacterClass": 0, "otherwise": 1,
                          "receivedDynamicOverride": "cardInfo.specialSkillponit (original spelling)",
                          "evidence": ["3510:57", "9176:124"],
                          "excludedKeywordDescriptions": {"61": "临时", "63": "耗竭"}},
            "lifecycle": {"cost": 0, "cannotFreeze": True, "removeWhenLeavingHand": True,
                          "cardId": 410104, "cardType": 7, "evidence": ["3391:410104", "6593:53"]},
            "generationDestination": {"pile": "HAND_CARD_PILE", "owner": "target.charID", "count": 1,
                                      "evidence": "7693:496.5 AddSpecialSkillCardNode.Start",
                                      "limit": "This proves the explicit generation node; the ordinary three-point server mutator body is not present in the inspected client scripts."},
        },
        "elsa": {
            "characterId": 1, "cardId": 410104, "skillId": 410104, "name": card["NAME"],
            "damageStateIds": [row["id"] for row in damage], "stagePercentages": factors, "sumPercent": sum(factors),
            "target": {"skillTargetType": 1, "symbol": "ENUM_OPPOSITE_SINGLE", "stateTargetType": 16, "stateSymbol": "ENUM_SINGEL"},
            "lastState": states[-1], "video": table_fields(tables["elsa_video"], 410104),
            "damagePolicyBoundary": "Use each state's percentage with the existing explicit neutral damage policy; original getRpgValue/cardAction provider remains unresolved. Do not apply card-level 300 to all eight states.",
            "legacyConflict": "speciall_skill_table[1] retains SkillID=600, Damage=175 and an all-enemies description. Its SpecialSkillCardID=410104 is still read by the current card path; legacy damage/energy fields are not the 410104 card rules.",
        },
        "entryGates": {
            "interpretation": "Static evaluation of 5947:9 and all five course rows; not original-server observation",
            "cases": gates,
            "firstExplicitTutorialEnable": {"mazeId": 3998, "name": "序章 终局", "battleId": 1703, "sceneId": 2004,
                                            "firstEnabledRound": 2, "characters": [1, 3], "currentlyPlayableDefinition": False},
            "existingCityPreview": {"encounterId": "city-preview-10405", "battleId": 10405,
                                    "sourceName": table_fields(tables["current_city_encounter"], 10405)["Name"],
                                    "sourceTutorialGateAllowsRound1": True,
                                    "storyUnlockRecovered": False,
                                    "scope": "The only current non-tutorial playable definition; may opt into the recovered default gate as a local preview after the engine implements generation. Not a recovered official progression entry."},
        },
        "providerBoundary": {"inventoryEntries": len(inventory), "exactSymbolReferences": references,
                             "originalServerComboMutatorRecovered": False,
                             "unknowns": ["Exact ordinary generation ordering relative to skill effects and lethal damage",
                                          "Overflow/hand-full handling and extra-point overflow",
                                          "Whether no-point cards leave or break an existing streak in every server edge case",
                                          "Exact turn-reset implementation; same-round requirement is observed in shipped descriptions",
                                          "Native/dynamic implementation and live server-only modifiers are outside this static search"]},
        "minimalAuthoritativeImplementation": [
            {"step": 1, "scope": "Versioned opt-in definition/state", "details": "Keep existing v1/v2 saves valid. Add explicit ultimate rules and runtime card ownership/type/point/lifecycle metadata. Persist current streak owner+points and per-character per-round generated counts."},
            {"step": 2, "scope": "Accepted play-card command", "details": "Inside the existing transaction, advance eligible same-character points, generate at three with cap three, append a deterministic unique owned instance to hand, and emit the resulting state/events once. Ultimate itself contributes zero. Client only predicts presentation."},
            {"step": 3, "scope": "Card lifecycle and validation", "details": "Allow validated generated registry entries and nonempty removed zone, remove ultimate after play or leaving hand, never recycle into discard/draw; reset round counters/streak according to explicit same-round policy. Bound accumulated generated/removed registry separately from hand/deck; 30 rounds can produce 90 ultimates."},
            {"step": 4, "scope": "Evidence-backed 410104 effects", "details": "Add eight individual damage effects from state percentages, keep numeric tagged/AP semantics and per-hit rounding. Treat energyadd(num=0,num1 default0) as a verified no-op. Use the existing play-card request with server-issued instanceId, not a client-supplied skill or damage total."},
            {"step": 5, "scope": "Scenario gate", "details": "Keep tutorial-5000 disabled. Only opt city-preview-10405 into its source default tutorial gate after the versioned engine is ready; restoring official 3998/1703 requires the two-character encounter definition and round-2 unlock."},
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cardId": 410104, "hitCount": len(factors), "stagePercentages": factors,
                      "gateCases": gates, "firstExplicitTutorialEnable": "3998 / 1703 / round 2",
                      "businessCodeChanged": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
