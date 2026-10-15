"""Stage verified original prologue assets for the shared Cocos client."""
import hashlib
import json
import shutil
from pathlib import Path
from export_elsa_model import split_glb

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'legacy/cocos-poc/assets/resources/recovered/prologue'


def main():
    records = []
    from trace_battle_orientation import main as trace_orientation
    trace_orientation()
    orientation_source = ROOT/'analysis/battle-visual/battle-orientation/player-orientation.json'
    DEST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(orientation_source, DEST/'player-orientation.json')
    records.append(dict(source=str(orientation_source), destination=str(DEST/'player-orientation.json'),
                        sha256=hashlib.sha256(orientation_source.read_bytes()).hexdigest()))
    for folder, name, target in [('scene-export', 'prologue-scene.glb', 'scene/scene.glb'),
                                 ('actor-battle-idle', 'prologue-elsa.glb', 'actor/actor.glb'),
                                 ('weapon', 'elsa-weapon-static.glb', 'weapon/weapon.glb'),
                                 ('enemy-reactions', 'enemy-reactions.glb', 'enemy/enemy.glb')]:
        source = ROOT/'analysis/battle-visual'/folder/name
        report = json.loads((source.parent/('static-export-report.json' if folder == 'weapon' else 'report.json')).read_text('utf8'))
        blob = source.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        if digest != report['glb_sha256']:
            raise ValueError('Source GLB differs from verified export')
        dest = DEST/target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        records.append(dict(source=str(source), destination=str(dest), sha256=digest))
        if folder == 'weapon':
            binding = json.loads((source.parent/'binding-report.json').read_text('utf8'))
            if not binding['all_vertices_single_joint_unit_weight'] or len(binding['used_bones']) != 1:
                raise ValueError('Weapon no longer has one rigid influence')
            (DEST/'weapon-binding.json').write_text(json.dumps(binding), encoding='utf8')
        if folder == 'scene-export':
            doc, _ = split_glb(blob)
            (DEST/'cameras.json').write_text(json.dumps(doc['extras']['sourceCameras']), encoding='utf8')
    lighting = json.loads((ROOT/'analysis/battle-visual/lightmaps/bindings.json').read_text('utf8'))
    images = []
    for i, image in enumerate(lighting['decoded_images']):
        output = image['outputs'][0]
        source = ROOT/output['png']
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != output['png_sha256']:
            raise ValueError('Lightmap PNG hash differs from decoder record')
        target = DEST/f'light-{i}.png'
        shutil.copyfile(source, target)
        images.append(f'recovered/prologue/light-{i}')
        records.append(dict(source=str(source), destination=str(target), sha256=digest))
    (DEST/'lightmaps.json').write_text(json.dumps(dict(images=images, bindings=lighting['bindings'])), encoding='utf8')
    shutil.copyfile(ROOT/'tools/templates/cocos-prologue-lightmap.effect', DEST/'lightmap.effect')
    (DEST/'provenance.json').write_text(json.dumps(records, indent=2), encoding='utf8')
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
