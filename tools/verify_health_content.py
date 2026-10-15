"""Check source-linked HUD images in native exports, not their runtime rendering."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_health(check, bundle, paths, packaged_hashes):
    assets = ROOT/'legacy/cocos-poc/assets/resources/recovered/battle-ui'
    sprites = json.loads((ROOT/'analysis/battle-ui/sprites.json').read_text('utf8'))['frames']
    expected = {row['name']: row['png_sha256'] for row in sprites}
    for actor in ('player', 'monster'):
        report = json.loads((ROOT/f'analysis/battle-ui/health/{actor}-portrait/report.json').read_text('utf8'))
        expected[actor+'-head'] = report['output_sha256']
        check(actor+' portrait extraction still matches report',
            hashlib.sha256((ROOT/report['output']).read_bytes()).hexdigest() == report['output_sha256'])
    required = {'player-hp','player-hp-bg','monster-hp','monster-hp-bg','shield-icon',
        'head-back','head-front','player-head','monster-head'}
    check('Recovered HUD manifest covers all active images', required <= expected.keys())
    check('HUD source PNGs match extraction hashes', all(
        hashlib.sha256((assets/(name+'.png')).read_bytes()).hexdigest() == expected[name] for name in required))
    check('Every active HUD sprite has a resource entry', all(
        'recovered/battle-ui/'+name+'/spriteFrame' in paths for name in required))
    check('Exact source HUD PNG streams are packaged', all(expected[name] in packaged_hashes for name in required))
    check('Current portrait and life-state code compiled', all(marker in bundle for marker in (
        'player-head', 'monster-head', 'monster-hp', 'setHeaderLife', 'headerArt')))
    breakdown = json.loads((ROOT/'analysis/battle-ui/health/breakdown-portrait/report.json').read_text('utf8'))
    check('Breakdown icon source and package bytes match',
        hashlib.sha256((assets/'breakdown-icon.png').read_bytes()).hexdigest() == breakdown['output_sha256']
        and breakdown['output_sha256'] in packaged_hashes)
    check('Breakdown icon and status HUD are exported', 'recovered/battle-ui/breakdown-icon/spriteFrame' in paths
        and all(marker in bundle for marker in ('breakdownDisplay','BreakdownTriggered')))
