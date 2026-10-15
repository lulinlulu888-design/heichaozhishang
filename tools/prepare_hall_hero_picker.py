"""Recover the source hall picker strip, templates and initial-hero portraits.

Only the two recovered initial characters are instantiated. This is a local
preview subset, never a claim of original account ownership or complete UI.
"""
import argparse
import copy
import json
from pathlib import Path

from audit_hall_ui_dependencies import main as audit
from extract_game_data import export_table
from inspect_battle_rules import export
from prepare_unreal_hall_ui import build, digest, geometry, multiply, packed, verified
from recover_hall_ui_sprites import main as recover_pixels
from recover_monster_portrait import recover_virtual_sprite

ROOT = Path(__file__).resolve().parents[1]
DEP = ROOT/'analysis/hall/hero-picker'
OUT = ROOT/'analysis/unreal/hall-hero-picker'
ENTRIES = {
    'base': ('uires/Common/ChooseCharacterNode_ext.csb', 'dependencies', 'pixels'),
    'head': ('uires/Common/CharHeadItem/CharItemArea_ext.csb', 'head-dependencies', 'head-pixels'),
    'select': ('uires/Common/CharHeadItem/Char_Status_Select_ext.csb', 'select-dependencies', 'select-pixels'),
}


def main(recover=False):
    table = export_table(8995, [1, 3])
    heroes = sorted(table['rows'], key=lambda r: r['id'])
    if [r['id'] for r in heroes] != [1, 3] or not all(r['fields']['InitChar'] is True for r in heroes):
        raise ValueError('Reviewed initial-character configuration changed')
    script_rows = json.loads((ROOT/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    sources = [export(next(r for r in script_rows if r['index']==index), names)
               for index, names in (
                   (5795, ('_onCharListChooseChar', '_onCharListChooseClicked', '_onCharListQuitClicked', 'onChangeChar')),
                   (3661, ('initComponents', '_createWidgetFromPath', 'CharHeadItem', 'getOriCharAllData')),
                   (1715, ('getCSBFilePath', 'assignChar', 'showMultiSelect', 'fakeChooseSelf')),
                   (1523, ('<lambda>',)), (4819, ('_initAutoWidgets', 'switchStateTo_InHall')),
                   (8672, ('_initAutoWidgets', 'switchStateTo_single_select')))]
    # Verify the SquareUnlockIcon producer directly, without executing any APK code.
    icon_lambda = next(c for c in sources[3]['code_objects'] if c['constant_path']==[28])
    if [i.get('operand') for i in icon_lambda['instructions'] if i['opname']=='LOAD_CONST'] != ['PowerSupportSystemIcon', '']:
        raise ValueError('Source portrait property binding changed')
    hall = json.loads((ROOT/'analysis/unreal/hall-ui/layout.json').read_text('utf8'))
    attach = [n for n in hall['nodes'] if n['instancePath']=='Layer/Main/MidBottom/ChooseCharacterNode']
    if len(attach)!=1:
        raise ValueError('Original hall picker attachment is not unique')
    layouts = {}
    for key, (entry, dep, pixels) in ENTRIES.items():
        if recover:
            audit(entry, DEP/dep)
            recover_pixels(DEP/dep, DEP/pixels)
        build(entry, DEP/dep/'report.json', DEP/pixels/'report.json', OUT/key,
              root_matrix=attach[0]['worldMatrixBottomLeft'] if key=='base' else None)
        layouts[key] = json.loads((OUT/key/'layout.json').read_text('utf8'))
    base, head, selected = (layouts[key] for key in ('base','head','select'))
    nodes = {n['instancePath']: n for n in base['nodes']}
    strip = nodes['Node/Main/HeadPanel/Cut/ScrollView']
    if strip['direction']!=2 or strip['size']!=[1200,120]:
        raise ValueError('Reviewed horizontal strip geometry changed')
    # CharScrollView receives the detached 120x120 Panel from CharItemArea.
    panel = next(n for n in head['nodes'] if n['instancePath']=='Node/Panel')
    if panel['size']!=[120,120]:
        raise ValueError('Original avatar cell size changed')
    sprite_by_key = {(s['plist'],s['sourceFrame']): s for layout in layouts.values() for s in layout['sprites']}
    items, controls, portraits = [], [], []
    allowed = ('Node/Main/HeadPanel/Bg', 'Node/Main/HeadPanel/ButtonChoose', 'Node/Main/HeadPanel/ButtonQuit')
    for original in base['drawItems']:
        if not any(original['instancePath']==p or original['instancePath'].startswith(p+'/') for p in allowed):
            continue
        item = copy.deepcopy(original)
        item['previewExcludedReason'] = None
        item['clipGeometry'] = [next(n for n in base['nodes'] if n['id']==i)['clipGeometry'] for i in item['clipNodeIds']]
        items.append(item)
    for action, name in (('hero-confirm','ButtonChoose'),('hero-cancel','ButtonQuit')):
        node = nodes['Node/Main/HeadPanel/'+name]
        controls.append(dict(action=action, size=node['size'], geometry=geometry(node['worldMatrixBottomLeft'],node['size'])))
    head_nodes = {n['name']: n for n in head['nodes']}
    for ordinal, hero in enumerate(heroes):
        hero_id = hero['id']
        if recover:
            recover_virtual_sprite(hero['fields']['PowerSupportSystemIcon'], DEP/f'hero-{hero_id:03}')
        portrait = json.loads((DEP/f'hero-{hero_id:03}'/'report.json').read_text('utf8'))
        if portrait['logical']!=hero['fields']['PowerSupportSystemIcon'] or portrait['size']!=[180,180]:
            raise ValueError('Original portrait path/size mismatch')
        png = verified(portrait['output'],portrait['output_sha256'])
        sprite_id = f'hero-{hero_id:03}-portrait'
        portraits.append(dict(id=sprite_id,png=str(png),pngSha256=portrait['output_sha256'],size=portrait['size'],
                              sourceReport=str(DEP/f'hero-{hero_id:03}'/'report.json'),
                              sourceReportSha256=digest(DEP/f'hero-{hero_id:03}'/'report.json')))
        cell = multiply(strip['worldMatrixBottomLeft'], [1,0,0,1,ordinal*panel['size'][0],0])
        controls.append(dict(action=f'hero-preview-{hero_id}',heroId=hero_id,size=panel['size'],geometry=geometry(cell,panel['size'])))
        for name in ('icon','img_mask'):
            node = head_nodes[name]
            sprite = sprite_id if name=='icon' else sprite_by_key[('uires/'+node['resource']['plist'], node['resource']['path'])]['id']
            items.append(dict(id=f'hero-{hero_id}-{name}',kind='sprite',heroId=hero_id,selectedOnly=False,
                size=node['size'],geometry=geometry(multiply(cell,node['worldMatrixBottomLeft']),node['size']),
                spriteId=sprite,color=[1,1,1,1],opacity=1,clipGeometry=[],
                layout=node['layout'],instancePath=node['instancePath'],sourceOffset=node['offset']))
        # Original single-select frame attaches to Panel_item's centre at .55.
        frame = next(d for d in selected['drawItems'] if d['instancePath']=='Node/Panel_item/selected_frame')
        char_node = head_nodes['Node_char']
        frame_node = next(n for n in selected['nodes'] if n['instancePath']=='Node/Panel_item/selected_frame')
        item = copy.deepcopy(frame)
        item.update(id=f'hero-{hero_id}-selected',heroId=hero_id,selectedOnly=True,clipGeometry=[],
                    geometry=geometry(multiply(multiply(cell,char_node['worldMatrixBottomLeft']),
                                                frame_node['worldMatrixBottomLeft']),frame_node['size']))
        items.append(item)
    used_sprites = {i['spriteId'] for i in items if i['kind']=='sprite'}
    used_fonts = {i['fontId'] for i in items if i['kind']=='text'}
    sprites = {s['id']:s for l in layouts.values() for s in l['sprites']}
    sprites.update({s['id']:s for s in portraits})
    fonts = {s['id']:s for l in layouts.values() for s in l['fonts']}
    if not used_sprites.issubset(sprites) or not used_fonts.issubset(fonts):
        raise ValueError('Picker runtime resources unresolved')
    result = dict(schemaVersion=1,canvas=base['canvas'],entry=base['entry'],items=items,controls=controls,
        sprites=[sprites[k] for k in sorted(used_sprites)],fonts=[fonts[k] for k in sorted(used_fonts)],
        heroes=[dict(id=r['id'],name=r['fields']['NAME']) for r in heroes],
        evidence=dict(sourceTable=table,modules=sources,
            layouts={key:dict(path=str(OUT/key/'layout.json'),sha256=digest(OUT/key/'layout.json')) for key in layouts},
            hallAttachment=dict(nodeId=attach[0]['id'],matrix=attach[0]['worldMatrixBottomLeft'],
                                hallLayoutSha256=digest(ROOT/'analysis/unreal/hall-ui/layout.json'))),
        limitations=['Local initial-character preview subset, not original ownership state.',
            'Source list/normal buttons/portraits/single-select frame; timeline, inertia, rarity/level/counter badges remain unrestored.',
            'Character-change entry uses a clearly separate local header control; original clipped exchange menu remains unresolved.',
            'Original server protocol is not recovered by this layout conversion.'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'layout.json').write_text(packed(result),'utf8')
    print(json.dumps(dict(items=len(items),sprites=len(result['sprites']),heroes=[1,3],
                          layoutSha256=digest(OUT/'layout.json'))))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recover',action='store_true',help='Extract all required source layouts and pixels again')
    main(parser.parse_args().recover)
