"""Recover source fan-flame geometry/material dependencies, without approximating FX."""
import hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
from trace_shiranui_effects import main as trace
from export_elsa_model import extract,parse_materials,bind_materials
from inspect_neox_model import parse_model,ModelError
from neox_resource_paths import read_catalogue,lookup_logical
from extract_texture_samples import APK_SHA256

ROOT=Path(__file__).resolve().parents[1]

def main():
    trace()
    out=ROOT/'analysis/characters/shiranui/effects';directory=out/'assets';directory.mkdir(exist_ok=True)
    report=json.loads((out/'report.json').read_text('utf8'))
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk';catalogue=read_catalogue(apk)
    sources={};models=[];references=[]
    def get(path):
        path=path.replace('\\','/')
        if path not in sources:
            target=directory/(hashlib.sha256(path.encode()).hexdigest()[:16]+Path(path).suffix)
            sources[path]=extract(apk,catalogue,path,target,APK_SHA256)
        return Path(sources[path]['sample_path']).read_bytes()
    for logical in sorted({r['path'] for r in report['references'] if r['path'].endswith('.gim')}):
        gim=get(logical);model=parse_model(get(logical[:-4]+'.mesh'))
        mtg=get(logical[:-4]+'.mtg');materials=parse_materials(mtg,expected_slots=None)
        binding_error=None
        try:bindings=bind_materials(model,gim,materials)
        except ModelError as error:
            bindings=[];binding_error=str(error)
        for element in ET.fromstring(mtg).iter():
            for key,value in element.attrib.items():
                if key=='TechName':value=value.split('::',1)[0]
                if not value.lower().endswith(('.tga','.dds','.png','.ktx','.fx','.nfx','.hlsl')):continue
                ref=value.replace('\\','/')
                candidate=str(Path(ref).with_suffix('.ktx')).replace('\\','/') if ref.endswith(('.tga','.dds','.png')) else ref
                hits=lookup_logical(catalogue,candidate)
                references.append(dict(model=logical,field=key,reference=ref,candidate=candidate,matches=len(hits)))
                if len(hits)==1:get(candidate)
        models.append(dict(path=logical,vertices=len(model['positions']),submeshes=len(model['submeshes']),
                           materials=materials,bindings=bindings,binding_error=binding_error))
    result=dict(apk_sha256=APK_SHA256,models=models,sources=sources,references=references,
        limitations=['Geometry and material references recovered; original FX runtime not executed',
                    'Texture suffix mapping is candidate lookup, not proof of original loader branch',
                    'Shader macros, uniforms, blend equations and effect hierarchy must be ported before faithful display'])
    (out/'asset-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(models=[dict(path=m['path'],vertices=m['vertices'],submeshes=m['submeshes']) for m in models],
                         sources=len(sources),references=references)))

if __name__=='__main__':main()
