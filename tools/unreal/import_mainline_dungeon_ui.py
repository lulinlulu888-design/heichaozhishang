"""Import the prepared mainline dungeon panel into the worldline UI folder.

--validate-only runs in normal Python. Import needs the full UE 5.8 editor.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'analysis/unreal/mainline-dungeon-ui/layout.json'
DEST = '/Game/Recovered/Worldline/Dungeon/UI'
REPORT = ROOT / 'analysis/unreal/mainline-dungeon-ui/import-result.json'


def validate():
    raw = INPUT.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    layout = json.loads(raw)
    if layout['schemaVersion'] != 1 or layout['entry'].endswith('MainLineDungeonPanel_ext.csb') is False:
        raise ValueError('Unexpected dungeon layout')
    if layout['challengeId'] != 3997:
        raise ValueError('Dungeon page must describe challenge 3997')
    names = {item.get('nodeName') for item in layout['page']['items']}
    if 'TxtChallenNum' not in names or 'TxtDesc' not in names or 'BtnGo' not in names:
        raise ValueError('Dungeon info controls missing')
    actions = {row['action'] for row in layout['page']['controls']}
    if actions != {'explore', 'back'}:
        raise ValueError('Unexpected dungeon controls: ' + str(sorted(actions)))
    for row in layout['sprites'] + layout['fonts']:
        field, sha_field = ('png', 'pngSha256') if 'png' in row else ('ttf', 'sha256')
        path = Path(row[field]).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != row[sha_field]:
            raise ValueError('Dungeon resource identity mismatch')
        if 'png' in row:
            data = path.read_bytes()
            if data[:8] != b'\x89PNG\r\n\x1a\n' or list(struct.unpack('>II', data[16:24])) != row['size']:
                raise ValueError('Dungeon image dimensions drifted')
    return layout, sha


def main(validate_only=False):
    layout, sha = validate()
    summary = dict(passed=True, validationOnly=validate_only, layoutSha256=sha, drawItems=len(layout['page']['items']))
    if validate_only:
        print(json.dumps(summary, ensure_ascii=False))
        return
    import unreal
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import import_hall_ui
    import_hall_ui.DEST = DEST
    sprites = {row['id']: import_hall_ui.import_one(row, 'Texture2D') for row in layout['sprites']}
    fonts = {row['id']: import_hall_ui.import_one(row, 'FontFace') for row in layout['fonts']}
    cls = unreal.load_class(None, '/Script/Hczs.HczsHallLayoutAsset')
    if not cls:
        raise RuntimeError('Build HczsEditor before import')
    package = DEST + '/DungeonLayout'
    asset = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if not asset:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class', cls)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('DungeonLayout', DEST, cls, factory)
    if not asset:
        raise RuntimeError('Cannot create dungeon layout')
    runtime = dict(schemaVersion=1, canvas=layout['canvas'], entry=layout['entry'], challengeId=layout['challengeId'],
                   items=layout['page']['items'], controls=layout['page']['controls'])
    asset.set_editor_property('LayoutJson', json.dumps(runtime, ensure_ascii=False))
    asset.set_editor_property('SourceLayoutSha256', sha)
    asset.set_editor_property('Sprites', sprites)
    asset.set_editor_property('Fonts', fonts)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
        raise RuntimeError('Cannot save dungeon layout')
    summary.update(validationOnly=False, asset=asset.get_path_name())
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', 'utf8')
    unreal.log('HCZS dungeon panel imported: ' + str(REPORT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    main(args.validate_only)
