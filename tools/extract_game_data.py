"""Recover literal cdata constructor arguments without executing game code.

Only the observed taggeddict declaration and a small expression grammar are
accepted. taggeddict is an opaque marker: this tool extracts its literal input,
not its runtime result or side effects. Unknown operations abort extraction.
"""
from __future__ import annotations

import argparse
import bisect
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct

from extract_npk import Marshal2

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "analysis/assets/decoded/script"
MODULES = {"characters": 8995, "initial_attacks": 1338, "cards": 3391, "skills": 9333}
SAMPLE_CHARACTER_IDS = {1, 2, 3}
# Exact card-table row IDs, selected as a small card-data example. No arithmetic
# conversion from inventory item IDs and no claim of a complete starter deck.
SAMPLE_CARD_IDS = {410101, 410102, 410104, 410105}
TAGGEDDICT = object()


class UnsupportedData(ValueError):
    pass


@dataclass
class Value:
    value: object
    start: int
    end: int
    constants: tuple = ()
    names: tuple = ()


@dataclass
class LiteralMap:
    expected_size: int
    entries: dict = field(default_factory=dict)


@dataclass
class TaggedArguments:
    mapping: LiteralMap


def plain(value):
    """Convert only finite neutral literals; reject code, opaque bytes and objects."""
    if isinstance(value, Value):
        return plain(value.value)
    if isinstance(value, TaggedArguments):
        return plain(value.mapping)
    if isinstance(value, LiteralMap):
        result = {}
        for key, (item, _) in value.entries.items():
            key = plain(key)
            if not isinstance(key, (str, int)) or isinstance(key, bool):
                raise UnsupportedData("JSON object key must be string or integer")
            key = str(key)
            if key in result:
                raise UnsupportedData("key collision after JSON conversion")
            result[key] = plain(item)
        return result
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UnsupportedData("non-UTF8 data is not a text literal") from error
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    raise UnsupportedData(f"unsupported literal type: {type(value).__name__}")


def source_lines(module):
    """Python 2 lnotab uses unsigned address/line deltas; offsets remain primary."""
    return _line_index(module["firstlineno"], module["lnotab"])


@lru_cache(maxsize=8)
def _line_index(first_line, table):
    if len(table) % 2:
        raise UnsupportedData("odd lnotab length")
    offsets, lines = [0], [first_line]
    address, line = 0, first_line
    for delta_address, delta_line in zip(table[0::2], table[1::2]):
        address += delta_address
        line += delta_line
        offsets.append(address)
        lines.append(line)
    return offsets, lines


def location(value, module):
    offsets, lines = source_lines(module)
    return {"bytecode_start": value.start, "bytecode_end_exclusive": value.end,
            "source_line": lines[bisect.bisect_right(offsets, value.start) - 1],
            "constant_indices": list(value.constants), "loaded_names": list(value.names)}


