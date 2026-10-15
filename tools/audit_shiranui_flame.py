"""Quantify source bounds discrepancy and retain shader branches for porting."""
import hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
from inspect_neox_model import parse_model

ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'analysis/characters/shiranui/effects'
    assets=json.loads((out/'asset-report.json').read_text('utf8'))
    def read(logical):
        source=assets['sources'][logical];raw=Path(source['sample_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Source changed')
        return raw
    rows=[]
    for model in assets['models']:
        logical=model['path'];gim=ET.fromstring(read(logical))
        mesh=parse_model(read(logical[:-4]+'.mesh'))
        for element,sub in zip(gim.find('SubMesh'),mesh['submeshes']):
            positions=mesh['positions'][sub['vertex_start']:sub['vertex_start']+sub['vertex_count']]
            center=list(map(float,element.attrib['BoundingCenter'].split(',')))
            half=list(map(float,element.attrib['BoundingHalf'].split(',')))
            lower=[min(p[k] for p in positions) for k in range(3)]
            upper=[max(p[k] for p in positions) for k in range(3)]
            errors=[max(abs(lower[k]-(center[k]-half[k])),abs(upper[k]-(center[k]+half[k]))) for k in range(3)]
            rows.append(dict(model=logical,submesh=element.tag,source_center=center,source_half=half,
                             mesh_min=lower,mesh_max=upper,axis_max_errors=errors,
                             strict_1e_4_pass=max(errors)<=1e-4))
    shader=read('shader/lancer3.fx').decode('gb18030');lines=shader.splitlines()
    ranges={'distortion_and_colour_uv':[971,1003],'colour_strength':[1055,1060],
            'alpha_mask':[1102,1115],'dissolve':[1116,1127],'alpha_product':[1128,1131],
            'platform_linear_output':[1139,1152]}
    snippets={name:dict(lines=span,text='\n'.join(lines[span[0]-1:span[1]])) for name,span in ranges.items()}
    result=dict(bounds=rows,shader_sha256=assets['sources']['shader/lancer3.fx']['sha256'],
        shader_snippets=snippets,material_macros=[dict(model=m['path'],macros=[x['macros'] for x in m['materials']]) for m in assets['models']],
        observations=['03 discrepancy is concentrated on near-planar Z with serialized half extent zero; raw mesh coordinates preserved',
                      'Floating UV distortion samples red and adds the same displacement to U and V',
                      'Mask uses pow(mask.r + 0.01, alpha_mask_intensity)',
                      'Dissolve uses pow(clamp((noise.r-strength+0.1)*5,0,1), hardness)'],
        limitations=['Cause of near-planar bounds discrepancy not proven; strict check remains failed',
                     'SFX uniform overrides, native macro selection, colour conversion and HDR/blending still require integration',
                     'Static source audit, not runtime rendering equivalence'])
    (out/'flame-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(dict(bounds=rows,macros=result['material_macros']),ensure_ascii=False))

if __name__=='__main__':main()
