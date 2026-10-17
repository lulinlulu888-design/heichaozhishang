"""Import the pinned PCM for Future's show, shield and buff skill-bank cues."""
import hashlib
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
PCM = ROOT / 'analysis/characters/hero-003/battle-actions/source/pcm'
DEST = '/Game/Recovered/Audio/Future'
CUES = (
    ('815007610', 'c354625b0505ac366aadce2a41d252efb3f7583d034bbbef2115d1660415e64f', 'FutureShow_815007610'),
    ('787477600', '9934894af2d1ba08046e5ec83cbd43f5130243dc60b66fb2f119778f07f1a3b9', 'FutureShield_787477600'),
    ('132220398', 'ef2aa2a2e330a6b2890d87863ba7ceccc53ba2fe11beec53c0477859a0f49e39', 'FutureBuff_132220398'),
)


def run():
    for source_id, digest, name in CUES:
        wav = PCM / (source_id + '.wav')
        actual = hashlib.sha256(wav.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError('Future PCM changed: ' + source_id)
        package = DEST + '/' + name
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            old = unreal.load_asset(package)
            if old.get_class().get_name() != 'SoundWave' or unreal.EditorAssetLibrary.get_metadata_tag(old, 'HczsSourceSHA256') != digest:
                raise RuntimeError('Existing Future sound does not match the pinned PCM: ' + name)
            unreal.log('HCZS future sound reused ' + package)
            continue
        task = unreal.AssetImportTask()
        for key, value in [('filename', str(wav)), ('destination_path', DEST), ('destination_name', name),
                           ('automated', True), ('replace_existing', False), ('save', False)]:
            task.set_editor_property(key, value)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        objects = [item for item in task.get_objects() if item.get_class().get_name() == 'SoundWave']
        if len(objects) != 1:
            raise RuntimeError('Future SoundWave import failed: ' + name)
        sound = objects[0]
        unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsSourceSHA256', digest)
        unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsWwiseSourceId', source_id)
        if not unreal.EditorAssetLibrary.save_loaded_asset(sound, only_if_is_dirty=False):
            raise RuntimeError('Cannot save Future sound: ' + name)
        unreal.log('HCZS future sound imported name=%s duration=%.3f' % (name, sound.get_editor_property('duration')))
    unreal.SystemLibrary.execute_console_command(None, 'QUIT_EDITOR')


if __name__ == '__main__':
    run()
