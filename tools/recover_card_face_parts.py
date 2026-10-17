"""Recover the FightSmallCard type bar, type icon, rarity gem and description templates.

FightCard._assignShown binds img_type <- CardImgPath.CardTypeName (card_img_table CardTypeImg),
img_infobar <- CardTypeImgBg, rare_bg <- CardRarityBgImg and Ssr_NL <- CardRarityImg
(CardRarityTypeImage[CARD_RARITY]). The description is card_table RPG_DESCRIPTION, whose %s
is the first damage amount computed by the server. No game code is executed.
"""
import hashlib
import json
import sys
from pathlib import Path

from extract_game_data import export_table
from recover_card_usable_light import load, FIGHT_CARD
from inspect_battle_rules import instructions, walk_codes
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/card-face'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
CARD_TABLE, CARD_IMG_TABLE = 3391, 9257
CARDS = [110001, 110009, 210003, 410101, 410102]
# FightSmallCard.csb nodes relative to the 126x166 card centre (Cocos y up).
LAYOUT = {'img_infobar': {'position': [-46, 62], 'size': [48, 94], 'anchor': [0.5, 1], 'scale': 0.6},
          'img_type': {'parent': 'img_infobar', 'position': [24, 52], 'size': [40, 40], 'anchor': [0.5, 0.5]},
          'rare_bg': {'position': [0, -20], 'size': [120, 120], 'anchor': [0.5, 0.5], 'scale': 0.5},
          'Ssr_NL': {'parent': 'rare_bg', 'position': [60, 60], 'size': [120, 120], 'anchor': [0.5, 0.5]},
          'Descr': {'position': [0, -50], 'size': [102, 24], 'anchor': [0.5, 1], 'fontSize': 12,
                    'color': [54, 52, 85]}}


def main():
    assign = [s.get('operand') for s in instructions(next(
        c for _p, c in walk_codes(load(FIGHT_CARD)) if c['name'] == b'_assignShown'))]
    needed = {'_cimg_type', 'CardTypeName', '_cimg_infobar', 'CardTypeImgBg', '_cSsr_NL', 'CardRarityImg',
              '_crare_bg', 'CardRarityBgImg', 'isPurpleCard'}
    if not needed <= set(assign):
        raise ValueError('FightCard._assignShown no longer binds the small-card type bar and rarity gem')
    cards = {row['id']: row['fields'] for row in export_table(CARD_TABLE, CARDS)['rows']}
    if set(cards) != set(CARDS) or {f['CARD_TYPE'] for f in cards.values()} != {0}:
        raise ValueError('Hand cards are no longer all CARD_TYPE 0')
    images = export_table(CARD_IMG_TABLE, [0])['rows'][0]['fields']
    logical = {'card-type-bar-attack': images['CardTypeImgBg'], 'card-type-icon-attack': images['CardTypeImg']}
    rarities = sorted({f['CARD_RARITY'] for f in cards.values()})
    for rarity in rarities:
        logical['card-rarity-bg'] = images['CardRarityTypeBGImage'][str(rarity)]
        logical[f'card-rarity-{rarity}'] = images['CardRarityTypeImage'][str(rarity)]
    if len({images['CardRarityTypeBGImage'][str(r)] for r in rarities}) != 1:
        raise ValueError('Rarity backgrounds differ between hand cards')
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for key, path in logical.items():
        report = recover_virtual_sprite(path, OUT/key, key, provenance={'card_img_table[0]': path})
        frames.append({'name': key, 'logical': path, 'png': report['output'], 'size': report['size'],
                       'png_sha256': report['output_sha256']})
    faces = {str(cid): {'name': f['NAME'], 'rarity': f['CARD_RARITY'], 'cardType': f['CARD_TYPE'],
                        'description': f['RPG_DESCRIPTION'], 'formula': f['RPG_FORMULA'],
                        'defaultFormula': f['RPG_DEFAULT_FORMULA']}
             for cid, f in sorted(cards.items())}
    if any(face['description'].count('%s') != 1 for face in faces.values()):
        raise ValueError('Description templates must hold exactly one %s')
    report = {'apk_sha256': APK, 'frames': frames, 'layout': LAYOUT, 'cards': faces,
              'binding': 'FightCard._assignShown: img_type<-CardTypeName(CardTypeImg), img_infobar<-CardTypeImgBg, '
                         'rare_bg<-CardRarityBgImg, Ssr_NL<-CardRarityImg; rare_bg/Ssr_NL visible = isPurpleCard',
              'limitations': ['isPurpleCard compares Type with CurseType through a remapped COMPARE_OP; the reference '
                              'video shows the gem on all five attack cards, so it is drawn for non-curse cards.',
                              'doSetCardDescriptionRichText colouring, EffectVxRare and the kafei node are not reproduced.',
                              'The %s value is the server reconstruction; the reference video shows about 1.2x larger '
                              'numbers (AP near 578 against the 482.4 base), whose modifier is not recovered.']}
    path = OUT/'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(hashlib.sha256(path.read_bytes()).hexdigest(), [(f['name'], f['size']) for f in frames])


if __name__ == '__main__':
    sys.exit(main())
