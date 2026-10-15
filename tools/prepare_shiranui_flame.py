"""Prepare exact active-layer geometry/textures and shader defaults for a renderer."""
import hashlib,json,re
from pathlib import Path
from decode_ktx import convert,DEFAULT_DECODER
from inspect_neox_model import parse_model
from export_neox_gltf import encode_glb

ROOT=Path(__file__).resolve().parents[1]
PARAMETERS=('g_vDistortionTiling','g_vDistortionSpeed','g_fDistortionStrength1',
    'g_vFloatingTilingU1','g_vFloatingTilingV1','g_vFloatingSpeed1',
    'offset_u','offset_v','mirror_u','mirror_v','rotation_floatTex01',
    'alpha_mirror_u','alpha_mirror_v','alpha_rotation','alpha_mask_intensity',
    'g_vDissolveTiling','g_vDissolveSpeedU','g_vDissolveSpeedV','g_DissolveStrength',
    'g_dissolve_hardness','g_fFloatingStrength1','g_colFloatingColor1','alphaMtl')

def main():
    base=ROOT/'analysis/characters/shiranui/effects'
    assets=json.loads((base/'asset-report.json').read_text('utf8'))
    effects=json.loads((base/'report.json').read_text('utf8'))
    out=base/'render-inputs';out.mkdir(exist_ok=True)
    def read(path):
        record=assets['sources'][path];data=Path(record['sample_path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Input changed')
        return data
    shader=read('shader/lancer3.fx').decode('gb18030')
    defaults={}
    for name in PARAMETERS:
        semantic=re.search(r'\bfloat\s+'+re.escape(name)+r'\s*:\s*(\w+)\s*;',shader)
        if semantic:
            defaults[name]=dict(semantic=semantic.group(1),value=None,
                                source_line=shader[:semantic.start()].count('\n')+1)
            continue
        pattern=r'\b(?:float|int)([234]?)\s+'+re.escape(name)+r'\s*(?:<.*?>)?\s*=\s*([^;]+);'
        hits=list(re.finditer(pattern,shader,re.S))
        if len(hits)!=1:raise ValueError('Ambiguous shader default '+name)
        match=hits[0];literal=match.group(2).strip().strip('{}')
        parts=[p.strip().removesuffix('f') for p in literal.split(',')]
        if not all(re.fullmatch(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',p) for p in parts):
            raise ValueError('Nonliteral shader default '+name)
        values=list(map(float,parts));expected=int(match.group(1) or '1')
        if len(values)!=expected:raise ValueError('Default arity mismatch')
        defaults[name]=dict(value=values if expected>1 else values[0],
                            source_line=shader[:match.start()].count('\n')+1)
    model_path='effects/modeleffect/char/buzhihuo/ui_idle_huoyan_01_uv.gim'
    record=next(m for m in assets['models'] if m['path']==model_path)
    if record['binding_error']:raise ValueError('Active geometry not validated')
    model=parse_model(read(model_path[:-4]+'.mesh'))
    blob,_,_=encode_glb(model,'Shiranui original flame 01 geometry',skin=False)
    (out/'flame-01.glb').write_bytes(blob)
    texture_paths=[]
    for key in ('Tex0','TexDistortion','TexMask','TexDissolve'):
        path=record['materials'][0]['params'][key].replace('\\','/')
        path=str(Path(path).with_suffix('.ktx')).replace('\\','/')
        read(path);texture_paths.append(Path(assets['sources'][path]['sample_path']))
    decoded=convert(texture_paths,out/'textures',DEFAULT_DECODER)
    result=dict(shader_sha256=assets['sources']['shader/lancer3.fx']['sha256'],defaults=defaults,
        material=record['materials'][0],geometry_sha256=hashlib.sha256(blob).hexdigest(),
        textures=decoded['textures'],source_effects=effects['files'],
        limitations=['Renderer input only; shader, transforms, frame interpolation and blend execution pending',
                    '03 ignored layer not exported; no alteration of source geometry or enable flags'])
    (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(defaults=len(defaults),textures=len(decoded['textures']),geometry_bytes=len(blob))))

if __name__=='__main__':main()