def parse_data(module, max_instructions=500000):
    """Static expression recognizer, deliberately not a general Python VM."""
    code, constants, names = module["bytecode"], module["consts"], module["names"]
    prelude = bytes.fromhex("99000099010086000074000091000026")
    if not code.startswith(prelude) or constants[:2] != [-1, [b"taggeddict"]] or names[:1] != [b"taggeddict"]:
        raise UnsupportedData("unrecognized taggeddict declaration")
    environment = {b"taggeddict": TAGGEDDICT, b"True": True, b"False": False}
    bindings = {}
    stack = []
    position = len(prelude)
    count = 0

    def pop():
        if not stack:
            raise UnsupportedData(f"stack underflow at {position}")
        return stack.pop()

    while position < len(code):
        count += 1
        if count > max_instructions:
            raise UnsupportedData("instruction budget exceeded")
        start = position
        opcode = code[position]
        position += 1
        argument = None
        if opcode >= 90:
            if position + 2 > len(code):
                raise UnsupportedData("truncated opcode argument")
            argument = struct.unpack_from("<H", code, position)[0]
            position += 2
        if opcode == 0x99:  # LOAD_CONST
            if argument >= len(constants):
                raise UnsupportedData("constant index out of range")
            value = constants[argument]
            plain(value)  # refuses code objects before they can enter the stack
            stack.append(Value(value, start, position, (argument,)))
        elif opcode == 0x65:  # LOAD_NAME, only previously bound literals/known marker
            if argument >= len(names) or names[argument] not in environment:
                raise UnsupportedData("unresolved name")
            name = names[argument]
            binding = environment[name]
            stack.append(Value(binding.value if isinstance(binding, Value) else binding, start, position,
                               binding.constants if isinstance(binding, Value) else (), (name.decode("utf-8"),)))
        elif opcode == 0x97:  # BUILD_MAP (generator's literal count hint)
            stack.append(Value(LiteralMap(argument), start, position))
        elif opcode == 0x08:  # STORE_MAP: map, value, key -> map
            key, value = pop(), pop()
            if not stack or not isinstance(stack[-1].value, LiteralMap):
                raise UnsupportedData("STORE_MAP target is not a literal map")
            mapping = stack[-1].value
            if not isinstance(key.value, (int, bytes, str)) or isinstance(key.value, bool):
                raise UnsupportedData("unsupported map key")
            if key.value in mapping.entries:
                raise UnsupportedData("duplicate literal key")
            mapping.entries[key.value] = (value, start)
            stack[-1].end = position
        elif opcode in (0x87, 0x5A):  # BUILD_TUPLE / BUILD_LIST
            if argument > len(stack):
                raise UnsupportedData("sequence stack underflow")
            parts = stack[-argument:] if argument else []
            if argument:
                del stack[-argument:]
            stack.append(Value([part.value for part in parts], parts[0].start if parts else start,
                               position, tuple(i for part in parts for i in part.constants),
                               tuple(n for part in parts for n in part.names)))
        elif opcode == 0x83:  # CALL_FUNCTION is recognized as syntax, never invoked
            if argument != 1:
                raise UnsupportedData("only taggeddict(one literal map) is recognized")
            item, callable_name = pop(), pop()
            if callable_name.value is not TAGGEDDICT or not isinstance(item.value, LiteralMap):
                raise UnsupportedData("arbitrary calls are forbidden")
            if len(item.value.entries) != item.value.expected_size:
                raise UnsupportedData("map literal differs from observed generator size hint")
            stack.append(Value(TaggedArguments(item.value), callable_name.start, position))
        elif opcode == 0x91:  # STORE_NAME
            if argument >= len(names):
                raise UnsupportedData("name index out of range")
            name, value = names[argument], pop()
            if name == b"data":
                if stack or not isinstance(value.value, TaggedArguments):
                    raise UnsupportedData("data must be one taggeddict literal expression")
                return value.value.mapping, {"data_assignment_offset": start, "parsed_end": position,
                                             "unparsed_tail_bytes": len(code) - position,
                                             "instructions_recognized": count, "symbol_bindings": bindings}
            if name in environment or not isinstance(value.value, (int, float, bytes, str, bool)):
                raise UnsupportedData("only unique literal symbol declarations are accepted")
            environment[name] = value
            bindings[name.decode("utf-8")] = {"value": plain(value), **location(value, module),
                                              "assignment_offset": start}
        else:
            raise UnsupportedData(f"unsupported opcode 0x{opcode:02x} at bytecode offset {start}")
    raise UnsupportedData("data assignment not found")


def read_module(index, directory=SCRIPT_DIR):
    inventory = json.loads((directory / "index.json").read_text("utf-8"))
    matches = [row for row in inventory if row["index"] == index]
    if len(matches) != 1:
        raise UnsupportedData("expected exactly one inventory record")
    row = matches[0]
    path = directory / f'{index:05d}_{row["name_hash"]:08x}.marshal'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["decoded_sha256"]:
        raise UnsupportedData("marshal digest mismatch")
    parser = Marshal2(raw)
    module = parser.obj()
    if parser.pos != len(raw) or module.get("type") != "code":
        raise UnsupportedData("marshal must contain one complete data module")
    if module["filename"].decode("utf-8") != row["filename"]:
        raise UnsupportedData("module filename mismatch")
    mapping, recognition = parse_data(module)
    return row, module, mapping, recognition


