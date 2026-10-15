"""Bounded source-resource audit for original challenge 3998 / battle 1703.

Hash-verifies the supplied APK and decoded table modules, extracts only the
selected boss/scene metadata and battle clips, and never runs original code.
Outputs are ignored analysis artifacts; no game/UE assets are modified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_elsa_model import extract, parse_materials
from decode_ktx import parse_ktx
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_library, parse_clip, clip_path
from inspect_neox_model import parse_model, summary
from neox_resource_paths import read_catalogue, lookup_logical
from trace_first_encounter import literal_table

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / 'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
OUT = ROOT / 'analysis/prologue-boss/resource-audit'


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', 'utf8')


def main():
    with APK.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != APK_SHA256:
            raise ValueError('Unexpected source APK')
    cat = read_catalogue(APK)
    tables = {}
    for name, index, selected in [('entity', 1955, {2003}), ('model', 1268, {503}),
                                   ('lod', 6328, {295, 296, 297}), ('scene', 9650, {2004})]:
        table = literal_table(index, selected)
        write(OUT / (name+'.json'), table)
        tables[name] = table
    entity = tables['entity']['rows'][0]['fields']
    scene = tables['scene']['rows'][0]['fields']
    model_path = next(r['fields']['MODEL_PATH'] for r in tables['lod']['rows'] if r['id']==295)
    if entity['LOD_ID'] != 503 or tables['model']['rows'][0]['fields']['LOD_MODEL_LIST'] != [295,296,297]:
        raise ValueError('Reviewed boss entity linkage changed')
    extracted = []

    def get(logical):
        logical = logical.replace('\\', '/')
        # File names come from trusted parser results but still cannot escape.
        target = (OUT/'source'/logical).resolve()
        if not target.is_relative_to((OUT/'source').resolve()):
            raise ValueError('Path escapes audit output')
        source = extract(APK, cat, logical, target, APK_SHA256)
        extracted.append(source)
        return target

    gim = get(model_path)
    mesh = get(model_path[:-4]+'.mesh')
    mtg = get(model_path[:-4]+'.mtg')
    model = summary(parse_model(mesh.read_bytes()))
    write(OUT/'mesh-summary.json', model)
    mats = parse_materials(mtg.read_bytes(), expected_slots=None)
    write(OUT/'materials.json', mats)
    root = ET.fromstring(gim.read_bytes())
    libraries = {v.replace('\\','/') for node in root.iter() for v in node.attrib.values() if v.lower().endswith('.gisacl')}
    if len(libraries) != 1:
        raise ValueError(f'Expected one source animation library, got {libraries}')
    library_path = libraries.pop()
    library_file = get(library_path)
    library = parse_library(library_file.read_bytes(), allow_empty_roots=True)
    write(OUT/'animation-library.json', library)
    # Only clips required by original battle state/timeline mappings, plus the
    # separately named transform asset. Existence does not prove a phase trigger.
    slots = ['IDLE_1','HIT_1','HIT_3','DIE','ATK_1','ATK_H_1','ATK_H_2',
             'TRANSFORM','SKILL_PART_1','SKILL_PART_2']
    clip_names = sorted({entity['ANIM_STATES_'+slot] for slot in slots if entity.get('ANIM_STATES_'+slot)})
    clip_rows, missing_clips = [], []
    for name in clip_names:
        record = next((r for r in library['clips'] if r['name']==name), None)
        if record is None:
            alternative=next((r for r in library['clips'] if r['name']==name+'_change'),None)
            missing_clips.append({'name':name,'reason':'literal name not in actual animation library',
                                  'availableTransformedVariant':alternative,
                                  'note':'A suffixed variant is not missing content; its phase trigger must be established separately.'})
            continue
        path = clip_path(library_path,name)
        if len(lookup_logical(cat,path)) != 1:
            missing_clips.append({'name':name,'reason':'not uniquely present in APK','path':path})
            continue
        clip = parse_clip(get(path).read_bytes())
        clip_rows.append({'name':name,'libraryRecord':record,'clip':clip})
    write(OUT/'selected-clips.json', clip_rows)
    event_path = model_path[:-4]+'.ags'
    events = {'logicalPath':event_path,'present':len(lookup_logical(cat,event_path))==1}
    if events['present']:
        event_file = get(event_path)
        event_root = ET.fromstring(event_file.read_bytes())
        tracks = event_root.find('AnimationEventTracks')
        events['sourceSha256'] = hashlib.sha256(event_file.read_bytes()).hexdigest()
        events['tracks'] = {n.tag:[dict(e.attrib) for e in n] for n in tracks} if tracks is not None else {}
        events['sourceLines'] = [{'line':i,'xml':line.strip()}
            for i,line in enumerate(event_file.read_text('utf8').splitlines(),1)
            if 'EventTrack_' in line or 'TimeRatio=' in line]
    write(OUT/'animation-events.json',events)
    scene_file = get(scene['ScenePath'])
    scene_root = ET.fromstring(scene_file.read_bytes())
    refs=[]
    for i,line in enumerate(scene_file.read_text('utf8').splitlines(),1):
        if 'Path=' in line or 'camera_1' in line:
            refs.append({'line':i,'xml':line.strip()})
    files=[{'tag':n.tag,**n.attrib} for n in scene_root.findall('.//AllFiles/*')]
    for f in files:
        path=f.get('Path','').replace('\\','/')
        f['archiveMatches']=lookup_logical(cat,path) if '/' in path else []
    write(OUT/'scene-references.json',{'sourceSha256':hashlib.sha256(scene_file.read_bytes()).hexdigest(),
          'fileReferences':files,'lineReferences':refs,
          'presetCameras':[dict(n.attrib) for n in scene_root.findall('.//PresetCameras/Camera')],
          'lights':[dict(n.attrib) for n in scene_root.findall('.//Lights/light')],
          'coverage':'AllFiles direct references only; nested materials, textures, probes and SFX dependencies need recursive conversion.'})
    texture_refs=[]
    for m in mats:
        for param,value in m['params'].items():
            if param.startswith('Tex') and isinstance(value,str) and '/' in value.replace('\\','/'):
                logical=value.replace('\\','/')
                paths=[logical]
                if logical.lower().endswith(('.png','.tga','.dds')):
                    paths.append(logical.rsplit('.',1)[0]+'.ktx')
                candidates = [{'path':p,'matches':lookup_logical(cat,p)} for p in paths]
                actual = [c for c in candidates if len(c['matches'])==1]
                texture = {'materialSlot':m['slot'],'param':param,'sourceReference':logical,'candidates':candidates}
                if len(actual)==1 and actual[0]['path'].endswith('.ktx'):
                    texture_file=get(actual[0]['path'])
                    texture['ktx']=parse_ktx(texture_file.read_bytes())
                texture_refs.append(texture)
    write(OUT/'texture-references.json',texture_refs)
    result={'schemaVersion':1,'evidenceKind':'hash-verified ordinary static extraction; no source runtime',
            'apkSha256':APK_SHA256,'battleId':1703,'monsterId':2013,'entityId':2003,
            'modelPath':model_path,'animationLibraryPath':library_path,
            'boneCount':library['bone_count'],'libraryClipCount':library['clip_count'],
            'recoveredClips':[{'name':r['name'],'durationMs':r['libraryRecord']['duration_ms']} for r in clip_rows],
            'missingClips':missing_clips,'materialCount':len(mats),'scenePath':scene['ScenePath'],
            'animationEventsPresent':events['present'],
            'sceneFileCount':len(files),'sceneUnresolvedReferences':[f for f in files if not f['archiveMatches']],
            'sources':extracted,
            'limits':['Metadata/mesh/clip extraction is not glTF conversion or an Unreal import.',
                      'A transform animation and TransformMusic field do not establish a phase/HP trigger.',
                      'Material parameters and scene object references are preserved; shaders/effects are not emulated.']}
    write(OUT/'report.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['sources','sceneUnresolvedReferences']},ensure_ascii=False))


if __name__=='__main__':
    main()
