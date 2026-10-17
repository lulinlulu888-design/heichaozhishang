"""Recover the prologue 1703 deck's missing small-card faces.

card_table gives each card's CHARACTER_IMAGE, CARD_TYPE, CARD_RARITY and
RPG_DESCRIPTION; card_img_table[CARD_TYPE] gives the small frame, type bar
and type icon. Only cards and type parts the existing manifests lack are
recovered. %s binds to the first shield for APSHD formulas and to the first
damage for AP ones. No game code is executed.
"""
import hashlib
import json
import sys
from pathlib import Path

from extract_game_data import export_table
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/party-cards'
FIXTURE = ROOT / 'clients/unreal5 5.8/Source/Hczs/Private/Tests/Fixtures/prologue-boss-party-v1.json'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
CARD_TABLE, CARD_IMG_TABLE = 3391, 9257
HAVE_ART = {110001, 110009, 210003, 410101, 410102, 410104}
TYPE_NAMES = {1: 'skill', 2: 'ability', 6: 'def'}
SIZES = {'frame': [234, 182], 'bar': [48, 94], 'icon': [40, 40]}
VALUE = {'AP': 'first-damage', 'APSHD': 'first-shield'}


def main():
    definition = json.loads(FIXTURE.read_text('utf8'))['initial']['battle']['scenario']['definition']
    ids = sorted({int(e['cardId']) for e in definition['deck']})
    cards = {row['id']: row['fields'] for row in export_table(CARD_TABLE, ids)['rows']}
    types = sorted({f['CARD_TYPE'] for f in cards.values()} - {0})
    if set(types) - set(TYPE_NAMES):
        raise ValueError(f'Unreviewed card types in the deck: {types}')
    img = {row['id']: row['fields'] for row in export_table(CARD_IMG_TABLE, [0] + types)['rows']}
    for t in types:
        if img[t]['CardFeeBg'] != img[0]['CardFeeBg'] or img[t]['CardRarityTypeImage'] != img[0]['CardRarityTypeImage']:
            raise ValueError(f'card_img_table[{t}] no longer shares cost/rarity art with the attack row')
    logical = {}
    for t in types:
        name = TYPE_NAMES[t]
        logical[f'card-frame-{name}'] = (img[t]['CardFramsSmall'], f'card_img_table[{t}].CardFramsSmall', SIZES['frame'])
        logical[f'card-type-bar-{name}'] = (img[t]['CardTypeImgBg'], f'card_img_table[{t}].CardTypeImgBg', SIZES['bar'])
        logical[f'card-type-icon-{name}'] = (img[t]['CardTypeImg'], f'card_img_table[{t}].CardTypeImg', SIZES['icon'])
    for cid in ids:
        if cid not in HAVE_ART:
            logical[f'card-{cid}'] = (cards[cid]['CHARACTER_IMAGE'], f'card_table[{cid}].CHARACTER_IMAGE', [286, 286])
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for key, (path, field, size) in logical.items():
        report = recover_virtual_sprite(path, OUT / key, key, provenance={field: path})
        if list(report['size']) != size:
            raise ValueError(f'{key} is {report["size"]}, expected {size}')
        frames.append({'name': key, 'logical': path, 'png': report['output'], 'size': list(report['size']),
                       'png_sha256': report['output_sha256'], 'field': field})
    faces = {}
    for cid in ids:
        f = cards[cid]
        if f['CARD_TYPE'] == 0:
            continue
        formula = f.get('RPG_FORMULA') or []
        if f['RPG_DESCRIPTION'].count('%s') != len(formula) or len(formula) > 1 or (formula and formula[0][0] not in VALUE):
            raise ValueError(f'Card {cid} description/formula pairing is not reviewed')
        name = TYPE_NAMES[f['CARD_TYPE']]
        faces[str(cid)] = {'name': f['NAME'], 'rarity': f['CARD_RARITY'], 'cardType': f['CARD_TYPE'],
                           'description': f['RPG_DESCRIPTION'], 'formula': formula,
                           'defaultFormula': f.get('RPG_DEFAULT_FORMULA'),
                           'frame': f'card-frame-{name}', 'typeBar': f'card-type-bar-{name}', 'typeIcon': f'card-type-icon-{name}',
                           'descriptionValue': VALUE[formula[0][0]] if formula else 'none'}
    report = {'apk_sha256': APK, 'frames': frames, 'cards': faces,
              'binding': 'card_table CHARACTER_IMAGE -> Face_NL_S; card_img_table[CARD_TYPE] CardFramsSmall/CardTypeImgBg/CardTypeImg',
              'limitations': ['#R...#l rich-text keyword colour is stripped, not rendered red.',
                              '%s uses the client preview of the first shield/damage effect; the original formula evaluator is not executed.']}
    path = OUT / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(hashlib.sha256(path.read_bytes()).hexdigest(), {r['name']: r['size'] for r in frames})


if __name__ == '__main__':
    sys.exit(main())
