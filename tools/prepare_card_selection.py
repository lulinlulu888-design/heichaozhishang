"""Stage source-bound selection sprites and layout; execute no original scripts.

Generated FPS metadata is deliberately not treated as playback timing: the
shipped CommonActionTimeline.initAuto does not apply that parameter.
"""
import hashlib
import json
import shutil
from pathlib import Path
import inspect_battle_rules as static

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/battle-ui'
SOURCE = OUT/'card-selection'
DEST = ROOT/'clients/cocos-poc/assets/resources/recovered/card-selection'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def main():
    index = json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    auto = static.export(next(r for r in index if r['index'] == 9511),
                         ('<module>', '_initAutoWidgets', '_initAutoActions'))
    common = static.export(next(r for r in index if r['index'] == 6095),
                           ('__init__', 'initAuto', 'playAnimation'))
    (OUT/'selection-auto-evidence.json').write_text(json.dumps(auto, ensure_ascii=False, indent=2), 'utf8')
    (OUT/'selection-common-timeline-evidence.json').write_text(json.dumps(common, ensure_ascii=False, indent=2), 'utf8')
    instructions = next(c for c in auto['code_objects'] if c['name'] == '_initAutoWidgets')['instructions']
    colors = {}
    for a, b, c in zip(instructions, instructions[1:], instructions[2:]):
        if [a['opname'], b['opname'], c['opname']] != ['LOAD_CONST', 'LOAD_CONST', 'STORE_MAP']:
            continue
        values, key = a.get('operand'), b.get('operand')
        if isinstance(values, list) and len(values) == 4 and isinstance(key, str):
            if not all(type(v) is int and 0 <= v <= 255 for v in values):
                raise ValueError('Invalid source color')
            colors[key] = dict(argb=values, instruction_offset=a['offset'])
    if set(colors) != {'S11','S12','S21','S22','S31','S32','S41','S42','DesignStatus'}:
        raise ValueError('Source color map changed')
    provenance = json.loads((SOURCE/'provenance.json').read_text('utf8'))
    if digest(OUT/'selection-timeline.json') != provenance['timeline_sha256']:
        raise ValueError('Timeline differs from extracted sprite provenance')
    timeline = json.loads((OUT/'selection-timeline.json').read_text('utf8'))
    clock = json.loads((OUT/'native-selection-clock.json').read_text('utf8'))
    layout = next(r for r in json.loads((OUT/'layout-trees.json').read_text('utf8'))['layouts']
                  if r['name'] == 'EffectCardSelected_SmallCard')
    if layout['source']['sha256'] != timeline['source']['sha256']:
        raise ValueError('Timeline and hierarchy use different CSB')
    if digest(OUT/'EffectCardSelected_SmallCard.csb') != layout['source']['sha256']:
        raise ValueError('Source CSB changed')
    nodes = list(walk(layout['tree']))
    sprites = [n for n in nodes if n['classname'] == 'Sprite']
    if len(sprites) != 8 or any(n['blend_func'] != [1, 1] for n in sprites):
        raise ValueError('Unexpected selection sprite blend inventory')
    tags = {n['action_tag'] for n in nodes}
    if any(t['action_tag'] not in tags for t in timeline['timelines']):
        raise ValueError('Unbound animation track')
    # Validate every input before writing shared-client resource files.
    for frame in provenance['frames']:
        if digest(SOURCE/frame['name']) != frame['png_sha256']:
            raise ValueError('Extracted PNG changed: '+frame['name'])
    DEST.mkdir(parents=True, exist_ok=True)
    for frame in provenance['frames']:
        shutil.copyfile(SOURCE/frame['name'], DEST/frame['name'])
    manifest = dict(schema_version=1, source=layout['source'], colors=colors,
        hierarchy=layout['tree'], duration=timeline['duration'], speed=timeline['speed'],
        animations=timeline['animations'], timelines=timeline['timelines'],
        frames=[dict(source_path=f['key'], resource=Path(f['name']).stem,
                     size=f['size'], png_sha256=f['png_sha256']) for f in provenance['frames']],
        evidence=dict(auto_sha256=digest(OUT/'selection-auto-evidence.json'),
            common_timeline_sha256=digest(OUT/'selection-common-timeline-evidence.json'),
            atlas_sha256=provenance['texture_source']['sha256']),
        timing=dict(generated_fps=30, source_action_speed=timeline['speed'],
            native_frame_interval=clock['frame_interval_float32'],
            derived_fps=timeline['speed']/clock['frame_interval_float32'],
            native_evidence_sha256=digest(OUT/'native-selection-clock.json'),
            verified_wallclock_fps=None,
            note='Native step accumulates delta*speed and divides by frame interval. Source CSB speed application by loader and original runtime remain unverified.'),
        limitations=['Resource manifest does not by itself verify client playback.',
            'Source runtime visual equivalence and wall-clock timing remain unverified.',
            'Blend constants are source OpenGL ONE/ONE; renderer alpha conventions require validation.'])
    (DEST/'selection.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(dict(frames=len(provenance['frames']), sprites=len(sprites), colors=len(colors),
        tracks=len(timeline['timelines']), destination=str(DEST))))


if __name__ == '__main__':
    main()
