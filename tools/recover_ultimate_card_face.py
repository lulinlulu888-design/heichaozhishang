"""Recover Elsa's ultimate card 410104 small-card art and its CARD_TYPE 7 frame.

card_table 410104: CHARACTER_IMAGE aiersha5.png, CARD_TYPE 7, CARD_RARITY 4, COST 0.
card_img_table[7] differs from row 0 only in the frames: CardFramsSmall is
bg_ex_s_infight.png; the type bar/icon and the rarity gems stay the attack ones.
RPG_DEFAULT_FORMULA 300 is three times AP, which the eight server hits sum to
(within per-hit rounding), so the %s shows the card's total opponent damage.
The SpineRes card animation is not reproduced. No game code is executed.
"""
import hashlib
import json
import sys
from pathlib import Path

from extract_game_data import export_table
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/ultimate-card'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
CARD_TABLE, CARD_IMG_TABLE, CARD = 3391, 9257, 410104


def main():
    card = export_table(CARD_TABLE, [CARD])['rows'][0]['fields']
    if (card['CARD_TYPE'], card['CARD_RARITY'], card['COST'], card['SKILL_ID']) != (7, 4, 0, CARD):
        raise ValueError('Card 410104 is no longer the zero-cost type-7 rarity-4 ultimate')
    if card['RPG_DESCRIPTION'].count('%s') != 1 or card['RPG_DEFAULT_FORMULA'] != [[300]] or card['RPG_FORMULA'] != [['AP']]:
        raise ValueError('Ultimate description formula changed')
    rows = {row['id']: row['fields'] for row in export_table(CARD_IMG_TABLE, [0, 7])['rows']}
    attack, special = rows[0], rows[7]
    for key in ('CardTypeImg', 'CardTypeImgBg', 'CardFeeBg', 'CardRarityTypeImage', 'CardRarityTypeBGImage'):
        if attack[key] != special[key]:
            raise ValueError('card_img_table[7] no longer shares ' + key + ' with the attack row')
    logical = {'card-410104': card['CHARACTER_IMAGE'], 'card-frame-ex': special['CardFramsSmall']}
    if logical['card-frame-ex'] != 'uires/AllUIRes/Card/bg_ex_s_infight.png':
        raise ValueError('Type-7 small frame changed')
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for key, path in logical.items():
        report = recover_virtual_sprite(path, OUT/key, key, provenance={'card_table[410104]' if key == 'card-410104'
                                                                         else 'card_img_table[7].CardFramsSmall': path})
        frames.append({'name': key, 'logical': path, 'png': report['output'], 'size': list(report['size']),
                       'png_sha256': report['output_sha256']})
    sizes = {row['name']: row['size'] for row in frames}
    if sizes != {'card-410104': [286, 286], 'card-frame-ex': [234, 182]}:
        raise ValueError('Ultimate art or EX frame no longer matches the small-card sizes')
    face = {'name': card['NAME'], 'rarity': card['CARD_RARITY'], 'cardType': card['CARD_TYPE'],
            'description': card['RPG_DESCRIPTION'], 'formula': card['RPG_FORMULA'],
            'defaultFormula': card['RPG_DEFAULT_FORMULA'], 'frame': 'card-frame-ex', 'descriptionValue': 'total-damage'}
    report = {'apk_sha256': APK, 'frames': frames, 'cards': {str(CARD): face},
              'binding': 'card_table CHARACTER_IMAGE -> Face_NL_S; card_img_table[CARD_TYPE].CardFramsSmall -> CharImage_NL_S',
              'limitations': ['SpineRes uires/spineRes/card/aiersa_01/aiersa_card_01 (animated card art) is not reproduced.',
                              'The %s total is the sum of the eight server hits; the original rich-text value path is not executed.',
                              'EffectVxRare and the EX card glow are not reproduced.']}
    path = OUT/'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(hashlib.sha256(path.read_bytes()).hexdigest(), sizes)


if __name__ == '__main__':
    sys.exit(main())
