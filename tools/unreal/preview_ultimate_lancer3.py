"""Render isolated source moon-blade material at two effect times; save no level."""
import json
import time
import traceback
from pathlib import Path
import unreal as u
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/battle-visual/elsa-ultimate/effects'
started = time.monotonic()
task = None
stage = 0
LIFECYCLE = '-HczsMoonbladeLifecycle' in u.SystemLibrary.get_command_line()
TIMES = [0, .12, .36, .6] if LIFECYCLE else [0, .3]
PREFIX = 'moonblade-lifecycle' if LIFECYCLE else 'moonblade'


def set_time(seconds):
    dynamic.set_scalar_parameter_value('EffectTime', seconds)
    if not LIFECYCLE: return
    model = json.loads((OUT / 'moonblade-lifecycle.json').read_text('utf8'))['models'][0]
    lifetime = float(model['attributes']['FxLifeSpan'])
    t = min(1, max(0, seconds / lifetime))
    for source, param in [('alphaMtl', 'SourceAlpha'), ('g_DissolveStrength', 'SourceDissolve')]:
        frames = model['shaderCurves'][source]['frames']
        value = frames[-1]['value'][0]
        for a, b in zip(frames, frames[1:]):
            if t <= b['time']:
                ratio = max(0, (t-a['time'])/(b['time']-a['time']))
                value = a['value'][0] + ratio*(b['value'][0]-a['value'][0]); break
        dynamic.set_scalar_parameter_value(param, value)


def tick(delta):
    global task, stage, started
    try:
        if time.monotonic() - started > 60: raise RuntimeError('Screenshot deadline exceeded')
        if task is None and time.monotonic() - started > 5:
            task = u.AutomationLibrary.take_high_res_screenshot(900, 900, str(OUT / f'{PREFIX}-{stage}.png'), camera=camera, delay=1)
        elif task is not None and task.is_task_done():
            shot = OUT / f'{PREFIX}-{stage}.png'
            if not shot.is_file(): raise RuntimeError('Screenshot missing')
            if stage < len(TIMES)-1:
                stage += 1; task = None; started = time.monotonic()
                set_time(TIMES[stage])
            else:
                (OUT / f'{PREFIX}-preview.json').write_text(json.dumps({'passed': True, 'times': TIMES, 'originalEffectPlayback': False, 'shaderScalarCurvesApplied': LIFECYCLE}), 'utf8')
                u.unregister_slate_post_tick_callback(handle); u.SystemLibrary.quit_editor()
    except Exception:
        (OUT / 'material-preview.json').write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}), 'utf8')
        u.unregister_slate_post_tick_callback(handle); u.SystemLibrary.quit_editor()


if any((OUT / f'{PREFIX}-{i}.png').exists() for i in range(len(TIMES))):
    raise RuntimeError('Refusing screenshot overwrite')
u.EditorLoadingAndSavingUtils.new_blank_map(False)
actors = u.get_editor_subsystem(u.EditorActorSubsystem)
mesh_path = next(r['mesh'] for r in json.loads((OUT / 'ue-readback.json').read_text('utf8'))['models'] if r['source'].endswith('/plane_yueren.gim'))
actor = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(0, 0, 0))
component = actor.get_component_by_class(u.StaticMeshComponent)
component.set_static_mesh(u.load_asset(mesh_path))
dynamic = component.create_dynamic_material_instance(0, u.load_asset('/Game/Recovered/Battle/ElsaUltimateEffects/MaterialsDynamic/M_plane_yueren'))
set_time(0)
center, extent = actor.get_actor_bounds(False)
sizes = [extent.x, extent.y, extent.z]
direction = [0, 0, 0]; direction[sizes.index(min(sizes))] = max(sizes) * 3
position = center + u.Vector(*direction)
camera = actors.spawn_actor_from_class(u.CameraActor, position, u.MathLibrary.find_look_at_rotation(position, center))
camera.get_component_by_class(u.CameraComponent).set_editor_property('field_of_view', 50)
handle = u.register_slate_post_tick_callback(tick)
