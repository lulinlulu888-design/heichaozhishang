"""Ledger of recovered reports: path, bytes and sha256, plus declared outputs.

Rewrites the ledger only when an input report's bytes change. A listed report
that is absent is a gap; the others are still indexed. This does not extract,
convert or import.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS = [
    'analysis/unreal/battle-ui/manifest.json',
    'analysis/battle-ui/party-cards/report.json',
    'analysis/prologue-boss/future-actions/report.json',
    'analysis/characters/hero-003/battle-actions/export/export-report.json',
    'analysis/prologue-boss/mechanism-audit/enemySkills.json',
]
DEFAULT_LEDGER = ROOT / 'analysis/assets/recovered-output-ledger.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def index(reports, ledger_path):
    rows, gaps = [], []
    for relative in reports:
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            gaps.append(relative)
            continue
        raw = path.read_bytes()
        row = {'path': relative, 'bytes': len(raw), 'sha256': sha(raw)}
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get('sha256'), str):
            row['declaredOutputSha256'] = doc['sha256']
        rows.append(row)
    digest = sha(json.dumps(rows, sort_keys=True).encode('utf8'))
    previous = json.loads(ledger_path.read_text('utf8')) if ledger_path.is_file() else {}
    unchanged = previous.get('inputsSha256') == digest and previous.get('gaps') == gaps
    if unchanged:
        return dict(unchanged=True, ledger=str(ledger_path), entries=len(rows), gaps=gaps)
    ledger = {'schema': 'hczs-recovered-output-ledger-v1', 'inputsSha256': digest, 'entries': rows, 'gaps': gaps,
              'limits': ['Hashes the report files only. It does not open the APK or the Unreal assets they name.']}
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return dict(unchanged=False, ledger=str(ledger_path), entries=len(rows), gaps=gaps, sha256=sha(ledger_path.read_bytes()))


def main():
    print(json.dumps(index(DEFAULT_REPORTS, DEFAULT_LEDGER), ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
