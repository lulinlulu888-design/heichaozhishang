"""Extract the original worldline CSB graph and explicit script art references.

The old Python marshal code is read as data, never executed.  This report is
ordinary static-tool evidence linked to the retained REA APK archive evidence.
Authored CSB values and player-bound chapter values remain separate.
"""
import hashlib
import json
import plistlib
from collections import Counter, deque
from pathlib import Path

from audit_hall_ui_dependencies import nodes, ui_path
from export_elsa_model import extract
from extract_npk import Marshal2
from extract_texture_samples import APK_SHA256
from inspect_battle_ui_layout import CLASSES
from neox_resource_paths import lookup_logical, read_catalogue
from prepare_unreal_hall_ui import HallReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/worldline/ui-dependencies'
ENTRY = 'uires/OutFightPanel/Story/MainLineStoryDialog_ext.csb'
# These four auto files are bound by the original MainLineStoryDialog script.
AUTO_INDICES = (3623, 2280, 3644, 3583)


class WorldlineReader(HallReader):
    def node(self, table, depth=0):
        # Shared Reader knows the common NodeTree/WidgetOptions representation;
        # the additional class is verified against the original option fields.
        CLASSES.add('ScrollView')
        result = super().node(table, depth)
        if result.get('options_status') or result['classname'] != 'ScrollView':
            return result
        options = self.pointer(self.field(table, 2))
        data = self.pointer(self.field(options, 0))
        def scalar(index, fmt, default):
            field = self.field(data, index)
            return self.scalar(fmt, field) if field else default
        def color(index):
            field = self.field(data, index)
            return list(self.unpack('BBBB', field)) if field else None
        result['background_resource'] = self.resource(self.pointer(self.field(data, 1)))
        result['clip_enabled'] = bool(scalar(2, 'B', 0))
        result['background_color_argb'] = color(3)
        result['background_start_color_argb'] = color(4)
        result['background_end_color_argb'] = color(5)
        result['background_color_type'] = scalar(6, 'i', 0)
        result['background_opacity'] = scalar(7, 'B', 255)
        field = self.field(data, 9)
        result['cap_insets'] = list(self.unpack('ffff', field)) if field else None
        result['scale9_size'] = self.pair(self.field(data, 10))
        result['scale9_enabled'] = bool(scalar(11, 'B', 0))
        result['inner_size'] = self.pair(self.field(data, 12))
        result['direction'] = scalar(13, 'i', 0)
        result['bounce_enabled'] = bool(scalar(14, 'B', 0))
        result['scrollbar_enabled'] = bool(scalar(15, 'B', 1))
        result['scrollbar_auto_hide'] = bool(scalar(16, 'B', 1))
        result['scrollbar_auto_hide_time'] = scalar(17, 'f', .2)
        if result['direction'] not in (0, 1, 2, 3):
            raise ValueError('Invalid original ScrollView direction')
        return result


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def strings(value):
    if isinstance(value, bytes):
        yield value.decode('utf8', 'replace')
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from strings(child)


def script_refs():
    index_path = ROOT / 'analysis/assets/decoded/script/index.json'
    index = {row['index']: row for row in json.loads(index_path.read_text('utf8'))}
    result = []
    for number in AUTO_INDICES:
        row = index[number]
        path = ROOT / row['output']
        if digest(path) != row['decoded_sha256']:
            raise ValueError('Decoded script hash changed: ' + str(number))
        refs = sorted({s for s in strings(Marshal2(path.read_bytes()).obj())
                       if s.endswith(('.csb', '.plist', '.png', '.ttf'))})
        result.append(dict(index=number, filename=row['filename'], path=str(path),
                           sha256=digest(path), resourceStrings=refs))
    if ENTRY not in result[0]['resourceStrings']:
        raise ValueError('Original worldline auto script no longer binds the expected entry')
    return dict(indexPath=str(index_path), indexSha256=digest(index_path), rows=result)


