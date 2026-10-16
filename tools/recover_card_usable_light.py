"""Recover the small-card usable outline named by UIConst.CARD_FRAME_TO_USABLE without execution."""
import hashlib
import json
import sys
from pathlib import Path

from extract_npk import Marshal2
from inspect_battle_rules import instructions, read_module, walk_codes
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
UICONST = 'analysis/assets/decoded/script/06870_b5bf8b0d.marshal'
FIGHT_CARD = 'analysis/assets/decoded/script/06992_b90a5163.marshal'
DEFAULT_LIGHT = 'uires/CommonRes/SpecialImage/smallCard_light.png'


def load(relative):
    raw = (ROOT/relative).read_bytes()
    obj = Marshal2(raw).obj()
    return read_module({'output': relative, 'decoded_sha256': hashlib.sha256(raw).hexdigest(),
                        'filename': obj['filename'].decode()})


def usable_map():
    steps = list(instructions(load(UICONST)))
    end = next(k for k, step in enumerate(steps)
               if step['opname'] == 'STORE_NAME' and step.get('operand') == 'CARD_FRAME_TO_USABLE')
    start = max(k for k in range(end) if steps[k]['opname'] == 'BUILD_MAP')
    body = steps[start+1:end]
    if len(body) % 3 or any(body[k+2]['opname'] != 'STORE_MAP' for k in range(0, len(body), 3)):
        raise ValueError('Unexpected CARD_FRAME_TO_USABLE literal shape')
    return {body[k+1]['operand']: body[k]['operand'] for k in range(0, len(body), 3)}


def main():
    mapping = usable_map()
    if mapping.get('') != DEFAULT_LIGHT or 'uires/AllUIRes/Card/bg_atk_s.png' in mapping:
        raise ValueError('Attack frames no longer fall back to the default usable outline')
    assign = [step.get('operand') for step in instructions(next(
        code for _path, code in walk_codes(load(FIGHT_CARD)) if code['name'] == b'_assignShown'))]
    if not {'CARD_FRAME_TO_USABLE', 'CardFramsSmall', '_wUsable'} <= set(assign):
        raise ValueError('FightCard no longer binds the frame to the usable outline')
    report = recover_virtual_sprite(DEFAULT_LIGHT, ROOT/'analysis/battle-ui/card-usable', 'small-card-light',
        provenance=dict(card_frame_to_usable=mapping, binding='FightCard._assignShown loads '
            'CARD_FRAME_TO_USABLE.get(CardFramsSmall, default) into FightSmallCard Usable (182x234)'))
    if tuple(report['size']) != (182, 234):
        raise ValueError('Outline size no longer matches the FightSmallCard Usable node')
    print(json.dumps(dict(output=report['output'], size=report['size'], sha256=report['output_sha256'])))


if __name__ == '__main__':
    sys.exit(main())
