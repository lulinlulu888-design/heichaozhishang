"""Validate/import the original worldline page and unused chapter templates.

--validate-only runs in normal Python.  Import requires full UE5.8 Editor Slate
for original FontFace files.  Only /Game/Recovered/Worldline/UI is written.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/'analysis/unreal/worldline-ui/layout.json'
DEST='/Game/Recovered/Worldline/UI'
REPORT=ROOT/'analysis/unreal/worldline-ui/import-result.json'
PINNED_LAYOUT='8afc937db8a3cc13ddde0bc771995734895b590828b70454444d7b9e282007ef'


def validate():
    raw=INPUT.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=PINNED_LAYOUT:
        raise ValueError('Source layout/policy changed; review before import')
    layout=json.loads(raw)
    if layout['schemaVersion']!=1 or layout['canvas']['drawOrigin']!='top-left':
        raise ValueError('Unknown worldline draw convention')
    if layout['progressBinding']['available'] or layout['progressBinding']['chapterInstances']!=0:
        raise ValueError('Unverified original chapter state must not be inferred')
    for row in layout['sources']:
        path=Path(row['csb']).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['source']['sha256']:
            raise ValueError('Original CSB identity mismatch')
    for row in layout['sprites']+layout['fonts']:
        field,sha_field=('png','pngSha256') if 'png' in row else ('ttf','sha256')
        path=Path(row[field]).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=row[sha_field]:
            raise ValueError('Original resource identity mismatch')
        if 'png' in row:
            data=path.read_bytes()
            if data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR' or list(struct.unpack('>II',data[16:24]))!=row['size']:
                raise ValueError('Original source image dimensions drifted')
    if len(layout['templates'])!=3:
        raise ValueError('Original chapter template definitions missing')
    sprite_ids={r['id'] for r in layout['sprites']}
    font_ids={r['id'] for r in layout['fonts']}
    for item in layout['page']['items']:
        if item['kind']=='sprite' and item['spriteId'] not in sprite_ids:
            raise ValueError('Original page sprite missing')
        if item['kind']=='text' and item['fontId'] not in font_ids:
            raise ValueError('Original page typeface missing')
        if 'chapteritem_' in item['layout'].lower() or 'chaperitem_' in item['layout'].lower():
            raise ValueError('Do not instantiate authored chapter states into player page')
    return layout,sha


def main(validate_only=False):
    layout,sha=validate()
    summary=dict(passed=True,validationOnly=validate_only,layoutSha256=sha,
                 pageDrawItems=len(layout['page']['items']),textures=len(layout['sprites']),
                 fontFaces=len(layout['fonts']),chapterTemplateDefinitions=3,chapterInstances=0,
                 progressAvailable=False)
    if validate_only:
        print(json.dumps(summary,ensure_ascii=False))
        return
    import unreal
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import import_hall_ui
    if '-run=' in unreal.SystemLibrary.get_command_line().lower():
        raise RuntimeError('Use full Editor -ExecutePythonScript for FontFace import')
    # Reuse the common original image/font import policy; its target is scoped
    # to this distinct worldline folder, never the existing hall DataAsset.
    import_hall_ui.DEST=DEST
    sprites={r['id']:import_hall_ui.import_one(r,'Texture2D') for r in layout['sprites']}
    fonts={r['id']:import_hall_ui.import_one(r,'FontFace') for r in layout['fonts']}
    cls=unreal.load_class(None,'/Script/Hczs.HczsHallLayoutAsset')
    if not cls:
        raise RuntimeError('Build HczsEditor before import')
    package=DEST+'/WorldlineLayout'
    asset=unreal.load_asset(package) if unreal.EditorAssetLibrary.does_asset_exist(package) else None
    if asset:
        if asset.get_editor_property('SourceLayoutSha256')!=sha:
            raise RuntimeError('Existing worldline layout has a different reviewed identity')
    else:
        factory=unreal.DataAssetFactory()
        factory.set_editor_property('data_asset_class',cls)
        asset=unreal.AssetToolsHelpers.get_asset_tools().create_asset('WorldlineLayout',DEST,cls,factory)
    if not asset:
        raise RuntimeError('Cannot create original worldline DataAsset')
    runtime=dict(schemaVersion=1,canvas=layout['canvas'],entry=layout['entry'],items=layout['page']['items'],
                 controls=layout['page']['controls'],templates=layout['templates'],
                 progressBinding=layout['progressBinding'],backgroundAuthority=layout['backgroundAuthority'])
    asset.set_editor_property('LayoutJson',json.dumps(runtime,ensure_ascii=False))
    asset.set_editor_property('SourceLayoutSha256',sha)
    asset.set_editor_property('Sprites',sprites)
    asset.set_editor_property('Fonts',fonts)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset,only_if_is_dirty=False):
        raise RuntimeError('Cannot save original worldline DataAsset')
    reloaded=unreal.load_asset(package)
    if len(reloaded.get_editor_property('Sprites'))!=len(sprites) or len(reloaded.get_editor_property('Fonts'))!=len(fonts):
        raise RuntimeError('Worldline resource references failed saved readback')
    summary.update(validationOnly=False,engine=unreal.SystemLibrary.get_engine_version(),asset=asset.get_path_name(),
                   sourceImages={k:dict(asset=v.get_path_name(),size=[v.blueprint_get_size_x(),v.blueprint_get_size_y()]) for k,v in sprites.items()},
                   sourceFonts={k:v.get_path_name() for k,v in fonts.items()},
                   originalRuntimeExecuted=False,localProgressInferred=False)
    REPORT.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    unreal.log('HCZS worldline static source UI imported: '+str(REPORT))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    main(args.validate_only)
