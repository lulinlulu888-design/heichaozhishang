"""Import the verified 3.7-second battle entrance onto the existing battle skeleton.

Inside UE Python: main(apply=True) imports into an empty owned destination.
main() verifies an existing import without mutation. Never edits a map or actor.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_recovered_assets import make_pipeline, read_glb

SOURCE = ROOT / 'analysis/battle-visual/entrance'
DEST = '/Game/Recovered/Battle/Entrance'
SKELETON = '/Game/Recovered/Battle/Elsa/elsa_battle_Skeleton.elsa_battle_Skeleton'
MESH = '/Game/Recovered/Battle/Elsa/elsa_battle.elsa_battle'
OWNER = 'HCZS.SourceEntranceSHA256'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_plan():
    manifest = json.loads((SOURCE / 'manifest.json').read_text('utf8'))
    report = json.loads((SOURCE / 'export-report.json').read_text('utf8'))
    glb = SOURCE / 'elsa_entrance.glb'
    digest = sha(glb)
    if (manifest['kind'] != 'hczs-battle-entrance' or manifest['ueSkeleton'] != SKELETON
            or manifest['ueDestination'] != DEST or manifest['file'] != glb.name
            or digest != manifest['sha256'] or digest != report['sha256']
            or report['source']['sha256'] != '5edd67050254abc33125ea1390b0cc6d83a5896a3ebf1e3ea72901198e734a51'
            or manifest['durationSeconds'] != 3.7 or manifest['boneCount'] != 180
            or manifest['event1']['ratioLiteral'] != '0.144595'):
        raise ValueError('Verified source entrance manifest/GLB changed')
    doc = read_glb(glb.read_bytes())
    names = [doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']]
    if names != report['boneNames'] or len(names) != 180 or len(doc['animations']) != 1:
        raise ValueError('Entrance source skeleton/animation inventory changed')
    if doc['animations'][0]['name'] != 'fight_idle_show' or len(doc['animations'][0]['channels']) != 540:
        raise ValueError('Incomplete entrance animation channels')
    return manifest, glb, digest, names


def main(apply=False):
    import unreal
    manifest, glb, digest, original_names = source_plan()
    skeleton, mesh = unreal.load_asset(SKELETON), unreal.load_asset(MESH)
    if not isinstance(skeleton, unreal.Skeleton) or not isinstance(mesh, unreal.SkeletalMesh):
        raise ValueError('Existing battle mesh/skeleton missing')
    if mesh.get_editor_property('skeleton') != skeleton:
        raise ValueError('Existing battle mesh uses another skeleton')
    skeleton_file = ROOT / 'clients/unreal5 5.8/Content/Recovered/Battle/Elsa/elsa_battle_Skeleton.uasset'
    mesh_file = ROOT / 'clients/unreal5 5.8/Content/Recovered/Battle/Elsa/elsa_battle.uasset'
    original_hashes = {str(p): sha(p) for p in (skeleton_file, mesh_file)}
    paths = unreal.EditorAssetLibrary.list_assets(DEST, recursive=True, include_folder=False)
    imported = False
    if apply and not paths:
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
        result = manager.import_asset(DEST, unreal.InterchangeManager.create_source_data(str(glb)), params)
        if not (result[0] if isinstance(result, tuple) else result):
            raise RuntimeError('UE rejected entrance animation import')
        paths = unreal.EditorAssetLibrary.list_assets(DEST, recursive=True, include_folder=False)
        imported = True
    objects = [unreal.load_asset(path) for path in paths]
    if len(objects) != 1 or not isinstance(objects[0], unreal.AnimSequence):
        raise ValueError('Expected exactly one entrance AnimSequence; never overwrite other assets')
    animation = objects[0]
    if not imported and unreal.EditorAssetLibrary.get_metadata_tag(animation, OWNER) != digest:
        raise ValueError('Existing asset is not owned by this verified source import')
    if animation.get_editor_property('skeleton') != skeleton or abs(animation.get_play_length() - 3.7) > .001:
        raise ValueError('Entrance skeleton/duration differs from source')
    options = unreal.AnimPoseEvaluationOptions()
    for key, value in {'evaluation_type': unreal.AnimDataEvalType.COMPRESSED,
                       'should_retarget': False, 'extract_root_motion': False,
                       'incorporate_root_motion_into_pose': True,
                       'optional_skeletal_mesh': mesh}.items():
        options.set_editor_property(key, value)
    # UE Interchange replaces spaces in the source skeletal node names with '-'.
    expected_names = {name.replace(' ', '-') for name in original_names}
    samples, prior, motion = [], None, 0.
    for seconds in (0., manifest['event1']['seconds'], 1.85, 3.7):
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(animation, seconds, options)
        if not unreal.AnimPoseExtensions.is_valid(pose):
            raise ValueError('Imported entrance pose cannot be evaluated')
        actual_names = {str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)}
        if actual_names != expected_names:
            raise ValueError('Imported entrance bone names/count differ from battle source')
        positions = []
        for name in sorted(expected_names):
            transform = unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.WORLD)
            position = transform.translation
            positions.extend((position.x, position.y, position.z))
        if not all(math.isfinite(v) for v in positions):
            raise ValueError('Imported entrance contains nonfinite bone positions')
        if prior is not None:
            motion = max(motion, max(abs(a-b) for a, b in zip(positions, prior)))
        prior = positions
        samples.append({'seconds': seconds, 'boneCount': len(actual_names), 'finite': True})
    if motion <= 1e-4:
        raise ValueError('Imported entrance has no observed skeletal motion')
    if imported:
        unreal.EditorAssetLibrary.set_metadata_tag(animation, OWNER, digest)
        if not unreal.EditorAssetLibrary.save_loaded_asset(animation, only_if_is_dirty=False):
            raise RuntimeError('Entrance animation save failed')
    if any(sha(Path(path)) != digest0 for path, digest0 in original_hashes.items()):
        raise ValueError('Existing battle mesh or skeleton was unexpectedly changed')
    return {'passed': True, 'imported': imported, 'animation': animation.get_path_name(),
            'skeleton': SKELETON, 'mesh': MESH, 'seconds': animation.get_play_length(),
            'boneCount': len(expected_names), 'poseSamples': samples,
            'maxBonePositionChange': motion, 'sourceSha256': digest,
            'existingMeshAndSkeletonFilesUnchanged': True,
            'event1': manifest['event1'], 'actualScenePlaybackVerified': False,
            'mapModified': False}


if __name__ == '__main__':
    destination = ROOT / 'analysis/unreal/entrance/animation-import.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        import unreal
        outcome = main('-HczsEntranceAnimationApply' in unreal.SystemLibrary.get_command_line())
    except Exception:
        destination.write_text(json.dumps({'passed': False, 'error': traceback.format_exc()},
                                          ensure_ascii=False, indent=2), 'utf8')
        raise
    destination.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps(outcome, ensure_ascii=False))
