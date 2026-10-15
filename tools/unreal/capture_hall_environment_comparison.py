"""Render identical hall cameras with original and candidate SH materials."""
import json
import time
import traceback
from pathlib import Path
import unreal as u

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/unreal/hall-lighting/environment'
report = json.loads((OUT / 'ue-comparison.json').read_text('utf8'))
actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
hero = next(a for a in actors if a.get_actor_label() == 'HCZS_elsa')
component = hero.get_component_by_class(u.SkeletalMeshComponent)
camera = next(a for a in actors if a.get_actor_label() == 'HCZSInspectionCamera')
world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
if world.get_path_name().split('.')[0] != report['map']:
    raise RuntimeError('Expected isolated comparison map')
for row in report['materials']:
    component.set_material(row['slot'], u.load_asset(row['original']))
stage = 0
task = None
started = time.monotonic()


def tick(delta):
    global stage, task, started
    try:
        if time.monotonic()-started > 90:
            raise RuntimeError('Screenshot deadline exceeded')
        if task is None and time.monotonic()-started > 8:
            task = u.AutomationLibrary.take_high_res_screenshot(1280,720,str(OUT / f'hall-sh-{stage}.png'),camera=camera,delay=1)
        elif task is not None and task.is_task_done():
            if not (OUT / f'hall-sh-{stage}.png').is_file():
                raise RuntimeError('Screenshot missing')
            if stage == 0:
                for row in report['materials']:
                    component.set_material(row['slot'], u.load_asset(row['comparison']))
                stage = 1
                task = None
                started = time.monotonic()
            else:
                report['renderVerified'] = True
                report['renderPlatform'] = 'Windows editor; Android not yet verified'
                (OUT / 'render-comparison.json').write_text(json.dumps(report,indent=2),'utf8')
                u.unregister_slate_post_tick_callback(handle)
                u.SystemLibrary.quit_editor()
    except Exception:
        (OUT / 'render-error.txt').write_text(traceback.format_exc(),'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()


handle = u.register_slate_post_tick_callback(tick)
