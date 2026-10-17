"""Import the pinned PCM of ailisha_show_2 (Wwise source 580663517).

The music ags plays this event at fight_idle_show ratio 0.0183. Bank volume is
the sound node's -6 dB plus its actor-mixer -1.5 dB. Bus and master are not applied.
"""
import hashlib
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
WAV = ROOT / 'analysis/battle-visual/elsa-audio/pcm/580663517.wav'
SHA = 'bb7b6e7c9f0420670c593366261063f14fbc0b36752bf1a1599822f3921bee5a'
DEST = '/Game/Recovered/Audio/Elsa'
NAME = 'ElsaShow_580663517'


def run():
    digest = hashlib.sha256(WAV.read_bytes()).hexdigest()
    if digest != SHA:
        raise ValueError('Entrance PCM changed')
    package = DEST + '/' + NAME
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        old = unreal.load_asset(package)
        if old.get_class().get_name() != 'SoundWave' or unreal.EditorAssetLibrary.get_metadata_tag(old, 'HczsSourceSHA256') != digest:
            raise RuntimeError('Existing entrance sound does not match the pinned PCM')
        unreal.log('HCZS entrance sound reused ' + package)
        unreal.SystemLibrary.execute_console_command(None, 'QUIT_EDITOR')
        return
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(WAV)), ('destination_path', DEST), ('destination_name', NAME),
                       ('automated', True), ('replace_existing', False), ('save', False)]:
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects = [o for o in task.get_objects() if o.get_class().get_name() == 'SoundWave']
    if len(objects) != 1:
        raise RuntimeError('Entrance SoundWave import failed')
    sound = objects[0]
    unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsSourceSHA256', digest)
    unreal.EditorAssetLibrary.set_metadata_tag(sound, 'HczsWwiseSourceId', '580663517')
    if not unreal.EditorAssetLibrary.save_loaded_asset(sound, only_if_is_dirty=False):
        raise RuntimeError('Cannot save entrance sound')
    unreal.log('HCZS entrance sound imported duration=%.3f' % sound.get_editor_property('duration'))
    unreal.SystemLibrary.execute_console_command(None, 'QUIT_EDITOR')


if __name__ == '__main__':
    run()
