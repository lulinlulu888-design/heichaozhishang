"""Export the APK's ultimate event/queue dispatch without executing game code."""
import hashlib
import json
from pathlib import Path

import inspect_battle_rules as source
from audit_elsa_hit_timing import MODULE_SHA

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-visual/elsa-ultimate/event-dispatch.json'
SELECTIONS = {
    4497: {'play', 'createReactTrack', 'casterAnimEvent', 'getSkillReactTimeList'},
    6025: {'getAnimReactCount', 'startVideo', '_onVideoReady', '_onVideoComplete'},
    6286: {'start', 'setStepMode', 'update', 'playNextAction', 'updateNowAction'},
    7532: {'enableTrack'},
}


def main():
    rows = {r['index']: r for r in json.loads((source.SCRIPT / 'index.json').read_text('utf8'))}
    exports = []
    for mid, names in SELECTIONS.items():
        row = rows[mid]
        if mid in MODULE_SHA and row['decoded_sha256'] != MODULE_SHA[mid]:
            raise ValueError('Reviewed battle script identity changed')
        source.read_module(row)  # Validates complete marshal, file hash and source name.
        item = source.export(row, names)
        if mid == 4497:
            item['code_objects'] = [c for c in item['code_objects'] if c['constant_path'][0] == 9]
        elif mid == 6025:
            item['code_objects'] = [c for c in item['code_objects'] if c['constant_path'][0] == 14]
        if {c['name'] for c in item['code_objects']} != names:
            raise ValueError('Expected dispatch functions missing or ambiguous')
        exports.append(item)
    functions = {(mid, c['name']): c for mid, item in zip(SELECTIONS, exports) for c in item['code_objects']}

    def anchor(mid, name, start, end):
        c = functions[mid, name]
        instructions = [i for i in c['instructions'] if start <= i['offset'] < end]
        if not instructions or instructions[0]['offset'] != start or instructions[-1]['end_exclusive'] != end:
            raise ValueError('Instruction-aligned source anchor changed')
        return {'moduleIndex': mid, 'function': name, 'constantPath': c['constant_path'],
                'bytecodeSha256': c['bytecode_sha256'], 'start': start, 'endExclusive': end}

    result = {'schema': 'hczs-ultimate-event-dispatch-v1', 'originalApkExecuted': False,
              'exports': exports, 'findings': [
        {'claim': 'Ultimate playback enables reaction-track step mode and registers attack-prefix and end animation events.',
         'anchors': [anchor(4497, 'play', 123, 273)]},
        {'claim': 'Each attack-prefix event calls playNextAction; end also advances and clears step mode.',
         'anchors': [anchor(4497, 'casterAnimEvent', 0, 181)]},
        {'claim': 'Reaction track is built from childActionList, not directly from damage-only configuration rows.',
         'anchors': [anchor(4497, 'createReactTrack', 86, 114), anchor(4497, 'createReactTrack', 280, 308)]},
        {'claim': 'Starting a sequence activates and baseStart-initializes actions; it does not automatically basePlay the first action.',
         'anchors': [anchor(6286, 'start', 0, 48)]},
        {'claim': 'Step mode updates the current action but prevents automatic advancement in update.',
         'anchors': [anchor(6286, 'update', 13, 68)]},
        {'claim': 'One playNextAction can skip flagged actions and drain zero-duration actions; a still-playing action prevents advancing.',
         'anchors': [anchor(6286, 'playNextAction', 0, 235)]},
        {'claim': 'The video callbacks suspend native global speed and restore the current game speed after playback.',
         'anchors': [anchor(6025, '_onVideoReady', 0, functions[6025, '_onVideoReady']['instructions'][-1]['end_exclusive']),
                     anchor(6025, '_onVideoComplete', 0, functions[6025, '_onVideoComplete']['instructions'][-1]['end_exclusive'])]},
    ], 'unknowns': [
        'Actual original-server childActionList for skill 410104 is not available.',
        'Nine authored attack cues cannot be assigned one-to-one to eight damage states without stage-action grouping/durations.',
        'Do not synthesize a ninth DamageApplied receipt from the animation track.',
    ]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'path': str(OUT), 'modules': len(exports), 'functions': len(functions),
                      'findings': len(result['findings']), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
