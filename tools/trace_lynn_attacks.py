"""Extract only Lynn attack clips selected by verified source skill timelines."""
import json
from pathlib import Path
from trace_lynn_cards import main as trace_cards
from inspect_neox_animation import file_sha256,parse_library,parse_clip,clip_path,extract_with_provenance,map_bones,save_json
from inspect_neox_model import parse_model
from neox_resource_paths import read_catalogue
from extract_texture_samples import APK_SHA256
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/lynn/attacks'
def main():
    trace_cards();OUT.mkdir(parents=True,exist_ok=True)
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    if file_sha256(apk)!=APK_SHA256:raise ValueError('APK changed')
    audit=json.loads((OUT.parent/'asset-audit.json').read_text('utf8'))
    chain=json.loads((OUT.parent/'battle/card-chain.json').read_text('utf8'))
    def read(logical):
        record=audit['sources'][logical];path=Path(record['sample_path'])
        if file_sha256(path)!=record['sha256']:raise ValueError('Audited source changed')
        return path.read_bytes()
    libpath='character\\player\\lin\\lin.gisacl'
    library=parse_library(read(libpath),allow_empty_roots=True)
    model=parse_model(read('character/player/lin/lin.mesh'));catalogue=read_catalogue(apk)
    names=sorted({r['clip'] for r in chain['animation_map']})
    if names!=['crit_1','crit_4','fire_1']:raise ValueError('Skill mapping changed')
    results=[]
    for name in names:
        path=OUT/(name+'.gisacl');source=extract_with_provenance(apk,catalogue,clip_path(libpath,name),path,APK_SHA256)
        raw=path.read_bytes();clip=parse_clip(raw)
        clip.update(source=source,library_sha256=library['sha256'],library_record=next(r for r in library['clips'] if r['name']==name),
            bone_mapping=map_bones(library,clip,[b['name'] for b in model['bones']]),
            timeline_references=[r for r in chain['animation_map'] if r['clip']==name],
            acl_format_bytes=list(raw[clip['acl_offset']+20:clip['acl_offset']+27]))
        save_json(OUT/(name+'.json'),clip)
        results.append(dict(name=name,**{k:clip[k] for k in ['acl_sha256','samples','bone_count','acl_format_bytes']}))
    save_json(OUT/'extraction.json',results);print(json.dumps(results))
if __name__=='__main__':main()
