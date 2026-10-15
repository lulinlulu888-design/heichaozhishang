"""Project the complete UseRole=1 display directory from pinned module 8995."""
import hashlib
import json
from pathlib import Path
from extract_game_data import export_table
from extract_texture_samples import APK_SHA256

ROOT = Path(__file__).resolve().parents[1]
DECODED = '1998f8eb7ff9598936b27e61197f96b364a305c01f0f1ca6d1481aba716b6ffb'
PAYLOAD = '04f68a25876383d410811c454260c3d8f058c08fa573e144fe1c16263d5f8dfb'
PROJECTION = 'c7dd949b6398079ca1c5fefc1417a66ee00bb2491d3b44509420b79d928fdcba'
ELSA_MODEL = '823397c87ae22bbdaa1fc20b07352da0b2b3a252d0f755fb1998dd5d2578b193'


def elsa_hall_evidence():
    """Verify existing actual UE results, without running UE or importing assets again.

    These are ordinary-tool reconstruction evidence, not REA Evidence records.
    Server capability remains a reviewed code policy; JSON cannot grant heroes.
    """
    reports = {}
    references = []
    for name, relative in (
            ('readback', 'analysis/unreal/plan/import-readback-elsa.json'),
            ('editor', 'analysis/unreal/plan/editor-open-elsa.json'),
            ('pose', 'analysis/unreal/pose/comparison-after.json')):
        raw = (ROOT / relative).read_bytes()
        reports[name] = json.loads(raw)
        references.append(dict(path=relative, sha256=hashlib.sha256(raw).hexdigest()))
    readback, editor, pose = (reports[name] for name in ('readback', 'editor', 'pose'))
    model_path = ROOT / 'analysis/elsa-hall/elsa-hall-idle.colour-reference.glb'
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != ELSA_MODEL:
        raise ValueError('Reviewed Elsa hall model changed')
    assets = readback.get('assets', [])
    if (readback.get('schema') != 'hczs-unreal-import-readback-v1'
            or not readback.get('passed') or readback.get('failures') != []
            or not readback.get('validation', {}).get('engine_asset_readback_executed')
            or not readback.get('validation', {}).get('source_inputs_byte_identical')
            or len(assets) != 1 or assets[0].get('id') != 'elsa'
            or assets[0].get('source_sha256') != ELSA_MODEL):
        raise ValueError('Actual Elsa UE import readback is incomplete')
    meshes = [o for o in assets[0]['objects'] if o['class_name'] == 'SkeletalMesh']
    animations = [o for o in assets[0]['objects'] if o['class_name'] == 'AnimSequence']
    if (len(meshes) != 1 or meshes[0].get('bone_count') != 180
            or meshes[0].get('path') != '/Game/Recovered/Elsa/elsa.elsa'
            or len(animations) != 1 or animations[0].get('play_length_seconds') != 4.0
            or animations[0].get('source_animation_names') != ['home_stand_idle_1']
            or animations[0].get('skeleton') != meshes[0].get('skeleton')):
        raise ValueError('Elsa preview must use the original hall idle and matching skeleton')
    actors = [a for a in pose.get('ue_actors', []) if a.get('label') == 'HCZS_elsa']
    if (editor.get('elsa_bones') != 180 or not editor.get('camera_pilot_called')
            or 'L_ElsaHallAlignedPreview.' not in editor.get('world', '')
            or len(actors) != 1 or abs(actors[0]['actor_rotation']['pitch']) > 1e-5
            or abs(actors[0]['actor_rotation']['roll']) > 1e-5
            or not pose.get('validation', {}).get('unreal_readback_compared')
            or pose.get('max_glb_vs_acl_matrix_error') != 0):
        raise ValueError('Actual aligned Elsa Editor preview evidence is incomplete')
    return dict(heroId=1, renderer='unreal-editor', platform='windows',
                sourceAnimation='home_stand_idle_1', sourceModelSha256=ELSA_MODEL,
                evidenceKind='ordinary-tool-reconstruction-evidence', references=references,
                fullOriginalVisualsVerified=False, packagedPlatformsVerified=False)


def main():
    table = export_table(8995)
    source = table['source']
    if (source['index'], source['apk_member'], source['decoded_sha256'], source['payload_sha256']) != (
            8995, 'assets/script.npk', DECODED, PAYLOAD):
        raise ValueError('Original hero module identity changed')
    heroes = sorted((dict(id=row['id'], name=row['fields']['NAME']) for row in table['rows']
                     if row['fields'].get('UseRole') == 1), key=lambda hero: hero['id'])
    digest = hashlib.sha256(json.dumps(heroes, ensure_ascii=False, separators=(',', ':')).encode('utf8')).hexdigest()
    if len(heroes) != 35 or table['total_source_rows'] != 228 or digest != PROJECTION:
        raise ValueError('Reviewed complete hero directory changed')
    result = dict(schema='hczs-server-heroes-v1', apkSha256=APK_SHA256, source=source,
                  selection=dict(field='UseRole', equals=1, totalSourceRows=228, selectedRows=35),
                  projectionSha256=digest, heroes=heroes,
                  recoveryPolicy='hczs-hall-preview-policy-v2',
                  reconstructionEvidence=[elsa_hall_evidence()])
    target = ROOT / 'analysis/game-data/heroes.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(dict(file=str(target), heroes=len(heroes), projectionSha256=digest)))


if __name__ == '__main__':
    main()
