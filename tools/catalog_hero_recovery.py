"""Catalogue all UseRole=1 heroes from shipped tables and bounded metadata reads.

Never executes APK scripts, imports into UE, extracts mesh/texture payloads or
changes game saves. Counts distinguish configured paths, pack-index candidates,
parsed metadata, retained UE readback and current asset files.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import zlib

from extract_texture_samples import APK_SHA256
from inspect_battle_rules import export, read_module, walk_codes, instructions
from inspect_neox_animation import clip_path, parse_library
from neox_resource_paths import read_catalogue, resource_hash
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'clients/unreal5 5.8'
SOURCE_PIN = '1998f8eb7ff9598936b27e61197f96b364a305c01f0f1ca6d1481aba716b6ffb'
TABLE_IDS = [8995, 961, 1955, 1268, 6328, 9416, 2302, 5888, 3391, 9561, 8498, 6655, 9650]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def reference(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, (tuple, list)):
        for v in value:
            yield from strings(v)


def anchor(table, row, field):
    return {'moduleIndex': table['source']['index'], 'rowId': row['id'], 'field': field,
            'location': row.get('field_sources', {}).get(field)}


class Resources:
    """Read bounded GIM/library metadata only, retaining pack identity and digests."""
    def __init__(self, apk, catalogue, budget):
        self.archive = zipfile.ZipFile(apk)
        self.streams = {}
        self.entries = defaultdict(list)
        for pack in catalogue:
            for entry in pack['entries']:
                self.entries[(pack['member'], entry['name_hash'])].append({'member': pack['member'], **entry})
        self.budget = budget
        self.read_bytes = 0
        self.blobs = {}
        self.records = {}
        self.errors = []

    def lookup(self, path):
        normalized = path.replace('\\', '/')
        if '/' not in normalized:
            return []
        mount, relative = normalized.split('/', 1)
        return self.entries.get((f'assets/res/{mount}.npk', resource_hash(relative)), [])

    def record(self, path):
        path = path.replace('\\', '/')
        if path not in self.records:
            matches = self.lookup(path)
            self.records[path] = {'path': path, 'status': 'indexed-unique' if len(matches) == 1 else 'ambiguous' if matches else 'not-indexed',
                                  'matches': matches, 'payloadSha256': None, 'metadataParsed': False}
        return self.records[path]

    def metadata(self, path):
        path = path.replace('\\', '/')
        if path in self.blobs:
            return self.blobs[path]
        record = self.record(path)
        if len(record['matches']) != 1:
            return None
        row = record['matches'][0]
        if row['encryption'] or row['compression'] not in (0, 1) or row['original_size'] > 1024 * 1024:
            record['metadataIssue'] = 'unsupported or exceeds 1 MiB metadata limit'
            return None
        if self.read_bytes + row['original_size'] > self.budget:
            record['metadataIssue'] = 'total metadata budget exhausted'
            return None
        stream = self.streams.setdefault(row['member'], None)
        if stream is None:
            stream = self.streams[row['member']] = self.archive.open(row['member'])
        stream.seek(row['offset'])
        raw = stream.read(row['stored_size'])
        if len(raw) != row['stored_size']:
            raise ValueError('Truncated pack entry')
        if row['compression']:
            decoder = zlib.decompressobj()
            blob = decoder.decompress(raw, row['original_size'] + 1)
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError('Compressed metadata framing mismatch')
        else:
            blob = raw
        if len(blob) != row['original_size']:
            raise ValueError('Metadata decoded length mismatch')
        self.read_bytes += len(blob)
        self.blobs[path] = blob
        record['payloadSha256'] = hashlib.sha256(blob).hexdigest()
        return blob

    def libraries(self, path):
        record = self.record(path)
        if 'animationLibraries' in record:
            return record['animationLibraries']
        blob = self.metadata(path)
        if blob is None:
            record['animationLibraries'] = None
            return None
        try:
            if b'<!DOCTYPE' in blob or b'<!ENTITY' in blob:
                raise ValueError('XML entities are unsupported')
            tree = ET.fromstring(blob)
            if tree.tag != 'NeoX':
                raise ValueError('Unexpected GIM root')
            libraries = [node.attrib['value'].replace('\\', '/') for node in tree.findall('GisFiles/*')]
            record.update(metadataParsed=True, animationLibraries=libraries)
            return libraries
        except (ET.ParseError, KeyError, ValueError) as error:
            record.update(animationLibraries=None, metadataIssue=str(error))
            return None

    def library(self, path):
        record = self.record(path)
        if 'clipNames' in record:
            return record['clipNames']
        blob = self.metadata(path)
        if blob is None:
            record['clipNames'] = None
            return None
        try:
            parsed = parse_library(blob, allow_empty_roots=True)
            record.update(metadataParsed=True, boneCount=parsed['bone_count'],
                          clipNames=[c['name'] for c in parsed['clips']])
            return record['clipNames']
        except (ValueError, AssertionError, KeyError) as error:
            record.update(clipNames=None, metadataIssue=str(error))
            return None

    def close(self):
        for stream in self.streams.values():
            if stream:
                stream.close()
        self.archive.close()


def ue_evidence(hero_id):
    reports = []
    configured = {1: [('analysis/unreal/plan/import-readback-elsa.json', 'elsa')],
                  33: [('analysis/unreal/plan/import-readback.json', 'shiranui'),
                       ('analysis/unreal/plan/import-readback.json', 'shiranui_weapon')]}
    objects = []
    for relative, identity in configured.get(hero_id, []):
        path = ROOT / relative
        if not path.exists():
            continue
        doc = json.loads(path.read_text('utf8'))
        if not doc.get('passed') or doc.get('failures') or not doc.get('validation', {}).get('engine_asset_readback_executed'):
            continue
        for asset in doc.get('assets', []):
            if asset.get('id') != identity:
                continue
            reports.append({**reference(path), 'engineVersion': doc.get('engine_version')})
            for obj in asset.get('objects', []):
                if obj.get('class_name') not in ('SkeletalMesh', 'AnimSequence'):
                    continue
                asset_path = obj['path'].split('.')[0]
                if not asset_path.startswith('/Game/Recovered/'):
                    raise ValueError('Unexpected retained asset ownership')
                disk = PROJECT / 'Content' / (asset_path.removeprefix('/Game/') + '.uasset')
                objects.append({'class': obj['class_name'], 'asset': obj['path'], 'sourceAnimations': obj.get('source_animation_names'),
                                'currentFilePresent': disk.is_file(), 'currentFile': reference(disk) if disk.is_file() else None,
                                'currentNativeReadbackReexecuted': False})
    if hero_id == 1:
        path = ROOT / 'analysis/unreal/battle-inputs/native-readback.json'
        if path.is_file():
            doc = json.loads(path.read_text('utf8'))
            if doc.get('passed') and doc.get('read_only'):
                reports.append({**reference(path), 'engineVersion': doc.get('engine_version')})
                player = doc.get('combatants', {}).get('player', {})
                for kind, asset, animations in [('SkeletalMesh', player.get('mesh'), None)] + [
                        ('AnimSequence', anim['path'], [name]) for name, anim in player.get('animation_refs', {}).items()]:
                    if not asset or not asset.startswith('/Game/Recovered/Battle/Elsa/'):
                        continue
                    disk = PROJECT / 'Content' / (asset.split('.')[0].removeprefix('/Game/') + '.uasset')
                    objects.append({'class': kind, 'asset': asset, 'sourceAnimations': animations,
                                    'currentFilePresent': disk.is_file(), 'currentFile': reference(disk) if disk.is_file() else None,
                                    'currentNativeReadbackReexecuted': False})
    converted = []
    for relative in {1: ['analysis/elsa-hall/export-report.json'], 2: ['analysis/characters/lynn/export/export-report.json'],
                     33: ['analysis/characters/shiranui/export/export-report.json']} .get(hero_id, []):
        path = ROOT / relative
        if not path.is_file():
            continue
        doc = json.loads(path.read_text('utf8'))
        output = Path(doc['output'])
        if output.is_file() and sha(output) == doc.get('sha256'):
            converted.append({'report': reference(path), 'output': reference(output), 'sourceAnimationNames':
                              [a.get('name') for a in doc.get('animations', [])], 'originalMaterialFidelityVerified': False})
    return {'status': 'retained-native-readback-and-current-files' if objects else 'no-mapped-native-readback',
            'reports': reports, 'objects': objects, 'convertedColourReferenceModels': converted,
            'fullHeroRecovered': False, 'originalLightingVerified': None, 'allVfxVerified': None,
            'allUltimatePresentationVerified': None, 'fourPlatformPackagesVerified': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'analysis/hero-recovery/catalog.json')
    parser.add_argument('--metadata-budget-mib', type=int, default=32, choices=range(1, 65))
    args = parser.parse_args()
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if sha(apk) != APK_SHA256:
        raise ValueError('Original APK identity changed')
    tables = {idx: literal_table(idx) for idx in TABLE_IDS}
    by_id = {idx: {r['id']: r for r in t['rows']} for idx, t in tables.items()}
    heroes = [r for r in tables[8995]['rows'] if r['fields'].get('UseRole') == 1]
    if tables[8995]['source']['decoded_sha256'] != SOURCE_PIN or len(heroes) != 35 or tables[8995]['total_source_rows'] != 228:
        raise ValueError('Reviewed hero selection changed')
    # Source consumer explicitly assigns specialSkillID = charID before table lookup.
    script_rows = json.loads((ROOT / 'analysis/assets/decoded/script/index.json').read_text('utf8'))
    consumer = export(next(r for r in script_rows if r['index'] == 6222), ('getSpecialSkillDes',))
    code = consumer['code_objects'][0]
    if code['constant_path'] != [45] or not any(i.get('operand') == 'speciall_skill_table' and i['offset'] == 30 for i in code['instructions']):
        raise ValueError('Hero/special skill table association consumer changed')
    catalogue = read_catalogue(apk)
    resources = Resources(apk, catalogue, args.metadata_budget_mib * 1024 * 1024)
    members = {i.filename: i for i in resources.archive.infolist()}
    result = []
    try:
        for hero in sorted(heroes, key=lambda r: r['id']):
            hid, fields = hero['id'], hero['fields']
            dresses = [r for r in tables[961]['rows'] if r['fields'].get('CharID') == hid]
            entities = defaultdict(set)
            for key in ['ENTITY_ID', 'CULTIVATE_ENTITY_ID', 'HOME_ENTITY_ID']:
                eid = fields.get(key)
                if type(eid) is int and (key != 'HOME_ENTITY_ID' or eid != 0 or fields.get('ENTITY_ID') == 0):
                    entities[eid].add('character.' + key)
            for dress in dresses:
                for key in ['EntityID', 'CultivateEntityID', 'PVPEntityID']:
                    if type(dress['fields'].get(key)) is int:
                        entities[dress['fields'][key]].add(f'dress.{dress["id"]}.{key}')
            entity_rows, model_paths, library_paths, decorations, effects = [], set(), set(), {}, set()
            for eid, bindings in sorted(entities.items()):
                entity = by_id[1955].get(eid)
                if entity is None:
                    entity_rows.append({'entityId': eid, 'bindings': sorted(bindings), 'sourceRowFound': False})
                    continue
                ef = entity['fields']
                model_group = by_id[1268].get(ef.get('LOD_ID'))
                models = []
                if model_group:
                    for level_id in model_group['fields'].get('LOD_MODEL_LIST', []):
                        level = by_id[6328].get(level_id)
                        if not level:
                            continue
                        logical = level['fields'].get('MODEL_PATH')
                        if logical:
                            model_paths.add(logical.replace('\\', '/'))
                            libraries = resources.libraries(logical) if logical.lower().endswith('.gim') else None
                            if libraries:
                                library_paths.update(libraries)
                            models.append({'lodRowId': level_id, 'level': level['fields'].get('LEVEL'), 'path': logical,
                                           'source': anchor(tables[6328], level, 'MODEL_PATH'), 'animationLibraries': libraries})
                animation_bindings = {k: v for k, v in ef.items() if k.startswith('ANIM_STATES_') and isinstance(v, str) and v}
                library_names = {p: resources.library(p) for m in models for p in m['animationLibraries'] or []}
                animations = []
                for category, predicate in [('hall', lambda key: key.startswith('ANIM_STATES_HOME_') or key == 'ANIM_STATES_CHOOSE_STAND_IDLE'),
                                             ('battle', lambda key: not key.startswith('ANIM_STATES_HOME_') and key != 'ANIM_STATES_CHOOSE_STAND_IDLE')]:
                    for key, name in animation_bindings.items():
                        if not predicate(key):
                            continue
                        candidates = []
                        for library, names in library_names.items():
                            try:
                                logical = clip_path(library, name).replace('\\', '/')
                                resources.record(logical)
                                candidates.append({'library': library, 'path': logical, 'declaredInParsedLibrary': name in names if names is not None else None})
                            except ValueError:
                                pass
                        animations.append({'category': category, 'state': key, 'name': name,
                                           'source': anchor(tables[1955], entity, key), 'clipCandidates': candidates})
                for key, values in ef.items():
                    if key.endswith('DRESS_UP_LIST') and isinstance(values, list):
                        for decoration_id in values:
                            decoration = by_id[9416].get(decoration_id)
                            if decoration and decoration['fields'].get('MODEL'):
                                logical = decoration['fields']['MODEL'].replace('\\', '/')
                                decorations[decoration_id] = {'id': decoration_id, 'path': logical,
                                                             'bindings': [eid, key], 'source': anchor(tables[9416], decoration, 'MODEL')}
                                resources.record(logical)
                    effects.update(v.replace('\\', '/') for v in strings(values) if v.lower().endswith('.sfx'))
                entity_rows.append({'entityId': eid, 'bindings': sorted(bindings), 'sourceRowFound': True, 'lodGroupId': ef.get('LOD_ID'),
                                    'models': models, 'configuredAnimations': animations})
            special = by_id[2302].get(hid)
            card_ids = set()
            for build in tables[9561]['rows']:
                if build['fields'].get('Character') == hid:
                    item = by_id[8498].get(build['fields'].get('CardItemID'))
                    if item and type(item['fields'].get('CARD_ID')) is int:
                        card_ids.add(item['fields']['CARD_ID'])
            if special:
                card_ids.add(special['fields']['SpecialSkillCardID'])
            skill_ids, video_rows = set(), []
            for cid in sorted(card_ids):
                card = by_id[3391].get(cid)
                if card:
                    for key, value in card['fields'].items():
                        if key in ['SKILL_ID','SKILL_IDS','COUNTER_SKILL_ID','CRITICAL_SKILL_ID','ROUNDEND_SKILL_ID']:
                            skill_ids.update(v for v in (value if isinstance(value, list) else [value]) if type(v) is int and v > 0)
            ultimate_card_ids = set()
            if special:
                cid = special['fields']['SpecialSkillCardID']
                while cid and cid not in ultimate_card_ids:
                    ultimate_card_ids.add(cid)
                    card = by_id[3391].get(cid)
                    cid = card['fields'].get('NEXT_LEVEL_ID') if card else None
            for cid in sorted(ultimate_card_ids):
                video = by_id[5888].get(cid)
                if video:
                    logical = video['fields']['VideoPath']
                    member = 'assets/res/video/' + logical
                    video_rows.append({'cardId': cid, 'path': logical, 'zipMember': member, 'zipMemberPresent': member in members,
                                       'bytes': members[member].file_size if member in members else None,
                                       'source': anchor(tables[5888], video, 'VideoPath'), 'playbackVerified': None})
            timeline_ids = []
            for timeline in tables[6655]['rows']:
                if timeline['fields'].get('OwnerSkill') in skill_ids:
                    timeline_ids.append(timeline['id'])
                    effects.update(v.replace('\\', '/') for v in strings(timeline['fields'].get('DATA')) if v.lower().endswith('.sfx'))
            for effect in sorted(effects):
                resources.record(effect)
            model_records = [resources.record(p) for p in sorted(model_paths)]
            clips = {c['path'] for e in entity_rows for a in e.get('configuredAnimations', []) for c in a['clipCandidates']}
            ue = ue_evidence(hid)
            result.append({'id': hid, 'name': fields['NAME'], 'englishName': fields.get('ENGLISH_NAME'), 'initialCharacter': fields.get('InitChar'),
                           'source': anchor(tables[8995], hero, 'UseRole'),
                           'skins': [{'id': r['id'], 'default': r['fields'].get('Default') == 1, 'name': r['fields'].get('Name'),
                                      'entityId': r['fields'].get('EntityID'), 'cultivateEntityId': r['fields'].get('CultivateEntityID'),
                                      'source': anchor(tables[961], r, 'CharID')} for r in dresses],
                           'entities': entity_rows, 'models': sorted(model_paths), 'animationLibraries': sorted(library_paths),
                           'decorationsAndWeapons': list(decorations.values()),
                           'ultimate': {'specialTableRow': hid if special else None, 'configuredFields': special['fields'] if special else None,
                                        'specialTableConsumer': {'moduleIndex': 6222, 'constantPath': [45], 'bytecodeRange': [0, 48]},
                                        'videos': video_rows, 'scene': by_id[9650].get(special['fields'].get('SpecialSkillSceneID'), {}).get('fields') if special else None,
                                        'runtimeTriggerAndFullPresentationVerified': None},
                           'vfx': {'explicitSourceSfxPaths': sorted(effects), 'linkedCardIds': sorted(card_ids), 'linkedSkillIds': sorted(skill_ids),
                                   'linkedTimelineIds': timeline_ids, 'allGraphAndParticleDependenciesEnumerated': False},
                           'counts': {'skinRowsIncludingDefault': len(dresses), 'nonDefaultSkinRows': sum(r['fields'].get('Default') != 1 for r in dresses),
                                      'uniqueConfiguredModelPaths': len(model_paths), 'uniqueIndexedModelPaths': sum(r['status'] == 'indexed-unique' for r in model_records),
                                      'animationLibraries': len(library_paths), 'configuredClipPaths': len(clips),
                                      'indexedClipPaths': sum(resources.record(p)['status'] == 'indexed-unique' for p in clips),
                                      'explicitSfxPaths': len(effects), 'ultimateVideoPaths': len({v['path'] for v in video_rows}),
                                      'ueCurrentSkeletalMeshFilesFromRetainedReadback': sum(o['class'] == 'SkeletalMesh' and o['currentFilePresent'] for o in ue['objects'])},
                           'ue': ue, 'unknowns': ['Full original shader, lighting and particle equivalence has not been verified.',
                             'HOME_ENTITY_ID=0 on non-Elsa heroes is not automatically bound to Elsa; scene runtime fallback remains unverified.',
                             'Index match is a path-hash candidate; animation bytecode/pose and texture fidelity need separate validation.']})
    finally:
        resources.close()
    all_models = {p for hero in result for p in hero['models']}
    all_clips = {c['path'] for hero in result for e in hero['entities'] for a in e.get('configuredAnimations', []) for c in a['clipCandidates']}
    all_effects = {p for hero in result for p in hero['vfx']['explicitSourceSfxPaths']}
    all_videos = {v['path'] for hero in result for v in hero['ultimate']['videos']}
    summary = {'characterSourceRows': 228, 'useRoleHeroRows': 35, 'dressTableTotalRows': tables[961]['total_source_rows'],
               'selectedHeroSkinRowsIncludingDefault': sum(len(h['skins']) for h in result),
               'selectedHeroNonDefaultSkinRows': sum(h['counts']['nonDefaultSkinRows'] for h in result),
               'heroesWithUniqueIndexedModel': sum(h['counts']['uniqueIndexedModelPaths'] > 0 for h in result),
               'uniqueConfiguredModelPaths': len(all_models), 'uniqueIndexedModelPaths': sum(resources.record(p)['status'] == 'indexed-unique' for p in all_models),
               'uniqueAnimationLibraryPaths': len({p for h in result for p in h['animationLibraries']}),
               'uniqueConfiguredClipPaths': len(all_clips), 'uniqueIndexedClipPaths': sum(resources.record(p)['status'] == 'indexed-unique' for p in all_clips),
               'heroesWithIndexedHallClip': sum(any(a['category'] == 'hall' and any(resources.record(c['path'])['status'] == 'indexed-unique' for c in a['clipCandidates']) for e in h['entities'] for a in e.get('configuredAnimations', [])) for h in result),
               'uniqueExplicitSfxPaths': len(all_effects), 'uniqueIndexedExplicitSfxPaths': sum(resources.record(p)['status'] == 'indexed-unique' for p in all_effects),
               'uniqueUltimateVideoPaths': len(all_videos), 'uniquePresentUltimateVideoPaths': len({v['path'] for h in result for v in h['ultimate']['videos'] if v['zipMemberPresent']}),
               'heroesWithPresentUltimateVideo': sum(any(v['zipMemberPresent'] for v in h['ultimate']['videos']) for h in result),
               'heroesWithRetainedUeReadbackAndCurrentMeshFile': sum(h['counts']['ueCurrentSkeletalMeshFilesFromRetainedReadback'] > 0 for h in result),
               'heroesWithVerifiedColourReferenceGlb': sum(bool(h['ue']['convertedColourReferenceModels']) for h in result),
               'fullyRecoveredOriginalHeroes': 0, 'metadataPayloadsRead': len(resources.blobs), 'metadataBytesRead': resources.read_bytes}
    report = {'schema': 'hczs-hero-recovery-catalog-v1', 'evidenceKind': 'hash-verified-static-ordinary-tools-plus-retained-ue-readback',
              'apkSha256': APK_SHA256, 'selection': {'field': 'UseRole', 'equals': 1}, 'sourceTables':
              {str(idx): {'source': t['source'], 'totalRows': t['total_source_rows']} for idx, t in tables.items()},
              'specialSkillConsumer': consumer, 'npkIndexes': [{k: p[k] for k in ['member','index_sha256','index_offset','file_size']} for p in catalogue],
              'summary': summary, 'heroes': result, 'resources': [resources.records[p] for p in sorted(resources.records)],
              'limits': ['No original APK or Unreal runtime executed for this catalogue.', 'No mesh, texture, clip payload or VFX graph converted by this tool.',
                         'Counts are unique source paths, not visually distinct meshes, decoded animation frames, or verified original playability.',
                         'VFX includes only literal entity and linked skill-timeline .sfx references; indirect graph/particle dependencies remain incomplete.',
                         'Retained UE native reports are paired with current asset files; this does not reexecute native readback or verify current rendering.',
                         'REA APK inventory remains separate from these ordinary-tool table and XML observations.']}
    output = args.output.resolve()
    output.relative_to(ROOT / 'analysis')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({'output': output.relative_to(ROOT).as_posix(), 'sha256': sha(output), 'summary': summary}, ensure_ascii=True))


if __name__ == '__main__':
    main()
