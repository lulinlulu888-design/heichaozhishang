"""Extract Shiranui source model and explicit HOME_STAND_IDLE clip for hall preview."""
import hashlib,json
import xml.etree.ElementTree as ET
from pathlib import Path
from extract_game_data import export_table
from export_elsa_model import extract,parse_materials,bind_materials,write_json
from extract_texture_samples import APK_SHA256
from inspect_neox_model import parse_model,summary
from inspect_neox_animation import parse_library,parse_clip,clip_path,map_bones
from neox_resource_paths import read_catalogue

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/shiranui'

def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    OUT.mkdir(parents=True,exist_ok=True);cat=read_catalogue(apk);sources={}
    def get(path):
        dest=OUT/'source'/(hashlib.sha256(path.encode()).hexdigest()[:16]+Path(path).suffix)
        if path not in sources:sources[path]=extract(apk,cat,path,dest,APK_SHA256)
        return dest.read_bytes()
    char=export_table(8995,{33});entity=export_table(1955,{71,72});lod=export_table(1268,{250})
    levels=export_table(6328,{530,531,532,533})
    if char['rows'][0]['fields']['ENTITY_ID']!=71 or next(r for r in entity['rows'] if r['id']==71)['fields']['LOD_ID']!=250:raise ValueError('Character relation changed')
    path=next(r for r in levels['rows'] if r['id']==530)['fields']['MODEL_PATH']
    if path!='character/player/buzhihuo/buzhihuo_yangcheng.gim':raise ValueError('Model selection changed')
    gim=get(path);model=parse_model(get(path[:-4]+'.mesh'));materials=parse_materials(get(path[:-4]+'.mtg'),expected_slots=None)
    libraries=[e.attrib['value'] for e in ET.fromstring(gim).findall('GisFiles/*')]
    if len(libraries)!=1:raise ValueError('Multiple animation libraries need review')
    libpath=libraries[0];library=parse_library(get(libpath),allow_empty_roots=True)
    for m in materials:
        if 'Tex0' in m['params']:get(str(Path(m['params']['Tex0']).with_suffix('.ktx')).replace('\\','/'))
    name=next(r for r in entity['rows'] if r['id']==71)['fields']['ANIM_STATES_HOME_STAND_IDLE']
    if name!='home_stand_idle_1':raise ValueError('Hall idle selection changed')
    raw=get(clip_path(libpath,name));clip=parse_clip(raw);idle=OUT/'idle';idle.mkdir(exist_ok=True)
    (idle/(name+'.gisacl')).write_bytes(raw)
    decoration=export_table(9416,{191})
    weapon_path=decoration['rows'][0]['fields']['MODEL']
    if weapon_path!='character/player/buzhihuo/buzhihuo_weapon.gim':raise ValueError('Weapon relation changed')
    weapon_gim=get(weapon_path);weapon_model=parse_model(get(weapon_path[:-4]+'.mesh'))
    weapon_materials=parse_materials(get(weapon_path[:-4]+'.mtg'),expected_slots=None)
    for material in weapon_materials:
        for key in ('Tex0','TexBaseColor'):
            if key in material['params']:get(str(Path(material['params'][key]).with_suffix('.ktx')).replace('\\','/'))
    weapon_libpath=ET.fromstring(weapon_gim).find('GisFiles/*').attrib['value']
    weapon_library=parse_library(get(weapon_libpath),allow_empty_roots=True)
    weapon_raw=get(clip_path(weapon_libpath,name));weapon_clip=parse_clip(weapon_raw)
    weapon_idle=OUT/'idle-weapon';weapon_idle.mkdir(exist_ok=True)
    (weapon_idle/(name+'.gisacl')).write_bytes(weapon_raw)
    weapon_clip.update(source=sources[clip_path(weapon_libpath,name)],library_sha256=weapon_library['sha256'],
        library_record=next(r for r in weapon_library['clips'] if r['name']==name),
        bone_mappings={weapon_path[:-4]+'.mesh':map_bones(weapon_library,weapon_clip,[b['name'] for b in weapon_model['bones']])},
        acl_format_bytes=list(weapon_raw[weapon_clip['acl_offset']+20:weapon_clip['acl_offset']+27]))
    write_json(weapon_idle/(name+'.json'),weapon_clip)
    mappings={path[:-4]+'.mesh':map_bones(library,clip,[b['name'] for b in model['bones']])}
    clip.update(source=sources[clip_path(libpath,name)],library_sha256=library['sha256'],
        library_record=next(r for r in library['clips'] if r['name']==name),
        bone_mappings=mappings,
        acl_format_bytes=list(raw[clip['acl_offset']+20:clip['acl_offset']+27]))
    write_json(idle/(name+'.json'),clip)
    write_json(OUT/'asset-audit.json',dict(apk_sha256=APK_SHA256,character=char,entities=entity,lod=lod,levels=levels,
        sources=sources,decoration=decoration,
        models=[dict(path=path,mesh=summary(model),materials=materials,bindings=bind_materials(model,gim,materials)),
            dict(path=weapon_path,mesh=summary(weapon_model),materials=weapon_materials,bindings=bind_materials(weapon_model,weapon_gim,weapon_materials))],
        libraries={libpath:library,weapon_libpath:weapon_library},selection='LOD row530 selected for local hall inspection; original runtime LOD selection not observed',
        limits=['HOME_ENTITY_ID=0 is not assumed to refer to Elsa; explicit entity71 hall animation fields are used.',
            'Decoration191 path recovered; attachment/animation playback, spring simulation and source effects need verification.']))
    print(json.dumps(dict(model=path,library=libpath,clip=name,acl_sha256=clip['acl_sha256'],samples=clip['samples'],bones=clip['bone_count'],format=clip['acl_format_bytes'])))
    print(json.dumps(dict(weapon=weapon_path,library=weapon_libpath,acl_sha256=weapon_clip['acl_sha256'],samples=weapon_clip['samples'],bones=weapon_clip['bone_count'],format=weapon_clip['acl_format_bytes'])))

if __name__=='__main__':main()
