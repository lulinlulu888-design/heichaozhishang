"""Source worldline UI static audit; reuse decoded APK evidence, run no game code.

The UI conversion worker owns CSB extraction/rendering. This audit owns the
entry flow, original script consumers, source activity records and ID domains.
REA inventory Evidence is preserved separately from ordinary-tool decoding.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from extract_texture_samples import APK_SHA256
from extract_game_data import export_table
from inspect_battle_rules import read_module, walk_codes, export, instructions
from neox_resource_paths import lookup_logical
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/worldline-ui'
INDEX = ROOT / 'analysis/assets/decoded/script/index.json'
CATALOGUE = ROOT / 'analysis/resource-mapping/npk-indices.json'
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
SOURCE_FILES = {
    5795:'ui\\ui_hall\\HallNewPanel.py',
    6836:'ui_auto\\uires_HallMainPanel_NewHallPanel_HomeBattle_story.py',
    5456:'ui\\UIOutput.py', 9661:'logic\\phase\\PhaseConst.py',
    1131:'logic\\phase\\phaseDetailed\\PhaseHall.py',
    4341:'logic\\phase\\phaseDetailed\\PhaseBase.py', 6870:'ui\\UIConst.py',
    3954:'ui\\ui_mainline\\MainLineStoryDialog.py',
    3623:'ui_auto\\uires_OutFightPanel_Story_MainLineStoryDialog.py',
    2280:'ui_auto\\uires_OutFightPanel_Story_ChaperItem_Current.py',
    3644:'ui_auto\\uires_OutFightPanel_Story_ChaperItem_Passed.py',
    3583:'ui_auto\\uires_OutFightPanel_Story_ChapterItem_Locked.py',
    6732:'ui_auto\\uires_OutFightPanel_Story_NewChapterArea.py',
    4776:'ui_auto\\uires_StoryOpenAnimation_StoryOpenAnimation.py',
    8434:'ui\\UIDataSource.py', 1009:'ui\\ui_data\\ChallengDataTools.py',
}
FUNCTIONS = {
    5795:('on_BtnStory_ButtonUp','updateCurMainline'),
    5456:('onEnterMainLineStory','setCurPhase','onEnterMainlineDungeon'),
    1131:('PhaseMainLineStory','getDialogKwargs','getCreateUIKwargs'),
    4341:('showDialog','DialogName'),
    3954:('getCSBFilePath','assign','assignActivities','arrangeActivities','getActivityStatus','getChapterItemStatus',
          'getChapterItem','getItemHide','canEnter','onChapterSelected','onClose','on_Btn_branch_ButtonUp',
          'initTopUI','showBookInAnim','initComponents'),
    8434:('getActivityDataByGroupType','getSingerActivityData'),
    1009:('getActivityDataByGroupType','getSingerActivityData','activityCompare','getIfAllChallengePassed',
          'getActivityData','getLastMainlineActivityId'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(relative, data):
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False), 'utf8')
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path.read_bytes()))


def root_code(module, name, path=None):
    matches = [(p,c) for p,c in walk_codes(module) if c['name'].decode('utf8')==name and (path is None or p==tuple(path))]
    if len(matches)!=1:
        raise ValueError('Code object is missing/ambiguous: ' + name)
    return matches[0]


def anchor(index, module, name, path, operands=()):
    p,c = root_code(module,name,path)
    ops=list(instructions(c))
    return dict(module=index,filename=SOURCE_FILES[index],function=name,constant_path=list(p),
                bytecode_sha256=sha(c['bytecode']),first_source_line=c['firstlineno'],
                matching_instructions=[i for i in ops if i.get('operand') in operands])


def widget_bindings(index,module):
    result=[]
    for p,c in walk_codes(module):
        if c['name']!=b'_initAutoWidgets':continue
        ops=list(instructions(c))
        for start in range(len(ops)-4):
            seq=ops[start:start+5]
            if seq[0].get('operand')=='findNodeByPath' and [x['opname'] for x in seq]==[
                'LOAD_ATTR','LOAD_CONST','CALL_FUNCTION','LOAD_FAST','STORE_ATTR']:
                result.append(dict(module=index,constant_path=list(p),bytecode_sha256=sha(c['bytecode']),
                    bytecode_offset=seq[0]['offset'],node_path=seq[1]['operand'],widget_attribute=seq[4]['operand']))
    return result


def bounded_registry(index,module,needle):
    ops=list(instructions(module))
    hits=[i for i,op in enumerate(ops) if op.get('operand')==needle]
    return dict(module=index,filename=SOURCE_FILES[index],constant_path=[],bytecode_sha256=sha(module['bytecode']),
                windows=[ops[max(0,i-5):i+13] for i in hits])


def rea_inventory():
    path=ROOT/'analysis/rea/initial-artifact-evidence.json'
    raw=path.read_bytes();bundle=json.loads(raw)
    if not any(artifact.get('digest',{}).get('sha256')==APK_SHA256 for artifact in bundle['artifacts']):
        raise ValueError('Retained REA bundle belongs to another artifact')
    records=[]
    for record in bundle['records']:
        if record['operation'] in ('inventory_artifact','inspect_artifact'):
            records.append(dict(evidence_id=record['evidence_id'],operation=record['operation'],
                authority=record['authority'],confidence=record['confidence'],limitations=record['limitations']))
    if len(records)!=2:
        raise ValueError('Expected retained archive inventory/inspection records')
    return dict(bundle=path.relative_to(ROOT).as_posix(),bundle_sha256=sha(raw),records=records,
                supports='APK/ZIP identity and member inventory only',
                does_not_support='Original UI execution, page appearance, Python/CSB behavioral semantics')


def title_audit():
    """Independent addition; do not change the frozen main source-audit record."""
    records=[]
    for index in (3935,1623):
        table=export_table(index)
        selected=[row for row in table['rows'] if row['id']=='MAIN_LINE_TITLE']
        if len(selected)!=1:
            raise ValueError('Original title key missing/ambiguous')
        field='TextContent' if index==3935 else 'Title'
        if selected[0]['fields'][field]!='世界线':
            raise ValueError('Original title text changed')
        records.append({**table,'rows':selected,'selection':'Exact string key MAIN_LINE_TITLE'})
    return write('title-localization.json',dict(schema='hczs-worldline-title-source-v1',
        evidence_kind='Ordinary-tool static source table/bytecode evidence; no original UI execution',
        consumer=dict(module=3954,function='initTopUI',constant_path=[21,9],
                      widget='_cLeftTopArea',method='assign',key='MAIN_LINE_TITLE'),
        resolved_original_title='世界线',source_tables=records,
        note='Topbar_left CSB author placeholder is replaced by original script; never display its unrelated task title'))


def main():
    with APK.open('rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=APK_SHA256:
        raise ValueError('Original APK identity changed')
    rows={row['index']:row for row in json.loads(INDEX.read_text('utf8'))}
    catalogue=json.loads(CATALOGUE.read_text('utf8'))
    modules={};artifacts=[];bindings=[];references=[]
    for index,filename in SOURCE_FILES.items():
        row=rows[index]
        if row['filename']!=filename:
            raise ValueError('Original module identity changed: '+str(index))
        module=read_module(row);modules[index]=module
        if index in (9661,6870):
            evidence=bounded_registry(index,module,'MainLineStoryDialog')
        else:
            evidence=export(row,FUNCTIONS.get(index,('<module>','_initAutoWidgets','_initAutoControls','getCSBFilePath')))
        artifacts.append(dict(module=index,filename=filename,decoded_sha256=row['decoded_sha256'],
                              **write('scripts/'+str(index)+'.json',evidence)))
        bindings.extend(widget_bindings(index,module))
        if not filename.startswith('ui_auto\\'):continue
        for p,c in walk_codes(module):
            for ci,value in enumerate(c['consts']):
                if not isinstance(value,bytes):continue
                text=value.decode('utf8','replace')
                if len(text)>512 or not text.endswith(('.csb','.png','.plist','.ttf','.fnt')):continue
                resolved=text if text.startswith('uires/') else 'uires/'+text
                hits=lookup_logical(catalogue,resolved)
                references.append(dict(module=index,constant_path=list(p),constant_index=ci,literal=text,
                    lookup_path=resolved,matches=hits,
                    scope='Literal source resource reference; standalone NPK hash probe only. Atlas/VT frames may have zero standalone matches; state/variant not executed'))
    activities=export_table(4931)
    main_rows=[row for row in activities['rows'] if row['fields'].get('ActivityGroupType')==0]
    main_activities={**activities,'rows':main_rows,'selection':'ActivityGroupType exact literal 0; catalog not account progress'}
    main_ref=write('data/main-activities.json',main_activities)
    challenge_ref=write('data/prologue-challenges.json',literal_table(5921,{3997,3998}))
    battle_ref=write('data/city-test-battle.json',literal_table(6500,{10405}))
    scene_data=literal_table(9650,{239,2077,2081,2133})
    scene_ref=write('data/scene-associations.json',scene_data)
    maze_ref=write('data/prologue-maze.json',literal_table(1303,{3997}))
    scene_lookup={row['id']:dict(fields=row['fields'],scene_resource_matches=lookup_logical(catalogue,row['fields']['ScenePath']))
                  for row in scene_data['rows']}
    prologue=next(row for row in main_rows if row['id']==2)['fields']
    if prologue['ChallengeList']!=[3997,3998] or prologue['MainChapterNum']!='00':
        raise ValueError('Prologue activity association changed')
    first_path=ROOT/'analysis/first-encounter/encounter.json'
    first=json.loads(first_path.read_text('utf8'))
    if first['entry'] != {'guide_group':1001,'activity':2,'challenge':3997,'maze':3997,'battle':5000,
                          'source_entry_function':'5947:[4] startNewPlayerCourse',
                          'historical_trigger_limit':'isNewPlayerCourse [3] is a False-returning stub; original runtime trigger not verified.'}:
        raise ValueError('Reviewed tutorial entry chain changed')
    report=dict(schema='hczs-original-worldline-source-audit-v1',apk_sha256=actual,
        evidence_kind='Hash-verified ordinary static marshal/cdata/catalog analysis, separate from retained REA inventory',
        rea_evidence=rea_inventory(),source_index_sha256=sha(INDEX.read_bytes()),catalogue_sha256=sha(CATALOGUE.read_bytes()),
        modules=artifacts,widget_bindings=bindings,source_resource_references=references,
        entry_flow=[
            anchor(5795,modules[5795],'on_BtnStory_ButtonUp',[80,25],('onEnterMainLineStory','showAnim')),
            anchor(5456,modules[5456],'onEnterMainLineStory',[11,816],('MainLineStory','MainLineEndAni','setCurPhase','getNeedPlayResultAniMLActivity')),
            bounded_registry(9661,modules[9661],'MainLineStoryDialog'),
            anchor(1131,modules[1131],'PhaseMainLineStory',[46],('MainLineStory','clsName')),
            anchor(4341,modules[4341],'showDialog',[7,32],('DialogName','showDialog')),
            bounded_registry(6870,modules[6870],'MainLineStoryDialog'),
            anchor(3954,modules[3954],'getCSBFilePath',[21,0],('RES_FILE_NAME',)),
        ],
        primary_page=dict(logic_module=3954,auto_module=3623,layout='uires/OutFightPanel/Story/MainLineStoryDialog_ext.csb',
                          atlases=['uires/CommonUI.plist','uires/OutFightPanel.plist'],
                          class_registration='ui.ui_mainline.MainLineStoryDialog / DIALOG_SPECIAL',
                          normal_entry='phase MainLineStory -> MainLineStoryDialog, not a local encounter picker'),
        template_variants=[dict(module=2280,state='current',kind='source chapter visual template; not local account state'),
                           dict(module=3644,state='passed',kind='source chapter visual template; not local account state'),
                           dict(module=3583,state='lock',kind='source chapter visual template; not local account state')],
        page_states=dict(names=['BeforeTen','AfterTen'],selection_predicate_runtime_verified=False,
                         note='Same packaged auto page has design/resource alternatives, not independently established APK versions'),
        data_binding=dict(chain=[3954,8434,1009],group_filter='ActivityGroupType.ActivityGroupMain',
            source_account_fields=['Globals.Player.getActivityData(): activity ID map; special snake_task_dict key guard',
                                   'serverInfo.isClose','IfAllChallengePassed','LockedArgs'],
            special_key_guard=dict(module=1009,constant_path=[466],literal='snake_task_dict',
                                   bytecode_offsets=[59,62,65,68],comparison_argument=3,
                                   note='Special key is excluded before activity ID conversion, not used as the activity-list container'),
            current_local_progress_api_verified=False,source_account_progress_observed=False,
            item_consumed_fields=['Id','ActivityName','SeasonName','MainChapterNum','ResultRes','TabPic',
                                  'ActivitySimpleResultDesc','ActivityEndDateDesc'],
            activity_catalog=main_ref,source_main_activity_count=len(main_rows),
            chapter_numbers=[row['fields'].get('MainChapterNum') for row in main_rows]),
        encounter_domains=dict(tutorial=dict(local_encounter_id='tutorial-5000',activity_id=2,chapter_number='00',
            chapter_name='序章',challenge_id=3997,maze_id=3997,battle_id=5000,guide_group=1001,
            static_chapter_membership_verified=True,normal_worldline_page_selects='ActivityId2 then MainLineDungeon',
            source_chapter_map_scene_id=239,source_chapter_map_scene=scene_lookup[239],ml_maze_json_id=50002,
            scene_table=scene_ref,maze_table=maze_ref,
            base_battle_scene_id=2081,maze_loading_scene_override=2133,
            effective_original_battle_scene_runtime_verified=False,
            original_first_account_trigger_executed=False,source_progress_not_inferred=True,
            challenges=challenge_ref,existing_reviewed_chain=dict(path=first_path.relative_to(ROOT).as_posix(),sha256=sha(first_path.read_bytes()))),
            city=dict(local_encounter_id='city-preview-10405',battle_id=10405,source_name='测试-比克卢',scene_id=2077,
                monster_id=6605,source=battle_ref,chapter_or_challenge_association_verified=False,
                scene_table=scene_ref,source_scene=scene_lookup[2077],
                local_level40_policy_is_original=False,
                reference_scan='analysis/battle-visual/city-scenes/encounter-reference-scan.json',
                reference_scan_scope='Exact standalone int10405 in 9696 decoded modules only; no JSON/map/dynamic reference coverage')),
        minimum_restore=dict(phase1='Original page layout/atlas/static chapter catalog preview with unknown progress explicitly disclosed',
            phase2='Authoritative chapter/challenge progression API and original status consumers, then enter original MainLineDungeon page',
            prohibit=['Do not place the local two-item encounter catalog into original chapter templates',
                      'Do not label authored current/passed/locked examples as real account progression',
                      'Do not expose city test10405 as an original numbered chapter',
                      'Do not equate literal activity5000 with tutorial battle5000']),
        limits=['Original APK UI/scripts were not executed; no original network account state exists.',
            'Partial opcode mapping preserves UNKNOWN; conditional and positional layout semantics need renderer/runtime comparison.',
            'CSB parsing/atlas extraction and source static rendering are produced separately by the UI conversion worker.',
            'BeforeTen/AfterTen are same APK internal design states; older/newer released UI versions cannot be asserted.',
            'character_stage_cfg exact decoded-script filename/literal search returned no hit; its target identity remains unresolved.'])
    target=write('source-audit.json',report)
    title=title_audit()
    print(json.dumps(dict(**target,source_main_activities=len(main_rows),modules=len(artifacts),
                         widget_bindings=len(bindings),resource_literals=len(references),title=title,apk_executed=False),ensure_ascii=False))


if __name__=='__main__':
    main()
