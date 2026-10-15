"""Stage previously recovered atlas pixels, checking their evidence hashes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
report_path = ROOT / 'analysis/battle-ui/piles/sprites/report.json'
report = json.loads(report_path.read_text('utf8'))
destination = ROOT / 'legacy/cocos-poc/assets/resources/recovered/pile-ui'
destination.mkdir(parents=True, exist_ok=True)
for frame in report['frames']:
    data = (ROOT / frame['png']).read_bytes()
    if hashlib.sha256(data).hexdigest() != frame['sha256']:
        raise ValueError('Recovered sprite hash mismatch: ' + frame['name'])
    (destination / (frame['name'] + '.png')).write_bytes(data)
(destination / 'provenance.json').write_text(json.dumps({
    'source_report_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
    'apk_sha256': report['apk_sha256'], 'frames': report['frames'],
    'limitations': ['Recovered pixels; client layout and pagination are reconstructed.'],
}, ensure_ascii=False, indent=2), 'utf8')
print(f'Staged {len(report["frames"])} verified pile UI sprites')
