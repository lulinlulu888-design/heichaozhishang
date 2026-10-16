"""Recover original entrance-banner/HUD CSB keyframes and exact atlas sprites.

Reads original APK resources only. No original code, UI, or Unreal execution.
Named animations retain individual tracks, easing, texture swaps and callbacks;
they are never collapsed into a single fade or replacement text banner.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import sys

from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_battle_ui_layout import Reader
from inspect_battle_rules import export, read_module
from csb_timeline import timeline_with_inner, walk
from neox_resource_paths import read_catalogue
from recover_pile_ui_sprites import recover
from recover_entrance_direct_images import recover as recover_direct
from prepare_battle_draw_recipe import recover as recover_draw
from trace_first_encounter import inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/entrance'
MODULES = {'normal': 3700, 'elite': 681, 'boss': 6739, 'hud': 6424}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', 'utf8')


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    rows = inventory()
    catalogue = read_catalogue(apk)
    layouts, script_evidence, resources = {}, {}, {}
    for index, names in [(5873, ('getCSBFilePath', 'initComponents', 'play', '_onAnimFirstEnd', '<lambda>', 'MaxDuration', 'showPop')),
                         (3414, ('getCSBFilePath', 'onBattleStart', '_showUI', 'showRoundBeginPop')),
                         (6095, ('getAnimationDuration', 'playAnimation', 'initAnimationInfo'))]:
        result = export(rows[index], names)
        path = OUT / 'scripts' / f'{index}.json'
        write_json(path, result)
        script_evidence[str(index)] = {'file': str(path), 'sha256': sha(path.read_bytes()), 'source': rows[index]}
    for identifier, index in MODULES.items():
        module = read_module(rows[index])
        paths = [v.decode('utf8') for v in module['consts'] if isinstance(v, bytes) and v.endswith(b'.csb')]
        if len(paths) != 1:
            raise ValueError('Ambiguous original CSB path')
        path = OUT / 'csb' / (identifier + '.csb')
        source = extract(apk, catalogue, paths[0], path, APK_SHA256)
        raw = path.read_bytes()
        reader = Reader(raw, preserve_unknown=True)
        root = reader.scalar('I', 0)
        if reader.string(reader.field(root, 0)) != '2.1.0.0':
            raise ValueError('Unsupported source layout schema')
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        timeline = timeline_with_inner(raw)
        flat, tags, subprojects = [], {}, []
        for node, parents in walk(tree):
            entry = {k: v for k, v in node.items() if k != 'children'}
            entry['parents'] = parents
            flat.append(entry)
            tag = node.get('action_tag')
            if tag not in (None, 0):
                tags.setdefault(tag, []).append(node.get('name'))
            if node.get('project_path'):
                subprojects.append({'node': node['name'], 'actionTag': tag, 'path': node['project_path']})
            for key in ('resource', 'pressed_resource', 'disabled_resource', 'background_resource'):
                ref = node.get(key)
                if ref and ref.get('path'):
                    resources[(ref['path'], ref.get('plist'))] = ref
        for track in timeline['timelines']:
            track['targetNodeNames'] = tags.get(track['action_tag'], [])
            for frame in track['frames']:
                if frame['kind'] == 'texture' and frame.get('value'):
                    ref = frame['value']
                    resources[(ref['path'], ref.get('plist'))] = ref
        speed = timeline['speed']
        for animation in timeline['animations']:
            animation['sourceDurationSeconds'] = (animation['end'] - animation['start']) / (60 * speed) if speed > 0 else None
        layouts[identifier] = {'module': rows[index], 'source': source, 'tree': tree,
                               'nodes': flat, 'timeline': timeline, 'subprojects': subprojects,
                               'shaderResourceStrings': sorted(set(s.decode('ascii') for s in
                                   re.findall(rb'EditorShaderRes/[A-Za-z0-9_./-]+', raw)))}
    selected = {
        'normal': ['animation0', 'animation2', 'animation1'], 'elite': ['In'], 'boss': ['in'], 'hud': ['In']}
    for key, names in selected.items():
        actual = {a['name'] for a in layouts[key]['timeline']['animations']}
        if not set(names).issubset(actual):
            raise ValueError('Requested original named animation missing: ' + key)
    write_json(OUT / 'layouts.json', {'apkSha256': APK_SHA256, 'layouts': layouts})
    # Synthetic binding tree feeds the shared exact atlas cropper and includes
    # animated TextureFrame references, without modifying the actual source trees.
    atlas_resources = [r for r in resources.values() if r.get('plist') and r['path'].endswith('.png')]
    wanted = {r['path']: 'sprite_' + sha((r['plist'] + '|' + r['path']).encode())[:16] for r in atlas_resources}
    synthetic = {'layouts': {'bindings': {'tree': {'children': [
        {'children': [], 'resource': ref} for ref in atlas_resources]}}}}
    binding_path = OUT / 'sprite-bindings.json'
    write_json(binding_path, synthetic)
    recover(wanted, OUT / 'sprites', binding_path)
    recovered = json.loads((OUT / 'sprites/report.json').read_text('utf8'))
    direct = recover_direct()
    draw = recover_draw()
    sprites = list(recovered['frames']) + [{**r, 'name': 'direct_' + r['name'],
        'source_frame': r['requestedResource'], 'plist': None} for r in direct['frames']]
    sprite_map = {r['source_frame']: r for r in sprites}
    for layout in layouts.values():
        for node in layout['nodes']:
            ref = node.get('resource') or {}
            if ref.get('path') in sprite_map:
                node['spriteId'] = sprite_map[ref['path']]['name']
        for track in layout['timeline']['timelines']:
            for frame in track['frames']:
                if frame['kind'] == 'texture' and frame.get('value') and frame['value']['path'] in sprite_map:
                    frame['spriteId'] = sprite_map[frame['value']['path']]['name']
    particle_sources = []
    for ref in resources.values():
        if not ref.get('plist') and ref['path'].endswith('.plist'):
            path = OUT / 'particles' / Path(ref['path']).name
            source = extract(apk, catalogue, 'uires/' + ref['path'], path, APK_SHA256)
            particle_sources.append({'requestedResource': ref['path'], 'source': source,
                                     'localFile': str(path.relative_to(ROOT)), 'implemented': False})
    result = {'schema': 'hczs-battle-entrance-ui-v1', 'sourceApkSha256': APK_SHA256,
              'originalRuntimeExecuted': False, 'scripts': script_evidence, 'layouts': layouts,
              'sprites': sprites, 'atlasSources': recovered['sources'],
              'directImageSources': direct, 'particleSources': particle_sources,
              'drawCard': {'file': str((OUT / 'draw-evidence.json').relative_to(ROOT)),
                  'sha256': sha((OUT / 'draw-evidence.json').read_bytes()),
                  'findings': draw['findings'], 'numericValidation': draw['numericValidation']},
              'durationEvidence': {'module': 6095, 'method': 'CommonActionTimeline.getAnimationDuration',
                  'sourceLine': 110, 'formula': '(endIndex - startIndex) / (timeline.getTimeSpeed() * 60)'},
              'playback': {'normal': {'first': 'animation0', 'onFirstEndDelayFrames': 1,
                  'thenIf_STAGE_BEGIN_true': 'animation2', 'thenOtherwise': 'animation1'},
                  'elite': {'animation': 'In'}, 'boss': {'animation': 'in'},
                  'selection': 'IsBoss first; else IsElite; else normal (BeginStartPop.initComponents lines101-106)',
                  'hud': {'animation': 'In', 'trigger': 'FightPanel.onBattleStart line260'}, 'popupMaxDuration': 3},
              'unresolvedDirectImages': [r for r in resources.values() if not r.get('plist')
                  and r['path'].endswith('.png') and r['path'] not in sprite_map],
              'unimplementedSourceShaderTracks': {key: [
                  {'property': t['property'], 'actionTag': t['action_tag'], 'targetNodeNames': t['targetNodeNames']}
                  for t in layout['timeline']['timelines'] if t['property'].startswith('Splendor_')]
                  for key, layout in layouts.items()},
              'limitations': ['Nested ProjectNode layout instances are referenced separately; preserve local transforms/constraints',
                  'Easing enums and inner actions retained; native timeline playback not executed',
                  'APK fork union field10 is a bounded float vector; field11 zero RotationX values are retained as floats with source offsets; fork runtime semantics unverified',
                  'Splendor shader parameter tracks and shader texture-name strings are preserved, not recreated in UE by this tool',
                  'Original particle definitions extracted; particle runtime and nested HUD subproject internals not reconstructed here',
                  'CSB colour bytes remain A,R,G,B; atlas pixels retain alpha and trimming',
                  'No claim that every battle is elite; banner variant follows source flags'],
              'destination': '/Game/Recovered/Battle/Entrance/UI'}
    result['recipeSha256'] = sha(json.dumps(result, sort_keys=True, separators=(',', ':')).encode())
    write_json(OUT / 'playback-recipe.json', result)
    print(json.dumps({'layouts': {k: {'animations': v['timeline']['animations'], 'nodes': len(v['nodes']),
        'tracks': len(v['timeline']['timelines']), 'subprojects': v['subprojects']} for k, v in layouts.items()},
        'sprites': len(sprites), 'unresolvedDirectImages': result['unresolvedDirectImages']}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
