"""Recover bounded, hash-verified first-encounter evidence without running APK code."""
from __future__ import annotations
from dataclasses import replace
import argparse
import hashlib
import json
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from extract_game_data import parse_data, plain, location, TaggedArguments
from inspect_battle_rules import read_module, export, instructions, literal_story_graph

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT/'analysis/assets/decoded/script/index.json'
OUT = ROOT/'analysis/first-encounter'


def inventory():
    return {row['index']: row for row in json.loads(INDEX.read_text('utf8'))}


def literal_table(index, selected=None):
    """Recognize literal rows; optionally skip one observed metadata import.

    Metadata is NOT imported/evaluated. Undefined names still fail the existing
    literal parser. A removed 10-byte import span is rebased in all locations.
    This is not a runtime table interpreter or a general bytecode evaluator.
    """
    row = inventory()[index]
    module = read_module(row)
    code = module['bytecode']
    skipped = None
    shift = 0
    enum_replacements = []
    # Exact known generator sequence: LOAD_CONST -1, LOAD_CONST ['*'],
    # IMPORT_NAME <table>_meta, IMPORT_STAR. Keep original pools unchanged.
    if (code[16:26] == bytes.fromhex('9900009902008601004a')
            and module['consts'][:3] == [-1, [b'taggeddict'], [b'*']]
            and len(module['names']) > 1 and module['names'][1].endswith(b'_meta')):
        skipped = {'module': module['names'][1].decode('utf8'),
                   'bytecode_start': 16, 'bytecode_end_exclusive': 26,
                   'semantics': 'Not imported. Only subsequent self-contained literal constructor arguments recovered.'}
        module_for_parser = dict(module, bytecode=code[:16]+code[26:])
        shift = 10
        # Only direct scalar assignments in the matching shipped metadata file.
        # Substitute literal LOAD_NAME operands for recognition; never execute an
        # import, function, lambda or table helper. Record original locations.
        target = module['names'][1].decode('utf8')+'.py'
        meta_rows = [r for r in inventory().values() if r['filename'].split('\\')[-1] == target]
        if len(meta_rows) != 1:
            raise ValueError('metadata module identity is ambiguous')
        meta = read_module(meta_rows[0])
        meta_ops = list(instructions(meta))
        if any(ins['opcode'] not in (0x99, 0x91, 0x87, 0x5a, 0x53) for ins in meta_ops):
            raise ValueError('metadata is not a straight-line literal declaration module')
        bindings = {}
        for before, after in zip(meta_ops, meta_ops[1:]):
            if (before['opcode'] == 0x99 and after['opcode'] == 0x91
                    and after['offset'] == before['end_exclusive']
                    and isinstance(before.get('operand'), (int, float, str, bool))):
                name = after['operand']
                if name in bindings:
                    raise ValueError('metadata scalar assigned twice')
                bindings[name] = {'value': before['operand'], 'metadata_index': meta_rows[0]['index'],
                    'metadata_decoded_sha256': meta_rows[0]['decoded_sha256'],
                    'constant_index': before['argument'], 'declaration_start': before['offset'],
                    'assignment_offset': after['offset']}
        rewritten = bytearray(module_for_parser['bytecode'])
        constants = list(module['consts'])
        for ins in instructions(module):
            if ins['opcode'] != 0x65 or ins['operand'] in ('taggeddict', 'True', 'False'):
                continue
            name = ins['operand']
            if name not in bindings:
                continue  # Existing parser will reject genuinely unresolved names.
            ix = len(constants)
            constants.append(bindings[name]['value'])
            rewritten[ins['offset']-shift:ins['end_exclusive']-shift] = b'\x99'+struct.pack('<H', ix)
            enum_replacements.append({'name': name, 'original_offset': ins['offset'],
                                      'temporary_constant_index': ix, **bindings[name]})
        module_for_parser.update(bytecode=bytes(rewritten), consts=constants)
    else:
        module_for_parser = module
    mapping, recognition = parse_data(module_for_parser)

    def locate(value):
        loc = location(replace(value, start=value.start+shift, end=value.end+shift,
            constants=tuple(ix for ix in value.constants if ix < len(module['consts']))), module)
        refs = [r for r in enum_replacements if loc['bytecode_start'] <= r['original_offset'] < loc['bytecode_end_exclusive']]
        if refs:
            loc['metadata_scalar_references'] = refs
        return loc

    rows = []
    for key, (value, at) in mapping.entries.items():
        if selected is not None and key not in selected:
            continue
        if not isinstance(value.value, TaggedArguments):
            raise ValueError('expected opaque taggeddict row constructor')
        fields = value.value.mapping
        rows.append({'id': plain(key), 'fields': plain(fields),
            'source': {**locate(value), 'map_assignment_offset': at+shift},
            'field_sources': {plain(k): {**locate(v), 'map_assignment_offset': pos+shift}
                              for k, (v, pos) in fields.entries.items()}})
    if selected is not None and {r['id'] for r in rows} != set(selected):
        raise ValueError('requested row absent')
    for key in ('data_assignment_offset', 'parsed_end'):
        recognition[key] += shift
    return {'source': {'apk_member': 'assets/script.npk', **row},
            'semantics': 'Static literal constructor arguments only; no runtime defaults, function calls or imported code evaluated.',
            'skipped_metadata_import': skipped, 'metadata_scalar_references': enum_replacements,
            'recognition': recognition,
            'total_source_rows': len(mapping.entries), 'rows': rows}


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


