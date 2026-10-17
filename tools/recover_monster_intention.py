"""Recover the tutorial monster IntentionArea inputs from static APK data without execution.

skill_table.SKILL_INTENTIONS -> monster_intention_table row -> icon/bg sprites, plus the
IntentionArea/ModelUIArea placement constants the UE HUD reproduces.
"""
import hashlib
import json
import plistlib
import re
import sys
from pathlib import Path
from PIL import Image

from extract_game_data import export_table
from extract_npk import Marshal2
from inspect_battle_rules import instructions, read_module, walk_codes
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/intention'
APK = 'aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4'
INTENTION_AREA = 'analysis/assets/decoded/script/01695_2e37df00.marshal'
MODEL_UI_AREA = 'analysis/assets/decoded/script/00923_194eb319.marshal'
SKILL_TABLE, INTENTION_TABLE = 9333, 7463
ENEMY_STATES = 'analysis/first-encounter/enemy-skill-states.json'
FIGHT_ATLAS = ('analysis/battle-ui/entrance/sprites/FightPanel/atlas.plist',
               'analysis/battle-ui/entrance/sprites/FightPanel/decoded/atlas.1c1a54ff26bf.m0.f0.png')
ICON_BG = 'FightPanel/FightNewPanel/res/ui_fight/img_fight_intention_bg.png'
# CSB IntentionItem_type1/type2_ext.csb share these nodes; NumText is droidsansfallback 20,
# white, outline 2 black (read with prepare_unreal_hall_ui.HallReader).
LAYOUT = {'csb': ['uires/FightPanel/SimUI/IntentionItem_type1_ext.csb', 'uires/FightPanel/SimUI/IntentionItem_type2_ext.csb'],
          'img_iconbg': {'position': [0, 0], 'size': [52, 52]},
          'sprite_light': {'position': [0, 0], 'blend_func': [1, 771], 'texture': 'same as Intention_NL'},
          'Intention_NL': {'position': [0, 0], 'size': [86, 98]},
          'NumText': {'position': [6, -12], 'anchor': [0, 0.5], 'fontSize': 20, 'font': 'CommonRes/droidsansfallback.ttf',
                      'color': [255, 255, 255, 255], 'outline': {'size': 2, 'color': [0, 0, 0, 255]}},
          'IntentionArea': {'IntentionItem.y': 40, 'arrange': 'x_i = -(60n+46)/2 + 23 + 60i + 30, y = IntentionItem.y + 20'},
          'ModelUIArea': {'setEntityPosition': 'root at model screen pos; height = head.y - root.y + 30',
                          'setIntenUIPos': 'IntentionArea at (0, height + diff); diff clamps below FLOAT_TOP_POS.y - 50'},
          'fade': 'IntentionItem.playAnimIn runFadeInAnimation 0.3 s'}


def load(relative):
    raw = (ROOT/relative).read_bytes()
    obj = Marshal2(raw).obj()
    return read_module({'output': relative, 'decoded_sha256': hashlib.sha256(raw).hexdigest(),
                        'filename': obj['filename'].decode()})


def code(module, name):
    return next(c for _path, c in walk_codes(module) if c['name'] == name.encode())


def consts(module, name):
    return [s.get('operand') for s in instructions(code(module, name)) if s['opname'] == 'LOAD_CONST']


def crop_atlas(logical, target):
    plist_path, png_path = (ROOT/p for p in FIGHT_ATLAS)
    num = lambda text: [int(v) for v in re.findall(r'-?\d+', text)]
    frame = plistlib.loads(plist_path.read_bytes())['frames'][logical]
    atlas = Image.open(png_path).convert('RGBA')
    fx, fy, fw, fh = num(frame['frame'])
    sx, sy, sw, sh = num(frame['sourceColorRect'])
    crop = atlas.crop((fx, fy, fx + (fh if frame['rotated'] else fw), fy + (fw if frame['rotated'] else fh)))
    if frame['rotated']:
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    if crop.size != (sw, sh):
        raise ValueError('Intention bg trim rectangle mismatch')
    image = Image.new('RGBA', tuple(num(frame['sourceSize'])))
    image.paste(crop, (sx, sy))
    image.save(target)
    return {'logical': logical, 'png': target.relative_to(ROOT).as_posix(), 'size': list(image.size),
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'atlas': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FIGHT_ATLAS}}


