"""Recover battle parameter provenance and publish a bounded scalar-port contract.

Never imports APK modules, constructs executable code objects, evaluates a string,
or interprets game bytecode. The scalar reference functions below are independent,
manually reviewed translations. Unresolved entity methods must remain inputs.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "analysis/battle-parameters"
# These pin the APK revision underlying the manually reviewed contract.
GUARDS = {
    618: "4c56f3a17723f1fd70fcadb687039af93c781882d7c4f0b02e5c6366bebba3d8",
    3510: "114173991c7458dc152e5d410f6f485b771af7ebdf1da5965b794b237751a5d0",
    4057: "5f2f5005957df167c2f4d871030a34d5ccb2fee4d4a817261f0b5271be6af40a",
    5973: "2afd2f51c37a386141806d3ba04b6af240cbbe9af6f77402bc62bc76b726bb97",
    6221: "e09e9130987752b7bd2f875e86b620cb6af290cf4fd291be1bd4b932031f2b9f",
    7042: "ea9b0bb6c277d605e039bbbc6e18d4eabad98fb8316659948129efa4709586fc",
    7554: "5ad78dc543e9a48f4365739497f8916b4604b4c6eec2ce4a7fdd8a33e2d59ab2",
    8010: "70e12558e90078b6d7f73c27a8b9755d68a45f98330052ced1e5d4bfa2487326",
    8527: "dc49779df51c11affbefe407292259ebabb7d4e5ebdb3f3ce2b0bb7149467047",
    9137: "76523206f60bf128cab471310a44f63b15f69cd65b967475fedb0a88f7cd4cd2",
    9176: "fc9d2d84bc2d3b79636c1b774292c2c69f91fb07a57556d43db0cba2655b8c64",
    9422: "3564bc207d67cc6e02b886cc8740c9ae342c3074a9df659f931a172a7cce8982",
    8750: "0fcde2fd8710b3e9617b1805ef4f1c74c8e155ecd21690a1f6dd622cd584874d",
    3391: "c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09",
    8903: "be8c1ea4abc43f7dab5e38187e6ac286f2f338aef1581313eb99d099dbea090c",
    6561: "9eb36cdf917798fd84e940279a4bd8dfdca67ea74d0086d8bfb9b85ec0d0e40a",
    1794: "48748b4c787a550d28f95d5fbf5b12a1a3713002ece489d6b0a9560ed0165c45",
}


def typed(value):
    """Keep Python integer/float distinctions across JSON/JavaScript boundaries."""
    if type(value) is int:
        return {"numeric_type": "integer", "decimal": str(value)}
    if type(value) is float:
        return {"numeric_type": "binary64", "decimal": repr(value), "hex": value.hex()}
    if isinstance(value, dict):
        return {str(k): typed(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [typed(v) for v in value]
    return value


def classic_div(a, b):
    return a // b if type(a) is int and type(b) is int else a / b


def resolved_damage(p):
    """Only calcDamage's scalar orchestration, with every dependency supplied.

    Inputs are a snapshot for one call, not methods resolved on invented entities.
    In particular extraAttackedValue and slowHp must come from the documented
    intermediate damage values; they are not assumed independent coefficients.
    """
    trace = []

    def record(name, value):
        trace.append({"stage": name, "value": value})
        return value

    value = record("base_and_add", p["rpgBasicActionValue"] + p["addAttackValue"])
    if p["rpgAttackType"] != 3:
        value = record("counter", value * p["combatCounterRatioValue"])
        value = record("defense", value * p["dstEntityDefenseValue"])
        buff = 1 + p["attackFactorValue"] + p["attackedFactorValue"]
        if p["dstIsPlayer"]:
            buff = max(1 - 0.9, buff)
        value = record("buff", value * buff)
        value = record("critical", value * p["criticalRatioValue"])
    ratio = 1 + p["propDamageIncValue"] - p["propDamageReduceValue"]
    if p["rpgAttackType"] == 1:
        ratio += p["propAtkDamageIncValue"] - p["propAtkDamageReduceValue"]
    elif p["rpgAttackType"] == 2:
        ratio += p["propMgcDamageIncValue"] - p["propMgcDamageReduceValue"]
    value = record("damage_properties", value * ratio)
    value = record("overwhelm", value * p["overwhelmRatio"])
    value = record("extra_attack", value + p["extraAttackValue"])
    value = record("extra_attacked", value + p["extraAttackedValue"])
    value = record("extra_damage", value + p["extraDamage"])
    if p["isPVP"]:
        value = record("pvp", value * p["pvpAtkRatio"])
    if p["isDamageSkillPreview"]:
        value = record("preview_slow_hp", value - p["slowHp"])
    if value <= 1:
        value = 1
    value = record("clamped", value)
    return int(value), trace


def overwhelm(src_player, dst_player, lv_diff, disabled):
    if disabled:
        return 1
    ratio = 0
    if src_player and not dst_player:
        if lv_diff < 5:
            ratio = 0
        elif lv_diff <= 15:
            ratio = 0.02 + 0.5 * (lv_diff - 5) * (lv_diff - 4) * 0.015
        else:
            ratio = 1
    elif not src_player and dst_player:
        if lv_diff <= 4:
            ratio = 0
        elif lv_diff <= 9:
            ratio = 0.5
        elif lv_diff < 15:
            ratio = 1.5
        elif lv_diff <= 30:
            ratio = 2 + 0.2 * (lv_diff - 15)
        else:
            ratio = 5
    if src_player and dst_player:
        ratio = 0  # All three observed branches assign exactly zero.
    elif not src_player and not dst_player:
        if lv_diff <= 3:
            ratio = 0
        elif lv_diff > 30:
            ratio = 2
        else:
            ratio = 0.5 * (lv_diff - 2) * (lv_diff - 3) * 0.005
    return 1 + max(0, ratio)


def counter_ratio(a, b, table, all_counter, all_ratio):
    if all_counter:
        return 1.0 if b == 7 else all_ratio / float(100)
    result = 100
    row = table.get(a)
    if row is not None:
        if row.get("beCounterID") == b:
            result = row.get("beCounterRatio", 100)
        if row.get("counterID") == b:
            result = row.get("counterRatio", 100)
    return result / float(100)


def critical_outcome(src_critical, defend_critical, block_prop, draw,
                     src_critical_damage, card_extra, block_damage_prop):
    """The supplied draw is random.uniform(0, max(critical+block, 1.0))."""
    critical = max(0, src_critical - defend_critical) / 1000.0
    block = block_prop / 1000.0
    upper = max(critical + block, 1.0)
    if not 0 <= draw <= upper:
        raise ValueError("draw is outside the source function's interval")
    if draw <= critical:
        return 1, src_critical_damage + card_extra
    if draw <= critical + block:
        return 2, 1.0 - block_damage_prop
    return 0, 1.0


def scalar_probes(counter_table):
    """Hand-selected expectations; no APK instructions are evaluated."""
    cases = []

    def check(kind, inputs, actual, expected, trace=None):
        if actual != expected:
            raise AssertionError((kind, inputs, actual, expected))
        cases.append({"kind": kind, "inputs": typed(inputs), "expected": typed(expected),
                      **({"trace": typed(trace)} if trace is not None else {})})

    # Explicit synthetic snapshots: neutral values here are test inputs only.
    base = dict(rpgBasicActionValue=100, addAttackValue=0, rpgAttackType=1,
                combatCounterRatioValue=1, dstEntityDefenseValue=1,
                attackFactorValue=0, attackedFactorValue=0, dstIsPlayer=False,
                criticalRatioValue=1, propDamageIncValue=0, propDamageReduceValue=0,
                propAtkDamageIncValue=0, propAtkDamageReduceValue=0,
                propMgcDamageIncValue=0, propMgcDamageReduceValue=0,
                overwhelmRatio=1, extraAttackValue=0, extraAttackedValue=0,
                extraDamage=0, isPVP=False, isDamageSkillPreview=False)
    snapshots = [
        (base, 100),
        ({**base, "rpgBasicActionValue": 100.75, "addAttackValue": 0.5,
          "combatCounterRatioValue": 1.2, "dstEntityDefenseValue": 0.5,
          "attackFactorValue": 0.1, "criticalRatioValue": 1.5,
          "propDamageIncValue": 0.3, "propDamageReduceValue": 0.1,
          "overwhelmRatio": 1.02, "extraAttackValue": 2, "extraAttackedValue": 3,
          "extraDamage": 4, "isPVP": True, "pvpAtkRatio": 0.8,
          "isDamageSkillPreview": True, "slowHp": 5.25}, 100),
        ({**base, "rpgAttackType": 3, "addAttackValue": 2,
          "propDamageIncValue": 0.1, "overwhelmRatio": 1.5,
          "extraAttackValue": 3, "extraAttackedValue": 4, "extraDamage": 5,
          "isPVP": True, "pvpAtkRatio": 0.8}, 144),
        ({**base, "attackFactorValue": -2, "dstIsPlayer": True}, 9),
        ({**base, "attackFactorValue": -2, "dstIsPlayer": False}, 1),
        ({**base, "rpgAttackType": 2, "propMgcDamageIncValue": 0.5,
          "propAtkDamageIncValue": 9}, 150),
        ({**base, "rpgAttackType": 3, "rpgBasicActionValue": 9007199254740993}, 9007199254740993),
        ({**base, "rpgBasicActionValue": 1.9}, 1),
    ]
    for inputs, expected in snapshots:
        result, trace = resolved_damage(inputs)
        check("resolved_damage", inputs, result, expected, trace)
    incomplete = dict(base)
    del incomplete["criticalRatioValue"]
    try:
        resolved_damage(incomplete)
    except KeyError:
        cases.append({"kind": "missing_required_dependency", "field": "criticalRatioValue", "expected": "reject"})
    else:
        raise AssertionError("missing coefficient was silently filled")
    for a, b, expected in [(100, 200, 0), (100.0, 200, 0.5), (-1, 2, -1), (-1.0, 2, -0.5)]:
        check("classic_division", [a, b], classic_div(a, b), expected)
    for sp, dp, level, disabled, expected in [
        (True, False, 4, False, 1), (True, False, 5, False, 1.02),
        (True, False, 15, False, 1.845), (True, False, 16, False, 2),
        (False, True, 4, False, 1), (False, True, 5, False, 1.5),
        (False, True, 9, False, 1.5), (False, True, 10, False, 2.5),
        (False, True, 15, False, 3.0), (False, True, 30, False, 6.0),
        (False, True, 31, False, 6), (True, True, 30, False, 1),
        (False, False, 3, False, 1), (False, False, 4, False, 1.005),
        (False, False, 30, False, 2.89), (False, False, 31, False, 3),
        (False, True, 30, True, 1),
    ]:
        args = [sp, dp, level, disabled]
        check("overwhelm", args, overwhelm(*args), expected)
    for a, b, all_counter, all_ratio, expected in [
        (1, 2, False, 100, 1.2), (1, 4, False, 100, 1.0),
        (1, 1, False, 100, 1.0), (999, 2, False, 100, 1.0),
        (1, 7, True, 170, 1.0), (1, 2, True, 170, 1.7),
    ]:
        args = [a, b, all_counter, all_ratio]
        check("counter", args, counter_ratio(a, b, counter_table, all_counter, all_ratio), expected)
    for args, expected in [
        ([0, 0, 0, 0.0, 1.5, 0, 0.3], (1, 1.5)),
        ([200, 0, 300, 0.2, 1.5, 0.25, 0.3], (1, 1.75)),
        ([200, 0, 300, 0.5, 1.5, 0, 0.3], (2, 0.7)),
        ([200, 0, 300, 0.500001, 1.5, 0, 0.3], (0, 1.0)),
    ]:
        check("critical_outcome_with_supplied_draw", args, critical_outcome(*args), expected)
    return {"evidence_kind": "independent scalar translations; synthetic vectors, not gameplay recordings",
            "numeric_encoding": "integer decimal strings and binary64 decimal/hex preserve Python numeric type",
            "cases": cases}


def main():
    inventory = {r["index"]: r for r in json.loads((static.SCRIPT / "index.json").read_text("utf8"))}
    modules = {}
    for index, digest in GUARDS.items():
        if inventory[index]["decoded_sha256"] != digest:
            raise ValueError(f"source revision changed for {index}; manually re-audit the contract")
        modules[index] = static.read_module(inventory[index])
    OUTPUT.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

    selected = {
        618: {(24, 0), (24, 2), (24, 3), (26, 4)},
        3510: {(14,), (19,), (22,), (27,), (28,)},
        4057: {(25, 8), (25, 10), (25, 12), (25, 13)},
        5973: {(35,), (47,), (49,), (80,)},
        6221: {(), (127,), (195,), (1175,)},
        7042: {(3,), (4,), (5,), (7,), (8,), (9,), (10,)},
        7554: {(5, n) for n in range(15)},
        8010: {(351,), (353, 1), (355, 1), (357,), (358,)},
        8527: {(507,)}, 9137: {(9, 0), (9, 1), (9, 5), (9, 8)},
        9176: {(37,), (42,), (43,), (44,)}, 9422: {(3, 2)},
        6561: {(62,)}, 1794: {(31,)},
    }
    sources = {}
    for index, paths in selected.items():
        evidence = static.export(inventory[index])
        evidence["code_objects"] = [c for c in evidence["code_objects"] if tuple(c["constant_path"]) in paths]
        for path, obj in static.walk_codes(modules[index]):
            if path not in paths:
                continue
            key = str(index) + ":" + ".".join(map(str, path))
            sources[key] = {"index": index, "filename": inventory[index]["filename"],
                "npk_offset": inventory[index]["offset"], "constant_path": list(path),
                "name": obj["name"].decode("utf8"),
                "bytecode_sha256": hashlib.sha256(obj["bytecode"]).hexdigest(),
                "field_reads": [{"name": i.get("operand"), "offset": i["offset"]}
                                for i in static.instructions(obj) if i["opcode"] == 0x60],
                "numeric_constants": [{"constant_index": n, **typed(v)} for n, v in enumerate(obj["consts"])
                                      if type(v) in (int, float)]}
        write(f"{index:05d}_instructions.json", evidence)

    cards = export_table(3391, {410101, 610101, 810101, 410102, 610102, 810102})
    states = export_table(8903, {365, 366, 367, 368})
    counters = export_table(8750, None)
    write("cards-with-upgrades.json", cards)
    write("skill-states.json", states)
    write("counter-types.json", counters)
    for row in cards["rows"] + states["rows"]:
        if row["fields"].get("_RUNTIMEARGS"):
            raise ValueError("sample contains runtime expressions; literal-only mapping is no longer adequate")
    by_card = {r["id"]: r for r in cards["rows"]}
    chains = []
    for start in (410101, 410102):
        sequence, seen, key = [], set(), start
        while key != -1:
            if key in seen or key not in by_card:
                raise ValueError("unexpected upgrade chain")
            seen.add(key)
            f = by_card[key]["fields"]
            sequence.append({"id": key, "level": f["LEVEL"], "skill_id": f["SKILL_ID"],
                             "diy_keys": f["SKILL_DIY_PARAMETER"], "diy_values": typed(f["SKILL_DIY_VALUE"]),
                             "display_formula": f["RPG_FORMULA"], "display_values": typed(f["RPG_DEFAULT_FORMULA"])})
            key = f["NEXT_LEVEL_ID"]
        chains.append(sequence)
    write("parameter-chains.json", {
        "format": "hczs-battle-parameter-provenance-v1", "upgrade_chains": chains,
        "edges": [
            {"from": "card_table.NEXT_LEVEL_ID", "to": "next card row", "source": "3510:14", "range": [0, 23]},
            {"from": "skillId", "to": "skill_state_table.extra_data row IDs", "source": "8010:357", "range": [0, 69]},
            {"from": "Adapter field", "to": "top-level row field, then row.DATA field, else None", "source": "8010:353.1", "range": [0, 129]},
            {"from": "cardAction argument", "to": "storyline.cardAction and context.cardAction", "source": "618:24.0", "range": [22, 35]},
            {"from": "STORYLINE_PARAM key", "to": "diyActionData same key overrides default", "source": "618:24.3", "range": [6, 137]},
            {"from": "diyActionData extra key", "to": "appended parameter with type string int", "source": "618:24.3", "range": [256, 349]},
            {"from": "SKILL_DIY_PARAMETER/VALUE", "to": "GM findRelation parameter map", "source": "8527:507", "range": [636, 927]},
        ],
        "unresolved_edges": [
            "No demonstrated constructor maps card_table SKILL_DIY_* to cardAction.diyActionData in this APK.",
            "getRpgValue provider and its possible RPG_* override rules remain unresolved; no repeat native-name audit was performed.",
            "The GM relation helper is not evidence that the battle constructor uses its mapping.",
            "athlete_utils special-skill DIY reads a different table, not ordinary card DIY.",
        ],
        "runtime_reader": {"source": "4057:25.12", "sample_runtimeargs_absent": True,
            "behavior": "get returns original row when _RUNTIMEARGS empty; __getitem__ returns raw row without this runtime branch"},
        "conditional_examples": [
            {"condition": "IF the unlocated builder supplies VALUE=0 from card 410102 as diyActionData",
             "consequence": "getCardParamList overrides the getCard state's VALUE=1 with 0",
             "proved_condition": False},
            {"condition": "IF no same-key DIY value is supplied", "consequence": "the state's VALUE=1 is retained"},
        ],
    })
    write("function-sources.json", {"modules": [inventory[i] for i in GUARDS], "functions": sources,
        "opcode_corroboration": {"0x51": {"name": "UNARY_NOT", "source": "6561:62", "offset": 368,
            "upstream": "https://github.com/python/cpython/blob/v2.7.18/Lib/calendar.py#L616"}}})
    write("calculation-contract.json", calculation_contract())
    probes = scalar_probes({r["id"]: r["fields"] for r in counters["rows"]})
    write("scalar-vectors.json", probes)
    write("new-boundary-search.json", boundary_search(inventory))
    print(json.dumps({"output": str(OUTPUT), "functions": len(sources),
                      "scalar_cases": len(probes["cases"]), "upgrade_rows": len(cards["rows"])}))


def calculation_contract():
    dependencies = [
        ("rpgBasicActionValue", "7042:10", "basicDamage + (improvement.factor * src.getRpgPropByKey(improvement.propType) + improvement.base) when base-card improvement exists", ["basicDamage", "cardTypeID/base-card map", "ownerTeam.athleteCardImproveData", "src rpg properties"]),
        ("addAttackValue", "7554:5.0", "card additional value + src.getAttackAddValue() + int(rpgBasicActionValue * (card.extraBaseDamagePercent / 100.0))", ["card.getAdditionalDamageValue", "src.getAttackAddValue", "card.extraBaseDamagePercent"]),
        ("combatCounterRatioValue", "3510:27", "all-counter override except OTHER_WORLD=7, else counter_type_table; ratio denominator float(100)", ["counter_type_table", "isCombatCounterAll", "combatCounterAllRatio", "combatCounterType"]),
        ("dstEntityDefenseValue", "7042:9", "PropAtk / (PropAtk + max(selected defense - PropBreakDefend, 0) * 5); attack==0 returns integer 0", ["src/dst getBasicProp", "Python 2 numeric operand types"]),
        ("attackFactorValue", "7554:5.4", "entity attack factor + card attack factor if target/card exist + battle.getExtraBattleFormula(src,dst,DamageIncPercent)", ["7554:5.9", "card.getAttackFactorValue", "battle.getExtraBattleFormula"]),
        ("attackedFactorValue", "7554:5.5", "entity attacked factor - reduceDamegedRate/100.0 unless id(src) is excluded", ["7554:5.8", "excludeReduceDamageDict", "reduceDamegedRate"]),
        ("criticalRatioValue", "7042:7", "truthy probInfo['CrticalAndBlockRatio'], else src.rpgGetCardCriticalDamageRatio(card)", ["probInfo", "7554:5.6", "card.getCriticalDamageRatio"]),
        ("property ratios", "7554:5.12", "getBasicProp maps enum to key; raw property plus modifiers; only PropAtk clamped >=0", ["7554:5.13", "7554:5.14", "rpgPropModifier numeric types and iteration order"]),
        ("overwhelmRatio", "7042:8", "piecewise source/destination IsPlayer and level difference, final 1+max(0,ratio); optional disable", ["src.avatar.notUseOverwhelm", "src/dst.level", "src/dst.IsPlayer"]),
        ("extraAttackValue", "7554:5.2", "card.getExtraDamageValue() if card exists, else 0", ["card.getExtraDamageValue"]),
        ("extraAttackedValue", "7554:5.3", "dst.getExtraBeHurtValue(); common implementation returns integer 0; subclass dispatch unverified", ["7554:5.11"]),
        ("pvpAtkRatio", "7042:7", "dst.battleInst.pvpAtkRatio when isPVP", ["battle instance state; assignment not recovered"]),
        ("slowHp", "7042:7", "dst.getCurrentHurtSlowHp(current value, damageInfo), only for skill preview", ["dst.getCurrentHurtSlowHp"]),
    ]
    # Ranges are byte offsets relative to common/formula.py calcDamage [7].
    stages = [
        ("base_and_add", [0x6b, 0x9c], "always", ["add", "rpgBasicActionValue", "addAttackValue"]),
        ("counter", [0xb7, 0xd0], "rpgAttackType != 3", ["multiply", "value", "combatCounterRatioValue"]),
        ("defense", [0xd0, 0xec], "rpgAttackType != 3", ["multiply", "value", "dstEntityDefenseValue"]),
        ("buff", [0xec, 0x153], "rpgAttackType != 3", ["multiply", "value", ["player_minimum_if", "dstIsPlayer", ["add", ["add", typed(1), "attackFactorValue"], "attackedFactorValue"], ["subtract", typed(1), typed(0.9)]]]),
        ("critical", [0x153, 0x17c], "rpgAttackType != 3", ["multiply", "value", "criticalRatioValue"]),
        ("damage_properties", [0x1bd, 0x299], "always", ["multiply", "value", "1+generalInc-generalReduce plus physical OR magic inc-minus-reduce"]),
        ("overwhelm", [0x299, 0x2b2], "always", ["multiply", "value", "overwhelmRatio"]),
        ("extra_attack", [0x2b2, 0x2cb], "always", ["add", "value", "extraAttackValue"]),
        ("extra_attacked", [0x2cb, 0x2ea], "always", ["add", "value", "extraAttackedValue"]),
        ("extra_damage", [0x2ea, 0x2f4], "always", ["add", "value", "extraDamage"]),
        ("pvp", [0x2f4, 0x313], "isPVP", ["multiply", "value", "pvpAtkRatio"]),
        ("preview_slow_hp", [0x313, 0x341], "isDamageSkillPreview", ["subtract", "value", "slowHp"]),
        ("minimum", [0x341, 0x356], "value <= 1", typed(1)),
        ("return", [0x3cf, 0x3d9], "always", ["int_truncate_toward_zero", "value"]),
    ]
    return {
        "format": "hczs-static-damage-contract-v1", "source": "7042:7",
        "status": "port-ready scalar orchestration with required resolved dependencies; not a battle engine",
        "dependencies": [{"name": n, "source": s, "expression": e, "requires": r} for n, s, e, r in dependencies],
        "stages": [{"name": n, "offset_range_end_exclusive": r, "when": c, "expression": e} for n, r, c, e in stages],
        "factor_collections": {
            "attack": {"source": "7554:5.9", "expression": "sequential sum(factor.getValue(dst)-1), then sequential sum(commonValue-1)"},
            "attacked": {"source": "7554:5.8", "expression": "sequential sum(factor.getValue(src)-1), then sequential sum(commonValue/100.0)"}},
        "random_helper": {"source": "7042:4", "draw": "uniform(0,max(critical+block,1.0))",
            "comparison": "critical if draw<=critical, else block if draw<=critical+block, else normal",
            "limits": "Do not substitute this helper for calcDamage's probInfo/card-critical path without a proven caller. RNG state/order is unresolved."},
        "numeric_rules": [
            "Preserve arbitrary-precision integer versus binary64 float tags, even for values such as 100.0.",
            "Classic division floors only when BOTH operands are integers; mixed/float division uses binary64.",
            "int(float) truncates toward zero; no intermediate rounding unless explicitly present in a dependency.",
            "Do not replace 1-0.9 by 0.1: binary64 100*(1-0.9) truncates to 9 in this exact expression.",
            "Do not reassociate multiplications/additions or reorder modifier dictionaries without a defined snapshot order.",
            "strengthFactor is accepted but not consumed by the observed _calcRpgBasicActionValue/getRpgPropByKey bodies.",
            "JSON raw numbers cannot preserve Python types or >2^53 integers; use the tagged scalar-vector representation.",
        ],
        "external_boundaries": ["cardAction construction and getRpgValue", "cardObj modifier methods",
            "entity getAttackAddValue and dynamic factor.getValue", "battle.getExtraBattleFormula",
            "runtime entity property types/collection order", "PVP state assignment", "preview delayed HP",
            "beHurt/shields/HP application", "RNG state/scheduling/turns/deck"],
        "caller_obligations": [
            "Reject missing coefficients instead of defaulting unknowns to zero/one.",
            "extraAttackedValue must be resolved after extraAttackValue using the intermediate value; slowHp after PVP.",
            "Synthetic test snapshots do not prove any specific card's real damage or runtime property types.",
            "Side effects of debugCalcDamage are excluded; the scalar contract preserves the numerical return only.",
        ],
        "constant_sources": {
            "RpgAttackType": {"source": "6221:195", "values": {"NotAttack": 0, "PhysicalAttack": 1, "MagicAttack": 2, "RealAttack": 3}},
            "PlayerMinReduceDamgeRatio": {"source": "6221:", "load_offset": 964, "store_offset": 967, "value": typed(0.9)},
            "CounterTypeEqualValue": {"source": "6221:", "load_offset": 13945, "store_offset": 13948, "value": typed(100)},
            "OTHER_WORLD": {"source": "6221:1175", "load_offset": 42, "store_offset": 45, "value": typed(7)},
        },
    }


def boundary_search(inventory):
    terms = {"diyActionData", "getAdditionalDamageValue", "getAttackAddValue", "getExtraDamageValue",
             "getExtraBattleFormula", "getCriticalDamageRatio", "getCurrentHurtSlowHp",
             "attackFactors", "attackedFactors", "attackCommonFactors", "attackedCommonFactors",
             "SKILL_DIY_PARAMETER", "SKILL_DIY_VALUE", "pvpAtkRatio"}
    symbols = [json.loads(line) for line in (static.SCRIPT / "symbols.jsonl").read_text("utf8").splitlines()]
    findings = []
    for symbol in symbols:
        if not terms.intersection(symbol["names"] + symbol["strings"] + symbol["functions"]):
            continue
        if "\\cdata\\" in symbol["filename"]:
            continue  # Selected table data is separately exported with row offsets.
        row = inventory[symbol["index"]]
        for path, code in static.walk_codes(static.read_module(row)):
            for item in static.instructions(code):
                if isinstance(item.get("operand"), str) and item["operand"] in terms:
                    findings.append({"source": row, "constant_path": list(path),
                                     "function": code["name"].decode("utf8"), "instruction": item})
    return {"scope": "new parameter/coefficient boundaries, direct names/assignments/literals in non-cdata modules",
            "limitations": "No absence proof for generated names, runtime inheritance/registration, external or additional payloads.",
            "references": findings}


if __name__ == "__main__":
    main()
