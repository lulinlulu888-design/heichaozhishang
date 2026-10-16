"""Prepare OwnCardArea's original `In` clip, which the battle HUD In starts.

FightPanel.onBattleStart (module 3414, lines 259-260) calls _showUI(True) and
plays FightMainPanel `In`; that timeline's ActionValue track starts the nested
OwnCardArea `In` at its first frame. Reads the extracted original CSB only.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from csb_timeline import timeline_with_inner, walk
from inspect_battle_ui_layout import Reader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'analysis/battle-ui/OwnCardArea.csb'
SOURCE_SHA256 = '81273767f5d227e90ca1d8bdc07a0bf08100485c35833898afe24efbd51536f9'
HUD_LAYOUTS = ROOT / 'analysis/battle-ui/entrance/layouts.json'
OUT = ROOT / 'analysis/battle-ui/hud-in/own-card-area-in.json'
LOGICAL_PATH = 'uires/FightPanel/OwnCardArea_ext.csb'


def nested_trigger():
    hud = json.loads(HUD_LAYOUTS.read_text('utf8'))['layouts']['hud']
    start = next(a for a in hud['timeline']['animations'] if a['name'] == 'In')['start']
    track = next(t for t in hud['timeline']['timelines']
                 if t['property'] == 'ActionValue' and t['targetNodeNames'] == ['OwnCardArea'])
    frame = next(f for f in track['frames'] if f['value']['currentAnimationName'] == 'In')
    if frame['index'] != start or frame['value']['innerActionType'] != 1:
        raise ValueError('HUD In no longer starts OwnCardArea In at its first frame')
    return {'hudAnimation': 'In', 'hudFrame': frame['index'], 'innerActionType': 1,
            'sourceOffset': frame['sourceOffset']}


def clip(raw):
    reader = Reader(raw, preserve_unknown=True)
    root = reader.scalar('I', 0)
    if reader.string(reader.field(root, 0)) != '2.1.0.0':
        raise ValueError('Unsupported source layout schema')
    tree = reader.node(reader.pointer(reader.field(root, 3)))
    timeline = timeline_with_inner(raw)
    interval = next(a for a in timeline['animations'] if a['name'] == 'In')
    # walk() yields parents by name/tag only; rebuild indices from traversal order.
    nodes, stack = [], []
    for node, parents in walk(tree):
        while len(stack) > len(parents):
            stack.pop()
        entry = {k: v for k, v in node.items() if k != 'children'}
        entry['parent'] = stack[-1] if stack else -1
        # HUD In only needs group transforms here; sprites stay with the existing HUD painter.
        entry['unsupported'] = ['source-sprite-not-imported'] if entry.get('resource') else []
        stack.append(len(nodes))
        nodes.append(entry)
    tags = {}
    for node in nodes:
        tags.setdefault(node['action_tag'], []).append(node['name'])
    tracks = []
    for track in timeline['timelines']:
        names = tags.get(track['action_tag'], [])
        if len(names) != 1:
            raise ValueError('Ambiguous OwnCardArea animation target')
        tracks.append(dict(track, targetNodeNames=names))
    return dict(schema='hczs-source-ui-timeline-v1', fps=60, speed=timeline['speed'],
                startFrame=interval['start'], endFrame=interval['end'],
                easingPolicy='cocos2d-x-3.17.2', nodes=json.loads(json.dumps(nodes)), tracks=json.loads(json.dumps(tracks)))


def main():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('OwnCardArea source changed')
    value = dict(sourceLogicalPath=LOGICAL_PATH, sourceSha256=SOURCE_SHA256,
                 trigger=dict(nestedTrigger=nested_trigger(), script='FightPanel.onBattleStart', module=3414, lines=[259, 260]),
                 clip=clip(raw), originalRuntimeExecuted=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')
    print(json.dumps({'output': str(OUT), 'nodes': len(value['clip']['nodes']), 'tracks': len(value['clip']['tracks']),
                      'frames': [value['clip']['startFrame'], value['clip']['endFrame']]}))


if __name__ == '__main__':
    main()
