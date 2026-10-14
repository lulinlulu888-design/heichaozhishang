"""Trace source targeting-arrow dispatch, resources and shaders without target execution."""
import hashlib
import json
from pathlib import Path
import inspect_battle_rules as static
from neox_resource_paths import read_catalogue, lookup_logical, parse_vt_config
from export_elsa_model import extract
from extract_texture_samples import APK_SHA256
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/battle-ui'


def main():
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:
            raise ValueError('APK identity changed')
    index=json.loads((static.SCRIPT/'index.json').read_text('utf8'))
    scripts=[]
    for number,methods in [(6870,('<module>',)),(6992,('_doArrowTouch','_doArrowSeek','hideArrow')),
                           (1730,('initComponents','_showArrow','_setArrow','_removeArrow'))]:
        report=static.export(next(r for r in index if r['index']==number),methods)
        if number==6870:
            report['code_objects'][0]['instructions']=[i for i in report['code_objects'][0]['instructions'] if 17723<=i['offset']<=17761]
            report['excerpt_only']=True
        scripts.append(report)
    catalogue=read_catalogue(apk)
    shaders=[]
    for name in ('arroweffect.vs','arroweffect.ps'):
        path=OUT/name
        source=extract(apk,catalogue,'common/shader/cocosui/'+name,path,APK_SHA256)
        shaders.append(dict(source=source,text=path.read_text('utf8')))
    config=OUT/'arrow-vt_config.jsondata'
    config_source=extract(apk,catalogue,'packed_png/vt_data/vt_config.jsondata',config,APK_SHA256)
    vt=parse_vt_config(config.read_bytes())
    textures=[]
    inputs=[]
    provenance=[]
    texture_out=OUT/'target-arrow'
    texture_out.mkdir(parents=True,exist_ok=True)
    for name in ('arrowhead','arrowflow','arrowbg'):
        path=f'uires/shader_santu/{name}.png'
        archive_path=path[:-4]+'.pkm'
        matches=lookup_logical(catalogue,archive_path)
        if len(matches)!=1:
            raise ValueError(f'Expected unique UI suffix mapping for {path}')
        destination=texture_out/(name+'.ktx')
        source=extract(apk,catalogue,archive_path,destination,APK_SHA256)
        inputs.append(destination)
        provenance.append(dict(source,logical_path=path,archive_logical_path=archive_path,
            sample_path=str(destination.resolve())))
        textures.append(dict(path=path,direct_matches=lookup_logical(catalogue,path),
            vt_matches=[r for r in vt['fullPathToPng'] if r['key'].lower()==path.lower()],
            suffix_mapping_matches=matches,source=source))
    provenance_path=texture_out/'provenance.json'
    provenance_path.write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf8')
    decoded=convert(inputs,texture_out,DEFAULT_DECODER,provenance_path=provenance_path,inspector=DEFAULT_INSPECTOR)
    evidence=dict(apk_sha256=APK_SHA256,scripts=scripts,shaders=shaders,texture_lookups=textures,vt_config_source=config_source,
        findings=['ArrowControl carries visible flag, card world position, pointer/target position and three texture paths.',
            'ArrowArea uses head scale .7 and SRCALPHA/ONE blending for the curve DrawNode.',
            'Native drawArrow receives basePos,targetPos,160,20,flow,bg,60,ArrowHead; numeric argument semantics unresolved.',
            'Fragment shader samples flow at (u,frac(v-CC_Time)) and combines flow*flow.a + background*(1-flow.a).'],
        texture_conversion_manifest=str(texture_out/'manifest.json'),
        texture_mapping_evidence='Existing native UI png-to-pkm suffix rule: docs/resource-path-mapping.md, 0xbfcd66..0xbfce0e',
        limitations=['Local static evidence, not REA runtime evidence', 'Native curve tessellation unresolved',
            'No replacement arrow implemented; decoded pixels do not validate runtime blending'])
    (OUT/'target-arrow-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(script_modules=len(scripts),extracted_shaders=len(shaders),decoded_textures=len(decoded['textures']))))


if __name__=='__main__':
    main()
