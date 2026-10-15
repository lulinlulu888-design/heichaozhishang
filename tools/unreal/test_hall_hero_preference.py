"""Actual native GameInstance HTTP/display check against an owned test database.

This drives Blueprint-callable session functions, not mouse input. It does not
claim that the original character picker UI has been restored.
"""
import hashlib
import json
from pathlib import Path
import re
import time
import traceback
import urllib.request

import unreal as u

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/unreal/hall-hero-selection'
manifest_file = ROOT / 'analysis/unreal/session-test/hall-hero-selection/server.json'
manifest = json.loads(manifest_file.read_text('utf8'))
port_match = re.search(r'(?:^|\s)-HczsServerPort=(\d+)(?:\s|$)',u.SystemLibrary.get_command_line())
if not port_match or not 17400 <= int(port_match[1]) < 17600 or int(port_match[1]) != manifest['port'] or not manifest['mongoDatabase'].startswith('hczs_test_ue_'):
    raise RuntimeError('Require the exact generated test server and isolated port')
port = int(port_match[1])
identity_request = urllib.request.Request('http://127.0.0.1:'+str(port)+'/__hczs_test_control/identity',
    headers={'Authorization':'Bearer '+manifest['controlToken']})
with urllib.request.urlopen(identity_request,timeout=10) as response:
    identity = json.load(response)
for key in ('runId','databaseIdentity','processIdentity','mongoDatabase','pid'):
    if identity[key] != manifest[key]:
        raise RuntimeError('Authenticated live test identity differs')
resume = '-HczsHallHeroResume' in u.SystemLibrary.get_command_line()
previous = json.loads((BASE/'native-create.json').read_text('utf8')) if resume else None
report = dict(serverIdentity=identity, mode='resume' if resume else 'create-switch',
    nativePointerInput=False, originalCharacterPickerRestored=False, steps=[], passed=False)
stage = 'bootstrap'
expected = [] if resume else [3,1,3]
target = None
game = None
presenter = None
camera = None
task = None
busy = False
started = time.monotonic()
output = BASE / ('native-resume.json' if resume else 'native-create.json')


def finish():
    report.update(passed=True,selectedProfileId=game.get_editor_property('selected_profile_id'))
    hall = game.get_editor_property('hall_preference')
    report.update(hallRevision=int(hall.get_editor_property('revision')),selectedHeroId=hall.get_editor_property('selected_hero_id'),
        displayedHeroId=presenter.get_editor_property('displayed_hero_id'),engine=u.SystemLibrary.get_engine_version())
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    u.unregister_slate_post_tick_callback(handle)
    u.SystemLibrary.quit_editor()


def tick(delta):
    global game,presenter,camera,stage,target,task,busy
    if busy:
        return
    busy = True
    try:
        if time.monotonic()-started > 120:
            raise RuntimeError('Native hall preference test deadline exceeded at '+stage)
        if game is None:
            world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
            if not world:
                return
            game = u.GameplayStatics.get_game_instance(world)
            actors = u.GameplayStatics.get_all_actors_of_class(world,u.HczsHallHeroPresentation)
            cameras = [a for a in u.GameplayStatics.get_all_actors_of_class(world,u.CameraActor) if a.actor_has_tag('HCZSInspectionCamera')]
            if len(actors) != 1 or len(cameras) != 1:
                raise RuntimeError('Actual game-world presenter/camera missing')
            presenter,camera = actors[0],cameras[0]
        if stage == 'bootstrap':
            if game.get_editor_property('request_in_flight') or not game.get_editor_property('local_service_available'):
                return
            if resume:
                if previous['serverIdentity']['mongoDatabase'] != identity['mongoDatabase']:
                    raise RuntimeError('Resume database differs')
                game.select_profile(previous['selectedProfileId'])
            else:
                game.create_local_profile('大厅未来原生验证')
            stage = 'profile'
        elif stage == 'profile' and game.is_hall_scene_ready():
            if resume:
                if game.get_editor_property('selected_profile_id') != previous['selectedProfileId']:
                    raise RuntimeError('Resume profile differs')
                hall = game.get_editor_property('hall_preference')
                if hall.get_editor_property('selected_hero_id') != 3 or hall.get_editor_property('revision') != previous['hallRevision']:
                    raise RuntimeError('Saved preference did not survive restart')
                target = 3
                stage = 'display'
            else:
                target = expected.pop(0)
                game.save_hall_hero(target)
                stage = 'display'
        elif stage == 'display' and game.is_hall_scene_ready():
            hall = game.get_editor_property('hall_preference')
            if hall.get_editor_property('selected_hero_id') != target:
                return
            problem = presenter.get_editor_property('last_problem')
            if problem:
                raise RuntimeError('Native hero display rejected confirmed preference: '+problem)
            if presenter.get_editor_property('displayed_hero_id') != target:
                return
            world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
            meshes = u.GameplayStatics.get_all_actors_of_class(world,u.SkeletalMeshActor)
            bases = [a for a in meshes if a.get_component_by_class(u.SkeletalMeshComponent).get_editor_property('skeletal_mesh_asset').get_path_name() == '/Game/Recovered/Elsa/elsa.elsa']
            replacements = [a for a in meshes if a.get_owner() == presenter]
            if len(bases) != 1 or len(replacements) > 1:
                raise RuntimeError('Runtime hall actor ownership is not unique')
            base = bases[0]
            replacement = replacements[0] if replacements else None
            if target == 3:
                if not replacement or not base.get_editor_property('hidden'):
                    raise RuntimeError('Future did not replace the base display')
                actual_mesh = replacement.get_component_by_class(u.SkeletalMeshComponent).get_editor_property('skeletal_mesh_asset').get_path_name()
                if '/Hero003/' not in actual_mesh:
                    raise RuntimeError('Displayed replacement is not Future')
            else:
                if replacement or base.get_editor_property('hidden'):
                    raise RuntimeError('Original Elsa display was not restored')
            report['steps'].append(dict(heroId=target,revision=int(hall.get_editor_property('revision')),
                displayedHeroId=presenter.get_editor_property('displayed_hero_id')))
            if expected:
                target = expected.pop(0)
                game.save_hall_hero(target)
            else:
                stage = 'capture'
                task = u.AutomationLibrary.take_high_res_screenshot(1600,900,str(BASE/('resume.png' if resume else 'confirmed.png')),camera=camera,delay=1)
        elif stage == 'capture' and task.is_task_done():
            path = BASE/('resume.png' if resume else 'confirmed.png')
            if not path.is_file() or path.stat().st_size < 10000:
                raise RuntimeError('Native confirmed preference frame missing')
            report.update(screenshot=str(path),screenshotSha256=hashlib.sha256(path.read_bytes()).hexdigest())
            finish()
    except Exception:
        report['error'] = traceback.format_exc()
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()
    finally:
        busy = False


if output.exists():
    output.rename(output.with_name(output.stem+'-previous-'+str(time.time_ns())+'.json'))
u.get_editor_subsystem(u.LevelEditorSubsystem).editor_play_simulate()
handle = u.register_slate_post_tick_callback(tick)
