"""Verify city source identity, derived data and actual native-export manifests."""
import copy
import hashlib
import json
from pathlib import Path
from export_elsa_model import split_glb

ROOT = Path(__file__).resolve().parents[1]

def verify_city(check, bundle, paths, png_hashes, resource_root):
    assets = ROOT/'legacy/cocos-poc/assets'
    staged = assets/'resources/recovered/city'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    check('City client templates match', all((assets/name).read_bytes() == (ROOT/'tools/templates'/template).read_bytes()
        for name, template in [('CitySceneView.ts','cocos-city-scene-view.ts'), ('ToolchainProof.ts','cocos-toolchain-proof.ts')]))
    check('City loaders and menu are compiled', all(s in bundle for s in
        ('recovered/city/', 'SourceCityCamera', 'WeaponInverseBind', 'CityOverlay', 'city_battle_', 'HCZS_CITY')))
    check('City material templates are current', all((staged/(name+'.effect')).read_bytes() ==
        (ROOT/f'tools/templates/cocos-city-{name}.effect').read_bytes() for name in ('opaque','cloud')))
    check('City materials are exported', all('recovered/city/'+name in paths for name in ('opaque','cloud')))
    records = json.loads((staged/'provenance.json').read_text('utf8'))
    formation = json.loads((staged/'formation-10405.json').read_text('utf8'))
    check('City battle formation resource is exported', 'recovered/city/formation-10405' in paths)
    check('City battle adapter and v2 state handling compiled', all(marker in bundle for marker in
        ('city-preview-10405-', 'getBattleActors', 'selectBattleScene', 'breakdown-reconstruction-v1', 'HealthRestored')))
    check('Local scenario selection and isolated battle client are compiled', all(marker in bundle for marker in
        ('switchService', 'createBattleClient', '正在切换试玩', '核对未确认的操作后再切换')))
    player_report = json.loads((ROOT/'analysis/battle-visual/city-scenes/player-placement/report.json').read_text('utf8'))
    enemy_report = json.loads((ROOT/'analysis/battle-visual/city-scenes/battle-placement/report.json').read_text('utf8'))
    check('City formation matches traced positions and monster source', formation['players'] == player_report['derived_slots']
        and formation['enemy'] == enemy_report['derived'] and formation['scene'] == 'city_battle_2')
    check('City four source skill clips are mapped', {k:v['clips'] for k,v in formation['actions'].items()} ==
        {'66051':['fire'], '66052':['fire'], '66053':['skill_3'], '66054':['skill_2']})
    check('Exactly two city source records', len(records) == 2)
    manifests, formations = [], []
    def collect(value):
        if isinstance(value, dict):
            if {'encounter','players','enemy','actions','policy'} <= value.keys(): formations.append(value)
            elif {'cameras','actors','clouds','opaque'} <= value.keys(): manifests.append(value)
            else:
                for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    for file in (resource_root/'assets/resources/import').rglob('*.json'):
        text = file.read_text('utf8')
        if ('sourceInstance' in text and 'clouds' in text) or 'formation-10405' in text or 'conditional_elite_scale' in text:
            collect(json.loads(text))
    check('Exact city battle formation data is present in native export', sum(m == formation for m in formations) == 1)
    for index, name in enumerate(('city_battle_1','city_battle_2')):
        record = records[index]
        source = ROOT/f'analysis/battle-visual/city-scenes/{name}/scene.glb'
        target = staged/name/'scene/scene.glb'
        check(name+' source and staged hashes match provenance', str(source) == record['source'] and
            digest(source) == record['source_sha256'] and digest(target) == record['output_sha256'])
        original, binary = split_glb(source.read_bytes())
        derived, derived_binary = split_glb(target.read_bytes())
        expected = copy.deepcopy(original)
        for i, node in enumerate(expected['nodes']):
            if 'mesh' in node: node['name'] = f'CitySource_{i}'
        check(name+' preserves all geometry and transforms', derived == expected and derived_binary == binary)
        manifest = json.loads((staged/name/'scene-data.json').read_text('utf8'))
        check(name+' metadata preserves source camera and actor instances', manifest['cameras'] == original['extras']['sourceCameras']
            and manifest['actors'] == original['extras']['sourceActorInstances'])
        check(name+' exact metadata is present in native export', sum(m == manifest for m in manifests) == 1)
        prefix = 'recovered/city/'+name
        check(name+' scene and metadata resource paths exist', prefix+'/scene-data' in paths and
            any(p.startswith(prefix+'/scene/') for p in paths))
        textures = sorted((staged/name).glob('texture-*.png'))
        check(name+' cloud textures are packaged unchanged', len(textures) == 3 and all(digest(p) in png_hashes for p in textures))
