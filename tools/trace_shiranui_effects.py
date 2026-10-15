"""Extract source fan FX trees and audit explicit references; no invented emitters."""
import hashlib,json
from pathlib import Path
from collections import deque,Counter
import xml.etree.ElementTree as ET
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from neox_resource_paths import read_catalogue,lookup_logical

ROOT=Path(__file__).resolve().parents[1]

def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=APK_SHA256:raise ValueError('APK changed')
    cat=read_catalogue(apk);out=ROOT/'analysis/characters/shiranui/effects'
    out.mkdir(parents=True,exist_ok=True)
    queue=deque(['effects/player/buzhihuo/ui_idle_3.sfx','effects/player/buzhihuo/ui_idle_4.sfx'])
    seen=set();files=[];references=[]
    def tree(e):return dict(tag=e.tag,attributes=e.attrib,children=[tree(c) for c in e])
    while queue:
        logical=queue.popleft()
        if logical in seen:continue
        if len(seen)>=32:raise ValueError('FX traversal budget exceeded')
        seen.add(logical)
        target=out/(hashlib.sha256(logical.encode()).hexdigest()[:16]+'.sfx')
        source=extract(apk,cat,logical,target,APK_SHA256)
        element=ET.fromstring(target.read_bytes().decode('gb18030'))
        files.append(dict(source=source,tree=tree(element),types=dict(Counter(e.tag for e in element.iter())),
            effects=[dict(type=e.tag,**e.attrib) for e in element.iter() if e.tag in ('Model','ParticleRes','Dummy')]))
        for ref in sorted({v.replace('\\','/') for e in element.iter() for v in e.attrib.values()
                           if v.lower().endswith(('.gim','.sfx','.tga','.dds','.png','.fx'))}):
            matches=lookup_logical(cat,ref)
            candidates=[]
            if Path(ref).suffix.lower() in ('.tga','.dds','.png'):
                mapped=str(Path(ref).with_suffix('.ktx')).replace('\\','/')
                candidates.append(dict(path=mapped,matches=len(lookup_logical(cat,mapped)),
                    interpretation='Candidate texture-container mapping; not original loader execution'))
            references.append(dict(parent=logical,path=ref,direct_matches=len(matches),candidates=candidates))
            if ref.endswith('.sfx') and len(matches)==1:queue.append(ref)
    report=dict(apk_sha256=APK_SHA256,files=files,references=references,
        evidence_kind='Local source extraction and static XML analysis; not REA runtime evidence',
        limitations=['FxIgnore and render quality flags preserved, not executed',
                    'Model/shader/texture playback and socket transforms not ported',
                    'No reconstructed particle simulation substituted for source effects'])
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(files=len(files),references=len(references),
        models=sum(f['types'].get('Model',0) for f in files),
        particle_resources=sum(f['types'].get('ParticleRes',0) for f in files))))

if __name__=='__main__':main()
