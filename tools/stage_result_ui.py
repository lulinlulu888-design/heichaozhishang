"""Stage hash-verified sprites of the registered BattleWin dialog."""
import hashlib
import json
import copy
from pathlib import Path
from inspect_selection_timeline import read_timeline

ROOT = Path(__file__).resolve().parents[1]
report_path = ROOT/'analysis/battle-ui/result/sprites/report.json'
report = json.loads(report_path.read_text('utf8'))
layout = ROOT/'analysis/battle-ui/result/layouts.json'
if hashlib.sha256(layout.read_bytes()).hexdigest() != report['layout_report_sha256']:
    raise ValueError('Result layout evidence changed; recover sprites again')
dest = ROOT/'clients/cocos-poc/assets/resources/recovered/result-ui'
dest.mkdir(parents=True, exist_ok=True)
for frame in report['frames']:
    data = (ROOT/frame['png']).read_bytes()
    if hashlib.sha256(data).hexdigest() != frame['sha256']:
        raise ValueError('Result sprite identity changed')
    (dest/(frame['name']+'.png')).write_bytes(data)
layouts = json.loads(layout.read_text('utf8'))
csb = ROOT/'analysis/battle-ui/result/3559.csb'
if hashlib.sha256(csb.read_bytes()).hexdigest() != layouts['layouts']['3559']['source']['sha256']:
    raise ValueError('Victory CSB identity changed')
timeline = read_timeline(csb.read_bytes())
tree = copy.deepcopy(layouts['layouts']['3559']['tree'])
vx = next(n for n in tree['children'] if n['name'] == 'Panel_VX')
panel = next(n for n in vx['children'] if n['name'] == 'Panel_1')
panel['children'] = [n for n in panel['children'] if n['name'] in ('perfect', 'perfect_black', 'img_event_win_up')]
if len(panel['children']) != 3:
    raise ValueError('Unexpected victory title hierarchy')
vx['children'] = [panel]; tree['children'] = [vx]
tags = {tree['action_tag'], vx['action_tag'], panel['action_tag'], *(n['action_tag'] for n in panel['children'])}
tracks = [t for t in timeline['timelines'] if t['action_tag'] in tags]
for track in tracks:
    if track['property'] not in ('Alpha', 'Scale', 'Position', 'AnchorPoint'):
        raise ValueError('Unsupported victory title track')
    for key in track['frames']:
        if key['easing_type'] not in (-1, 0, 2, 14, 20) or key['easing_points']:
            raise ValueError('Unsupported victory title easing')
clock = ROOT/'analysis/battle-ui/native-selection-clock.json'
manifest = dict(hierarchy=tree, timelines=tracks, animations=timeline['animations'],
    speed=timeline['speed'], frame_interval=json.loads(clock.read_text('utf8'))['frame_interval_float32'],
    frames=[dict(source_path=f['source_frame'], resource=f['name']) for f in report['frames']
            if f['name'] in ('victory-title', 'victory-shadow', 'victory-lettering')],
    csb_sha256=hashlib.sha256(csb.read_bytes()).hexdigest(),
    clock_report_sha256=hashlib.sha256(clock.read_bytes()).hexdigest(),
    limitations=['Title layers and ancestor tracks only; line effects, particles and rewards omitted.',
                 'Standard cocos2d-x easing interpretation; native fork and loader timing parity unverified.'])
(dest/'victory-title.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf8')
(dest/'provenance.json').write_text(json.dumps(dict(
    source_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
    apk_sha256=report['apk_sha256'], frames=report['frames'],
    title_manifest_sha256=hashlib.sha256((dest/'victory-title.json').read_bytes()).hexdigest(),
    limitations=manifest['limitations']),
    ensure_ascii=False, indent=2), 'utf8')
print('Staged', len(report['frames']), 'verified victory sprites')
