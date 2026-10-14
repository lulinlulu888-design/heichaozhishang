"""Verify recovered pile art and compiled gallery code, without claiming runtime fidelity."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_piles(check, bundle, paths, packaged_hashes):
    assets = ROOT / 'clients/cocos-poc/assets/resources/recovered/pile-ui'
    report_path = ROOT / 'analysis/battle-ui/piles/sprites/report.json'
    report = json.loads(report_path.read_text('utf8'))
    staged = json.loads((assets / 'provenance.json').read_text('utf8'))
    check('Pile provenance points to current recovery report',
          staged['source_report_sha256'] == hashlib.sha256(report_path.read_bytes()).hexdigest()
          and staged['frames'] == report['frames'])
    required = {'tab-background', 'tab-draw-selected', 'tab-discard-selected',
                'tab-consumed-selected', 'bottom-mask', 'change-view-icon', 'change-view-button'}
    frames = {frame['name']: frame for frame in report['frames']}
    check('Pile recovery report covers active images', required <= frames.keys())
    check('Staged pile PNGs match original recovered streams', all(
        hashlib.sha256((assets / (name + '.png')).read_bytes()).hexdigest() == frames[name]['sha256']
        for name in required))
    check('Pile sprite resources are exported', all(
        f'recovered/pile-ui/{name}/spriteFrame' in paths for name in required))
    check('Recovered pile PNG streams are packaged', all(
        frames[name]['sha256'] in packaged_hashes for name in required))
    check('Gallery, character mode and read-only detail are compiled', all(marker in bundle for marker in (
        'PileCardDetail', 'EnlargedCard', 'renderPileDetail', 'pileByCharacter', 'pilePage',
        'change-view-button', 'tab-background', 'pile-ui', 'big-atk')))
    card_frames = ROOT / 'clients/cocos-poc/assets/resources/recovered/card-frames'
    frame_report = json.loads((card_frames / 'provenance.json').read_text('utf8'))
    big = next(frame for frame in frame_report['frames'] if frame['key'] == 'card/bg_atk.png')
    check('Original large attack frame is current and packaged',
          hashlib.sha256((card_frames / 'big-atk.png').read_bytes()).hexdigest() == big['sha256']
          and big['sha256'] in packaged_hashes
          and 'recovered/card-frames/big-atk/spriteFrame' in paths)
