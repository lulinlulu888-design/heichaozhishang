"""Stage the five source-linked card sprites; fail on modified extraction outputs."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT/'analysis/card-art/tile-probe/manifest.json'
    manifest = json.loads(source.read_text('utf8'))
    expected = {110001, 110009, 210003, 410101, 410102}
    if {r['card_id'] for r in manifest['cards']} != expected or len(manifest['cards']) != 5:
        raise ValueError('Unexpected card art mapping')
    destination = ROOT/'clients/cocos-poc/assets/resources/recovered/cards'
    destination.mkdir(parents=True, exist_ok=True)
    for row in manifest['cards']:
        image = ROOT/row['sprite']
        if hashlib.sha256(image.read_bytes()).hexdigest() != row['sprite_sha256']:
            raise ValueError('Card sprite checksum mismatch')
        shutil.copyfile(image, destination/f"{row['card_id']}.png")
    shutil.copyfile(source, destination/'provenance.json')


if __name__ == '__main__':
    main()