def main():
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if digest(apk) != APK_SHA256:
        raise ValueError('Unexpected original APK bytes')
    catalogue = read_catalogue(apk)
    refs = script_refs()
    OUT.mkdir(parents=True, exist_ok=True)
    script_paths = {ui_path(p) for row in refs['rows'] for p in row['resourceStrings']}
    templates = sorted(p for p in script_paths if p.endswith('.csb') and p != ENTRY)
    queue = deque([ENTRY] + templates)
    visited, layouts, edges, resources = set(), [], [], []
    while queue:
        logical = queue.popleft()
        if logical in visited:
            continue
        if len(visited) >= 128:
            raise ValueError('Worldline graph budget exceeded')
        visited.add(logical)
        matches = lookup_logical(catalogue, logical)
        if len(matches) != 1:
            layouts.append(dict(path=logical, status='unresolved', matches=len(matches)))
            continue
        target = OUT / 'source' / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        source = extract(apk, catalogue, logical, target, APK_SHA256)
        reader = WorldlineReader(target.read_bytes(), preserve_unknown=True)
        root = reader.scalar('I', 0)
        version = reader.string(reader.field(root, 0))
        if version != '2.1.0.0':
            raise ValueError('Unsupported shipped CSB version: ' + str(version))
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        opaque = [dict(offset=n['offset'], classname=n['classname']) for n in nodes(tree)
                  if n.get('options_status')]
        layouts.append(dict(path=logical, source=source, tree=tree, version=version,
                            status='partial' if opaque else 'parsed',
                            node_count=len(reader.seen), opaque_nodes=opaque))
        for node in nodes(tree):
            if node.get('project_path'):
                child = ui_path(node['project_path'])
                edges.append(dict(parent=logical, node=node['name'], child=child))
                queue.append(child)
            for field in ('resource', 'pressed_resource', 'disabled_resource',
                          'background_resource', 'font_resource'):
                resource = node.get(field)
                if not resource or not resource.get('path'):
                    continue
                resolved = ui_path(resource.get('plist') or resource['path'])
                hits = lookup_logical(catalogue, resolved)
                resources.append(dict(layout=logical, node=node['name'], field=field,
                                      reference=resource, lookup_path=resolved,
                                      kind='atlas-frame' if resource.get('plist') else 'file',
                                      matches=len(hits),
                                      status='unique-index-match' if len(hits)==1 else 'unresolved'))
    # Script replacement art is not necessarily stored in authored CSB nodes.
    for row in refs['rows']:
        for reference in row['resourceStrings']:
            if reference.endswith('.csb'):
                continue
            logical = ui_path(reference)
            resources.append(dict(scriptIndex=row['index'], field='script-resource-string',
                reference=dict(path=reference, plist=None), lookup_path=logical,
                kind='file', matches=len(lookup_logical(catalogue, logical)),
                authority='original-auto-script-static-reference'))
    atlases = {}
    other_plists = {}
    for resource in resources:
        logical = resource['lookup_path']
        if not logical.endswith('.plist') or resource['matches'] != 1:
            continue
        if logical in other_plists:
            continue
        if logical not in atlases:
            target = OUT / 'source' / logical
            target.parent.mkdir(parents=True, exist_ok=True)
            source = extract(apk, catalogue, logical, target, APK_SHA256)
            atlas = plistlib.loads(target.read_bytes())
            if not isinstance(atlas,dict) or not isinstance(atlas.get('frames'),dict):
                other_plists[logical] = dict(source=source, keys=sorted(atlas) if isinstance(atlas,dict) else [],
                    kind='non-atlas-original-plist')
                continue
            texture = atlas.get('metadata', {}).get('textureFileName')
            texture_path = ui_path(texture) if texture else None
            atlases[logical] = dict(source=source, frame_count=len(atlas['frames']),
                texture_path=texture_path,
                texture_matches=len(lookup_logical(catalogue, texture_path)) if texture_path else 0)
        if resource['kind']=='atlas-frame':
            atlas = plistlib.loads((OUT / 'source' / logical).read_bytes())
            resource['frame_present'] = resource['reference']['path'] in atlas['frames']
    summary = dict(layouts=len(layouts), nodes=sum(x.get('node_count',0) for x in layouts),
        layout_status=dict(Counter(x['status'] for x in layouts)),
        opaque_nodes=sum(len(x.get('opaque_nodes',[])) for x in layouts),
        project_edges=len(edges), resources=len(resources), atlases=len(atlases),
        explicit_frames=sum(x.get('frame_present',False) for x in resources),
        templates=templates)
    report = dict(schemaVersion=1, apk_sha256=APK_SHA256, entry=ENTRY, summary=summary,
        scriptReferences=refs, layouts=layouts, project_edges=edges, resources=resources,
        atlases=atlases, other_plists=other_plists, evidence_kind='ordinary-tool-static-CSB-marshal-conversion',
        limitations=['No original UI runtime, chapter unlock state, timelines, responsive adaptation or button behavior executed',
                    'Authored chapter text and progress are design data, never local player state',
                    'Custom unknown options remain opaque; no inferred geometry or substitute art'])
    (OUT / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
