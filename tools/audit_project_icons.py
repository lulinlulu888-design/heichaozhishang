"""Audit retained UI metadata, PNG headers/hashes and current consumer source.

No APK extraction, image decoding/editing, engine launch or runtime mutation.
Counts are bounded to the retained virtual-texture catalogue and atlas/manifest
metadata. UI portraits, card illustrations, panels, animation frames, numeric
material maps and admin vector symbols have distinct categories.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/assets/icon-audit.json'
DOC = ROOT / 'docs/icon-restoration-plan.md'
REVIEWED_BATTLE_ICONS = {}
ICON_CATEGORIES = {'navigation-icon', 'item-icon-candidate', 'equipment-icon-candidate',
                   'currency-icon-candidate', 'ui-symbol-candidate', 'skill-buff-icon-candidate',
                   'other-icon-namespace-candidate'}
LABELS = {
    'navigation-icon': '功能导航图标', 'item-icon-candidate': '道具/遗留品图标候选',
    'equipment-icon-candidate': '装备图标候选', 'currency-icon-candidate': '货币图标候选',
    'ui-symbol-candidate': '操作/职业/阵营标记候选', 'skill-buff-icon-candidate': '技能/buff 图标候选',
    'other-icon-namespace-candidate': '其他 icon 命名空间候选', 'portrait': '头像',
    'character-illustration': '角色立绘/大幅肖像',
    'card-illustration': '卡面插画', 'promotion-art': '礼包/活动插画',
    'ui-animation-frame': 'UI 动效/粒子帧', 'text-or-glyph': '文字贴图/字形',
    'frame-or-panel': '边框/底板/进度条', 'navigation-control-art': '完整导航按钮美术',
    'card-ui-art': '卡牌边框/卡背等', 'unclassified-ui': '用途待确认 UI 图片',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def logical(key):
    value = key.replace('\\', '/').removeprefix('uires/AllUIRes/')
    return value


def classify(key):
    """Conservative path/namespace candidates; does not infer solely from PNG size."""
    value = logical(key).lower()
    basename = value.rsplit('/', 1)[-1]
    if value in REVIEWED_BATTLE_ICONS:
        return 'ui-symbol-candidate', 'explicit reviewed UE battle icon inventory role: ' + REVIEWED_BATTLE_ICONS[value]
    if '/face/' in value and value.startswith('card/'):
        return 'card-illustration', 'explicit card/face namespace'
    if '/headicon/' in value or '/head/' in value or '/portrait/' in value or value.startswith('character/choose/'):
        return 'portrait', 'explicit portrait namespace'
    if 'img_char_photo' in value or '/bigsan/' in value:
        return 'character-illustration', 'large character image namespace, not a compact icon'
    if value.startswith('icon/giftpack/') or value.startswith('banner/'):
        return 'promotion-art', 'promotion namespace; not a compact control icon'
    if '/vx_' in value or '/glow' in value or '_vx_' in value or 'buff_eff/' in value or '/particle' in value:
        return 'ui-animation-frame', 'animation/effect namespace; batch continuity must be preserved'
    if (value.startswith('fnt_') or re.search(r'(^|[/_])(txt|txtimg|font|glyph|word|number|num)([/_\d.]|$)', value)
            or basename in {'tab_inventory.png','tab_mission.png','tab_guild.png','tab_mailbox.png',
                            'tab_shopping.png','btn_1_memory.png','btn_cityoftime.png','btn_memory.png','btn_unknownfuture.png'}):
        return 'text-or-glyph', 'font/text marker or reviewed hall raster text'
    if value.startswith('icon/headicon/'):
        return 'portrait', 'explicit headicon namespace'
    if value.startswith('icon/item/') or value.startswith('icon/box/') or value.startswith('icon/relicplus/'):
        return 'item-icon-candidate', 'declared item/box/relic icon namespace; appearance not visually reviewed'
    if value.startswith('icon/equip'):
        return 'equipment-icon-candidate', 'declared equipment icon namespace'
    if value.startswith('icon/money/'):
        return 'currency-icon-candidate', 'declared currency icon namespace'
    if value.startswith(('icon/buff/', 'icon/talenticon/', 'icon/factors/')):
        return 'skill-buff-icon-candidate', 'declared buff/talent/factor icon namespace'
    if value.startswith(('icon/tab/', 'icon/homeeventbtn/', 'icon/event/', 'icon/jump/', 'icon/share/')):
        return 'navigation-icon', 'declared navigation icon namespace'
    if value.startswith(('icon/char_type/', 'icon/class/', 'icon/position/', 'icon/camp/', 'icon/grade/', 'icon/teamrecommendbadge/')):
        return 'ui-symbol-candidate', 'declared role/camp/grade icon namespace'
    if value.startswith('icon/'):
        return 'other-icon-namespace-candidate', 'icon namespace; semantic/visual review outstanding'
    if re.search(r'(^|[/_])(bg|bar|line|frame|border)([/_\d.]|$)', value):
        return 'frame-or-panel', 'background/bar/line/frame name, not a symbol'
    if 'btn_2_home_' in value or basename in {'btn_1_home_chat2_s1.png', 'icon_sign_for.png'}:
        return 'navigation-icon', 'reviewed original hall functional sprite'
    if re.search(r'(^|[/_])(icon|ico)([/_\d.]|$)', value) or '/pieceicon/' in value:
        return 'ui-symbol-candidate', 'explicit icon-name marker outside icon namespace'
    if value.startswith('card/'):
        return 'card-ui-art', 'card namespace excluding face illustrations'
    if basename.startswith('btn'):
        return 'navigation-control-art', 'complete button image, may contain borders/text/state'
    return 'unclassified-ui', 'insufficient semantic evidence; not auto-counted as icon'


def png_metadata(path):
    payload = path.read_bytes()
    if payload[:8] != b'\x89PNG\r\n\x1a\n' or payload[12:16] != b'IHDR' or len(payload) < 33:
        raise ValueError('Bad PNG header: ' + relative(path))
    width, height, bits, color = struct.unpack('>IIBB', payload[16:26])
    if not 0 < width <= 65536 or not 0 < height <= 65536:
        raise ValueError('Invalid PNG dimensions')
    return dict(size=[width, height], bit_depth=bits, color_type=color,
                encoded_sha256=digest(payload), bytes=len(payload), pixel_decode_performed=False)


def main(output=None):
    sources, errors = {}, []
    records, catalogue, intermediate_probes = {}, {}, []

    def read_json(path):
        raw = path.read_bytes()
        sources[relative(path)] = digest(raw)
        return json.loads(raw)

    battle_inventory_path = ROOT / 'analysis/unreal/battle-ui/icon-inventory.json'
    battle_inventory = read_json(battle_inventory_path) if battle_inventory_path.exists() else None
    if battle_inventory:
        allowed = {'energy-icon', 'end-icon-normal', 'end-icon-active', 'shield-icon', 'deck-icon', 'card-cost'}
        if {row['id'] for row in battle_inventory['icons']} != allowed:
            raise ValueError('Reviewed battle icon inventory identity changed')
        for row in battle_inventory['icons']:
            file = (ROOT / row['png']).resolve()
            info = png_metadata(file)
            if info['encoded_sha256'] != row['pngSha256'] or info['size'] != row['size']:
                raise ValueError('Reviewed battle icon source changed')
            REVIEWED_BATTLE_ICONS[logical(row['sourceFrame']).lower()] = row['id']

    def register(key, scope, dimensions=None, source=None):
        key = logical(key)
        entry = catalogue.setdefault(key, dict(logical_path=key, classification=classify(key)[0],
                                              classification_reason=classify(key)[1], sources=[], dimensions=[]))
        marker = dict(scope=scope, **(source or {}))
        if marker not in entry['sources']:
            entry['sources'].append(marker)
        if dimensions and dimensions not in entry['dimensions']:
            entry['dimensions'].append(dimensions)
        return entry

    vt_path = ROOT / 'analysis/resource-mapping/vt_config.parsed.json'
    vt = read_json(vt_path)
    raw_vt = ROOT / 'analysis/resource-mapping/vt_config.jsondata'
    if digest(raw_vt.read_bytes()) != vt['sha256']:
        raise ValueError('Retained virtual-texture source differs from parsed catalogue')
    sources[relative(raw_vt)] = vt['sha256']
    for row in vt['fullPathToPng']:
        register(row['value'], 'virtual-texture-catalogue', source=dict(full_path=row['key'], metadata_offset=row['offset']))
    atlas_files = sorted((ROOT / 'analysis').rglob('*.plist'))
    unique_atlases = {}
    for path in atlas_files:
        raw = path.read_bytes()
        sha = digest(raw)
        sources[relative(path)] = sha
        if sha in unique_atlases:
            unique_atlases[sha]['copies'].append(relative(path))
            continue
        try:
            atlas = plistlib.loads(raw)
        except Exception as error:
            errors.append(dict(path=relative(path), error=str(error)))
            continue
        atlas_row = dict(sha256=sha, copies=[relative(path)], frames=len(atlas.get('frames', {})),
                         texture_file=atlas.get('metadata', {}).get('textureFileName'),
                         kind='sprite-atlas' if atlas.get('frames') else 'non-sprite-plist')
        unique_atlases[sha] = atlas_row
        for key, frame in atlas.get('frames', {}).items():
            dims = list(map(int, re.findall(r'-?\d+', frame.get('sourceSize', ''))))
            if len(dims) != 2 or any(n <= 0 for n in dims):
                errors.append(dict(path=relative(path), frame=key, error='invalid sourceSize'))
                continue
            register(key, 'retained-atlas-frame', dims, dict(plist_sha256=sha, plist=relative(path),
                    frame_rect=frame.get('frame'), rotated=frame.get('rotated', False), texture_file=atlas_row['texture_file']))

    def add_image(key, filename, expected, report, declared=None):
        path = (ROOT / filename.replace('\\', '/')).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('UI manifest source outside workspace')
        if not path.exists():
            errors.append(dict(report=report, image=relative(path), error='referenced PNG missing'))
            return
        info = png_metadata(path)
        if expected and info['encoded_sha256'] != expected:
            raise ValueError('Recovered UI PNG identity mismatch: ' + relative(path))
        if declared and info['size'] != list(declared):
            raise ValueError('Recovered UI PNG dimensions differ: ' + relative(path))
        key = logical(key)
        if path.name.endswith('-candidate.png'):
            candidate = dict(logical_path=key, png=relative(path), report=report, **info,
                             role='intermediate virtual-tile stitch probe; not validated final cropped sprite')
            if candidate not in intermediate_probes:
                intermediate_probes.append(candidate)
            return
        register(key, 'recovered-original-PNG', info['size'], dict(report=report))
        identity = (key, info['encoded_sha256'])
        row = records.setdefault(identity, dict(logical_path=key, classification=classify(key)[0],
                     classification_reason=classify(key)[1], **info, files=[], reports=[], consumers=[]))
        if relative(path) not in row['files']:
            row['files'].append(relative(path))
        if report not in row['reports']:
            row['reports'].append(report)

    def walk(value, report, depth=0):
        if depth > 64:
            raise ValueError('Metadata nesting exceeds audit boundary')
        if isinstance(value, list):
            for item in value:
                walk(item, report, depth + 1)
        elif isinstance(value, dict):
            key = next((value[field] for field in ('logical_frame', 'source_frame', 'sourceFrame', 'key', 'logical', 'logical_path')
                        if isinstance(value.get(field), str) and value[field].lower().endswith('.png')), None)
            if key is None and isinstance(value.get('mapping'), dict):
                candidate = value['mapping'].get('key')
                if isinstance(candidate, str) and candidate.lower().endswith('.png'):
                    key = candidate
            filename = next((value[field] for field in ('png', 'sprite', 'output')
                             if isinstance(value.get(field), str) and value[field].lower().endswith('.png')), None)
            expected = next((value[field] for field in ('png_sha256', 'pngSha256', 'sprite_sha256', 'output_sha256', 'sha256')
                             if isinstance(value.get(field), str) and re.fullmatch(r'[0-9a-f]{64}', value[field])), None)
            if key and filename:
                size = value.get('size')
                add_image(key, filename, expected, report, size if isinstance(size, list) else None)
            for item in value.values():
                if isinstance(item, (dict, list)):
                    walk(item, report, depth + 1)

    scoped_metadata = set()
    for folder in ('analysis/battle-ui', 'analysis/card-art', 'analysis/hall/ui-sprites', 'analysis/resource-mapping/characters'):
        for path in (ROOT / folder).rglob('*.json'):
            if path.name in ('report.json', 'provenance.json', 'manifest.json', 'sprites.json', 'portraits.json'):
                scoped_metadata.add(path)
    for path in sorted(scoped_metadata):
        walk(read_json(path), relative(path))
    hall_path = ROOT / 'analysis/unreal/hall-ui/layout.json'
    hall = read_json(hall_path)
    walk(hall['sprites'], relative(hall_path))
    sprite_by_id = {sprite['id']: sprite for sprite in hall['sprites']}
    for item in hall['previewDrawItems']:
        if item['kind'] != 'sprite':
            continue
        source = sprite_by_id[item['spriteId']]
        key = (logical(source['sourceFrame']), source['pngSha256'])
        if key in records:
            records[key]['consumers'].append(dict(kind='UE-hall-prepared-draw', instance=item['instancePath'],
                original_widget_size=item['size'], draw_bounds=item['geometry']['bounds'],
                runtime_class='UHczsHallWidget', imported_asset='/Game/Recovered/Hall/UI/HallLayout'))
    battle_manifest = ROOT / 'analysis/unreal/battle-ui/manifest.json'
    if battle_manifest.exists():
        battle = read_json(battle_manifest)
        walk(battle['sprites'], relative(battle_manifest))
        for sprite in battle['sprites']:
            key = (logical(sprite['sourceFrame']), sprite['pngSha256'])
            if key in records:
                records[key]['consumers'].append(dict(kind='UE-battle-prepared-input', sprite_id=sprite['id'],
                    import_status='separate UE import/runtime report required', source=relative(battle_manifest)))
    if battle_inventory:
        for row in battle_inventory['icons']:
            key = (logical(row['sourceFrame']), row['pngSha256'])
            if key not in records:
                raise ValueError('Declared battle icon missing from recovered source records')
            records[key]['consumers'].append(dict(kind='UE-battle-declared-icon', sprite_id=row['id'],
                usage=row['usage'], declaredCurrentlyPainted=row['currentlyPainted'],
                declarationIsRuntimeEvidence=False, source=relative(battle_inventory_path)))
    ai_file = ROOT / 'analysis/unreal/hall-ui/ai-icons/provenance.json'
    ai_variants = []
    if ai_file.exists():
        ai = read_json(ai_file)
        for icon in ai['icons']:
            for variant in icon['variants']:
                path = Path(variant['path']).resolve()
                info = png_metadata(path)
                if info['encoded_sha256'] != variant['sha256']:
                    raise ValueError('AI PNG differs from provenance')
                ai_variants.append(dict(name=icon['name'], version=variant['version'], source_frame=icon['source']['sourceFrame'],
                    png=relative(path), **info, generated=True, original_resource=False))
    # Preserve the historical first audit, but include every retained generation
    # batch in this new status snapshot. Do not infer client import from PNGs.
    ai_by_path = {row['png']: row for row in ai_variants}
    ai_batches = []

    def add_ai(name, filename, source_key, batch, version=None, expected=None, selected=False):
        path = (ROOT / filename.replace('\\', '/')).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.exists():
            errors.append(dict(batch=batch, filename=filename, error='AI workspace copy missing or outside workspace'))
            return
        info = png_metadata(path)
        if expected and info['encoded_sha256'] != expected:
            raise ValueError('AI batch file hash changed: ' + relative(path))
        key = relative(path)
        row = ai_by_path.setdefault(key, dict(name=name, version=version, source_frame=logical(source_key),
                      png=key, **info, generated=True, original_resource=False, batches=[]))
        row.setdefault('batches', [])
        if batch not in row['batches']:
            row['batches'].append(batch)
        if selected:
            row['selectedCandidate'] = True

    for filename in ('analysis/unreal/hall-ui/ai-icons/provenance-unified.json',
                     'analysis/unreal/hall-ui/ai-icons/unified-generation.json'):
        path = ROOT / filename
        if not path.exists():
            continue
        data = read_json(path)
        for icon in data['icons']:
            name = icon['name']
            original = next(row for row in ai_variants if row['name'] == name)['source_frame']
            for variant in icon.get('variants', [icon]):
                add_ai(name, variant['path'], original, filename, variant['version'], variant.get('sha256'))
        ai_batches.append(dict(metadata=filename, kind='hall-style-variants', importedOrRenderedVerified=False))
    battle_by_id = {row['id']: row for row in (battle_inventory or {}).get('icons', [])}
    for filename in ('analysis/unreal/battle-ui/ai-icons/generation-requests.json',
                     'analysis/unreal/battle-ui/ai-icons/generation-retry-requests.json',
                     'analysis/unreal/battle-ui/ai-icons/generation-active-v3-request.json'):
        path = ROOT / filename
        if not path.exists():
            continue
        data = read_json(path)
        rows = data.get('records', [data])
        for row in rows:
            if row.get('id') in battle_by_id and row.get('output'):
                add_ai(row['id'], row['output'], battle_by_id[row['id']]['sourceFrame'], filename)
        ai_batches.append(dict(metadata=filename, kind='battle-generations', importedOrRenderedVerified=False))
    battle_provenance = ROOT / 'analysis/unreal/battle-ui/ai-icons/provenance.json'
    if battle_provenance.exists():
        data = read_json(battle_provenance)
        for row in data['icons']:
            add_ai(row['id'], row['variant'], battle_by_id[row['id']]['sourceFrame'], relative(battle_provenance),
                   row['version'], row['variantSha256'], selected=True)
        ai_batches.append(dict(metadata=relative(battle_provenance), kind='battle-reviewed-selection', importedOrRenderedVerified=False))
    common_provenance = ROOT / 'analysis/assets/ai-icons/common/provenance.json'
    if common_provenance.exists():
        data = read_json(common_provenance)
        for icon in data['icons']:
            for variant in icon['variants']:
                add_ai(icon['name'], variant['png'], icon['source']['sourceFrame'], relative(common_provenance),
                       variant['version'], variant['metadata']['sha256'], variant['selected'])
        ai_batches.append(dict(metadata=relative(common_provenance), kind='common-10-source-15-variants',
                              activeHallCandidates=2, libraryOnlySources=8, importedOrRenderedVerified=False))
    ai_variants = sorted(ai_by_path.values(), key=lambda row: row['png'])
    admin_usage = defaultdict(list)
    admin_source = ROOT / 'admin/src'
    for path in sorted(admin_source.rglob('*.vue')):
        raw = path.read_bytes()
        sources[relative(path)] = digest(raw)
        code = raw.decode('utf8')
        for match in re.finditer(r"import\s*\{([^}]+)\}\s*from\s*['\"]@element-plus/icons-vue['\"]", code):
            for name in match.group(1).split(','):
                name = name.strip().split(' as ')[0]
                if name:
                    admin_usage[name].append(relative(path))
    client_sources = []
    for path in sorted((ROOT / 'clients/unreal5 5.8/Source/Hczs').rglob('*.cpp')):
        code = path.read_text('utf8')
        if any(token in code for token in ('HallLayout', 'BattleAssets', 'Sprites', 'spriteId')):
            sources[relative(path)] = digest(path.read_bytes())
            client_sources.append(relative(path))
    recovered = sorted(records.values(), key=lambda row: (row['classification'], row['logical_path'], row['encoded_sha256']))
    hash_groups = defaultdict(list)
    for row in recovered:
        hash_groups[row['encoded_sha256']].append(row['logical_path'])
    duplicates = [dict(sha256=sha, logical_paths=sorted(set(keys))) for sha, keys in sorted(hash_groups.items()) if len(set(keys)) > 1]
    icon_records = [row for row in recovered if row['classification'] in ICON_CATEGORIES]
    next_candidates = sorted((row for row in icon_records if row['consumers'] and max(row['size']) <= 128
                              and not any(logical(variant['source_frame']) == row['logical_path'] for variant in ai_variants)),
                             key=lambda row: (0 if any(c['kind']=='UE-battle-prepared-input' for c in row['consumers']) else 1,
                                              max(row['size']), row['logical_path']))
    def counts(rows):
        return dict(sorted(Counter(row['classification'] for row in rows).items()))
    report = dict(schema='hczs-project-ui-icon-audit-v1', evidence_kind='ordinary read-only retained metadata and PNG header/hash audit; no new REA Evidence',
        scope=dict(virtual_texture_source_sha256=vt['sha256'], virtual_texture_names=len(vt['fullPathToPng']),
                   retained_plist_files=len(atlas_files), unique_plist_payloads=len(unique_atlases),
                   retained_atlas_frame_records=sum(row['frames'] for row in unique_atlases.values()),
                   scoped_ui_manifest_files=len(scoped_metadata), whole_apk_icon_count_verified=False),
        summary=dict(catalogue_logical_names=len(catalogue), catalogue_categories=counts(catalogue.values()),
            vt_icon_namespace_names=sum(row['value'].lower().startswith('icon/') for row in vt['fullPathToPng']),
            vt_icon_namespace_categories=dict(sorted(Counter('/'.join(row['value'].lower().split('/')[:2])
                 for row in vt['fullPathToPng'] if row['value'].lower().startswith('icon/')).items())),
            logical_names_with_known_dimensions=sum(bool(row['dimensions']) for row in catalogue.values()),
            logical_names_with_unknown_dimensions=sum(not row['dimensions'] for row in catalogue.values()),
            recovered_logical_image_variants=len(recovered), recovered_unique_png_hashes=len(hash_groups),
            recovered_categories=counts(recovered), recovered_icon_candidates=len(icon_records),
            recovered_icon_candidate_unique_hashes=len({row['encoded_sha256'] for row in icon_records}),
            intermediate_probe_images=len({row['png'] for row in intermediate_probes}),
            duplicate_hash_groups=len(duplicates), icon_dimensions=dict(sorted(Counter('%sx%s'%tuple(row['size']) for row in icon_records).items())),
            ai_variant_files=len(ai_variants), ai_original_icons=len({logical(row['source_frame']).lower() for row in ai_variants}),
            admin_vector_icon_names=len(admin_usage)),
        catalogue=sorted(catalogue.values(), key=lambda row: row['logical_path']),
        atlases=list(unique_atlases.values()), recovered_original_images=recovered,
        duplicate_png_hashes=duplicates, ai_variants=ai_variants,
        ai_batch_status=ai_batches,
        classification_revision=dict(addedReviewedRoleKeys=['shield-icon', 'card-cost'],
              source=relative(battle_inventory_path) if battle_inventory else None,
              reason='Reviewed functional icon roles in current battle HUD, not classification by size'),
        intermediate_probe_images=intermediate_probes,
        consumers=dict(ue_source_files=client_sources,
                       admin_vector_symbols=[dict(name=name, files=files) for name, files in sorted(admin_usage.items())],
                       admin_apk_image_consumption_verified=False),
        next_batch_candidates=next_candidates[:24], source_metadata_sha256=dict(sorted(sources.items())),
        reusable_tools=['tools/recover_hall_ui_sprites.py::crop_frame', 'tools/neox_resource_paths.py',
                        'tools/decode_ktx.py', 'tools/probe_card_vt_tiles.py', 'tools/audit_ai_hall_icons.py',
                        'tools/prepare_unreal_hall_ui.py', 'tools/prepare_unreal_battle_ui.py'],
        limitations=['Catalogue classification is conservative naming/namespace inference, not visual validation of all images.',
            'Global vt catalogue does not cover every native atlas or every NPK resource. Do not call this total APK icon count.',
            'Some catalogue names have no retained atlas dimensions or recovered pixels; unknown dimensions remain unknown.',
            'PNG duplicate count compares encoded SHA256, not perceptual similarity or decoded pixel equality.',
            'Prepared UE draw/input references are not proof of clickable functionality or runtime visual acceptance.',
            'Card illustrations, portraits, text, animated effects and whole buttons require their own restoration policy.',
            'Normal/mix/depth/alpha-mask/data textures are outside icon generation and may not be AI-painted as colour icons.',
            'Admin uses Element Plus vector symbols; no automatic replacement with game art is proposed.'], errors=errors)
    destination = Path(output) if output else (OUT.with_name('icon-audit-latest.json') if OUT.exists() else OUT)
    if not destination.resolve().is_relative_to((ROOT/'analysis/assets').resolve()):
        raise ValueError('Audit output must remain in analysis/assets')
    if destination.resolve() == OUT.resolve() and OUT.exists():
        raise ValueError('Historical first audit is retained; choose a new output path')
    report['output_file'] = relative(destination)
    report['historical_audit_file'] = relative(OUT) if OUT.exists() else None
    report['historical_audit_sha256'] = digest(OUT.read_bytes()) if OUT.exists() else None
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf8')
    write_document(report)
    print(json.dumps(dict(output=str(destination), scope=report['scope'], summary=report['summary'], errors=len(errors)), ensure_ascii=False))


def write_document(report):
    summary, scope = report['summary'], report['scope']
    lines = ['# 游戏图标恢复与高清化批次计划', '',
        '这是对现有 APK 提取元数据、原 PNG 的文件头/哈希及 UE/Admin 消费点的只读审计；没有重新解包 APK、调用 AI 或改写图片。最新机器明细为 `'+report['output_file']+'`；首轮 `analysis/assets/icon-audit.json` 保留不变。普通工具证据，不是新的 REA Evidence。', '',
        '## 统计边界', '',
        f'- 原虚拟纹理配置保留 {scope["virtual_texture_names"]:,} 个 UI 逻辑图片名；不是全部 APK 图片。',
        f'- 其中 `icon/` 命名空间 {summary["vt_icon_namespace_names"]:,} 项，包含头像、道具、装备、礼包等；这些不能全称为“小按钮图标”。各子目录原始数量见机器清单。',
        f'- 当前保存 {scope["retained_plist_files"]} 个 plist 文件，按 SHA256 去重 {scope["unique_plist_payloads"]} 个，包含 {scope["retained_atlas_frame_records"]:,} 条 frame 元数据。无 frames 的粒子配置单列，不算图标。',
        f'- 合并后 {summary["catalogue_logical_names"]:,} 个逻辑图片名；已恢复并在本次核验的 {summary["recovered_logical_image_variants"]} 个原 PNG 逻辑变体，对应 {summary["recovered_unique_png_hashes"]} 个唯一文件哈希。',
        f'- 其中 {summary["recovered_icon_candidates"]} 个是保守分类后的图标候选，{summary["recovered_icon_candidate_unique_hashes"]} 个唯一哈希；其余头像、卡面、边框、文字、完整按钮和动效单列。',
        '- 首轮名称分类得到19个；本轮按已核验的战斗消费清单补入护盾32×32与卡牌费用宝石70×82，共21个已识别静态图标源。角色判断来自实际消费角色声明，不是因为图片小。',
        f'- {summary["logical_names_with_known_dimensions"]:,} 个逻辑名已有 frame/PNG 尺寸，{summary["logical_names_with_unknown_dimensions"]:,} 个仍无尺寸证据；虚拟页映射尺寸不能代替图标尺寸。五张早期拼页候选已作为中间探针排除，最终卡面只计五张。',
        f'- AI 已有 {summary["ai_original_icons"]} 个原图标、{summary["ai_variant_files"]} 个独立变体文件。原图保留，不能称为恢复了原始高清资源。',
        '- AI 数量合并大厅历史/统一风格批次、战斗生成与审核批次、公共十图标批次；候选生成、选定、UE导入、实际屏幕验收是不同状态，未按文件存在冒充运行通过。',
        f'- Admin 使用 {summary["admin_vector_icon_names"]} 种 Element Plus 矢量符号；属于后台 UI，不混入 APK 图标恢复数。', '',
        '不能给出“APK 一共有多少个图标”的完整数量，原因是尚未全量提取/分类所有原图集；现有清单可以确定下一批工作，不需先把全部 PNG 导出一遍。', '',
        '## 分类总账', '', '| 分类 | 逻辑目录中 | 已恢复原 PNG 变体 |', '|---|---:|---:|']
    categories = sorted(set(summary['catalogue_categories']) | set(summary['recovered_categories']))
    for category in categories:
        lines.append(f'| {LABELS.get(category, category)} | {summary["catalogue_categories"].get(category, 0):,} | {summary["recovered_categories"].get(category, 0):,} |')
    lines += ['', '名称含 `icon` 的道具/头像/礼包也不一定是按钮小图标。`card/face/` 明确按卡面插画处理；`VX`/Glow/粒子帧按动效序列处理；边框与条形图按 UI 底板处理。无法确定的归“用途待确认”，不靠图片尺寸强行算图标。', '',
        '## 批次顺序与验收', '',
        '1. 已完成大厅顶栏五图标：保留原图与 AI 开关，复核同屏尺寸下主体占比、柔边、透明留白与原风格；变体身份见 `docs/ai-hall-icons.md`。',
        '2. 下一批优先当前 UE 战斗/大厅实际消费的低尺寸静态操作与状态符号；按同一原图集和视觉族批量，先逐图生成可追溯变体，再统一导入独立资源与可回退映射。下表只是候选，root 需先视觉复核。',
        '3. 补齐牌堆/能量/护盾/意图/回合等战斗 UI 符号。原卡面插画、头像与卡牌边框单独处理，不与小图标混在同一提示词或总数里。',
        '4. 再按道具、货币、装备、buff、导航等族扩展；按原图哈希缓存与复用，避免相同 PNG 在不同页面重复生成。未恢复像素的候选先使用通用提取/裁剪工具，不直接让 AI 猜图。',
        '5. 模型颜色纹理另立材质批次。法线、mix、深度、alpha-mask 等数值通道不按颜色图 AI 补绘；材质还需恢复原 UV、采样、着色与光照。', '',
        '每批门槛：原图/来源/生成工具/提示词/AI文件哈希完整；原图不变；实际尺寸与透明度核验；完整原按钮矩形下原图/AI对照；多尺度可读性和同族一致性；客户端能切回原素材。多出像素不自动等于更忠实。', '',
        '## 下一批可读候选', '', '| 原逻辑图 | 尺寸 | 当前消费 |', '|---|---|---|']
    for row in report['next_batch_candidates'][:12]:
        uses = ', '.join(sorted({c['kind'] for c in row['consumers']}))
        lines.append(f'| `{row["logical_path"]}` | {row["size"][0]}×{row["size"][1]} | {uses} |')
    if not report['next_batch_candidates']:
        lines.append('| 本批尚无额外已消费的小图标候选 | — | 不把未知用途图片硬补进批次 |')
    lines += ['', '详细原文件、尺寸、哈希、消费位置和重复组均在机器清单，所有图片只读。尺寸来自原 frame 的 sourceSize 或 PNG IHDR；虚拟页大小不是图标本体大小。', '',
        '## 现有公共工具', '',
        '- `recover_hall_ui_sprites.py::crop_frame`：原图集旋转/裁剪/补回透明画布；战斗工具复用同一格式。',
        '- `neox_resource_paths.py`、`decode_ktx.py`：路径匹配与固定解码器，不需手工逐条解包。',
        '- `probe_card_vt_tiles.py`：原虚拟纹理页与卡面恢复；不能把图集像素误当整图。',
        '- `prepare_unreal_hall_ui.py`、`prepare_unreal_battle_ui.py`：当前 UE 消费 manifest 和来源核验。',
        '- `audit_ai_hall_icons.py`：原图/AI变体哈希、尺寸、透明边界与显示对齐检查。',
        '- `audit_project_icons.py`：本次全项目只读目录/恢复像素/消费点/分类审计，避免把所有 PNG 都算图标。', '',
        '## 复现', '', '```powershell',
        "& 'C:/Users/5090B/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -X utf8 'tools/audit_project_icons.py'", '```', '',
        '本脚本只写本审计 JSON 与本文，不修改 PNG、APK、UE 资产、Admin 运行或存档。重复哈希口径为完整编码文件 SHA256，不是感知相似度；相同像素用不同 PNG 编码可能未归并。']
    DOC.write_text('\n'.join(lines)+'\n', 'utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New JSON snapshot under analysis/assets; historical icon-audit.json is never replaced')
    args = parser.parse_args()
    main(args.output)
