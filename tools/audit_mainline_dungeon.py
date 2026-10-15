"""Hash-verified original prologue map and progression audit; execute no APK code.

Reuse retained REA APK identity/inventory, decoded marshal/cdata, editor JSON,
and the existing direct SCN geometry conversion. Extract only selected CSBs
when no matching local evidence exists; never rebuild the complete APK index.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from extract_texture_samples import APK_SHA256
from extract_game_data import export_table
from inspect_battle_rules import read_module, walk_codes, instructions, export
from inspect_battle_ui_layout import Reader
from inspect_neox_model import extract_npk_entry
from neox_resource_paths import lookup, lookup_logical
from trace_first_encounter import literal_table
from audit_worldline_ui import rea_inventory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/mainline-dungeon'
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
INDEX = ROOT / 'analysis/assets/decoded/script/index.json'
CAT = ROOT / 'analysis/resource-mapping/npk-indices.json'
FUNCTIONS = {
    3954: ('getActivityStatus', 'getChapterItemStatus', 'canEnter', 'onChapterSelected'),
    5456: ('onEnterMainlineDungeon',), 5344: ('PhaseMainLineDungeon', 'endLoad'),
    7743: ('setArgs','getActivityData','initMapInfos','initEntityData','_initCamera',
           '_calculatePiecePos','generateMapOutline','generateMapOutlineDetail','buildMapDetail',
           'getCurChallengeID','getPreChallengeID','getPrePreChallengeID',
           'checkHasRemoved','addToHasRemoved','checkCanShowChallengePop','checkEnterChallenge'),
    1164: ('setArgs','CenterPos','DungeonWidth','DungeonHeight','CenterX','CenterY',
           'calculatePiecePos','getPiecePos'),
    1673: ('initMapPiece','initSceneData','getChessIDByXY','getPieceByChallenge'),
    3089: ('getModelData','getChallengeState','getModelPath','isChallengeSuc','onInit'),
    7324: ('_loadModel','_loadMapIcon','_initSfx'),
    6048: ('getMapPieceSettingData','getDungeonChessIDByUnit','getDungeonCenter',
           'getDungeonOffset','getDungeonLevelList'),
    7214: ('loadMazeJson','getGlobalDict','getMapDataDict','getMazeChess','getDungeonSceneID'),
    890: ('reloadSceneData','getSceneCenter'), 3635: ('__init__','setCameraData'),
    9526: ('getCSBFilePath','initComponents','initActivityData','refreshInChallenge',
           'assignProgrssNode','onMainlineDungeonCamMove','getChallengeData','enterChallenge',
           'checkCanEnter','checkCanShowPop','onMainlineDungeonChallengeSelect','assignStatus'),
    886: ('iCActivity','getActivityData','onActivityDataUpdate'),
    1009: ('getActivityServerData','refreshUpdateActivty','getIfAllChallengePassed',
           'getChallengeSucTime','getActivityData','getActivityDataByGroupType',
           'checkCanEnterMLChallenge'),
    3058: ('getChallengeSucTimes',),
    7022: ('validEnterActivity','validActivityTime','validExcelClose','validActivityLock',
           'validEnterChallenge','_checkPreChallenge','_checkChallengeOpen',
           'checkMaxTimes','isChallengeSuccessed'),
    9613: ('getMLActivityCurChallenge','getMLPreChallengeData'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path, expected=None):
    path = Path(path)
    raw = path.read_bytes()
    digest = sha(raw)
    if expected is not None and digest != expected:
        raise ValueError('Source hash mismatch: ' + str(path))
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest, bytes=len(raw))


def write(path, data):
    target = OUT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    return pin(target)


def code_anchor(modules, idx, function, path):
    code = dict(walk_codes(modules[idx]))[tuple(path)]
    if code['name'].decode() != function:
        raise ValueError('Code identity changed')
    ops = list(instructions(code))
    return dict(module=idx, function=function, constant_path=path,
                bytecode_sha256=sha(code['bytecode']), first_source_line=code['firstlineno'],
                unknown_opcode_count=sum(o['opname']=='UNKNOWN' for o in ops))


def references(module):
    result=[]
    for p,c in walk_codes(module):
        for ci,value in enumerate(c['consts']):
            if isinstance(value,bytes):
                s=value.decode('utf8','replace')
                if s.endswith(('.csb','.plist','.png','.ttf','.fnt')) and len(s)<512:
                    result.append(dict(constant_path=list(p), constant_index=ci, literal=s))
    return result


def selected_layout(logical, catalogue):
    rows=lookup_logical(catalogue, logical)
    if len(rows)!=1:
        return dict(logical_path=logical,status='missing-or-ambiguous',matches=rows)
    row=rows[0]
    target=OUT/'layouts'/Path(logical).name
    provenance=target.with_suffix('.source.json')
    if target.exists():
        source=json.loads(provenance.read_text('utf8'))
        if source['member']!=row['member'] or source['index']!=row['index']:
            raise ValueError('Existing CSB is from another source')
        pin(target,source['sha256'])
    else:
        source=extract_npk_entry(APK,row['member'],row['index'],target)
    data=target.read_bytes()
    reader=Reader(data,preserve_unknown=True)
    table=reader.scalar('I',0)
    version=reader.string(reader.field(table,0))
    if version!='2.1.0.0':
        raise ValueError('Unexpected source CSB version')
    tree=reader.node(reader.pointer(reader.field(table,3)))
    tree_ref=write('layouts/'+target.stem+'.tree.json',dict(
        logical_path=logical,source=source,version=version,node_count=len(reader.seen),tree=tree,
        limits=['Static bounded CSB schema reader, not runtime adaptation or animation playback',
                'Author labels/visibility are not verified account challenge state']))
    return dict(logical_path=logical,status='extracted-and-parsed',matches=rows,
                source=source,raw=pin(target),tree=tree_ref,node_count=len(reader.seen))


def main():
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:
            raise ValueError('Original APK identity changed')
    catalogue=json.loads(CAT.read_text('utf8'))
    rows={r['index']:r for r in json.loads(INDEX.read_text('utf8'))}
    modules={};script_refs=[]
    for idx,names in FUNCTIONS.items():
        modules[idx]=read_module(rows[idx])
        script_refs.append(dict(module=idx, filename=rows[idx]['filename'],
            decoded_sha256=rows[idx]['decoded_sha256'],
            **write('scripts/'+str(idx)+'.json',export(rows[idx],names))))
    # Auto classes named by the original MainLineDungeonPanel imports, not all
    # similarly named festival/system pages and not supposed chapter instances.
    autos=[5474,3969,1291,1496,5966,3788,2326,9410,3607,926]
    literal_refs=[]
    for idx in autos:
        m=read_module(rows[idx])
        script_refs.append(dict(module=idx, filename=rows[idx]['filename'],
            decoded_sha256=rows[idx]['decoded_sha256'],
            **write('scripts/'+str(idx)+'.json',export(rows[idx],
                ('<module>','_initAutoWidgets','_initAutoControls','getCSBFilePath')))))
        for ref in references(m):
            logical=ref['literal']
            if not logical.startswith('uires/'):logical='uires/'+logical
            literal_refs.append(dict(module=idx,**ref,lookup_path=logical,
                matches=lookup_logical(catalogue,logical),
                scope='Explicit resource literal, not confirmation of active runtime visibility'))
    layouts=[selected_layout(p,catalogue) for p in (
        'uires/MainLlineDungeonPanel/MainLineDungeonPanel_ext.csb',
        'uires/MainLlineDungeonPanel/DungeonInfoArea_ext.csb',
        'uires/MainLlineDungeonPanel/InfoPopArea_ext.csb')]
    activity=export_table(4931,[2])
    challenge=literal_table(5921,{3997,3998})
    scenes=literal_table(9650,{239,2081,2133})
    tiles=export_table(8161,[1,50,51])
    data_refs=dict(activity=write('data/activity2.json',activity),
                   challenges=write('data/challenges.json',challenge),
                   scene_associations=write('data/scenes.json',scenes),
                   map_piece_settings=write('data/map-piece-settings.json',tiles))
    maze_path=ROOT/'analysis/assets/npk/assets/00094_5700e1bb.json'
    maze_pin=pin(maze_path,'60e4ef3ff45e60b5a60979c4dafc4d46827558a9937c02addee4e2fddc4f6c73')
    maze=json.loads(maze_path.read_text('utf8'))['50002']
    if len(maze['MapData'])!=3 or maze['MapData']['20,22']['levelID']!=3997:
        raise ValueError('Reviewed original map binding changed')
    maze_ref=write('data/map50002.json',dict(source=maze_pin,
        runtime_file_literal='assets/editor/maze.json',canonical_npk_path='editor/maze.json',
        matches=lookup(catalogue,'editor/maze.json'),map_id=50002,data=maze,
        coordinate_order='Original buildMapDetail splits key into y,x; not x,y',
        account_progress=None))
    editor=ROOT/'analysis/assets/npk/assets/00145_8a9e76dc.json'
    editor_ref=dict(**pin(editor),matches=lookup(catalogue,'editor/scene.json'),
                    scene239_extra_center=json.loads(editor.read_text('utf8')).get('239'))
    scene_manifest=ROOT/'analysis/battle-visual/prologue-scene-manifest.json'
    scene_raw=ROOT/'analysis/battle-visual/scene-00220.bin'
    source_report=ROOT/'analysis/battle-visual/scene-export/report.json'
    source_glb=ROOT/'analysis/battle-visual/scene-export/prologue-scene.glb'
    manifest=json.loads(scene_manifest.read_text('utf8'))
    raw_pin=pin(scene_raw,'410761fae3aee0b8c67e9505831942d99eafb1dfa3380ea1a2e3699c963d53f7')
    model_report=json.loads(source_report.read_text('utf8'))
    glb_pin=pin(source_glb,'60c2e4082772918c4493e3d2fdd21d4ea35b441e374467dcb7aace40717ed8e4')
    source_checks=[dict(logical_path=s['logical_path'],**pin(Path(s['sample_path']),s['sha256']))
                   for s in model_report['sources']]
    ET.fromstring(scene_raw.read_bytes())
    resources=[]
    for record in tiles['rows']:
        for field,value in record['fields'].items():
            if not isinstance(value,str) or not value.endswith(('.gim','.sfx')):continue
            matches=lookup_logical(catalogue,value)
            resources.append(dict(map_piece_id=record['id'],field=field,path=value,
                matches=matches,status='present-in-catalogue' if len(matches)==1 else 'missing-or-ambiguous',
                bytecode_source=record['field_sources'][field],
                limit='Availability only; dynamic tile model/shader/effect not newly converted'))
    registry_ops=list(instructions(modules[1009]))
    bindings={}
    for key in ('ServerData','serverInfo','IfAllChallengePassed','SuccessTime','UnLockNeedChallenge'):
        hits=[i for i,o in enumerate(registry_ops) if o.get('operand')==key]
        bindings[key]=[registry_ops[max(0,i-6):i+10] for i in hits]
    write('scripts/dynamic-field-bindings.json',bindings)
    report=dict(schema='hczs-original-mainline-dungeon-audit-v1',apk_sha256=APK_SHA256,
        evidence_kind='Ordinary-tool static marshal/cdata/CSB/XML analysis; no original APK or UE execution',
        rea_evidence=rea_inventory(),source_index=pin(INDEX),catalogue=pin(CAT),
        scripts=script_refs,data=data_refs,layouts=layouts,resource_literals=literal_refs,
        original_entry=dict(activity_id=2,chapter='00',map_scene_id=239,map_json_id=50002,
            worldline_entry='3954 MainLineStoryDialog.onChapterSelected -> 5456 UIOutput.onEnterMainlineDungeon -> phase MainLineDungeon',
            challenge_ids=[3997,3998],first_challenge_to_maze=3997,first_loading_battle=5000,
            guide1001_is_separate_entry=True,local_battle5000_is_not_chapter_map=True),
        chapter_map=dict(editor_json=maze_ref,editor_scene_json=editor_ref,
            source_scene=raw_pin,source_scene_manifest=pin(scene_manifest),
            available_geometry=dict(glb=glb_pin,report=pin(source_report),
                counts={k:model_report[k] for k in ('meshes','instances','textures','materials')},
                validated_source_assets=source_checks,conversion_tool='tools/export_prologue_scene.py',
                direct_original_vertex_geometry=True,source_cameras=manifest['cameras'],
                limits=model_report['limitations']),
            dynamic_piece_resources=resources,
            grid=dict(height=30,width=29,source_scene_long_side=27,source_scene_short_side=14,
                coordinate_order='Map JSON keys y,x; source data[y][x]',
                origin=[3,16.26,233.7],editor_scene239_additional_center=None,
                source_grid_pitch=[24,27.712],odd_row_half_pitch=13.856,
                anchors=[code_anchor(modules,7743,'generateMapOutlineDetail',[10,60]),
                         code_anchor(modules,1164,'calculatePiecePos',[6,24]),
                         code_anchor(modules,1164,'CenterPos',[6,6])],
                runtime_positions_verified=False,
                limit='Grid parity opcode and optional layer/center logic remain partial; do not treat analytical coordinates as native readback')),
        progress=dict(original_raw_container='Globals.Player.activityDatas',
            remote_callback=dict(anchor=code_anchor(modules,886,'onActivityDataUpdate',[7,6]),
                callback_registration='rpc_method(CLIENT_STUB, (Int("a"), Dict("d"))) + ClientCallServerBack',
                write='self.activityDatas[str(activityID)] = activityData',
                original_packets_observed=False,initial_account_snapshot_producer_verified=False),
            raw_success_path='activityDatas[str(activityId)][str(challengeId)]["successTime"]',
            prologue_success_paths=['activityDatas["2"]["3997"]["successTime"]',
                                    'activityDatas["2"]["3998"]["successTime"]'],
            success_semantics=dict(consumer='numeric completion count',
                evidence=['7022 checkMaxTimes compares successTime < challenge_table.MaxTimes',
                          '7022 isChallengeSuccessed requires not None and >0',
                          '3058 getChallengeSucTimes returns value unchanged with get fallback0'],
                seconds_or_milliseconds_conversion_present=False,string_conversion_present=False,
                original_transport_value_type_verified=False,
                missing_default0_is_not_observed_account_progress=True),
            chapter_ui_selection=dict(consumer_anchor=code_anchor(modules,3954,'getActivityStatus',[21,26]),
                rules=['canEnter false -> Locked','canEnter true and IfAllChallengePassed true -> Passed',
                       'canEnter true and IfAllChallengePassed false -> Current'],
                can_enter='not serverInfo.get("isClose",False), original local read fallback only'),
            derived_fields=dict(ServerData='getActivityServerData: raw activity map get(str(Id),{})',
                serverInfo='refreshUpdateActivty(Id,ServerData,Challenge,ActivityType); mutates same map',
                isClose='Client writes result of validEnterActivity/validActivityTime combination; not independently verified raw server flag',
                LockedArgs='Client chooses errcodes/timeErrcodes; not independently verified raw server flag',
                weekClose='Client initially writes False; changes for ACTIVITY_WEEK_OPEN gate',
                IfAllChallengePassed='Client aggregate getIfAllChallengePassed(Challenge,Id): source published branch each successTime>0; debug branch differs',
                exact_shortcircuit_opcode_mapping_complete=False),
            challenge_unlock=dict(raw_key_presence='str(challengeId) in athlete.activityDatas[activityID]',
                consumer_anchor=code_anchor(modules,7022,'_checkPreChallenge',[11]),
                missing_key='Reject with Unlock-derived PreChallengeNotSuccess/DreamPreChallenge reason',
                existing_key='This predecessor-key gate passes; remaining activity/level/time/max-count gates still apply',
                prohibition='Do not add zero-success records for every configured challenge and call that original unlock state'),
            activity_gates=dict(static_fields=['Switch','Close','UnlockChallenge','UnlockChallengeNeedItems',
                'openWeekDay','startDayHour','endDayHour','startDayTime','endDayTime'],
                raw_account_inputs=['activity record presence','challenge record presence',
                    'successTime','useLockItem','isTimeLimitedOpen','finish','timeLimitedTimestamps'],
                clock_inputs=['getServerTime','getServerTimestamp'],
                valid_time_defaults=['Missing/empty activity record -> False, ACTIVITY_NOT_IN_SERVER',
                    'Nonempty activity record without isTimeLimitedOpen -> True,None',
                    'isTimeLimitedOpen false -> False,ACTIVITY_NOT_OPEN',
                    'Timed activity reads timeLimitedTimestamps and server clock; emergency finish participates'],
                filtering='getActivityServerData does not clone/filter the activity map; refreshUpdateActivty adds derived fields',
                authority='Raw account values/server clock not present in original APK; configuration alone cannot reconstruct current account state'),
            local_only_state='HasMlRemovedChallengeList is local animation/removal bookkeeping, not authority for completed challenges',
            actual_original_account_state_available=False),
        battle_scene_boundary=dict(base_scene_id=2081,base_scene='scene/city_battle_3/city_battle_3.scn',
            maze_override_scene_id=2133,maze_override_scene='scene/pszdu_battle_1/pszdu_battle_1.scn',
            effective_original_loading_priority_executed=False,
            map_scene239_is_separate=True),
        next_handoff=['Import existing source239 GLB with exact source camera, retain original shading/effect limits',
            'Render parsed original MainLineDungeonPanel CSB; data marker position is projected from scene, not a fabricated chapter tile',
            'Recover dynamic map piece models from pinned settings1/50/51, then verify source cell coordinates in native frame',
            'Implement separately labelled local progress provider for record presence and numeric success counts; derive original UI gate fields',
            'Wire authoritative battle completion -> challenge3997 progress -> challenge3998 availability only through verified source mapping'],
        limits=['Static APK analysis only; source UI/account/protocol execution is not established',
                'Partial opcode mapping retains UNKNOWN; undocumented VM opcodes are never silently guessed',
                'Original account/server progress does not exist in APK; any new local starting state is an adapter policy',
                'CSB timelines and 3D dynamic tile shaders/effects are not reproduced by this metadata audit',
                'No C++, Node, Admin, registry or UE runtime was modified'])
    result=write('source-audit.json',report)
    print(json.dumps(dict(**result,script_modules=len(script_refs),source_cells=len(maze['MapData']),
        layouts=[dict(path=x['logical_path'],status=x['status'],nodes=x.get('node_count')) for x in layouts],
        dynamic_piece_references=len(resources),apk_executed=False,ue_executed=False),ensure_ascii=False))


if __name__=='__main__':
    main()
