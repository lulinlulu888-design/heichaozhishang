"""Install reviewed Future display assets and a runtime preference listener.

Back up the existing hall package before adding the one owned presenter actor.
No profile, account, battle state or original APK bytes are changed.
"""
import hashlib
import json
from pathlib import Path
import shutil
import time
import traceback

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/unreal/hall-hero-selection'
OUT.mkdir(parents=True,exist_ok=True)
MAP = '/Game/Recovered/Hall/Maps/L_ElsaHallFxPreview'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install():
    source = ROOT / 'analysis/characters/hero-003/hall/unreal-preview/native-render.json'
    preview = json.loads(source.read_text('utf8'))
    if not preview['nativeContinuousPlaybackObserved'] or not preview['nativeRenderVerified'] or preview['sourceGlbSha256'] != '857f554062f0d61d2a529ff6407caebafaa13131f04f6be123fd86ef8f91c522':
        raise RuntimeError('Reviewed Future playback evidence differs')
    meshes = [u.load_asset(preview['mesh']),u.load_asset(preview['animation'])]
    if not isinstance(meshes[0],u.SkeletalMesh) or not isinstance(meshes[1],u.AnimSequence) or meshes[0].get_editor_property('skeleton') != meshes[1].get_editor_property('skeleton'):
        raise RuntimeError('Future mesh/idle is not available')
    materials = [row['material'] for row in sorted(preview['colorMaterials'],key=lambda row:row['slot'])]
    if len(materials) != 10 or any(not u.load_asset(path) for path in materials):
        raise RuntimeError('Future color materials are incomplete')
    base_mesh = '/Game/Recovered/Elsa/elsa.elsa'
    plan = dict(baseMesh=base_mesh,baseSourceScale=[.86,.86,.86],futureMesh=preview['mesh'],
        futureIdle=preview['animation'],futureSourceScale=preview['sourceScale'],materials=materials,
        futureSourceGlbSha256=preview['sourceGlbSha256'],displayPolicy='confirmed-local-hall-preference-v1')
    plan_sha = hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    destination = '/Game/Recovered/Hall/Heroes/v_'+plan_sha[:16]
    catalog_path = destination+'/HallHeroCatalog'
    catalog = u.load_asset(catalog_path) if u.EditorAssetLibrary.does_asset_exist(catalog_path) else None
    if catalog:
        if catalog.get_editor_property('source_evidence_sha256') != plan_sha:
            raise RuntimeError('Catalog namespace contains unrelated data')
    else:
        factory = u.DataAssetFactory()
        factory.set_editor_property('data_asset_class',u.HczsHallHeroCatalogAsset)
        catalog = u.AssetToolsHelpers.get_asset_tools().create_asset('HallHeroCatalog',destination,u.HczsHallHeroCatalogAsset,factory)
        if not catalog:
            raise RuntimeError('Catalog creation failed')
        visual = u.HczsHallHeroVisual()
        for field,value in dict(name='未来',source_glb_sha256=preview['sourceGlbSha256'],
                mesh=meshes[0],idle=meshes[1],
                materials=[u.load_asset(path) for path in materials],source_scale=u.Vector(*preview['sourceScale'])).items():
            visual.set_editor_property(field,value)
        for field,value in dict(source_evidence_sha256=plan_sha,base_mesh=u.load_asset(base_mesh),
                base_source_scale=u.Vector(.86,.86,.86),heroes={3:visual}).items():
            catalog.set_editor_property(field,value)
        if not u.EditorAssetLibrary.save_loaded_asset(catalog,False):
            raise RuntimeError('Catalog save failed')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if (not world or world.get_path_name().split('.')[0] != MAP) and '-run=pythonscript' in u.SystemLibrary.get_command_line().lower():
        world = u.EditorLoadingAndSavingUtils.load_map(MAP)
    if not world or world.get_path_name().split('.')[0] != MAP:
        raise RuntimeError('Start in the saved production hall map')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    existing = [a for a in actors.get_all_level_actors() if isinstance(a,u.HczsHallHeroPresentation)]
    if len(existing) > 1:
        raise RuntimeError('Duplicate hall preference presenters')
    source_map_file = ROOT / 'clients/unreal5 5.8/Content' / (MAP.removeprefix('/Game/')+'.umap')
    before = sha(source_map_file)
    changed = not existing or existing[0].get_editor_property('catalog') != catalog
    backup = OUT / 'backups' / ('hall-'+before+'.umap')
    if changed:
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():
            shutil.copy2(source_map_file,backup)
        if sha(backup) != before:
            raise RuntimeError('Original hall backup failed its hash check')
        actor = existing[0] if existing else actors.spawn_actor_from_class(u.HczsHallHeroPresentation,u.Vector(0,0,0))
        actor.set_actor_label('HCZSHallHeroPresentation')
        actor.set_editor_property('tags',['HCZSHallHeroPresentation'])
        actor.set_editor_property('catalog',catalog)
        if not u.EditorLoadingAndSavingUtils.save_map(world,MAP):
            raise RuntimeError('Hall presenter map save failed')
    result = dict(map=MAP,catalog=catalog.get_path_name(),planSha256=plan_sha,changed=changed,
        previousMapSha256=before,currentMapSha256=sha(source_map_file),backup=str(backup) if changed else None,
        nativeEvidenceSha256=sha(source),confirmedPreferenceOnly=True,originalCharacterPickerRestored=False)
    (OUT/'install.json').write_text(json.dumps(result,indent=2),'utf8')


try:
    previous_error = OUT/'install.error.txt'
    if previous_error.exists():
        previous_error.rename(OUT/('install.error-'+str(time.time_ns())+'.txt'))
    install()
except Exception:
    (OUT/'install.error.txt').write_text(traceback.format_exc(),'utf8')
    raise
