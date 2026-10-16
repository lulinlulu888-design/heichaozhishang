"""Write hash-verified, partial static battle-script evidence; execute no APK code.

Opcode names are the previously corroborated partial mapping. Unknown opcodes
stay numeric; this is not a decompiler or a VM. Offsets are relative to each code
object, identified by a path of constant indexes and its own bytecode digest.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import struct

from extract_npk import Marshal2, jsonable
from inspect_script_static import OP, NAMES
from extract_game_data import export_table

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "analysis/assets/decoded/script"
OUTPUT = ROOT / "analysis/battle-rules"
# Corroborated by shipped standard-library snippets against CPython 2.7 source;
# this is an analyst-derived opcode mapping, not a native dispatch-table dump.
EXTRA_OP = {0x08: "STORE_MAP", 0x97: "BUILD_MAP", 0x74: "IMPORT_FROM",
            0x3c: "GET_ITER", 0x95: "FOR_ITER", 0x7d: "UNPACK_SEQUENCE",
            0x41: "STORE_SUBSCR", 0x9d: "LIST_APPEND", 0xac: "POP_JUMP_IF_TRUE",
            0x2c: "BINARY_DIVIDE", 0x0d: "BINARY_TRUE_DIVIDE",
            0x34: "BINARY_FLOOR_DIVIDE", 0x15: "INPLACE_ADD",
            0x52: "INPLACE_MULTIPLY", 0x39: "BINARY_SUBTRACT",
            0x37: "INPLACE_SUBTRACT", 0x43: "UNARY_NEGATIVE",
            # lib/calendar.py formatday builds '%2i' % day, and isleap tests
            # year % 4 == 0. Both use this opcode. CPython 2.7.18 Lib/calendar.py.
            0x24: "BINARY_MODULO",
            # lib/calendar.py main: options.locale and not options.encoding;
            # cross-checked against CPython 2.7.18 Lib/calendar.py line 616.
            0x51: "UNARY_NOT"}


def read_module(row):
    path = ROOT / row["output"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["decoded_sha256"]:
        raise ValueError("decoded marshal hash mismatch")
    reader = Marshal2(raw)
    obj = reader.obj()
    if reader.pos != len(raw) or not isinstance(obj, dict) or obj.get("type") != "code":
        raise ValueError("expected one completely consumed module")
    if obj["filename"].decode("utf8") != row["filename"]:
        raise ValueError("source filename mismatch")
    return obj


def walk_codes(obj, path=()):
    yield path, obj
    for i, value in enumerate(obj["consts"]):
        if isinstance(value, dict) and value.get("type") == "code":
            yield from walk_codes(value, (*path, i))


def instructions(obj):
    code = obj["bytecode"]
    address, source_line = 0, obj["firstlineno"]
    line_offsets, lines = [0], [source_line]
    if len(obj["lnotab"]) % 2:
        raise ValueError("odd line-number table")
    for delta, line_delta in zip(obj["lnotab"][0::2], obj["lnotab"][1::2]):
        address += delta
        source_line += line_delta
        line_offsets.append(address)
        lines.append(source_line)
    pos = 0
    while pos < len(code):
        start, op = pos, code[pos]
        pos += 1
        arg = None
        if op >= 90:
            if pos + 2 > len(code):
                raise ValueError("truncated instruction argument")
            arg = struct.unpack_from("<H", code, pos)[0]
            pos += 2
        record = {"offset": start, "end_exclusive": pos, "opcode": op,
                  "opname": OP.get(op, EXTRA_OP.get(op, "UNKNOWN")), "argument": arg,
                  "source_line": lines[bisect.bisect_right(line_offsets, start) - 1]}
        pool = None
        if op == 0x99:
            pool = obj["consts"]
        elif op in NAMES or op == 0x74:
            pool = obj["names"]
        elif op in (0x61, 0x68):
            pool = obj["varnames"]
        if pool is not None:
            if arg >= len(pool):
                raise ValueError("operand index outside pool (mapping may be wrong)")
            value = pool[arg]
            if isinstance(value, dict) and value.get("type") == "code":
                record["operand"] = {"code_name": value["name"].decode("utf8")}
            else:
                record["operand"] = jsonable(value)
        yield record


def export(row, selected_names=()):
    module = read_module(row)
    result = {"evidence_kind": "hash-verified local static extraction; no APK execution or runtime observation",
              "source": {"apk_member": "assets/script.npk", **row}, "code_objects": []}
    for path, obj in walk_codes(module):
        name = obj["name"].decode("utf8")
        if selected_names and name not in selected_names:
            continue
        result["code_objects"].append({"name": name, "constant_path": list(path),
            "firstlineno": obj["firstlineno"], "argcount": obj["argcount"],
            "varnames": jsonable(obj["varnames"]), "names": jsonable(obj["names"]),
            "bytecode_sha256": hashlib.sha256(obj["bytecode"]).hexdigest(),
            "bytecode_size": len(obj["bytecode"]), "instructions": list(instructions(obj))})
    return result


def save(result):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    row = result["source"]
    stem = f'{row["index"]:05d}_' + row["filename"].replace("\\", "__").replace("/", "__")
    (OUTPUT / (stem + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    lines = [f'APK assets/script.npk index={row["index"]} NPK offset={row["offset"]}',
             f'marshal sha256={row["decoded_sha256"]}', f'module={row["filename"]}']
    for obj in result["code_objects"]:
        lines += [f'\n### {obj["name"]} constant_path={obj["constant_path"]} source_line={obj["firstlineno"]}',
                  f'bytecode_sha256={obj["bytecode_sha256"]}',
                  f'args/locals={obj["varnames"]!r}', f'names={obj["names"]!r}']
        for ins in obj["instructions"]:
            operand = repr(ins.get("operand", ""))
            lines.append(f'{ins["offset"]:05x} {ins["opcode"]:02x} {ins["opname"]:24} '
                         f'{str(ins["argument"]):6} line={ins["source_line"]} {operand}')
    (OUTPUT / (stem + ".partial-dis.txt")).write_text("\n".join(lines) + "\n", encoding="utf8")
    return stem


def literal_extra_data(module):
    """Recognize only taggeddict({literal integer: literal integer tuple}).

    Helpers before this expression are skipped structurally, never evaluated.
    This supports the observed skill-state/timeline reverse indexes, not general
    Python objects or wrappers. Every unsupported operation inside it is fatal.
    """
    code = list(instructions(module))
    endings = [n for n, item in enumerate(code)
               if item["opcode"] == 0x91 and item.get("operand") == "extra_data"]
    if len(endings) != 1:
        raise ValueError("expected one extra_data assignment")
    end = endings[0]
    starts = [n for n, item in enumerate(code[:end])
              if item["opcode"] == 0x65 and item.get("operand") == "taggeddict"]
    if not starts:
        raise ValueError("missing extra_data constructor")
    start = starts[-1]
    if code[start + 1]["opcode"] != 0x97:
        raise ValueError("extra_data constructor is not a literal map")
    hint = code[start + 1]["argument"]
    rows, stack = {}, []
    for item in code[start + 2:end - 1]:
        op, arg = item["opcode"], item["argument"]
        if op == 0x99:
            value = module["consts"][arg]
            if type(value) != int:
                raise ValueError("extra_data constant must be integer")
            stack.append(value)
        elif op == 0x87:
            if arg > len(stack):
                raise ValueError("extra_data tuple underflow")
            values = stack[-arg:] if arg else []
            if arg:
                del stack[-arg:]
            if any(type(v) != int for v in values):
                raise ValueError("extra_data tuple values must be integers")
            stack.append(tuple(values))
        elif op == 0x08:
            if len(stack) != 2:
                raise ValueError("extra_data assignment stack mismatch")
            values, key = stack
            if type(key) != int or type(values) != tuple or key in rows:
                raise ValueError("extra_data key/value or duplicate mismatch")
            rows[key] = {"row_ids": list(values), "map_assignment_offset": item["offset"]}
            stack = []
        else:
            raise ValueError("unsupported extra_data operation")
    call = code[end - 1]
    if call["opcode"] != 0x83 or call["argument"] != 1 or stack or len(rows) != hint:
        raise ValueError("extra_data literal shape mismatch")
    return {"constructor_offset": code[start]["offset"],
            "assignment_offset": code[end]["offset"], "total_keys": len(rows),
            "requested": {str(k): rows.get(k) for k in (6002, 6003, 410101, 410102)}}


def literal_story_graph(module):
    code = list(instructions(module))
    if ([x["opcode"] for x in code] != [0x99, 0x91, 0x99, 0x53]
            or code[1].get("operand") != "data"):
        raise ValueError("story graph is not a single constant assignment")
    raw = module["consts"][code[0]["argument"]]
    if not isinstance(raw, bytes):
        raise ValueError("story graph constant is not bytes")
    # JSON parsing is data decoding, not eval or execution of a game module.
    return {"constant_index": code[0]["argument"], "load_offset": code[0]["offset"],
            "raw_json_sha256": hashlib.sha256(raw).hexdigest(),
            "graph": json.loads(raw.decode("utf8"))}


def formula_probes(inventory):
    """Independent scalar translations guarded by exact static function hashes.

    No instruction is executed. Deliberately excludes entity lookup, RNG, buff
    systems and dispatch, and never claims the 200/300 choice is resolved.
    """
    expected = [(3510, (36,), "062afb8f22ead82634d253e2bda65211d70d84276252446f5424b546feefb231"),
                (3510, (39,), "3990707827682727fe3d299c9f7a42e083dcacab4f3c5bd90918280d8a585ebd"),
                (7042, (9,), "302cf4e69a36c20a76774f56baa7072f3b4b53383f4b9897cf7d56be4aafb4ed")]
    for index, path, digest in expected:
        obj = read_module(inventory[index])
        for constant in path:
            obj = obj["consts"][constant]
        if hashlib.sha256(obj["bytecode"]).hexdigest() != digest:
            raise ValueError("formula probe source changed; manual review required")
    def preview_ap(attack, percent):
        return int(attack * percent / 100.0)
    def py2_div(numerator, denominator):
        if type(numerator) == int and type(denominator) == int:
            return numerator // denominator
        return numerator / denominator
    def defense_factor(attack, defense, penetration):
        if attack == 0:
            return 0
        return py2_div(attack, attack + max(defense - penetration, 0) * 5)
    cases = [(0, 75, 0), (1, 75, 0), (2, 75, 1), (101, 75, 75),
             (101, 300, 303), (-2, 75, -1)]
    for attack, percent, expected_result in cases:
        assert preview_ap(attack, percent) == expected_result
    defense_cases = [(100.0, 20.0, 0.0, 0.5), (100.0, 20.0, 25.0, 1.0),
                     (0.0, 20.0, 0.0, 0), (100, 20, 0, 0)]
    for attack, defense, penetration, expected_result in defense_cases:
        assert defense_factor(attack, defense, penetration) == expected_result
    return {"kind": "independent scalar translations; not original-runtime execution",
            "source_guards": [{"index": i, "constant_path": p, "bytecode_sha256": h}
                              for i, p, h in expected],
            "ap_preview": [{"attack": a, "percent": p, "expected_int": v} for a, p, v in cases],
            "defense_factor": [{"attack": a, "defense": d, "penetration": b, "expected": v,
                                "numeric_type": "int" if type(a) == int else "float"}
                               for a, d, b, v in defense_cases],
            "warning": "Defense retains Python 2 classic division. Actual entity property numeric types and runtime overrides remain unverified."}


def build_report(inventory):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    def write(name, value):
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    selected = [296, 1280, 3510, 4168, 4497, 4762, 6221, 6224, 7042, 7554, 8010, 9176,
                2597, 414, 6561, 1644, 3976, 8976]
    for index in selected:
        save(export(inventory[index]))
    for index, ids in [(1280, {1}), (1338, {1, 2, 3}),
                       (3391, {6002, 6003, 410101, 410102}),
                       (9333, {410101, 410102}),
                       (8903, {365, 366, 367, 368, 4214831, 4214841}),
                       (6655, {2983, 2984}), (7372, {3})]:
        write(f"{index:05d}_data.json", export_table(index, ids))
    for index in (8903, 6655):
        write(f"{index:05d}_extra-data.json", {"source": inventory[index],
              "literal_index": literal_extra_data(read_module(inventory[index]))})
    for index in (4168, 3109):
        write(f"{index:05d}_story-graph.json", {"source": inventory[index],
              **literal_story_graph(read_module(inventory[index]))})
    write("formula-probes.json", formula_probes(inventory))
    # Search every decoded script for direct literal/name references, including
    # assignments (not merely functions named after these symbols).
    terms = {"getRpgValue", "beHurt", "DamageInfo", "InitAttackSkillID", "InitDeffendSkillID"}
    symbols = [json.loads(line) for line in (SCRIPT / "symbols.jsonl").open(encoding="utf8")]
    references = []
    for symbol in symbols:
        if not terms.intersection(set(symbol["names"]) | set(symbol["strings"]) | set(symbol["functions"])):
            continue
        row = inventory[symbol["index"]]
        for path, obj in walk_codes(read_module(row)):
            code = list(instructions(obj))
            for n, item in enumerate(code):
                if isinstance(item.get("operand"), str) and item["operand"] in terms:
                    references.append({"index": row["index"], "filename": row["filename"],
                        "sha256": row["decoded_sha256"], "constant_path": list(path),
                        "function": obj["name"].decode("utf8"), "instruction": item,
                        "window": code[max(0, n - 3):n + 4]})
    write("boundary-references.json", {"symbol_index_modules": len(symbols), "terms": sorted(terms),
        "limitations": "Exact names and literals only; generated/concatenated names, encrypted payloads and arbitrary runtime registration remain unknown.",
        "references": references})
    native = ROOT / "analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so"
    data = native.read_bytes()
    native_sha256 = hashlib.sha256(data).hexdigest()
    if native_sha256 != "54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef":
        raise ValueError("native source changed; bounded name-search scope requires review")
    searches = {}
    for term in ("getRpgValue", "beHurt", "DamageInfo", "ServerUtils"):
        searches[term] = {}
        for encoding in ("ascii", "utf-16-le", "utf-16-be"):
            raw = term.encode(encoding)
            positions, offset = [], 0
            while True:
                offset = data.find(raw, offset)
                if offset < 0:
                    break
                positions.append(offset)
                offset += 1
            searches[term][encoding] = positions
    write("native-search.json", {"path": str(native.relative_to(ROOT)),
        "sha256": native_sha256, "exact_string_offsets": searches,
        "registration_scope": "No literal name anchor means no named PyMethodDef/string-registration candidate was located; this is not exhaustive native control/data-flow proof.",
        "rea_limit": "Native provider unavailable in current REA session (Ghidra not configured); performed bounded raw-byte static search instead."})
    write("report-sources.json", {"modules": [inventory[i] for i in sorted(set(selected +
          [1338, 3391, 9333, 8903, 6655, 3109, 6221, 7372]))], "opcode_extension": EXTRA_OP,
          "limitations": "Static reconstruction only. No APK code object was executed or converted to an executable Python object."})
    return {"output": str(OUTPUT), "modules_exported": len(selected),
            "formula_probe_vectors": 10, "boundary_references": len(references)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", nargs="*", type=int)
    parser.add_argument("--function", action="append", default=[])
    parser.add_argument("--report", action="store_true", help="rebuild the focused battle evidence bundle")
    args = parser.parse_args()
    inventory = json.loads((SCRIPT / "index.json").read_text("utf8"))
    by_id = {row["index"]: row for row in inventory}
    if args.report:
        print(json.dumps(build_report(by_id)))
    if not args.report and not args.index:
        parser.error("provide module indexes or --report")
    for i in args.index:
        print(save(export(by_id[i], args.function)))


if __name__ == "__main__":
    main()
