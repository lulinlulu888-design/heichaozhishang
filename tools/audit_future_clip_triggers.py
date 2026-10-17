"""Read Future's gim triggers for the two prologue clips.

shield_1 and buff_2 both name effects/player/future/future_buff_2.sfx on
socket fx_center. BindType and the matrix are copied literally. This does not
attach a particle: fx_center has no BoneName, and the native meaning of
BindType 7 is not established here.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/prologue-boss/future-clip-triggers'
LOGICAL = 'character/player/future/future_yangcheng.gim'
EXPECTED = {
    'shield_1': {'socket': 'fx_center', 'sfx': 'effects/player/future/future_buff_2.sfx', 'spark': 'UnControlledStart'},
    'buff_2': {'socket': 'fx_center', 'sfx': 'effects/player/future/future_buff_2.sfx', 'spark': 'Start'},
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def clip_triggers(payload):
    """One trigger per named clip. Extra clips are ignored."""
    tree = ET.fromstring(payload.decode('gb18030'))
    sockets = {el.get('Name'): el for el in tree.find('Sockets')}
    found = {}
    triggers = tree.find('Triggers')
    for clip, expect in EXPECTED.items():
        node = triggers.find(clip) if triggers is not None else None
        events = [] if node is None else [el.find('trigger') for el in node]
        events = [el for el in events if el is not None]
        if len(events) != 1:
            raise ValueError('Clip %s trigger count changed: %d' % (clip, len(events)))
        el = events[0]
        socket = sockets.get(el.get('SocketName'))
        if socket is None:
            raise ValueError('Clip %s socket is missing: %s' % (clip, el.get('SocketName')))
        found[clip] = {
            'socket': el.get('SocketName'),
            'sfx': el.get('ObjectFileName', '').replace('\\', '/'),
            'spark': el.get('Spark'),
            'bindType': socket.get('BindType'),
            'boneName': socket.get('BoneName'),
            'matrixToBone': socket.get('MatrixToBone'),
        }
        if {k: found[clip][k] for k in ('socket', 'sfx', 'spark')} != expect:
            raise ValueError('Clip %s trigger changed: %s' % (clip, found[clip]))
    return found


def main():
    apk = next(ROOT.glob('*.apk'))
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise SystemExit('APK identity mismatch')
    catalogue = read_catalogue(apk)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'future_yangcheng.gim'
    extract(apk, catalogue, LOGICAL, target, APK_SHA256)
    payload = target.read_bytes()
    triggers = clip_triggers(payload)
    report = {
        'format': 'hczs-future-clip-triggers-v1',
        'logical': LOGICAL,
        'gimSha256': sha(payload),
        'clips': triggers,
        'playback': 'hook-only',
        'limits': [
            'fx_center has no BoneName.',
            'BindType and MatrixToBone are stored as written; native attachment is not interpreted.',
            'The particle document is not played.',
        ],
    }
    raw = json.dumps(report, ensure_ascii=False, indent=2).encode('utf8')
    (OUT / 'report.json').write_bytes(raw)
    print(json.dumps({'report': str(OUT / 'report.json'), 'sha256': sha(raw), 'clips': list(triggers)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
