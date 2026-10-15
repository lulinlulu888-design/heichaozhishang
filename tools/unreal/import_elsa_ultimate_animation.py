"""Import original crit_4 onto the existing battle skeleton, animations only.

Run in UE Python with -HczsUltimateAnimationApply for first import. Without the
flag, read back the existing import. Never overwrite assets or alter the map.
"""
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_recovered_assets import make_pipeline

SOURCE = ROOT / 'analysis/battle-visual/elsa-ultimate'
DEST = '/Game/Recovered/Battle/ElsaUltimate'
SKELETON = '/Game/Recovered/Battle/Elsa/elsa_battle_Skeleton.elsa_battle_Skeleton'


def main():
    import unreal
    report = json.loads((SOURCE / 'export-report.json').read_text('utf8'))
    glb = SOURCE / 'elsa-ultimate.glb'
    if hashlib.sha256(glb.read_bytes()).hexdigest() != report['sha256']:
        raise ValueError('Verified ultimate GLB changed')
    skeleton = unreal.load_asset(SKELETON)
    if not isinstance(skeleton, unreal.Skeleton):
        raise ValueError('Existing battle skeleton missing')
    skeleton_file = ROOT / 'clients/unreal5 5.8/Content/Recovered/Battle/Elsa/elsa_battle_Skeleton.uasset'
    skeleton_hash = hashlib.sha256(skeleton_file.read_bytes()).hexdigest()
    paths = unreal.EditorAssetLibrary.list_assets(DEST, recursive=True, include_folder=False)
    apply = '-HczsUltimateAnimationApply' in unreal.SystemLibrary.get_command_line()
    if apply:
        if paths:
            raise ValueError('Import destination already populated; use read-only verification')
        pipeline, overrides = make_pipeline(unreal, {'import_operation': 'asset'})
        common = pipeline.get_editor_property('common_skeletal_meshes_and_animations_properties')
        common.set_editor_property('try_auto_select_skeleton', False)
        common.set_editor_property('skeleton', skeleton)
        common.set_editor_property('import_only_animations', True)
        params = unreal.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        params.set_editor_property('replace_existing', False)
        params.set_editor_property('override_pipelines', overrides)
        manager = unreal.InterchangeManager.get_interchange_manager_scripted()
        source = unreal.InterchangeManager.create_source_data(str(glb))
        result = manager.import_asset(DEST, source, params)
        if not (result[0] if isinstance(result, tuple) else result):
            raise RuntimeError('UE rejected the source animation import')
        paths = unreal.EditorAssetLibrary.list_assets(DEST, recursive=True, include_folder=False)
    objects = [unreal.load_asset(path) for path in paths]
    if len(objects) != 1 or not isinstance(objects[0], unreal.AnimSequence):
        raise ValueError('Expected exactly one animation and no duplicated mesh/material/skeleton')
    animation = objects[0]
    if animation.get_editor_property('skeleton') != skeleton or abs(animation.get_play_length() - 7.2) > 0.001:
        raise ValueError('Imported skeleton or duration differs from source')
    if apply and not unreal.EditorAssetLibrary.save_loaded_asset(animation, only_if_is_dirty=False):
        raise RuntimeError('Animation save failed')
    if hashlib.sha256(skeleton_file.read_bytes()).hexdigest() != skeleton_hash:
        raise ValueError('Existing skeleton file changed unexpectedly')
    return {'passed': True, 'applied': apply, 'animation': animation.get_path_name(),
            'skeleton': SKELETON, 'seconds': animation.get_play_length(),
            'sourceSha256': report['sha256'], 'existingSkeletonFileUnchanged': True,
            'actualPlaybackVerified': False, 'videoCueIntegrationVerified': False}


if __name__ == '__main__':
    destination = ROOT / 'analysis/unreal/ultimate-videos/animation-import.json'
    try:
        outcome = main()
    except Exception:
        outcome = {'passed': False, 'error': traceback.format_exc()}
        destination.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding='utf8')
        raise
    destination.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(outcome, ensure_ascii=False))
