"""Trace the APK's prologue boss data without executing shipped code.

Reuses the public literal-table, bytecode and NPK extraction pipeline. This is
ordinary hash-verified static evidence, not a new REA runtime observation.
"""
from pathlib import Path
import hashlib
import json
import zipfile
import zlib
import xml.etree.ElementTree as ET

from trace_first_encounter import inventory, literal_table, extra_index
from inspect_battle_rules import export, read_module, literal_story_graph
from neox_resource_paths import lookup, resource_hash
from inspect_neox_model import extract_npk_entry
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/prologue-boss'
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')


def build():
    with APK.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    OUT.mkdir(parents=True, exist_ok=True)
    tables = {}

    def table(name, index, ids=None):
        value = literal_table(index, ids)
        save(name + '.json', value)
        tables[name] = value
        return {r['id']: r['fields'] for r in value['rows']}

    challenge = table('challenge', 5921, {3998})[3998]
    maze = table('maze', 1303, {3998})[3998]
    battle = table('battle', 5766, {1703})[1703]
    course = table('course', 4105, {2})[2]
    assert challenge['Unlock'] == [3997] and challenge['MazeIDList'] == [3998]
    assert maze['LoadingBattleID'] == course['FirstBattleID'] == 1703
    assert course['BattleChar'] == [1, 3] and course['CharLevel'] == [100, 100]
    assert len(course['CardPile']) == 14
    assert battle['MonsterInfo'] == [{'MonsterID': 2013, 'SpawnPointIdx': 0}]
    monster = table('monster', 2363, {2013})[2013]
    characters = table('characters', 8995, set(course['BattleChar']))
    cards = table('cards', 3391, {c[0] for c in course['CardPile']})
    groups = table('guide-group', 9623, {1002})
    guides = literal_table(8791)
    by_id = {r['id']: r for r in guides['rows']}
    selected = {r['id'] for r in guides['rows'] if r['fields'].get('GROUP') == 1002}
    pending = list(selected)
    while pending:
        following = by_id[pending.pop()]['fields'].get('NEXT_GUIDE', -1)
        if following == -1 or following in selected:
            continue
        if following not in by_id:
            raise ValueError('Missing linked guide')
        selected.add(following)
        pending.append(following)
    guides['rows'] = [r for r in guides['rows'] if r['id'] in selected]
    guides['selection'] = 'Group1002 plus explicit NEXT_GUIDE closure; not runtime execution order.'
    save('guides.json', guides)
    catalogue_path = ROOT / 'analysis/resource-mapping/npk-indices.json'
    catalogue = json.loads(catalogue_path.read_text('utf8'))
    bt_path = 'bt/' + monster['BT_PATH']
    bt_file = OUT / 'boss.xml'
    # BTs are in assets/assets.npk under their raw bt/... hash. They do not
    # belong to the res/<mount>.npk namespace used by model logical paths.
    with zipfile.ZipFile(APK) as archive:
        asset_list = archive.read('assets/assets.list')
        # Full member read verifies ZIP CRC; record it explicitly as well.
        assets_pack = archive.read('assets/assets.npk')
        zip_crc = archive.getinfo('assets/assets.npk').CRC
        if zlib.crc32(assets_pack) & 0xffffffff != zip_crc:
            raise ValueError('assets.npk ZIP CRC mismatch')
    if bt_path not in asset_list.decode('utf8').splitlines():
        raise ValueError('Boss BT not listed by shipped assets.list')
    matches = [row for row in lookup(catalogue, bt_path)
               if row['member'] == 'assets/assets.npk']
    if len(matches) != 1 or matches[0]['original_size'] > 4 * 1024 * 1024:
        raise ValueError('Boss BT missing, ambiguous or over extraction budget')
    match = matches[0]
    bt_source = extract_npk_entry(APK, match['member'], match['index'], bt_file)
    fields = ['name_hash', 'offset', 'stored_size', 'original_size', 'digest1',
              'digest2', 'compression', 'encryption']
    if tuple(bt_source['table_row']) != tuple(match[key] for key in fields):
        raise ValueError('Actual APK NPK row disagrees with cached catalogue')
    if int(bt_source['name_hash'], 16) != resource_hash(bt_path):
        raise ValueError('Actual boss BT name hash disagrees with listed path')
    bt_source.update(logical_path=bt_path, apk_sha256=APK_SHA256,
                     catalogue_sha256=hashlib.sha256(catalogue_path.read_bytes()).hexdigest(),
                     assets_list_sha256=hashlib.sha256(asset_list).hexdigest(),
                     assets_npk_sha256=hashlib.sha256(assets_pack).hexdigest(),
                     integrity={'zipMemberCrc32': f'{zip_crc:08x}', 'zipMemberCrc32Verified': True,
                                'npkRowMatchesCatalogue': True, 'logicalNameHashVerified': True,
                                'zlibStreamAndDecodedSizeVerified': True,
                                'npkDigestWordSemantics': 'preserved, not interpreted as a verified checksum'})
    save('boss.xml.provenance.json', bt_source)
    root = ET.fromstring(bt_file.read_bytes())
    bt_nodes = []
    def visit(node, path=()):
        bt_nodes.append({'element_path': list(path), 'tag': node.tag,
                         'attributes': node.attrib, 'text': node.text.strip() if node.text else ''})
        for index, child in enumerate(node):
            visit(child, (*path, index))
    visit(root)
    save('behavior-tree.json', {'source': bt_source, 'nodes': bt_nodes})
    enemy_skill_ids = {int(node.attrib['skillID']) for node in root.iter('Node')
                       if 'skillID' in node.attrib}
    if enemy_skill_ids != {74501, 74502, 74503}:
        raise ValueError('Expected boss skill set changed; manual review required')
    enemy_skills = table('enemy-skills', 9333, enemy_skill_ids)
    player_skill_ids = {skill for card in cards.values() for skill in card['SKILL_IDS']}
    player_skills = table('player-skills', 9333, player_skill_ids)
    all_skills = enemy_skill_ids | player_skill_ids
    reverse = {}
    state_rows = {}
    for name, index in [('skill-states', 8903), ('skill-timelines', 6655)]:
        reverse_index = extra_index(index, all_skills)
        missing = [int(key) for key, value in reverse_index['requested'].items() if value is None]
        if any(skill in missing for skill in enemy_skill_ids):
            raise ValueError('Boss skill missing state/timeline reverse index')
        selected_ids = {ident for value in reverse_index['requested'].values()
                        if value is not None for ident in value['value']}
        data = table(name, index, selected_ids)
        for key, value in reverse_index['requested'].items():
            if value is not None and any(data[ident]['OwnerSkill'] != int(key) for ident in value['value']):
                raise ValueError('Skill reverse index and OwnerSkill disagree')
        reverse_index['missingSkillIds'] = missing
        save(name + '-index.json', reverse_index)
        reverse[name] = reverse_index['requested']
        if name == 'skill-states':
            state_rows = data
    graph_names = {row['STORYLINE_NAME'] for row in state_rows.values()}
    graphs = []
    for row in inventory().values():
        filename = row['filename'].replace('\\', '/')
        if ('/card_action/server/' in filename or '/card_action/client/' in filename):
            name = filename.rsplit('/', 1)[-1][:-3]
            if name not in graph_names:
                continue
            graph = {'source': row, **literal_story_graph(read_module(row))}
            save(f'graph-{row["index"]}.json', graph)
            graphs.append({'index': row['index'], 'filename': filename,
                           'storylineName': name, 'jsonSha256': graph['raw_json_sha256']})
    buff_ids = {row['STORYLINE_PARAM']['BUFF_ID'] for row in state_rows.values()
                if 'BUFF_ID' in row.get('STORYLINE_PARAM', {})}
    buffs = table('referenced-buffs', 391, buff_ids)
    save('skill-graph-index.json', {'graphs': graphs,
        'requestedNames': sorted(graph_names),
        'missingServerNames': sorted(graph_names - {item['storylineName'] for item in graphs
                                    if '/server/' in item['filename']}),
        'missingClientNames': sorted(graph_names - {item['storylineName'] for item in graphs
                                    if '/client/' in item['filename']})})
    save('course-code.json', export(inventory()[5947], []))
    report = {'evidenceKind': 'hash-verified-static-extraction; no APK/server execution', 'apkSha256': APK_SHA256,
        'entry': {'challenge': 3998, 'maze': 3998, 'battle': 1703, 'course': 2, 'guideGroup': 1002},
        'team': [{'id': ident, 'name': characters[ident]['NAME'], 'level': level}
                 for ident, level in zip(course['BattleChar'], course['CharLevel'], strict=True)],
        'deck': [{'position': i, 'cardId': card, 'ownerCharacterId': owner,
                  'name': cards[card]['NAME'], 'skillId': cards[card]['SKILL_ID']}
                 for i, (card, owner) in enumerate(course['CardPile'])],
        'enemy': {'monsterId': 2013, 'name': monster['NAME'], 'entityId': monster['ENTITY_ID'],
                  'forcedBaseHp': monster['enforce_maxHp'], 'forcedBaseAttack': monster['enforce_PropAtk'],
                  'behaviorTree': bt_path},
        'specialSkill': {k: course[k] for k in ['DisableSpecialSkill', 'EnableSpecialSkillRound']},
        'skills': {'enemy': [{'id': ident, 'name': enemy_skills[ident]['NAME'],
                    'showName': enemy_skills[ident]['SHOW_NAME'],
                    'stateIds': reverse['skill-states'][str(ident)]['value'],
                    'timelineIds': reverse['skill-timelines'][str(ident)]['value']}
                   for ident in sorted(enemy_skill_ids)],
                   'playerSkillIds': sorted(player_skill_ids), 'graphCount': len(graphs),
                   'referencedBuffIds': sorted(buffs)},
        'btSelectionConfiguration': {'phase': 'PlayerRoundStart',
            'orderedBranches': [{'round': 1, 'skillId': 74503}, {'round': 2, 'skillId': 74501},
                                {'roundModulo': {'divisor': 2, 'result': 1}, 'skillId': 74502},
                                {'roundModulo': {'divisor': 2, 'result': 0}, 'skillId': 74503}],
            'selfRoundActions': ['SelfRoundStart', 'UseIntentionSkill', 'RoundEnd'],
            'scope': 'XML order and action references; BT node implementation and runtime dispatch not executed.'},
        'unlock': challenge['Unlock'], 'hasLoot': challenge['HasLoot'],
        'sceneReferences': {'battle': battle['BattleScene'], 'loadingOverrides': maze['LoadingBattleScene']},
        'guideIds': sorted(selected),
        'limitations': ['Two-player combat is not implemented by the current single-player battle-session.',
                       'BT conditions/actions and guide hooks are static data, not verified server execution.',
                       'Original team positioning, target selection and full player attributes need consumer tracing.',
                       'Special-skill consumers and synchronized round boundary are documented in docs/prologue-course.md; original runtime timing remains unverified.',
                       'Graph/state/timeline extraction preserves configured formulas and targets; final damage and buff execution still require consumer recovery.',
                       'Do not infer unlock processing or grant rewards from these static fields.']}
    save('report.json', report)
    return report


if __name__ == '__main__':
    value = build()
    print(json.dumps({'entry': value['entry'], 'team': value['team'], 'cards': len(value['deck']),
                      'enemy': value['enemy'], 'guides': value['guideIds']}, ensure_ascii=False))
