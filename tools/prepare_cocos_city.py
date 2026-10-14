"""Stage hash-verified city exports for the shared Cocos client."""
import hashlib
import json
import shutil
from pathlib import Path
from export_elsa_model import split_glb, pack_glb

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'clients/cocos-poc/assets/resources/recovered/city'

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    from trace_city_player_placement import main as trace_players
    from trace_city_battle_placement import main as trace_monster
    trace_players()
    trace_monster()
    from trace_first_encounter import literal_table
    skill_ids = {66051, 66052, 66053, 66054}
    skills = literal_table(9333, skill_ids)
    timelines = literal_table(6655, {660511, 660521, 660531, 660541})
    entity = literal_table(1955, {6605})['rows'][0]['fields']
    actions = {}
    for row in timelines['rows']:
        f = row['fields']
        if f['TIME'] != 0 or f['TYPE'] != 0 or f['DATA']['AFTER_EFFECT_LIST']:
            raise ValueError('Unsupported city action timing/effect')
        skill = next(s['fields'] for s in skills['rows'] if s['id'] == f['OwnerSkill'])
        actions[str(f['OwnerSkill'])] = dict(name=skill['SHOW_NAME'],
            clips=[entity['ANIM_STATES_' + state] for state in f['DATA']['ANIMATION_LIST']],
            source_timeline=row['id'])
    players = json.loads((ROOT/'analysis/battle-visual/city-scenes/player-placement/report.json').read_text('utf8'))
    monster = json.loads((ROOT/'analysis/battle-visual/city-scenes/battle-placement/report.json').read_text('utf8'))
    (DEST/'formation-10405.json').write_text(json.dumps(dict(
        encounter=10405, scene='city_battle_2', players=players['derived_slots'], enemy=monster['derived'], actions=actions,
        policy='Static formation preview. One Elsa in selectable slot; enemy uses base entity scale, not unverified elite multiplier.'
    ), ensure_ascii=False, indent=2), encoding='utf8')
    records = []
    for name in ('city_battle_1', 'city_battle_2'):
        source = ROOT/f'analysis/battle-visual/city-scenes/{name}/scene.glb'
        report = json.loads(source.with_name('export.json').read_text('utf8'))
        blob = source.read_bytes()
        if hashlib.sha256(blob).hexdigest() != report['sha256']:
            raise ValueError('City export changed')
        doc, binary = split_glb(blob)
        folder = DEST/name
        (folder/'scene').mkdir(parents=True, exist_ok=True)
        clouds, opaque = [], []
        for index, node in enumerate(doc['nodes']):
            if 'mesh' not in node: continue
            node['name'] = f'CitySource_{index}'
            for slot, primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
                material = doc['materials'][primitive['material']]
                if material.get('alphaMode', 'OPAQUE') == 'OPAQUE':
                    opaque.append(dict(node=node['name'], slot=slot))
                data = material.get('extras', {})
                if data.get('sourceModel') != 'effects/modeleffect/scene/plane_yun.gim': continue
                opaque = [r for r in opaque if (r['node'], r['slot']) != (node['name'], slot)]
                textures = {}
                for key, texture in dict(mainTexture=material['pbrMetallicRoughness']['baseColorTexture']['index'],
                                         noiseTexture=data['extraTextures']['TexDistortion'],
                                         maskTexture=data['extraTextures']['TexMask']).items():
                    image = doc['images'][doc['textures'][texture]['source']]
                    view = doc['bufferViews'][image['bufferView']]
                    offset = view.get('byteOffset', 0)
                    target = folder/f'texture-{texture}.png'
                    target.write_bytes(binary[offset:offset+view['byteLength']])
                    textures[key] = f'recovered/city/{name}/texture-{texture}'
                clouds.append(dict(node=node['name'], slot=slot, textures=textures, parameters=data['sourceParams']))
        output = pack_glb(doc,binary)
        (folder/'scene/scene.glb').write_bytes(output)
        (folder/'scene-data.json').write_text(json.dumps(dict(cameras=doc['extras']['sourceCameras'],
            actors=doc['extras']['sourceActorInstances'], clouds=clouds, opaque=opaque)), encoding='utf8')
        records.append(dict(source=str(source), source_sha256=report['sha256'],
            output_sha256=hashlib.sha256(output).hexdigest(), changes='Unique environment node names only'))
    shutil.copyfile(ROOT/'tools/templates/cocos-city-cloud.effect', DEST/'cloud.effect')
    shutil.copyfile(ROOT/'tools/templates/cocos-city-opaque.effect', DEST/'opaque.effect')
    (DEST/'provenance.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    print(json.dumps(records,indent=2))

if __name__ == '__main__': main()
