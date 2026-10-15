"""Import only reviewed source picker pixels/fonts and its separate DataAsset."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'analysis/unreal/hall-hero-picker'
PINNED_LAYOUT = 'e16538361d9ed3bb99d3ff2beff0367f2cc3b14fe5600ea144b3c642c1ff39fb'
DEST = '/Game/Recovered/Hall/HeroPicker'


def validate():
    raw = (BASE/'layout.json').read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != PINNED_LAYOUT:
        raise ValueError('Source picker layout differs; review before import')
    payload = json.loads(raw)
    if payload['schemaVersion']!=1 or [h['id'] for h in payload['heroes']]!=[1,3]:
        raise ValueError('Unexpected picker scope')
    controls = {r['action'] for r in payload['controls']}
    if controls != {'hero-confirm','hero-cancel','hero-preview-1','hero-preview-3'}:
        raise ValueError('Source picker controls missing')
    for row in payload['sprites']+payload['fonts']:
        source, expected = (row['png'],row['pngSha256']) if 'png' in row else (row['ttf'],row['sha256'])
        path = Path(source).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Picker source pixel/font changed')
    for row in payload['evidence']['layouts'].values():
        path = Path(row['path']).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Original template evidence changed')
    return payload,sha


def main():
    payload,sha = validate()
    import unreal
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import import_hall_ui
    if '-run=' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use the full Slate Editor for source FontFace import')
    import_hall_ui.DEST = DEST
    sprites = {r['id']:import_hall_ui.import_one(r,'Texture2D') for r in payload['sprites']}
    fonts = {r['id']:import_hall_ui.import_one(r,'FontFace') for r in payload['fonts']}
    cls = unreal.load_class(None,'/Script/Hczs.HczsHallLayoutAsset')
    if not cls:
        raise RuntimeError('Build HczsEditor first')
    package = DEST+'/HallHeroPicker'
    asset = unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if asset:
        if asset.get_editor_property('SourceLayoutSha256')!=sha:
            raise RuntimeError('Existing picker asset retained; reviewed identity differs')
    else:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class',cls)
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('HallHeroPicker',DEST,cls,factory)
    if not asset:
        raise RuntimeError('Cannot create picker layout asset')
    runtime = {k:payload[k] for k in ('schemaVersion','canvas','items','controls','heroes','entry','limitations')}
    asset.set_editor_property('SourceLayoutSha256',sha)
    asset.set_editor_property('LayoutJson',json.dumps(runtime,ensure_ascii=False))
    asset.set_editor_property('Sprites',sprites)
    asset.set_editor_property('Fonts',fonts)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset,only_if_is_dirty=False):
        raise RuntimeError('Cannot save picker asset')
    result = dict(passed=True,asset=asset.get_path_name(),layoutSha256=sha,items=len(payload['items']),
                  sprites=len(sprites),fontFaces=len(fonts),gameplayVerified=False)
    (BASE/'import-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    unreal.log('HCZS source hero picker imported')


if __name__=='__main__':
    if '--validate-only' in sys.argv:
        payload,sha=validate()
        print(json.dumps(dict(passed=True,layoutSha256=sha,items=len(payload['items']))))
    else:
        import unreal
        try:
            main()
        finally:
            if '-HczsImportHeroPicker' in unreal.SystemLibrary.get_command_line():
                unreal.SystemLibrary.quit_editor()