def extra_index(index, wanted):
    """Recognize the shipped reverse-index literal, keeping exact row order."""
    row = inventory()[index]
    module = read_module(row)
    ops = list(instructions(module))
    ends = [i for i, x in enumerate(ops) if x['opcode'] == 0x91 and x.get('operand') == 'extra_data']
    if len(ends) != 1:
        raise ValueError('expected one extra_data assignment')
    end = ends[0]
    start = max(i for i, x in enumerate(ops[:end]) if x['opcode'] == 0x65 and x.get('operand') == 'taggeddict')
    if ops[start+1]['opcode'] != 0x97:
        raise ValueError('extra_data must be literal map')
    stack, rows = [], {}
    for ins in ops[start+2:end-1]:
        op, arg = ins['opcode'], ins['argument']
        if op == 0x99:
            value = module['consts'][arg]
            if type(value) != int:
                raise ValueError('only integer reverse-index literals supported')
            stack.append(value)
        elif op == 0x87:
            if arg > len(stack):
                raise ValueError('reverse-index tuple underflow')
            values = stack[-arg:] if arg else []
            if any(type(x) != int for x in values):
                raise ValueError('reverse-index tuple must contain integers')
            if arg:
                del stack[-arg:]
            stack.append(tuple(values))
        elif op == 0x08:
            if len(stack) != 2:
                raise ValueError('reverse-index map stack mismatch')
            value, key = stack
            if type(key) != int or type(value) not in (int, tuple) or key in rows:
                raise ValueError('invalid reverse-index item')
            rows[key] = {'value': list(value) if isinstance(value, tuple) else value,
                         'map_assignment_offset': ins['offset']}
            stack = []
        else:
            raise ValueError('unsupported reverse-index instruction')
    if (stack or len(rows) != ops[start+1]['argument']
            or (ops[end-1]['opcode'], ops[end-1]['argument']) != (0x83, 1)):
        raise ValueError('reverse-index shape mismatch')
    return {'source': row, 'constructor_offset': ops[start]['offset'],
            'assignment_offset': ops[end]['offset'], 'total_keys': len(rows),
            'requested': {str(k): rows.get(k) for k in sorted(wanted)}}


