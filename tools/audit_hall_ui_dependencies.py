"""Expand original hall ProjectNodes; report exact resource lookups, not runtime UI."""
import hashlib
import json
import plistlib
from collections import Counter, deque
from pathlib import Path, PurePosixPath

from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_battle_ui_layout import Reader
from neox_resource_paths import lookup_logical, read_catalogue

ROOT = Path(__file__).resolve().parents[1]
ENTRY = 'uires/HallMainPanel/NewHallPanel/HomeHallMain_ext.csb'


def ui_path(path):
    path = path.replace('\\', '/')
    if path.startswith('/') or ':' in path or '..' in PurePosixPath(path).parts:
        raise ValueError(f'Unsafe UI reference: {path}')
    return path if path.startswith('uires/') else 'uires/' + path


def nodes(tree):
    yield tree
    for child in tree['children']:
        yield from nodes(child)


def main(entry=ENTRY, output=None):
    apk = ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != APK_SHA256:
        raise ValueError('Unexpected APK bytes')
    catalogue = read_catalogue(apk)
    entry = ui_path(entry)
    out = Path(output).resolve() if output is not None else ROOT/'analysis/hall/ui-dependencies'
    if not out.resolve().is_relative_to((ROOT/'analysis').resolve()):
        raise ValueError('UI dependency output must stay in analysis')
    out.mkdir(parents=True, exist_ok=True)
    queue, visited, layouts, edges, resources = deque([entry]), set(), [], [], []
    while queue:
        logical = queue.popleft()
        if logical in visited:
            continue
        if len(visited) >= 256:
            raise ValueError('Hall layout budget exceeded')
        visited.add(logical)
        matches = lookup_logical(catalogue, logical)
        if len(matches) != 1:
            layouts.append(dict(path=logical, status='unresolved', matches=len(matches)))
            continue
        target = out/'source'/logical
        target.parent.mkdir(parents=True, exist_ok=True)
        source = extract(apk, catalogue, logical, target, actual)
        reader = Reader(target.read_bytes(), preserve_unknown=True)
        root = reader.scalar('I', 0)
        version = reader.string(reader.field(root, 0))
        if version != '2.1.0.0':
            raise ValueError(f'Unexpected CSB version: {version}')
        try:
            tree = reader.node(reader.pointer(reader.field(root, 3)))
        except ValueError as exc:
            layouts.append(dict(path=logical, status='parser-gap', source=source, error=str(exc)))
            continue
        opaque = [dict(offset=n['offset'], classname=n['classname']) for n in nodes(tree)
                  if n.get('options_status') == 'opaque-unimplemented']
        layouts.append(dict(path=logical, status='partial' if opaque else 'parsed', source=source,
                            node_count=len(reader.seen), opaque_nodes=opaque, tree=tree))
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
                # With plist, path is a frame name: never claim it is a standalone file.
                reference = resource.get('plist') or resource['path']
                resolved = ui_path(reference)
                hits = lookup_logical(catalogue, resolved)
                resources.append(dict(layout=logical, node=node['name'], field=field,
                    reference=resource, lookup_path=resolved, matches=len(hits),
                    kind='atlas-frame' if resource.get('plist') else 'file',
                    status='unique-index-match' if len(hits) == 1 else 'unresolved'))
    atlases = {}
    for resource in resources:
        if resource['kind'] != 'atlas-frame' or resource['matches'] != 1:
            continue
        logical = resource['lookup_path']
        if logical not in atlases:
            target = out/'source'/logical
            target.parent.mkdir(parents=True, exist_ok=True)
            source = extract(apk, catalogue, logical, target, actual)
            atlas = plistlib.loads(target.read_bytes())
            texture = atlas.get('metadata', {}).get('textureFileName')
            texture_path = ui_path(texture) if texture else None
            atlases[logical] = dict(source=source, frame_names=set(atlas['frames']),
                frame_count=len(atlas['frames']), texture_path=texture_path,
                texture_matches=len(lookup_logical(catalogue, texture_path)) if texture_path else 0)
        resource['frame_present'] = resource['reference']['path'] in atlases[logical]['frame_names']
    for atlas in atlases.values():
        del atlas['frame_names']
    summary = dict(layouts=len(layouts), parsed=sum(x['status']=='parsed' for x in layouts),
        layout_status=dict(Counter(x['status'] for x in layouts)),
        opaque_nodes=sum(len(x.get('opaque_nodes', [])) for x in layouts),
        nodes=sum(x.get('node_count', 0) for x in layouts), project_edges=len(edges),
        resource_references=len(resources), resource_status=dict(Counter(x['status'] for x in resources)),
        unique_resource_paths=len({x['lookup_path'] for x in resources}),
        atlas_frame_checks=dict(Counter(str(x['frame_present']) for x in resources if 'frame_present' in x)))
    report = dict(apk_sha256=actual, entry=entry, summary=summary, layouts=layouts,
        project_edges=edges, resources=resources, atlases=atlases,
        evidence_kind='Local extraction and bounded static parser; not REA runtime evidence',
        limitations=['UI root prefix resolution only; unresolved references may use another mount',
            'Atlas frame membership checked for explicit plist references; pixels not decoded',
            'Unknown class options preserved opaque; only their common NodeTree children traversed',
            'No animation timeline, runtime visibility, responsive layout or button behavior executed'])
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