def main():
    area, model = load(INTENTION_AREA), load(MODEL_UI_AREA)
    if [v for v in consts(area, 'arrange') if isinstance(v, (int, float))] != [0, 60, 46, 2.0, 23, 30, 20, 30]:
        raise ValueError('IntentionArea.arrange constants changed')
    if 30 not in consts(model, 'setEntityPosition') or 50 not in consts(model, 'setIntenUIPos'):
        raise ValueError('ModelUIArea head offsets changed')
    if 0.3 not in consts(area, 'playAnimIn'):
        raise ValueError('IntentionItem fade-in changed')
    skills = {row['id']: row['fields']['SKILL_INTENTIONS'] for row in export_table(SKILL_TABLE, [990, 991, 992])['rows']}
    if skills != {990: [102], 991: [102], 992: [2]}:
        raise ValueError('Tutorial monster skill intentions changed')
    rows = {row['id']: row['fields'] for row in export_table(INTENTION_TABLE, [2, 102])['rows']}
    attack, defense = rows[102], rows[2]
    melee = {attack[k] for k in ('ICON_SOURCE_MELEE_LOW', 'ICON_SOURCE_MELEE_MED', 'ICON_SOURCE_MELEE_HGH')}
    if not attack['IS_ATK'] or melee != {attack['ICON_SOURCE']} or defense['IS_ATK'] or defense['NAME'] != '防御':
        raise ValueError('Intention rows 102/2 changed')
    states = json.loads((ROOT/ENEMY_STATES).read_text('utf8'))
    damage_types = {row['fields']['DAMAGE_TYPE'] for row in states['rows']
                    if row['fields'].get('STORYLINE_NAME') == 'SkillState_MonsterCauseDamage'}
    if damage_types != {1}:
        raise ValueError('Tutorial monster damage is no longer RpgAttackType.PhysicalAttack (1)')
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for key, logical in (('intention-attack', attack['ICON_SOURCE']), ('intention-defense', defense['ICON_SOURCE'])):
        report = recover_virtual_sprite(logical, OUT/key, key, provenance={'monster_intention_table': logical})
        if tuple(report['size']) != (86, 98):
            raise ValueError(f'{logical} no longer matches the 86x98 Intention_NL node')
        frames.append({'name': key, 'logical': logical, 'png': report['output'], 'size': report['size'],
                       'png_sha256': report['output_sha256']})
    bg = crop_atlas(ICON_BG, OUT/'intention-bg.png')
    if bg['size'] != [52, 52]:
        raise ValueError('Intention bg no longer matches img_iconbg')
    frames.append({'name': 'intention-bg', **{k: bg[k] for k in ('logical', 'png', 'size')}, 'png_sha256': bg['sha256'],
                   'atlas': bg['atlas']})
    report = {'apk_sha256': APK, 'frames': frames, 'layout': LAYOUT,
              'skills': {str(k): v for k, v in skills.items()},
              'intentions': {'102': {'name': attack['NAME'], 'isAtk': True, 'icon': 'intention-attack',
                                     'note': 'all MELEE/LOW-MED-HGH tiers are attack_ad3, so the damage ratio does not change the icon'},
                             '2': {'name': defense['NAME'], 'isAtk': False, 'icon': 'intention-defense'}},
              'damageType': 'skill_state_table DAMAGE_TYPE 1 = RpgAttackType.PhysicalAttack (MELEE icons)',
              'limitations': ['IntentionItem group_normal.icon (target IntentionHeadIcon) depends on runtime '
                              'getEntityCharIdByEid; the reference video shows no stripe, so it is not drawn.',
                              'FLOAT_TOP_POS clamp and the IntentionVX/In timelines are not reproduced.']}
    path = OUT/'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    sys.exit(main())
