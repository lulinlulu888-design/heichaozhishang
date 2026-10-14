"""Reject unsupported expressions and verify fixed literals from the real APK."""
import pathlib
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from extract_game_data import UnsupportedData, build_sample, export_table, location, parse_data, plain


def op(code, argument=None):
    return bytes([code]) + (struct.pack("<H", argument) if argument is not None else b"")


def sample_module(value=7):
    # Static syntax for: data = taggeddict({10: taggeddict({'COST': value})}).
    # The recognizer never resolves or invokes a real taggeddict implementation.
    prelude = bytes.fromhex("99000099010086000074000091000026")
    body = (op(0x65, 0) + op(0x97, 1) + op(0x65, 0) + op(0x97, 1)
            + op(0x99, 2) + op(0x99, 3) + op(0x08) + op(0x83, 1)
            + op(0x99, 4) + op(0x08) + op(0x83, 1) + op(0x91, 1))
    return {"type": "code", "bytecode": prelude + body,
            "consts": [-1, [b"taggeddict"], value, b"COST", 10],
            "names": [b"taggeddict", b"data"], "firstlineno": 1,
            "lnotab": bytes([16, 4]), "filename": b"fixture.py"}


class LiteralGrammarTests(unittest.TestCase):
    def test_literal_row_keeps_value_and_source(self):
        module = sample_module()
        mapping, recognition = parse_data(module)
        self.assertEqual(plain(mapping), {"10": {"COST": 7}})
        row, at = mapping.entries[10]
        self.assertEqual(location(row, module)["source_line"], 5)
        self.assertGreater(at, row.start)
        self.assertEqual(recognition["unparsed_tail_bytes"], 0)

    def test_helper_tail_is_reported_but_never_interpreted(self):
        module = sample_module()
        module["bytecode"] += b"\xff\xff\xff"
        mapping, recognition = parse_data(module)
        self.assertEqual(plain(mapping)["10"]["COST"], 7)
        self.assertEqual(recognition["unparsed_tail_bytes"], 3)

    def test_other_calls_imports_branches_and_unknown_opcodes_are_rejected(self):
        for instruction in (op(0x83, 0), op(0x86, 0), op(0x89, 16), b"\x01"):
            module = sample_module()
            module["bytecode"] = module["bytecode"][:16] + instruction + module["bytecode"][16:]
            with self.subTest(instruction=instruction.hex()), self.assertRaises(UnsupportedData):
                parse_data(module)

    def test_unresolved_names_and_executable_constants_are_rejected(self):
        module = sample_module()
        module["bytecode"] = module["bytecode"][:16] + op(0x65, 1) + module["bytecode"][16:]
        with self.assertRaisesRegex(UnsupportedData, "unresolved name"):
            parse_data(module)
        with self.assertRaises(UnsupportedData):
            parse_data(sample_module({"type": "code", "bytecode": b""}))

    def test_truncation_bad_prelude_indices_and_budget_are_rejected(self):
        for code in (b"", sample_module()["bytecode"][:-1],
                     sample_module()["bytecode"][:16] + op(0x99, 65535)):
            module = sample_module()
            module["bytecode"] = code
            with self.subTest(code=code.hex()), self.assertRaises(UnsupportedData):
                parse_data(module)
        with self.assertRaisesRegex(UnsupportedData, "budget"):
            parse_data(sample_module(), max_instructions=1)

    def test_opaque_bytes_and_nonfinite_values_are_not_invented(self):
        for value in (b"\xff", float("nan"), object()):
            with self.subTest(value=repr(value)), self.assertRaises(UnsupportedData):
                plain(value)

    def test_duplicate_map_keys_are_rejected(self):
        module = sample_module()
        assignment = op(0x99, 2) + op(0x99, 3) + op(0x08)
        module["bytecode"] = module["bytecode"].replace(assignment, assignment + assignment, 1)
        with self.assertRaisesRegex(UnsupportedData, "duplicate"):
            parse_data(module)


@unittest.skipUnless((ROOT / "analysis/assets/decoded/script/index.json").is_file(), "decoded APK evidence unavailable")
class ActualTableTests(unittest.TestCase):
    def test_sample_reports_missing_references_without_fabricating_rows(self):
        tables, summary = build_sample()
        self.assertEqual(summary["unresolved_skill_ids"], [6002, 6003])
        self.assertEqual({row["id"] for row in tables["skills"]["rows"]}, {0, 410101, 410102, 410104, 410105})

    def test_character_and_initial_skill_literals(self):
        characters = export_table(8995, {1, 2, 3})
        self.assertEqual(characters["total_source_rows"], 228)
        rows = {row["id"]: row for row in characters["rows"]}
        self.assertEqual(rows[1]["fields"]["NAME"], "\u827e\u5c14\u838e")
        self.assertEqual(rows[2]["fields"]["ENGLISH_NAME"], "LYNN FLY")
        self.assertEqual(rows[3]["fields"]["ENGLISH_NAME"], "MIRAI")
        self.assertEqual(rows[1]["fields"]["CHARTYPE"], 1)
        self.assertIn("NAME", rows[1]["field_sources"])
        initial = export_table(1338, {1})["rows"][0]["fields"]
        self.assertEqual(initial["InitAttackSkillID"], 6002)
        self.assertEqual(initial["InitDeffendSkillID"], 6003)
        self.assertEqual(initial["InitAttackValue"], 0)

    def test_card_cost_and_skill_reference_are_real_literals(self):
        cards = export_table(3391, {410101, 410104})
        self.assertEqual(cards["total_source_rows"], 1538)
        rows = {row["id"]: row["fields"] for row in cards["rows"]}
        self.assertEqual(rows[410101]["NAME"], "\u4e8c\u8fde\u65a9\u51fb")
        self.assertEqual(rows[410101]["COST"], 1)
        self.assertEqual(rows[410101]["SKILL_IDS"], [410101])
        self.assertEqual(rows[410101]["SKILL_DIY_VALUE"], [75])
        self.assertEqual(rows[410104]["COST"], 0)
        skills = export_table(9333, {410101, 410104})
        self.assertEqual(skills["total_source_rows"], 1487)
        self.assertEqual({row["id"] for row in skills["rows"]}, {410101, 410104})

    def test_absent_rows_and_unhandled_imported_constants_are_rejected(self):
        with self.assertRaisesRegex(UnsupportedData, "absent"):
            export_table(3391, {1})
        # Item tables import item_table_meta; do not guess CARD_ID via arithmetic.
        with self.assertRaisesRegex(UnsupportedData, "unsupported opcode"):
            export_table(6408, {1410101})


if __name__ == "__main__":
    unittest.main()
