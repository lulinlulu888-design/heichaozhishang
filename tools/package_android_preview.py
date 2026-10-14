"""Copy a currently verified Android export to a content-addressed local deliverable."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'analysis/cocos-android'


def main(variant='device'):
    from verify_android_content import main as verify_content
    verify_content(variant)
    EVIDENCE = ROOT / ('analysis/cocos-android-emulator' if variant == 'emulator' else 'analysis/cocos-android')
    content = json.loads((EVIDENCE / 'content-verification.json').read_text('utf8'))
    source = Path(content['apk'])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if not content['passed'] or content['apk_sha256'] != digest:
        raise ValueError('No matching successful content verification')
    architecture = 'x86_64-emulator' if variant == 'emulator' else 'arm64'
    destination = ROOT / 'runtime/dist' / f'hczs-android-{architecture}-preview-{digest[:12]}.apk'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        raise ValueError('Existing destination differs; preserve it for investigation')
    shutil.copyfile(source, destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        raise ValueError('Deliverable copy mismatch')
    report = dict(path=str(destination), variant=variant, sha256=digest, bytes=destination.stat().st_size,
                  runtime_verified=False, content_checks=len(content['checks']),
                  content_report_sha256=hashlib.sha256((EVIDENCE / 'content-verification.json').read_bytes()).hexdigest())
    (EVIDENCE / 'package-verification.json').write_text(json.dumps(report, indent=2), 'utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=('device', 'emulator'), default='device')
    main(parser.parse_args().variant)
