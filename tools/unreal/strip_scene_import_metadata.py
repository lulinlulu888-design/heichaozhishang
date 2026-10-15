"""Remove editor import metadata from packaged maps, preserving a byte-for-byte backup."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import unreal

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'clients/unreal5 5.8'
MAPS = [
    '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview',
    '/Game/Recovered/Battle/Maps/L_TutorialBattle',
    '/Game/Recovered/City/Maps/L_City2077Preview',
]
APPLY = '-HczsStripImportMetadata' in unreal.SystemLibrary.get_command_line()
STAMP = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
OUT = ROOT / 'analysis/unreal/android-build' / ('scene-metadata-' + STAMP)
OUT.mkdir(parents=True, exist_ok=False)
records = []
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for package in MAPS:
    source = PROJECT / 'Content' / (package.removeprefix('/Game/') + '.umap')
    backup = OUT / source.name
    shutil.copy2(source, backup)
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(backup.read_bytes()).digest()
    if not levels.load_level(package):
        raise RuntimeError('Cannot load ' + package)
    world = editor.get_editor_world()
    owners = [world.get_world_settings()]
    for actor in actors.get_all_level_actors():
        owners.extend(actor.get_components_by_class(unreal.ActorComponent))
    changes = []
    for owner in owners:
        try:
            data = list(owner.get_editor_property('asset_user_data'))
        except Exception:
            continue  # Not every component implements asset user data.
        removed = [v for v in data if v and v.get_class().get_path_name().startswith('/Script/InterchangeImport.')]
        if not removed:
            continue
        changes.append({'owner': owner.get_path_name(), 'classes': [v.get_class().get_path_name() for v in removed]})
        if APPLY:
            owner.set_editor_property('asset_user_data', [v for v in data if v not in removed])
    if APPLY and changes and not levels.save_current_level():
        raise RuntimeError('Cannot save ' + package)
    records.append({'map': package, 'backup': str(backup), 'changed': changes})
(OUT / 'result.json').write_text(json.dumps({'applied': APPLY, 'maps': records}, indent=2), encoding='utf8')
unreal.log('HCZS scene import metadata report: ' + str(OUT))
