"""Read-only APK integrity and source binding audit; not runtime equivalence."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
EXPECTED = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    apk_sha = digest(APK)
    if apk_sha != EXPECTED:
        raise ValueError('Original APK identity changed')
    with zipfile.ZipFile(APK) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError('ZIP CRC failed: ' + bad)
        member = 'lib/armeabi-v7a/libclient.so'
        original = hashlib.sha256(archive.read(member)).hexdigest()
        extracted = digest(ROOT / 'analysis/bootstrap/extracted' / member)
        if original != extracted:
            raise ValueError('Extracted native library differs from APK')
        members = len(archive.infolist())
    evidence_path = ROOT / 'analysis/rea/initial-artifact-evidence.json'
    bundle = json.loads(evidence_path.read_text('utf8'))
    records = []
    for record in bundle['records']:
        subject = record.get('subject') or {}
        if subject.get('digest', {}).get('sha256') == apk_sha:
            records.append({k: record.get(k) for k in
                            ('evidence_id', 'operation', 'authority', 'confidence', 'limitations')})
    if not records:
        raise ValueError('No matching retained REA Evidence')
    pairs = [
        ('tools/templates/cocos-city-scene-view.ts', 'legacy/cocos-poc/assets/CitySceneView.ts'),
        ('tools/templates/cocos-toolchain-proof.ts', 'legacy/cocos-poc/assets/ToolchainProof.ts'),
        ('tools/templates/cocos-recovered-character-view.ts', 'legacy/cocos-poc/assets/RecoveredCharacterView.ts'),
    ]
    templates = [{'template': a, 'client': b, 'identical':
                  (ROOT / a).read_bytes() == (ROOT / b).read_bytes()} for a, b in pairs]
    report = dict(scope='Local static integrity and identity checks; no original client execution',
                  apk_sha256=apk_sha, zip_members=members, zip_crc_valid=True,
                  native_sha256=original, native_matches_apk=True,
                  retained_rea_bundle_sha256=digest(evidence_path), retained_rea_records=records,
                  template_checks=templates,
                  limits=['Passing integrity does not establish original gameplay or rendering equivalence.',
                          'Retained REA records are reused; this local script is not a new REA Evidence producer.',
                          'No claim that online resource updates are present in this APK.'])
    out = ROOT / 'analysis/goal-alignment'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'integrity.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(report, ensure_ascii=False))
    if not all(row['identical'] for row in templates):
        raise ValueError('Client/template drift detected')


if __name__ == '__main__':
    main()