def export_table(index, selected_ids=None, directory=SCRIPT_DIR):
    row, module, mapping, recognition = read_module(index, directory)
    records = []
    for key, (value, assignment) in mapping.entries.items():
        if selected_ids is not None and key not in selected_ids:
            continue
        if not isinstance(value.value, TaggedArguments):
            raise UnsupportedData("table row must be literal taggeddict arguments")
        fields = value.value.mapping
        records.append({"id": plain(key), "fields": plain(fields),
                        "source": {**location(value, module), "map_assignment_offset": assignment},
                        "field_sources": {plain(name): {**location(item, module), "map_assignment_offset": at}
                                          for name, (item, at) in fields.entries.items()}})
    if selected_ids is not None and {record["id"] for record in records} != set(selected_ids):
        raise UnsupportedData("requested row is absent")
    return {"format": "hczs-static-cdata-v1", "evidence_kind": "local static extraction (not REA Evidence or runtime observation)",
            "value_semantics": "literal arguments passed to opaque taggeddict; wrapper behavior is not evaluated",
            "encoding_notes": ["Python 2 byte strings decode as strict UTF-8", "tuple/list both export as JSON arrays"],
            "source": {"apk_member": "assets/script.npk", **{key: row[key] for key in ("index", "filename", "name_hash", "offset", "stored_size", "payload_sha256", "decoded_sha256")}},
            "recognition": recognition, "total_source_rows": len(mapping.entries), "rows": records}


def build_sample():
    results = {
        "characters": export_table(MODULES["characters"], SAMPLE_CHARACTER_IDS),
        "initial_attacks": export_table(MODULES["initial_attacks"], SAMPLE_CHARACTER_IDS),
        "cards": export_table(MODULES["cards"], SAMPLE_CARD_IDS),
    }
    references = []
    for table in ("initial_attacks", "cards"):
        for record in results[table]["rows"]:
            for name, value in record["fields"].items():
                if name == "SKILL_IDS":
                    ids = value
                elif name in {"InitAttackSkillID", "InitDeffendSkillID", "SKILL_ID", "COUNTER_SKILL_ID",
                               "CRITICAL_SKILL_ID", "ROUNDEND_SKILL_ID", "SKILL_ID_WHEN_DRAW", "SKILL_ID_WHEN_PASS"}:
                    ids = [value]
                else:
                    continue
                references.extend({"table": table, "row": record["id"], "field": name, "skill_id": identity} for identity in ids)
    _, _, skills, _ = read_module(MODULES["skills"])
    wanted = {reference["skill_id"] for reference in references}
    results["skills"] = export_table(MODULES["skills"], wanted & set(skills.entries))
    for reference in references:
        reference["present_in_skill_table"] = reference["skill_id"] in skills.entries
    summary = {"kind": "small literal data sample, not a complete starter deck or battle implementation",
               "character_ids": sorted(SAMPLE_CHARACTER_IDS), "card_ids": sorted(SAMPLE_CARD_IDS),
               "skill_references": references,
               "unresolved_skill_ids": sorted(wanted - set(skills.entries)),
               "limitation": "Missing referenced rows are reported, never synthesized; runtime interpretation of fields is not established."}
    return results, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", choices=MODULES, action="append")
    ap.add_argument("--ids", nargs="+", type=int, help="exact row IDs (applies to each selected table)")
    args = ap.parse_args()
    output = ROOT / "analysis/game-data"
    output.mkdir(parents=True, exist_ok=True)
    if args.ids and not args.table:
        ap.error("--ids requires --table")
    if args.table:
        results = {name: export_table(MODULES[name], set(args.ids) if args.ids else None) for name in args.table}
    else:
        results, summary = build_sample()
        (output / "sample.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, result in results.items():
        dest = output / f"{name}.json"
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f'{name}: {len(result["rows"])}/{result["total_source_rows"]} rows -> {dest}')


if __name__ == "__main__":
    main()
