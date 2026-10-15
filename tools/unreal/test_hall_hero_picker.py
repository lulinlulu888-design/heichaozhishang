"""Actual Slate mouse/touch picker checks against an authenticated owned server.

Creates only a local test profile through GameInstance; hero operations route
through the painted widget and normal native pointer handlers, never direct
calls to PreviewHero/ConfirmPreview/SaveHallHero.

Launch through -ExecCmds="py <this file>" (ExecutePythonScript exits before
async callbacks finish). A fresh server run can supply -HczsPickerManifest=
with its generated server.json under analysis/unreal/session-test.
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
BASE = ROOT/'analysis/unreal/hall-hero-picker'
command = u.SystemLibrary.get_command_line()
manifest_argument = re.search(r'(?:^|\s)-HczsPickerManifest=(?:"([^"]+)"|(\S+))',command)
manifest_path = (Path(manifest_argument[1] or manifest_argument[2]) if manifest_argument else
    ROOT/'analysis/unreal/session-test/hall-hero-picker-20261015/server.json').resolve()
if not manifest_path.is_relative_to((ROOT/'analysis/unreal/session-test').resolve()) or manifest_path.name!='server.json':
    raise RuntimeError('Test manifest must be an owned server.json under the isolated test directory')
manifest = json.loads(manifest_path.read_text('utf8'))
port = re.search(r'(?:^|\s)-HczsServerPort=(\d+)(?:\s|$)',command)
if '-HczsHallHeroPickerTest' not in command or not port or int(port[1])!=manifest['port'] or not 17400<=int(port[1])<17600:
    raise RuntimeError('Require the exact isolated native picker test port/flag')
address = 'http://127.0.0.1:'+port[1]
request = urllib.request.Request(address+'/__hczs_test_control/identity',headers={'Authorization':'Bearer '+manifest['controlToken']})
with urllib.request.urlopen(request,timeout=10) as response:
    identity = json.load(response)
if not manifest['mongoDatabase'].startswith('hczs_test_ue_') or any(identity[k]!=manifest[k] for k in ('runId','databaseIdentity','processIdentity','mongoDatabase','pid')):
    raise RuntimeError('Authenticated owned server identity differs')
resume = '-HczsHallHeroPickerResume' in command
previous = json.loads((BASE/'native-picker.json').read_text('utf8')) if resume else None
if resume and (not previous['passed'] or previous['serverIdentity']!=identity):
    raise RuntimeError('Resume must use the same still-running owned server')
output = BASE/('native-picker-resume.json' if resume else 'native-picker.json')
if output.exists():
    output.rename(output.with_name(output.stem+'-previous-'+str(time.time_ns())+'.json'))
report = dict(passed=False,mode='restart-readback' if resume else 'native-pointer-flow',serverIdentity=identity,
    engine=u.SystemLibrary.get_engine_version(),nativePointerInput=True,steps=[],screenshots=[],
    scope='Source picker normal-state subset, local header entry, initial recovered heroes 1/3; not original account/runtime parity')
game = widget = presenter = None
stage = 'bootstrap'
started = time.monotonic()
after_paint = -1
capture_path = None
capture_ready_after = None
busy = False


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def hall_readback(expected_hero, revision):
    profile_id = game.get_editor_property('selected_profile_id')
    with urllib.request.urlopen(address+'/api/rebuild/v1/profiles/'+profile_id+'/hall',timeout=10) as response:
        hall = json.load(response)['hall']
    check(hall['selectedHeroId']==expected_hero and hall['revision']==revision,'Independent HTTP preference differs')
    report['steps'].append(dict(stage=stage,readback=hall,
        displayedHeroId=presenter.get_editor_property('displayed_hero_id')))


def click(action, touch=False):
    global after_paint
    before = json.loads(widget.development_describe_ui())
    check(widget.development_click_control(action,touch),'Real Slate pointer route failed for '+action)
    after = json.loads(widget.development_describe_ui())
    check(after['pointerEventSerial']==before['pointerEventSerial']+1 and after['lastPointerAction']==action
          and after['lastPointerTouch']==touch,'Native hit observation differs')
    report['steps'].append(dict(action=action,input='touch' if touch else 'mouse',nativePointerSerial=after['pointerEventSerial']))
    after_paint = before['paintSerial']


def finish():
    report.update(passed=True,selectedProfileId=game.get_editor_property('selected_profile_id'),
        finalUI=json.loads(widget.development_describe_ui()))
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    u.unregister_slate_post_tick_callback(handle)
    u.SystemLibrary.quit_editor()


def tick(delta):
    global game,widget,presenter,stage,busy,capture_path,after_paint,capture_ready_after
    if busy:
        return
    busy = True
    try:
        if report.get('lastStage')!=stage:
            report['lastStage']=stage
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
            u.log('HCZS picker stage='+stage)
        check(time.monotonic()-started<150,'Native picker test deadline at '+stage)
        if game is None:
            world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world()
            if not world:
                return
            game = u.GameplayStatics.get_game_instance(world)
            candidates = u.GameplayStatics.get_all_actors_of_class(world,u.HczsHallHeroPresentation)
            check(len(candidates)==1,'Unique hall hero presenter missing')
            presenter = candidates[0]
        if widget is None:
            widgets = u.WidgetLibrary.get_all_widgets_of_class(game,u.HczsHallWidget,True)
            if not widgets:
                return
            check(len(widgets)==1,'Unique painted hall widget missing')
            widget = widgets[0]
        paint = json.loads(widget.development_describe_ui())
        if paint.get('paintSerial',0)<=after_paint or paint.get('paintSerial',0)==0:
            return
        if stage=='bootstrap':
            if game.get_editor_property('request_in_flight') or not game.get_editor_property('local_service_available'):
                return
            if resume:
                game.select_profile(previous['selectedProfileId'])
            else:
                game.create_local_profile('原头像条交互验收')
            stage='profile'
        elif stage=='profile' and game.is_hall_scene_ready():
            if resume:
                if presenter.get_editor_property('displayed_hero_id')!=3:
                    return
                hall_readback(3,1)
                check(not paint['heroPickerOpen'],'Restart unexpectedly opened a transient picker')
                click('hero-open',True)
                stage='resume-cancel'
            else:
                hall_readback(None,0)
                check(presenter.get_editor_property('displayed_hero_id')==1,'Initial local fallback is not Elsa')
                click('hero-open')
                stage='preview-cancel'
        elif stage=='preview-cancel':
            check(paint['heroPickerOpen'] and {'选择','退出'}.issubset(paint['renderedTexts']),'Source picker buttons did not paint')
            click('hero-preview-3',True)
            stage='capture-preview'
        elif stage=='capture-preview':
            check(paint['displayedHeroId']==3 and not paint['heroPickerSaving'],'Temporary Future preview failed')
            if paint['pendingShaderJobs']:
                capture_ready_after = None
                return
            if capture_ready_after is None:
                capture_ready_after = time.monotonic()+2
                return
            if time.monotonic()<capture_ready_after:
                return
            hall_readback(None,0)
            capture_path=BASE/('preview-'+str(time.time_ns())+'.png')
            check(widget.development_capture_frame(str(capture_path)),'Cannot request native viewport frame')
            stage='cancel'
        elif stage=='cancel':
            if not capture_path.exists():
                return
            check(capture_path.stat().st_size>10000,'Native screenshot empty')
            report['screenshots'].append(dict(path=str(capture_path),sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest()))
            click('hero-cancel')
            stage='cancel-readback'
        elif stage=='cancel-readback':
            check(not paint['heroPickerOpen'] and paint['displayedHeroId']==1,'Cancel did not restore Elsa')
            hall_readback(None,0)
            click('hero-open',True)
            stage='preview-confirm'
        elif stage=='preview-confirm':
            click('hero-preview-3')
            stage='confirm'
        elif stage=='confirm':
            hall_readback(None,0)
            click('hero-confirm',True)
            stage='confirmed'
        elif stage=='confirmed' and game.is_hall_scene_ready():
            if paint['heroPickerOpen']:
                return
            check(paint['displayedHeroId']==3,'Confirmed hero did not remain Future')
            hall_readback(3,1)
            click('hero-open')
            stage='restore-saved'
        elif stage=='restore-saved':
            click('hero-preview-1',True)
            stage='cancel-saved'
        elif stage=='cancel-saved':
            check(paint['displayedHeroId']==1,'Elsa preview did not display')
            hall_readback(3,1)
            click('hero-cancel')
            stage='finish'
        elif stage=='resume-cancel':
            click('hero-cancel',True)
            stage='finish'
        elif stage=='finish':
            check(not paint['heroPickerOpen'] and paint['displayedHeroId']==3,'Exit did not restore confirmed Future')
            hall_readback(3,1)
            finish()
    except Exception:
        report.update(error=traceback.format_exc(),stage=stage)
        u.log_error('HCZS picker failed: '+report['error'])
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        u.unregister_slate_post_tick_callback(handle)
        u.SystemLibrary.quit_editor()
    finally:
        busy=False


output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
u.get_editor_subsystem(u.LevelEditorSubsystem).editor_request_begin_play()
handle = u.register_slate_post_tick_callback(tick)
