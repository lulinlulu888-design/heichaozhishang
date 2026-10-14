"""Hash-verified skill-graph static evidence; never execute original bytecode."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis/skill-graph"
GUARDS = {
    71: "f9d322b39dd33d8d3497cbb3a02eb8247abc5c845054e155082f1e2dad45e149",
    296: "c4c17c0ea6978bb79d210fa114ba7a9dd7e94547a1a158378024a986677fc8ad",
    353: "df922fac91e200a1e38ec32bb57d4cdce03227497158bea9e80278d4e45d4af8",
    618: "4c56f3a17723f1fd70fcadb687039af93c781882d7c4f0b02e5c6366bebba3d8",
    876: "8aab07824608ad9c4165ccb96a87ee8b1be2c3c02f402fe3b00088a3e5ddd8fc",
    1113: "063d1b1823940b950ea87c6768c15a854e2287502abc0a668cd9ff2ea63784b0",
    1467: "c1d8ac7b70c2816e1930a1c6b6bb817b9ab1bf52064d467a10a7f00f0e355e04",
    2259: "90d9cf79986bc2e693a5fa301f6d15371442c276c57302a14149e65929344eea",
    2657: "16825103cb4fcc14ac1de78281cff7b57dd4443280232db593a23de1917c5285",
    2905: "b41ad44d153a5e4ce30f147ee5025624ef967aa021361cd5a43ee73cae1d8890",
    3109: "f2922890e19f1eade4c4e937090805a453cae3ebfea24cfff1cabcb137c8bcda",
    3337: "ed10841fd909d595d2401743d6b9d8d8cece2a4510b42b1942e028520cf81fc9",
    3440: "ca5815437fd4137d05830808d087d263c589d895bb27764f3e6c1c77c58974b9",
    4059: "5971ddca28cb668efef58e156d17504547cb76266a90cb4b052728ac56db0efb",
    4168: "cd433af95790fb7d03d603d5b0d2fca3d8757f13ce7f3eb4500c69e809e381b8",
    4388: "979b65f716df4c98104f9612c14eb698ec268e475d92a4d841aafb782c64e3fe",
    4762: "bbbf251bb41e64ff3964c816331caeab5e75b8502a1e7766071299b5d86ad993",
    5250: "d54efaf1a338297946de71d8b2628a84e061ff3726c53047fa605c777e944581",
    6224: "2dd6c63498657b4be579e667be35510b277dd98ce1c34a9645a911dbae410a67",
    7042: "ea9b0bb6c277d605e039bbbc6e18d4eabad98fb8316659948129efa4709586fc",
    7186: "91c02e2a06f2a6ccedbd6e10587f1d7c4a4e6fccb7260ab09706afe48342d8fe",
    7455: "39791d4338014c4d41f0df310d3a2707dd5aed515f213a1be41ccca49b76b597",
    7693: "3fd1651026d81ce7add3654d16a78322249c7bad3f38fd148413d3a1f2e71317",
    7930: "46ff8b34afea4f0ac5899f2e573e30629603e740ad6d9a9a659d307ec6471894",
    7975: "901284167e043fda103c708eaed0401eeeb70863ccfd9a64d6e4a4aa0aa9766f",
    8010: "70e12558e90078b6d7f73c27a8b9755d68a45f98330052ced1e5d4bfa2487326",
    8178: "47769899605505af644076ba4c80305d7e0a1a174696a61fd47f7ae6eec1b9ac",
    8593: "eecae643ae57054115e971936dc44407de8a572be9ca65c51b05ec241d469a18",
    8951: "eb3401d986c1cc385a108923387e08bd19ae9afc23c1ce2af8c80c16530b9e85",
    9072: "e3547215ffc6ef0836491216fd9af9a965c2c3ace6f815a0cc843f49092bf162",
}

# Local only: corroborated against the bundled standard library and official
# CPython source. These labels do not claim native opcode-dispatch recovery.
LOCAL_OPS = {0x81: "LOAD_DEREF", 0x78: "LOAD_CLOSURE", 0x64: "MAKE_CLOSURE",
             0x8e: "CALL_FUNCTION_VAR_KW", 0xad: "LOAD_FAST_0_AND_CONST"}
GRAPH_MODULES = (2657, 3109, 4168, 7455, 8593)

# Explicit input/output port definitions for just the three inspected graphs.
# __out__ can be a data port (IntParameter), so classify by type and port,
# never by port spelling alone.
PORTS = {
    "IntParameter": ({}, {"__out__": "data"}),
    "StartEvent": ({}, {"__out__": "trigger"}),
    "DrawCardsNode": ({"__in__": "trigger", "num": "data", "filter": "data"},
                      {"__out__": "trigger", "cards": "data"}),
    "SkillGetRpgValue": ({"__in__": "trigger", "target": "data"},
                         {"__out__": "trigger", "rpgValue": "data"}),
    "CardFormulaAndDealDamage": ({"__in__": "trigger", "damageValue": "data", "finalExtraDamage": "data"},
                                 {"__out__": "trigger"}),
    "ProcedureStartNode": ({}, {"procedure": "data", "element": "data", "start": "trigger"}),
    "ProcedureEndNode": ({"end": "trigger", "output": "data"}, {}),
    "GetCardEnergyNode": ({"__in__": "trigger", "card": "data"},
                          {"__out__": "trigger", "isX": "trigger", "result": "data"}),
    "CompareNode": ({"__in__": "trigger", "x": "data", "target": "data"},
                    {"less": "trigger", "equal": "trigger", "greater": "trigger"}),
    "CalculateDamageNode": ({"__in__": "trigger", "basicDamage": "data", "finalExtraDamage": "data"},
                            {"__out__": "trigger", "damage": "data"}),
    "FunctionStartNode": ({}, {"procedure": "data", "start": "trigger"}),
    "FunctionNode": ({"__in__": "trigger", "procedure": "data"},
                     {"__out__": "trigger", "paramOut1": "data"}),
    "FunctionEndNode": ({"end": "trigger", "paramOut1": "data"}, {}),
    "MonsterIntentionStartNode": ({}, {"__out__": "trigger"}),
    "SetMonsterIntention": ({"__in__": "trigger", "damageValue": "data"}, {"__out__": "trigger"}),
    "AddShieldCard": ({"__in__": "trigger", "shieldValue": "data"}, {"__out__": "trigger"}),
    "IntAddNode": ({"x": "data-trigger", "y": "data-trigger"}, {"result": "data"}),
}


def enrich(result, module):
    objects = dict(static.walk_codes(module))
    for code in result["code_objects"]:
        raw = objects[tuple(code["constant_path"])]
        code["cellvars"] = static.jsonable(raw["cellvars"])
        code["freevars"] = static.jsonable(raw["freevars"])
        for ins in code["instructions"]:
            op, arg = ins["opcode"], ins["argument"]
            if op not in LOCAL_OPS:
                continue
            if op == 0xad and (result["source"]["index"], tuple(code["constant_path"])) not in {
                (7930, (8,)), (5250, (36, 5)), (5250, (36, 7)),
                (5250, (48, 10)), (5250, (48, 12)),
            }:
                continue
            ins["opname"] = LOCAL_OPS[op]
            ins["mapping_basis"] = "local analyst corroboration; opcode-corroboration.json"
            if op in (0x81, 0x78):
                pool = raw["cellvars"] + raw["freevars"]
                if arg >= len(pool):
                    raise ValueError("closure operand outside cell/free variable pool")
                ins["operand"] = static.jsonable(pool[arg])
            elif op == 0xad:
                if not raw["varnames"] or arg >= len(raw["consts"]):
                    raise ValueError("fused fast-zero/constant operand outside pools")
                ins["operand"] = {"fast_0": static.jsonable(raw["varnames"][0]),
                                  "constant": static.jsonable(raw["consts"][arg])}
    return result


def normalize_graph(index, data):
    storyline = data["Storyline"]
    nodes = storyline["nodeData"]
    expected_types = {
        2657: sorted(["IntParameter", "CardFormulaAndDealDamage", "CalculateDamageNode", "FunctionStartNode", "FunctionNode", "FunctionNode", "FunctionEndNode", "MonsterIntentionStartNode", "SetMonsterIntention", "SkillGetRpgValue", "StartEvent"]),
        3109: ["DrawCardsNode", "IntParameter", "StartEvent"],
        4168: ["CardFormulaAndDealDamage", "IntParameter", "SkillGetRpgValue", "StartEvent"],
        8593: ["CompareNode", "DrawCardsNode", "GetCardEnergyNode", "ProcedureEndNode", "ProcedureStartNode", "StartEvent"],
        7455: ["AddShieldCard", "IntAddNode", "IntParameter", "SkillGetRpgValue", "StartEvent"],
    }
    if sorted(n["Type"] for n in nodes.values()) != expected_types[index]:
        raise ValueError("graph node schema changed")
    edges = []
    for ordinal, edge in enumerate(storyline["lineData"]):
        src, dst = nodes[edge["startNode"]], nodes[edge["endNode"]]
        kind = PORTS[src["Type"]][1][edge["startPort"]]
        input_kind = PORTS[dst["Type"]][0][edge["endPort"]]
        if kind != input_kind.split("-")[0]:
            raise ValueError("unexpected mixed data/trigger edge in inspected graph")
        edges.append({"literal_ordinal_not_runtime_order": ordinal, "kind": kind,
                      "input_starts_node_on_data": input_kind == "data-trigger",
                      "source_type": src["Type"], "target_type": dst["Type"], **edge})
    for key, node in nodes.items():
        if node["NodeID"] != key:
            raise ValueError("graph NodeID differs from map key")
    return {"index": index, "nodes": nodes, "edges": edges,
            "limit": "Structural normalization only, not execution; dict/set ordering is not reconstructed."}


def build_contract(exports):
    def anchor(index, path, start=0, end=None):
        code = next(c for c in exports[index]["code_objects"] if c["constant_path"] == list(path))
        end = code["bytecode_size"] if end is None else end
        boundaries = {i["offset"] for i in code["instructions"]} | {code["bytecode_size"]}
        if start not in boundaries or end not in boundaries or start >= end:
            raise ValueError(f"invalid source interval {index}:{path} {start}:{end}")
        return {"module_index": index, "npk_offset": exports[index]["source"]["offset"],
                "constant_path": list(path), "name": code["name"],
                "bytecode_sha256": code["bytecode_sha256"], "interval": [start, end]}

    rules = [
        ("load", "LoadFromFile imports storyline_implement.<filename>, reads data, JSON-decodes str, then calls NodeGraphBuilder. This tool extracts the literal instead of performing that import.",
         [anchor(353, (13, 2), 0x2b, 0x8c), anchor(353, (13, 4))]),
        ("graph-schema", "nodeData is keyed by NodeID; lineData contains startNode/startPort/endNode/endPort. Builder creates nodes from Type and updates registered metadata fields from Data; parameterStyle, parameterName, value are separate parameter fields.",
         [anchor(8951, (29, 0)), anchor(8951, (9, 1)), anchor(8951, (9, 3)), anchor(8951, (9, 4)), anchor(9072, (13, 0))]),
        ("battle-parameters", "Battle runner retains every matching inputName node. It applies triples in list order, sets all nodes with matching name and exact type tag, does no numeric coercion, and ignores unmatched names/types. Thus the last same-name same-type triple wins for those nodes.",
         [anchor(1113, (7, 5)), anchor(1113, (9, 10)), anchor(1113, (9, 11)), anchor(2259, (35, 7))]),
        ("auto-start", "Sort (priority, runtime nodeID) descending. Parameter/FunctionStart/ProcedureStart priority 1000, StartEvent 1. Battle Run filters StartEvent subclasses by class-name membership in startNodes, while still running other auto-start nodes.",
         [anchor(876, (1, 0), 0x69, 0xc3), anchor(1113, (9, 10), 0x28, 0x3b), anchor(1113, (9, 12)), anchor(2259, (35, 5)), anchor(2259, (11, 1))]),
        ("synchronous-dispatch", "StartNode invokes Start(context); only a dict return synchronously calls FinishNode. None does not mean an empty success dictionary and does not automatically follow outgoing edges.",
         [anchor(876, (1, 5), 0xf1, 0x104), anchor(876, (1, 5), 0x16a, 0x192)]),
        ("finish-phases", "FinishNode first records output-trigger destinations, then writes all data outputs through input ports. Data ports with IsTrigger true queue destination starts. It appends ordinary trigger destinations afterwards and starts this list synchronously. Base InputData returns newData and does not wait for all incoming edges.",
         [anchor(876, (1, 6), 0xed, 0x375), anchor(4059, (8, 3)), anchor(4059, (8, 4))]),
        ("default-output", "For nodes with output triggers, pop __out__ from outputs. A falsy trigger list falls back to ['__out__'] if that output port exists in connectToMap; a string becomes a one-element list. An empty output dictionary can therefore continue along a default trigger.",
         [anchor(876, (1, 6), 0xed, 0x14e)]),
        ("ordering-limit", "Runtime connections are sets. Node IDs for editor-form graphs are allocated during Python 2 dict iteration. Do not promise JSON edge order, lexical NodeID order, or OwnerIndex order. The recovered guarantee is data-phase-before-trigger-phase; arbitrary multiple writers/fanout ordering remains unspecified.",
         [anchor(9072, (11, 0, 1)), anchor(9072, (11, 0, 2)), anchor(9072, (13, 2)), anchor(9072, (13, 3), 0xc7, 0xfe)]),
        ("rpg-boundary", "SkillGetRpgValue uses node.target, falling back to context.owner only for None, then returns cardAction.getRpgValue(target). It does not evaluate RPG_FORMULA. skillTableAdapter does field wrapping/type conversion, with no formula evaluation in these functions.",
         [anchor(296, (20, 6)), anchor(8010, (353, 1)), anchor(8010, (357,))]),
        ("draw-boundary", "With no filter, DrawCardsNode makes an always-true predicate and sets isNowDrawPile=False; with a procedure filter it sets True and synchronously evaluates the procedure via a nesting stack. It calls context.ownerTeam.drawCardsFromDrawPile(num, cardFilterFun=..., isNowDrawPile=...), then returns cards. Deck traversal/shuffle/limits/RNG are outside this node.",
         [anchor(7693, (63, 7)), anchor(7693, (63, 7, 1)), anchor(7693, (63, 7, 2)), anchor(7693, (63, 8))]),
        ("damage-boundary", "CardFormulaAndDealDamage truncates damageValue with Python int, resolves exact-int 0/1 entity selectors to owner/target, applies non-None actionData.DAMAGE_TYPE, creates DamageInfo including finalExtraDamage, attaches cardActionObj and isDamageSkill=True, and calls dstEntity.beHurt. The node does not set final HP.",
         [anchor(4762, (21, 8))]),
        ("shield-input", "SkillState_AddShield sends VALUE to IntAddNode.y and RPG output to x. Both data inputs are triggering; _calculateResult emits x+y without an integer cast. Data-trigger dispatch computes the sum before the explicit AddShieldCard trigger.",
         [anchor(7975, (13,)), anchor(7975, (13, 6)), anchor(7975, (22, 0)), anchor(876, (1, 6), 0x2d6, 0x313)]),
        ("shield-boundary", "For oprtType=0 AddShieldCard resolves target 0/1, calls calcBlock(shieldValue,1.0,target,cardObj,srcEntity=context.owner) and then target.addShieldHp(block,owner,getSkillInfo()). Type 1 force-sets shield, other types call decShieldHp. The inspected graph has oprtType=0.",
         [anchor(4762, (25, 6))]),
        ("monster-branches", "MonsterCauseDamage has distinct StartEvent (actual beHurt path) and MonsterIntentionStartNode (CalculateDamageNode then setMonsterIntention) branches. Both use a shared FunctionStart/End subgraph calling getRpgValue; VALUE reaches finalExtraDamage on both. Preview marks isDamageSkillPreview=True and calls calcDamageWithDamgeInfo without beHurt.",
         [anchor(618, (26, 1)), anchor(618, (26, 5)), anchor(6224, (11, 9)), anchor(7186, (11, 3))]),
        ("function-subgraph", "FunctionNode pushes itself, clears _result, awakens FunctionStartNode with paramIn1..5, then pops and returns _result. FunctionEndNode calls currNest.onFunctionEnd(paramOut1..5). This is synchronous nesting, not a promise or an independent asynchronous graph.",
         [anchor(5250, (44, 16)), anchor(5250, (44, 17)), anchor(5250, (48, 10)), anchor(5250, (48, 12)), anchor(5250, (52, 8))]),
        ("conditional-nodes", "CompareNode selects less/equal/greater using < then ==; YesNoNode applies Python bool to _calculate. EqualNode instead uses COMPARE_OP 8 (identity is), so numeric value equality is not a compatible replacement.",
         [anchor(5250, (12, 7)), anchor(5250, (20, 2)), anchor(5250, (16, 6))]),
        ("filtered-zero-energy", "Graph 640018 requests two cards through a filter: ProcedureStart.element -> GetCardEnergyNode -> CompareNode(target=0).equal -> ProcedureEnd. Energy-all cards emit isX with no result; that port is unconnected in this graph, so they do not reach the equality branch. The node reads provided runtime energy, not printed card-table cost.",
         [anchor(2905, (51, 7)), anchor(5250, (36, 5)), anchor(5250, (36, 7)), anchor(5250, (40, 4))]),
    ]
    block = {
        "evidence": anchor(7042, (11,)),
        "steps_in_order": [
            "if srcEntity truthy: call _calcRpgBasicActionValue(basicBlock,srcEntity,cardObj) with THREE positional arguments; helper signature is (basicValue,srcEntity,strengthFactor=None,cardObj=None), so third argument binds strengthFactor and helper.cardObj remains None; helper returns basicBlock unchanged. Else value=basicBlock.",
            "if srcEntity truthy: value *= 1 + src.PropAddTargetShield/1000.0",
            "if dstEntity truthy: value *= 1 + dst.PropBeAddShield/1000.0",
            "dstFactor=dst.getShieldFactorValue() if dst else 0; srcFactor=src.getSrcAddTargetShieldFactor(dst) if src else 0",
            "value *= 1 + srcFactor + dstFactor + (card.extraBaseBlockPercent/100.0 if card else 0)",
            "value += card.getAdditionalBlockValue() if card else 0",
            "if dst.battleInst.isPVP: value *= dst.battleInst.pvpShieldRatio",
            "return int(max(0,value))",
        ],
        "unused_arguments_in_this_body": ["agilityFactor", "cardActionObj"],
        "helper_call_binding": {"signature": ["basicValue", "srcEntity", "strengthFactor=None", "cardObj=None"],
                                "call_argument_count": 3, "instruction_offset": 0x12,
                                "strengthFactor_receives": "calcBlock.cardObj", "helper_cardObj": None,
                                "consequence": "No athleteCardImproveData bonus in calcBlock's initial helper call. Preserve this observed behavior, including when calcBlock.cardObj is truthy.",
                                "helper_evidence": anchor(7042, (10,)),
                                "defaults_evidence": "7042 module offsets 0x6a/0x6d load None; MAKE_FUNCTION 2"},
        "limit": "Formula body recovered; modifier providers, entity state changes, and authoritative initial attributes are external. Do not default missing providers to zero/one.",
    }
    return {
        "kind": "human-reviewed static reconstruction contract; no original game code executed",
        "source_scope": "bundled SunshineClient runtime and shared node classes; server runtime branch is not present as the same modules",
        "rules": [{"id": key, "meaning": meaning, "evidence": refs} for key, meaning, refs in rules],
        "calcBlock": block,
        "known_external_interfaces": ["cardAction.getRpgValue(target)", "ownerTeam.drawCardsFromDrawPile(num,cardFilterFun,isNowDrawPile)", "dstEntity.beHurt(DamageInfo)", "target.addShieldHp(block,owner,skillInfo)", "cardAction.setMonsterIntention(damageValue,damageTime)", "formula modifier providers from battle-parameters/calculation-contract.json"],
        "not_recovered": ["DIY table-list to runtime diyActionData provider", "skill-state OwnerIndex execution ordering", "getRpgValue formula evaluator", "authoritative HP/shield/deck state machine", "arbitrary graph fanout/set order"],
    }


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {r["index"]: r for r in json.loads((static.SCRIPT / "index.json").read_text(encoding="utf8"))}
    sources, exports, graphs = [], {}, []
    for index, expected in GUARDS.items():
        row = rows[index]
        if row["decoded_sha256"] != expected:
            raise ValueError(f"module {index}: evidence version changed")
        module = static.read_module(row)
        result = enrich(static.export(row), module)
        exports[index] = result
        write_json(f"{index:05d}_instructions.json", result)
        sources.append(result["source"])
        lines = [f"module {index}: {row['filename']}", f"NPK offset {row['offset']}; SHA256 {expected}"]
        for code in result["code_objects"]:
            lines += [f"\n### {code['name']} {code['constant_path']} line={code['firstlineno']}",
                      f"bytecode_sha256={code['bytecode_sha256']}", f"locals={code['varnames']}"]
            for ins in code["instructions"]:
                lines.append(f"{ins['offset']:05x} {ins['opname']:24} {str(ins['argument']):5} {ins.get('operand', '')!r}")
        (OUT / f"{index:05d}_partial-dis.txt").write_text("\n".join(lines) + "\n", encoding="utf8")
        if index in GRAPH_MODULES:
            ins = list(static.instructions(module))
            if [i["opname"] for i in ins] != ["LOAD_CONST", "STORE_NAME", "LOAD_CONST", "RETURN_VALUE"] or ins[1].get("operand") != "data":
                raise ValueError("graph module is not a single literal assignment")
            literal = module["consts"][ins[0]["argument"]]
            if not isinstance(literal, bytes):
                raise ValueError("graph data must be literal bytes")
            graph_data = json.loads(literal.decode("utf8"))
            graphs.append(normalize_graph(index, graph_data))
            write_json(f"{index:05d}_graph.json", {"source": result["source"],
                "literal_sha256": hashlib.sha256(literal).hexdigest(),
                "constant_index": ins[0]["argument"], "assignment_offset": ins[1]["offset"],
                "data": graph_data})
    write_json("normalized-graphs.json", graphs)
    write_json("execution-contract.json", build_contract(exports))
    enemy_row = rows[8903]
    if enemy_row["decoded_sha256"] != "be8c1ea4abc43f7dab5e38187e6ac286f2f338aef1581313eb99d099dbea090c":
        raise ValueError("enemy skill-state table version changed")
    static.read_module(enemy_row)
    enemy_states = static.export_table(8903, {2, 3, 4})
    write_json("enemy-skill-states.json", enemy_states)
    write_json("enemy-value-boundaries.json", {
        "source": enemy_states["source"],
        "rows": [{"state_id": r["id"], "skill_id": r["fields"]["OwnerSkill"],
                  "graph": r["fields"]["STORYLINE_NAME"],
                  "VALUE": r["fields"]["STORYLINE_PARAM"]["VALUE"],
                  "RPG_FORMULA_present": "RPG_FORMULA" in r["fields"],
                  "RPG_DEFAULT_FORMULA_present": "RPG_DEFAULT_FORMULA" in r["fields"],
                  "destination": "DamageInfo.extraDamage" if r["id"] in (2, 3) else "IntAddNode.y before calcBlock",
                  "field_source": r["field_sources"]["STORYLINE_PARAM"]} for r in enemy_states["rows"]],
        "limit": "Every graph still calls getRpgValue(owner). Missing RPG fields do not prove its return value is zero. Choosing zero requires an explicit reconstruction policy."})
    write_json("opcode-corroboration.json", {
        "kind": "analyst-derived static correspondence; not native dispatch-table verification",
        "shared_disassemblers_modified": False,
        "entries": [
            {"opcodes": {"0x81": "LOAD_DEREF", "0x78": "LOAD_CLOSURE", "0x64": "MAKE_CLOSURE", "0x8e": "CALL_FUNCTION_VAR_KW"},
             "source": "3337:10 and 3337:10.1", "anchor_offsets": ["0x3", "0x9", "0x12", "helper:0xc"],
             "official_source": "https://github.com/python/cpython/blob/v2.7.18/Lib/contextlib.py",
             "basis": "contextmanager closure has one cell func; helper reads func then calls it with args and kwds"},
            {"opcode": "0xad", "meaning": "LOAD_FAST_0_AND_CONST", "source": "7930:8 offset 0x9 argument 2",
             "official_source": "https://github.com/python/cpython/blob/v2.7.18/Lib/functools.py#L45-L46",
             "basis": "wraps must push wrapped (varnames[0]) then assigned keyword (consts[2]); corroborated independently by ProcedureStartNode self/procedure pair",
             "limit": "Applied only to exact-source anchors where fast-zero/constant stack shape was corroborated."}
        ]})
    write_json("sources.json", {"kind": "local hash-verified static evidence, not runtime observations", "modules": sources})
    print(f"Exported {len(sources)} verified code modules, 5 graphs and 3 enemy state rows to {OUT}")


if __name__ == "__main__":
    main()
