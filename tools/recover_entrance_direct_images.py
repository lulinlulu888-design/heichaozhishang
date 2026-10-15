"""Recover six original normal/elite/boss entrance textures without UE execution.

These names are absent from the source VT config. Their PNG requests resolve to
direct PKM-named KTX resources through the existing NeoX PNG-to-PKM mapping.
This tool reuses the source catalogue, CSB reader and ASTC decoder; no redrawing,
resizing, alpha replacement, client writes or synthetic texture headers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from decode_ktx import DEFAULT_DECODER, convert, parse_ktx
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from inspect_battle_rules import read_module
from inspect_battle_ui_layout import Reader
from neox_resource_paths import lookup_logical, parse_vt_config, read_catalogue
from trace_first_encounter import inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/battle-ui/entrance/direct'
PREFIX = 'CommonRes/BigSan/Project/Fight/'
WANTED = {
    PREFIX + 'fight_turn_bg_Color_03.png': 3340,
    PREFIX + 'fight_turn_bg_02.png': 4842,
    PREFIX + 'fight_turn_bg_01.png': 2990,
    PREFIX + 'fight_turn_bg_Color_01.png': 1367,
    PREFIX + 'fight_turn_bg.png': 2579,
    PREFIX + 'fight_turn_bg_Color.png': 1782,
}
LAYOUT_MODULES = {'normal': 3700, 'elite': 681, 'boss': 6739}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nodes(tree):
    yield tree
    for child in tree['children']:
        yield from nodes(child)


def texture_keyframes(reader, root):
    """Read only TextureFrame resources; other timeline variants stay untouched."""
    def vector(table, index):
        pointer = reader.pointer(reader.field(table, index))
        if not pointer:
            return []
        count = reader.scalar('I', pointer)
        if count > 10000:
            raise ValueError('Entrance timeline vector exceeds bounded reader')
        return [reader.pointer(pointer + 4 + i * 4) for i in range(count)]

    action = reader.pointer(reader.field(root, 4))
    for timeline in vector(action, 2):
        tag_field = reader.field(timeline, 1)
        action_tag = reader.scalar('i', tag_field) if tag_field else 0
        for frame in vector(timeline, 2):
            texture = reader.pointer(reader.field(frame, 3))
            if not texture:
                continue
            index_field = reader.field(texture, 0)
            yield {
                'origin': 'texture-keyframe', 'actionTag': action_tag,
                'frameIndex': reader.scalar('i', index_field) if index_field else 0,
                'property': reader.string(reader.field(timeline, 0)),
                'resource': reader.resource(reader.pointer(reader.field(texture, 2))),
            }


def recover(output_directory=OUT):
    """Return a source-bound six-image report; write only below analysis."""
    out = Path(output_directory).resolve()
    if not out.is_relative_to((ROOT / 'analysis').resolve()):
        raise ValueError('Recovered entrance textures must stay below analysis')
    apk = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('APK identity changed')
    out.mkdir(parents=True, exist_ok=True)
    catalogue = read_catalogue(apk)
    script_rows = inventory()
    refs, source_layouts = {}, {}
    for label, module_index in LAYOUT_MODULES.items():
        source_row = script_rows[module_index]
        module = read_module(source_row)
        csb_names = [c.decode('utf8') for c in module['consts']
                     if isinstance(c, bytes) and c.endswith(b'.csb')]
        if len(csb_names) != 1:
            raise ValueError('Ambiguous entrance CSB binding: ' + label)
        csb_path = out / 'source' / (label + '.csb')
        csb_source = extract(apk, catalogue, csb_names[0], csb_path, APK_SHA256)
        reader = Reader(csb_path.read_bytes(), preserve_unknown=True)
        root = reader.scalar('I', 0)
        if reader.string(reader.field(root, 0)) != '2.1.0.0':
            raise ValueError('Unsupported entrance layout schema')
        tree = reader.node(reader.pointer(reader.field(root, 3)))
        found = set()
        bindings = [{'origin': 'node', 'node': node['name'],
                     'actionTag': node.get('action_tag'), 'resource': node.get('resource', {})}
                    for node in nodes(tree)]
        bindings.extend(texture_keyframes(reader, root))
        for binding in bindings:
            ref = binding['resource']
            if ref.get('path') in WANTED:
                if ref.get('plist'):
                    raise ValueError('Expected direct resource became atlas-backed')
                found.add(ref['path'])
                refs.setdefault(ref['path'], []).append({
                    'layout': label, 'scriptModule': module_index,
                    'csbSha256': csb_source['sha256'],
                    **binding,
                })
        if not found:
            raise ValueError('No expected direct images in entrance layout: ' + label)
        source_layouts[label] = {'sourceScript': source_row, 'sourceCsb': csb_source,
                                 'directImagePaths': sorted(found)}
    if set(refs) != set(WANTED):
        raise ValueError('Expected six source CSB image bindings')

    config_path = out / 'source/vt_config.jsondata'
    config_source = extract(apk, catalogue, 'packed_png/vt_data/vt_config.jsondata',
                            config_path, APK_SHA256)
    config = parse_vt_config(config_path.read_bytes())
    frames = []
    for requested, expected_index in WANTED.items():
        logical = 'uires/' + requested
        matches = [r for r in config['fullPathToPng'] if r['key'].lower() == logical.lower()]
        if matches:
            raise ValueError('Expected direct image now has a VT alias')
        if lookup_logical(catalogue, logical):
            raise ValueError('Unexpected original PNG entry; review loader route')
        texture_logical = logical.removesuffix('.png') + '.pkm'
        entries = lookup_logical(catalogue, texture_logical)
        if len(entries) != 1 or entries[0]['index'] != expected_index:
            raise ValueError('Pinned direct texture catalogue entry changed')
        name = Path(requested).stem
        raw_path = out / 'source' / (name + '.ktx')
        texture_source = extract(apk, catalogue, texture_logical, raw_path, APK_SHA256)
        ktx = parse_ktx(raw_path.read_bytes())
        decoded = convert([raw_path], out / 'decoded' / name, DEFAULT_DECODER)
        outputs = decoded['textures'][0]['outputs']
        if len(outputs) != 1:
            raise ValueError('Expected one image per source texture')
        decoded_path = ROOT / outputs[0]['png']
        output = out / (name + '.png')
        # Copy the decoder's PNG bytes, preserving pixels and its color metadata.
        output.write_bytes(decoded_path.read_bytes())
        with Image.open(output) as image:
            rgba = image.convert('RGBA')
            size = list(image.size)
            alpha_extrema = list(rgba.getchannel('A').getextrema())
            nontransparent_bounds = rgba.getchannel('A').getbbox()
        frames.append({
            'name': name, 'requestedResource': requested,
            'logicalRequest': logical, 'resolvedTexture': texture_logical,
            'bindings': refs[requested], 'vtAliasMatches': [],
            'textureSource': texture_source, 'ktx': ktx,
            'decoded': outputs[0], 'size': size, 'alphaExtrema': alpha_extrema,
            'nontransparentBounds': nontransparent_bounds,
            'png': str(output.relative_to(ROOT)), 'sha256': sha(output),
        })

    existing_layouts = []
    for name in ('FightSmallCard', 'OwnCardArea'):
        path = ROOT / 'analysis/battle-ui' / (name + '.csb')
        provenance_path = path.with_suffix('.csb.provenance.json')
        if not path.exists() or not provenance_path.exists():
            continue
        provenance = json.loads(provenance_path.read_text('utf8'))
        if provenance['apk_sha256'] != APK_SHA256 or sha(path) != provenance['sha256']:
            raise ValueError('Existing card layout provenance mismatch')
        parsed = path.with_suffix('.source.json')
        existing_layouts.append({
            'name': name, 'csb': str(path.relative_to(ROOT)),
            'provenance': provenance, 'parsedLayout': str(parsed.relative_to(ROOT)),
            'parsedLayoutSha256': sha(parsed) if parsed.exists() else None,
        })
    report = {
        'apkSha256': APK_SHA256,
        'evidenceKind': 'Static source CSB bindings and direct original texture decoding',
        'sourceLayouts': source_layouts,
        'vtConfigSource': config_source, 'frames': frames,
        'existingCardLayouts': existing_layouts,
        'sharedFunctions': ['neox_resource_paths.read_catalogue/lookup_logical',
                            'export_elsa_model.extract', 'decode_ktx.parse_ktx/convert'],
        'limitations': ['No original UI or UE execution; source timeline handled separately.',
                        'No VT tile reconstruction needed for these six resources.',
                        'PNG decoding does not prove runtime material/blend/color fidelity.'],
    }
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                               allow_nan=False) + '\n', 'utf8')
    return report


def main():
    report = recover()
    print(json.dumps({'output': str(OUT), 'frames': [
        {'name': f['name'], 'size': f['size'], 'index': f['textureSource']['index']}
        for f in report['frames']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