def build(apk):
    from extract_texture_samples import APK_SHA256
    from neox_resource_paths import lookup, lookup_logical, resource_hash
    from inspect_neox_model import extract_npk_entry, parse_model
    from inspect_neox_animation import parse_library
    rows = inventory()
    h = hashlib.sha256()
    with apk.open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    if h.hexdigest() != APK_SHA256:
        raise ValueError('unexpected source APK identity')
    tables = {}
    def table(name, index, ids):
        data = literal_table(index, ids)
        save(name+'.json', data)
        tables[name] = data
        return {r['id']: r['fields'] for r in data['rows']}
    group = table('guide-groups', 9623, {1001, 1002})
    assert group[1001]['NAME'] == '序章-第一场战斗'
    assert group[1001]['CONDITION_PARAMS'] == [{'MazeId': 3997}]
    guides = literal_table(8791)
    guide_rows = {r['id']: r for r in guides['rows']}
    selected = {k for k, r in guide_rows.items() if r['fields'].get('GROUP') == 1001}
    pending = list(selected)
    while pending:
        following = guide_rows[pending.pop()]['fields'].get('NEXT_GUIDE', -1)
        if following == -1 or following in selected:
            continue
        if following not in guide_rows:
            raise ValueError('tutorial next-step reference is absent')
        selected.add(following)
        pending.append(following)
    guides['rows'] = [r for r in guides['rows'] if r['id'] in selected]
    guides['selection'] = 'Group 1001 plus explicit NEXT_GUIDE closure; step1855 belongs to shared group1000.'
    save('guide-steps.json', guides)
    challenge = table('challenges', 5921, {3997, 3998})
    maze = table('mazes', 1303, {3997, 3998})
    battle = table('battles', 4664, {5000})
    monster = table('monsters', 2363, {991})
    course = table('new-player-course.table', 4105, {1})
    assert challenge[3998]['Unlock'] == [3997]
    assert challenge[3997]['MazeIDList'] == [3997] and maze[3997]['LoadingBattleID'] == 5000
    assert battle[5000]['MonsterInfo'] == [{'MonsterID': 991, 'SpawnPointIdx': 0}]
    assert course[1]['FirstBattleID'] == 5000 and course[1]['BattleChar'] == [1]
    cards = table('player-cards', 3391, {c[0] for c in course[1]['CardPile']})
    card_skills = {c['SKILL_ID'] for c in cards.values()}
    skills = table('skills', 9333, card_skills | {990, 991, 992})
    player = table('player-character', 8995, {1})[1]
    table('player-base-formulas', 4879, {1})
    table('player-level-100', 8577, {100})
    table('player-occupation-ratios', 1617, {player['CHARTYPE']})
    entity = table('enemy-entity', 1955, {monster[991]['ENTITY_ID']})[6605]
    lod = table('enemy-lod', 1268, {entity['LOD_ID']})[6605]
    lod_rows = table('lod-index', 6328, set(lod['LOD_MODEL_LIST']))
    table('monster-level-reference', 6708, {1})
    wanted = set(skills)
    reverse = {}
    for name, index in [('skill-states', 8903), ('skill-timelines', 6655)]:
        idx = extra_index(index, wanted)
        if any(v is None for v in idx['requested'].values()):
            raise ValueError('missing requested skill reverse index')
        ids = {i for item in idx['requested'].values() for i in item['value']}
        data = table(name, index, ids)
        for key, item in idx['requested'].items():
            if any(data[i]['OwnerSkill'] != int(key) for i in item['value']):
                raise ValueError('reverse index disagrees with OwnerSkill')
        save(name+'-index.json', idx)
        reverse[name] = idx['requested']
    save('course-index.json', extra_index(4105, {5000}))
    graphs = []
    graph_names = {r['fields']['STORYLINE_NAME'] for r in tables['skill-states']['rows']}
    for row in rows.values():
        filename = row['filename'].replace('\\', '/')
        if '/card_action/server/' in filename and filename.rsplit('/', 1)[-1][:-3] in graph_names:
            graph = {'source': row, **literal_story_graph(read_module(row))}
            save(f'graph-{row["index"]}.json', graph)
            graphs.append({'index': row['index'], 'filename': filename, 'json_sha256': graph['raw_json_sha256']})
    code_scopes = {5947: [], 6525: ['dungeonCurMazeId', 'battleRoundCount'],
        5258: ['battleCompleteCountExpire'], 3510: ['getForceProp', 'getMonsterHP', 'getMonsterATK'],
        5304: ['getMonsterMouldData', 'resetMonsterMouldData'],
        4057: ['getStaticSingleThread', 'max_row_per_file', 'sub_table_index'],
        2128: [], 2949: [], 6221: ['CharBasicProps', 'GuideCondition', 'GuideExpireCondition', 'CharPos'],
        2165: ['getCharLevelBasicPropByLvAndRarity', 'getSingleCharBasicProp', 'getCharMaxHP']}
    for index, names in code_scopes.items():
        save(f'code-{index}.json', export(rows[index], names))
    constants = export(rows[6221], ['<module>'])
    constants['code_objects'][0]['instructions'] = [x for x in constants['code_objects'][0]['instructions'] if 0x3ee <= x['offset'] <= 0x460]
    save('first-enter-constant.json', constants)
    catalogue_path = ROOT/'analysis/resource-mapping/npk-indices.json'
    catalogue = json.loads(catalogue_path.read_text('utf8'))
    resources = []
    def extract(logical, output, root_mount=True):
        matches = lookup_logical(catalogue, logical) if root_mount else lookup(catalogue, logical)
        if not root_mount:
            matches = [r for r in matches if r['member'] == 'assets/assets.npk']
        if len(matches) != 1 or matches[0]['original_size'] > 4*1024*1024:
            raise ValueError('resource ambiguous, absent or exceeds extraction budget')
        row = matches[0]
        provenance = extract_npk_entry(apk, row['member'], row['index'], OUT/output)
        expected_hash = resource_hash(logical.split('/', 1)[1] if root_mount else logical)
        if int(provenance['name_hash'], 16) != expected_hash:
            raise ValueError('actual resource index does not match logical hash')
        provenance.update(logical_path=logical, apk_sha256=APK_SHA256, output=output)
        save(output+'.provenance.json', provenance)
        resources.append(provenance)
        return (OUT/output).read_bytes()
    with zipfile.ZipFile(apk) as z:
        asset_list = z.read('assets/assets.list')
    bt_path = 'bt/'+monster[991]['BT_PATH']
    if bt_path not in asset_list.decode('utf8').splitlines():
        raise ValueError('BT path not present in shipped assets.list')
    bt = ET.fromstring(extract(bt_path, 'newbie_cube.xml', False))
    bt_nodes = [e.attrib for e in bt.iter('Node')]
    assert {int(n['skillID']) for n in bt_nodes if 'skillID' in n} == {990, 991, 992}
    gim_path = next(r['MODEL_PATH'] for r in lod_rows.values() if r['LEVEL'] == 0)
    gim = ET.fromstring(extract(gim_path, 'enemy-model.gim'))
    mesh = parse_model(extract(gim.attrib['Mesh'], 'enemy-model.mesh'))
    mesh_summary = {k: v for k, v in mesh.items() if k not in
        {'positions', 'normals', 'indices', 'vertex_auxiliary_unknown', 'submeshes', 'bones', 'joints', 'weights', 'used_bones'}}
    mesh_summary.update(bone_count=len(mesh['bones']))
    save('enemy-model-structure.json', mesh_summary)
    animation = parse_library(extract(gim.find('GisFiles/FileName').get('value'), 'enemy-model.gisacl'))
    save('enemy-animation-library.json', animation)
    save('resources.json', {'apk_sha256': APK_SHA256,
        'catalogue_sha256': hashlib.sha256(catalogue_path.read_bytes()).hexdigest(),
        'assets_list_sha256': hashlib.sha256(asset_list).hexdigest(), 'entries': resources})
    report = {'evidence_kind': 'Static shipped data and partial bytecode control flow; no game code or UI executed.',
        'apk_sha256': APK_SHA256, 'entry': {'guide_group': 1001, 'activity': 2, 'challenge': 3997,
            'maze': 3997, 'battle': 5000, 'source_entry_function': '5947:[4] startNewPlayerCourse',
            'historical_trigger_limit': 'isNewPlayerCourse [3] is a False-returning stub; original runtime trigger not verified.'},
        'player': {'course_row': 1, **course[1], 'unique_card_ids': sorted(cards)},
        'player_attribute_next_anchor': {'module_index': 2165,
            'function': 'iCommonAthleteCharBasicProp.getCharLevelBasicPropByLvAndRarity',
            'constant_path': [6, 7], 'tables': ['character_basic_info.CHARTYPE',
                'character_type_cultivate_ratio_table', 'role_level_rank_table', 'character_quality_table', 'char_basic_prop'],
            'known_level_100_totalCultivateValue': 704.0,
            'unresolved': 'Tutorial rarity and composed passive/equipment/relic modifiers; formulas retained as strings, never eval executed.'},
        'enemy': {'monster_id': 991, 'spawn_point_index': 0, 'entity_id': 6605, 'lod_id': 6605,
            'forced_base_hp': 4600, 'forced_base_atk': 2.0, 'basis': 'combatUtils getForceProp -> early return in getMonsterHP/getMonsterATK; not final combat state'},
        'skill_links': [{'skill_id': k, 'states': reverse['skill-states'][str(k)]['value'],
                         'timelines': reverse['skill-timelines'][str(k)]['value']} for k in sorted(wanted)],
        'bt_nodes': bt_nodes, 'story_graphs': graphs,
        'model': {'logical_path': gim_path, 'vertices': mesh['vertex_count'], 'triangles': mesh['triangle_count'],
                  'bones': len(mesh['bones']), 'clip_names': [c['name'] for c in animation['clips']]},
        'unknowns': ['Original server trigger/initialization and card-pile consumption direction are not observed.',
            'No energy override in the recovered course row; global energy constants alone do not prove initialization.',
            'Player level is explicitly 100; complete base/growth/rarity/equipment/relic attribute composition is not recovered here.',
            'BT XML and skill graphs are data, not verified server AI execution or end-to-end target resolution.',
            'Preserve card/skill-state numeric disagreements; final parameter injection is not established by these tables.',
            'Challenge HasLoot=False while battle has DropPersistentItems; do not implement rewards from that field alone.',
            'Model geometry and animation library parsed; material rendering/clip playback is not exported or verified.']}
    save('encounter.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=int)
    parser.add_argument('--ids', nargs='*', type=int)
    parser.add_argument('--apk', type=Path, default=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk')
    args = parser.parse_args()
    if args.table is None:
        result = build(args.apk)
        print(json.dumps({'entry': result['entry'], 'model': result['model'], 'skill_links': result['skill_links']}, ensure_ascii=False))
        raise SystemExit(0)
    result = literal_table(args.table, set(args.ids) if args.ids is not None else None)
    save(f'{args.table}.table.json', result)
    print(json.dumps({'index': args.table, 'total': result['total_source_rows'],
                     'rows': [{'id': r['id'], 'fields': r['fields']} for r in result['rows']]}, ensure_ascii=False))
