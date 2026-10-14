"""Trace Lynn entity/LOD assets and validate source containers; no game execution."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from extract_game_data import export_table
from export_elsa_model import extract, parse_materials, bind_materials
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue, lookup_logical
from inspect_neox_model import parse_model, summary
from inspect_neox_animation import parse_library, clip_path
from decode_ktx import parse_ktx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/lynn'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256: raise ValueError('APK changed')
    catalogue=read_catalogue(apk); sources={}; errors=[]
    def get(path):
        if path not in sources:
            dest=OUT/'source'/(hashlib.sha256(path.encode()).hexdigest()[:16]+Path(path).suffix)
            sources[path]=extract(apk,catalogue,path,dest,APK_SHA256)
        return Path(sources[path]['sample_path']).read_bytes()
    entities=export_table(1955,{11,21}); lod=export_table(1268,{203})
    levels=export_table(6328,set(lod['rows'][0]['fields']['LOD_MODEL_LIST']))
    models=[]; libraries={}; textures={}
    for row in levels['rows']:
        path=row['fields']['MODEL_PATH']; result=dict(level=row,path=path)
        try:
            gim=get(path); xml=ET.fromstring(gim)
            mesh=xml.attrib.get('Mesh',path[:-4]+'.mesh'); mtg=path[:-4]+'.mtg'
            model=parse_model(get(mesh)); materials=parse_materials(get(mtg),expected_slots=None)
            result.update(mesh=summary(model),materials=materials,bindings=bind_materials(model,gim,materials))
            for material in materials:
                for key,logical in material['params'].items():
                    if key.startswith('Tex'):
                        candidate=str(Path(logical).with_suffix('.ktx')).replace('\\','/')
                        if candidate not in textures:
                            textures[candidate]=parse_ktx(get(candidate))
            paths=[e.attrib['value'] for e in xml.findall('GisFiles/*')]
            result['libraries']=paths
            for libpath in paths:
                if libpath in libraries: continue
                # Lynn contains source records with an empty root field. Preserve it;
                # this inventory does not infer root motion or decode these clips.
                lib=parse_library(get(libpath),allow_empty_roots=True)
                lib['empty_root_clips']=[c['name'] for c in lib['clips'] if not c['root_bone']]
                lib['clip_availability']=[dict(name=c['name'],path=clip_path(libpath,c['name']),
                    matches=lookup_logical(catalogue,clip_path(libpath,c['name']))) for c in lib['clips']]
                libraries[libpath]=lib
        except (ValueError,KeyError,ET.ParseError) as error:
            result['error']=str(error); errors.append(dict(path=path,error=str(error)))
        models.append(result)
    slave=export_table(5734)
    slave_matches=[r for r in slave['rows'] if r['id']==21]
    report=dict(evidence='Local hash-verified table joins and container parsing; not REA/runtime evidence',
        apk_sha256=APK_SHA256,entities=entities,lod=lod,levels=levels,models=models,libraries=libraries,
        textures=textures,sources=sources,errors=errors,
        cultivate_slave=dict(requested=21,table_source=slave['source'],rows=slave_matches),
        limits=['LOD level selection at runtime not observed; do not equate levels with battle/cultivate automatically.',
                'Clip presence is not ACL decoding or bone compatibility verification.',
                'No GLB export, original shader reproduction or client integration in this audit.',
                'Missing slave row is a source gap, not permission to replace it with another character.'])
    (OUT/'asset-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(models=len(models),libraries=len(libraries),textures=len(textures),sources=len(sources),
        clips=sum(r['clip_count'] for r in libraries.values()),missing_clips=sum(len(c['matches'])!=1 for r in libraries.values() for c in r['clip_availability']),
        cultivate_slave_found=bool(slave_matches),errors=errors)))

if __name__=='__main__': main()
