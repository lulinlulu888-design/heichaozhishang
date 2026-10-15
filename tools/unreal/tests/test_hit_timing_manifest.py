"""Source-bound import guards; no UE, network, database or source writes."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import import_battle_hit_timing as timing


class HitTimingManifestGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((timing.BASE / "manifest.json").read_bytes())

    def check(self, change=None):
        manifest = copy.deepcopy(self.original)
        if change:
            change(manifest)
        with tempfile.TemporaryDirectory(prefix="hczs-hit-manifest-") as folder:
            base = Path(folder)
            (base / "manifest.json").write_text(json.dumps(manifest, allow_nan=False), "utf8")
            with patch.object(timing, "BASE", base):
                return timing.verify_manifest()

    def test_valid_source_event_projection(self):
        manifest, _ = self.check()
        self.assertEqual(manifest["player_hit_events"]["fire_1"]["ratio_literal"], "0.230700")
        self.assertFalse(manifest["original_full_timing_equivalence"])

    def test_halfway_adapter_cannot_be_imported_as_source(self):
        with self.assertRaisesRegex(ValueError, "scalar/source projection"):
            self.check(lambda m: m["player_hit_events"]["fire_1"].update(progress=.5))

    def test_wrong_clip_stage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected hit-event manifest"):
            self.check(lambda m: m["card_animation_queues"]["410101"].append("fire_2"))

    def test_stale_source_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "audit changed"):
            self.check(lambda m: m.update(source_audit_sha256="0" * 64))

    def test_duration_cannot_silently_retime_clip(self):
        with self.assertRaisesRegex(ValueError, "scalar/source projection"):
            self.check(lambda m: m["player_hit_events"]["crit_1"].update(duration_seconds=1.0))


if __name__ == "__main__":
    unittest.main()
