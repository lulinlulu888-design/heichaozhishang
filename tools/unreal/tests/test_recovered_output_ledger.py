import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import index_recovered_outputs as ledger


class RecoveredOutputLedgerTest(unittest.TestCase):
    def test_rewrites_only_when_an_input_changes_and_keeps_going_past_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            present = root / 'analysis' / 'one.json'
            present.parent.mkdir()
            present.write_text(json.dumps({'sha256': 'abc'}), encoding='utf8')
            missing = 'analysis/missing.json'
            out = root / 'ledger.json'
            original = ledger.ROOT
            ledger.ROOT = root
            try:
                first = ledger.index(['analysis/one.json', missing], out)
                second = ledger.index(['analysis/one.json', missing], out)
                present.write_text(json.dumps({'sha256': 'def'}), encoding='utf8')
                third = ledger.index(['analysis/one.json', missing], out)
                saved = json.loads(out.read_text('utf8'))
            finally:
                ledger.ROOT = original
        self.assertFalse(first['unchanged'])
        self.assertEqual(first['gaps'], [missing])
        self.assertTrue(second['unchanged'])
        self.assertFalse(third['unchanged'])
        self.assertEqual(saved['entries'][0]['declaredOutputSha256'], 'def')


if __name__ == '__main__':
    unittest.main()
