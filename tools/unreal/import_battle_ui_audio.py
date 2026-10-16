"""Import the routed ui_battle deal cues (UI_DRAWCARD, UI_FAPAI_B) as USoundWave assets.

Run tools/extract_ui_battle_audio.py first, then this script inside the full Unreal Editor.
Only PCM previews listed by the verified route report are imported; nothing is re-mixed.
"""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / 'analysis/battle-ui/audio/fapai-routes.json'
DEST = '/Game/Recovered/Audio/UI'
REPORT = ROOT / 'analysis/unreal/battle-ui/audio-import-result.json'
EXPECTED = {'UI_DRAWCARD': [46920884, 81447368, 1061850655], 'UI_FAPAI_B': [1050791224]}


def routed_sources(report):
    found = {}
    for key, route in report['routes'].items():
        play = [a for a in route['actions'] if a['cls'] == 'CAkActionPlay']
        if len(play) != 1:
            raise ValueError('expected one play action for ' + key)
        found[key] = sorted(s['source_id'] for s in play[0]['sounds'])
    if found != {k: sorted(v) for k, v in EXPECTED.items()}:
        raise ValueError('route report no longer matches the client cue table: %s' % found)
    return sorted({s for v in found.values() for s in v})


def import_one(source_id, row):
    wav = ROOT / f'analysis/battle-ui/audio/pcm/{source_id}.wav'
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    if digest != row['pcm_sha256']:
        raise ValueError(f'PCM preview changed: {source_id}')
    name = f'UiBattle_{source_id}'
    package = f'{DEST}/{name}'
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        old = unreal.load_asset(package)
        if old.get_class().get_name() != 'SoundWave' or unreal.EditorAssetLibrary.get_metadata_tag(old, 'HczsSourceSHA256') != digest:
            raise RuntimeError('Existing asset retained: source differs at ' + package)
        return dict(source=source_id, asset=package, reused=True, duration=old.get_editor_property('duration'))
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(wav)), ('destination_path', DEST), ('destination_name', name),
                       ('automated', True), ('replace_existing', False), ('save', False)]:
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects = [o for o in task.get_objects() if o.get_class().get_name() == 'SoundWave']
    if len(objects) != 1:
        raise RuntimeError('SoundWave import failed: ' + package)
    sound = objects[0]
    unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsSourceSHA256', digest)
    unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsWwiseSourceId', str(source_id))
    if not unreal.EditorAssetLibrary.save_loaded_asset(sound, only_if_is_dirty=False):
        raise RuntimeError('Cannot save ' + package)
    duration = sound.get_editor_property('duration')
    if abs(duration - row['duration_seconds']) > 0.01:
        raise RuntimeError(f'Imported duration differs: {source_id} {duration} vs {row["duration_seconds"]}')
    return dict(source=source_id, asset=package, reused=False, duration=duration)


def run():
    report = json.loads(ROUTES.read_text('utf8'))
    rows = [import_one(s, report['media'][str(s)]) for s in routed_sources(report)]
    result = dict(passed=True, routes_sha256=hashlib.sha256(ROUTES.read_bytes()).hexdigest(), assets=rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf8')
    unreal.log('HCZS UI audio import passed: %d assets' % len(rows))
    return result


if __name__ == '__main__':
    run()
