"""Verify source-bound victory title data reaches a native export, without executing it."""
import hashlib
import json
import copy
from pathlib import Path
from inspect_selection_timeline import read_timeline

ROOT = Path(__file__).resolve().parents[1]


def verify_result(check, bundle, paths, png_hashes, resource_root):
    staged = ROOT/'clients/cocos-poc/assets/resources/recovered/result-ui'
    source = ROOT/'analysis/battle-ui/result'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    provenance = json.loads((staged/'provenance.json').read_text('utf8'))
    report = json.loads((source/'sprites/report.json').read_text('utf8'))
    m = json.loads((staged/'victory-title.json').read_text('utf8'))
    check('Victory provenance is current',
          provenance['source_report_sha256'] == digest(source/'sprites/report.json')
          and provenance['frames'] == report['frames']
          and provenance['title_manifest_sha256'] == digest(staged/'victory-title.json'))
    check('Victory CSB is the bound source', m['csb_sha256'] == digest(source/'3559.csb')
          == json.loads((source/'layouts.json').read_text('utf8'))['layouts']['3559']['source']['sha256'])
    # Normalize parser tuples to the JSON array representation used by Creator.
    timeline = json.loads(json.dumps(read_timeline((source/'3559.csb').read_bytes())))
    tree = copy.deepcopy(json.loads((source/'layouts.json').read_text('utf8'))['layouts']['3559']['tree'])
    vx = next(n for n in tree['children'] if n['name'] == 'Panel_VX')
    panel = next(n for n in vx['children'] if n['name'] == 'Panel_1')
    panel['children'] = [n for n in panel['children'] if n['name'] in ('perfect', 'perfect_black', 'img_event_win_up')]
    vx['children'] = [panel]; tree['children'] = [vx]
    check('Victory hierarchy matches source title subset', m['hierarchy'] == tree)
    tags = set()
    def visit(node):
        tags.add(node['action_tag'])
        for child in node['children']: visit(child)
    visit(m['hierarchy'])
    check('Victory tracks and timing match source subset', len(tags) == 6 and
          m['timelines'] == [t for t in timeline['timelines'] if t['action_tag'] in tags]
          and m['animations'] == timeline['animations'] and m['speed'] == timeline['speed'])
    clock = ROOT/'analysis/battle-ui/native-selection-clock.json'
    check('Victory clock evidence is current', m['clock_report_sha256'] == digest(clock)
          and m['frame_interval'] == json.loads(clock.read_text('utf8'))['frame_interval_float32'])
    required = {'victory-title', 'victory-shadow', 'victory-lettering'}
    frames = {f['name']: f for f in report['frames']}
    check('All active victory PNGs are unchanged and packaged', required <= frames.keys() and all(
        digest(staged/(name+'.png')) == frames[name]['sha256'] and frames[name]['sha256'] in png_hashes
        for name in required))
    check('Victory manifest and sprite paths are exported', 'recovered/result-ui/victory-title' in paths and all(
        'recovered/result-ui/'+name+'/spriteFrame' in paths for name in required))
    check('Victory animation and battle wiring are compiled', all(s in bundle for s in (
        'OriginalVictoryTitleTimeline', 'recovered/result-ui/', 'victoryTitle', 'victorySummary', 'HCZS_VICTORY')))
    check('Victory title template matches source',
          (ROOT/'tools/templates/cocos-victory-title-view.ts').read_bytes() ==
          (ROOT/'clients/cocos-poc/assets/VictoryTitleView.ts').read_bytes())
    # Creator serializes JsonAsset inside an import-array envelope. Compare the actual
    # embedded object, not merely its resource path or its source-side hash.
    exported = []
    def collect(value):
        if isinstance(value, dict):
            if value.get('csb_sha256') == m['csb_sha256'] and 'hierarchy' in value:
                exported.append(value)
            else:
                for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    for path in (resource_root/'assets/resources/import').rglob('*.json'):
        text = path.read_text('utf8')
        if 'csb_sha256' in text: collect(json.loads(text))
    check('Packaged JsonAsset contains exact victory manifest', len(exported) == 1 and exported[0] == m)
