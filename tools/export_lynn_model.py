"""Export Lynn source geometry, colour textures and sampled idle; no shader parity claim."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from export_elsa_model import encode_reference, split_glb, pack_glb, write_json, digest
from export_elsa_animation import encode, validate_roundtrip
from inspect_neox_model import parse_model, ModelError, matrix_rows
from export_elsa_animation import quaternion_matrix
from inspect_neox_animation import parse_library, file_sha256
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from verify_lynn_idle import verify_reference_skin, sampled_to_reference_layout

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/characters/lynn/export'

def export_character(out, model_path, library_path, clip_name, character_name, clip_directory=None):
    global OUT
    OUT=Path(out)
    OUT.mkdir(parents=True,exist_ok=True)
    audit=json.loads((OUT.parent/'asset-audit.json').read_text('utf8'))
    def read(logical):
        r=audit['sources'][logical]; p=Path(r['sample_path'])
        if file_sha256(p)!=r['sha256']: raise ValueError('Source identity changed')
        return p.read_bytes()
    selected=next(m for m in audit['models'] if m['path']==model_path)
    mesh_path=model_path[:-4]+'.mesh'
    model=parse_model(read(mesh_path))
    library=parse_library(read(library_path),allow_empty_roots=True)
    clip_directory=Path(clip_directory) if clip_directory else OUT.parent/'idle'
    metadata_path=clip_directory/(clip_name+'.json')
    metadata=json.loads(metadata_path.read_text('utf8'))
    pose_path=clip_directory/(clip_name+'.poses')
    if file_sha256(pose_path)!=metadata['poses']['sha256']:raise ValueError('Sample changed')
    values=np.frombuffer(pose_path.read_bytes(),dtype='<f4',offset=20).reshape(metadata['samples'],metadata['bone_count'],10)
    frame0={m['name']:sampled_to_reference_layout(values[0,m['clip_index']]) for m in metadata['bone_mappings'][mesh_path]}
    bind=verify_reference_skin(library,model,frame0)
    import copy
    materials=copy.deepcopy(selected['materials']); sources=[]; colour_adaptations=[]
    for material in materials:
        if 'Tex0' not in material['params']:
            if 'TexBaseColor' not in material['params']:
                raise ValueError('No explicit source colour texture')
            material['params']['Tex0']=material['params']['TexBaseColor']
            colour_adaptations.append(dict(slot=material['slot'],source_field='TexBaseColor',
                scope='Colour reference only; fur shells and native shader not reproduced'))
    no_shader=[m['slot'] for m in materials if not m['params']['Tex0']]
    for logical in sorted({m['params']['Tex0'] for m in materials} - {''}):
        key=str(Path(logical).with_suffix('.ktx')).replace('\\','/')
        read(key)
        sources.append({**audit['sources'][key],'material_logical_path':logical})
    provenance=OUT/'texture-provenance.json';write_json(provenance,sources)
    converted=convert([Path(r['sample_path']) for r in sources],OUT/'textures',DEFAULT_DECODER,
        provenance_path=provenance,inspector=DEFAULT_INSPECTOR)
    textures={}
    for t in converted['textures']:
        png=Path(t['outputs'][0]['png'])
        if not png.is_absolute():png=ROOT/png
        policy='Source sRGB colour; alpha preserved'
        if t['texture']['profile']=='linear':
            pixels=np.array(Image.open(png).convert('RGBA'));x=pixels[:,:,:3].astype(np.float64)/255
            pixels[:,:,:3]=np.clip(np.rint(np.where(x<=.0031308,x*12.92,1.055*x**(1/2.4)-.055)*255),0,255).astype('uint8')
            png=png.with_name(png.stem+'.gltf-srgb.png');Image.fromarray(pixels).save(png)
            policy='Linear source RGB encoded for glTF sRGB; alpha preserved'
        textures[t['provenance']['material_logical_path']]=dict(source_sha256=t['source_sha256'],
            gltf_png=str(png),gltf_png_sha256=digest(png.read_bytes()),colour_policy=policy)
    reference=dict(zip(library['bone_names'],library['reference_pose']))
    try:
        base,doc,_=encode_reference(model,selected['bindings'],materials,textures)
        joint_local_source='mesh bind locals (replaced by reference TRS below)'
    except ModelError as error:
        if 'unsupported shear' not in str(error):raise
        binds=[np.asarray(matrix_rows(b['matrix_raw'])) for b in model['bones']]
        for i,b in enumerate(model['bones']):
            local=binds[i] if b['parent'] is None else np.linalg.inv(binds[b['parent']])@binds[i]
            axes=local[:3,:3]/np.linalg.norm(local[:3,:3],axis=0)
            if i in model['used_bones'] and np.max(np.abs(axes.T@axes-np.eye(3)))>1e-4:
                raise ModelError('weighted bone bind carries shear that TRS skeletons cannot reproduce: '+b['name'])
        locals_by_name={}
        for b in model['bones']:
            p=reference[b['name']];m=np.eye(4);m[:3,:3]=quaternion_matrix(p[3:7])*p[7:10];m[:3,3]=p[:3]
            locals_by_name[b['name']]=m.tolist()
        base,doc,_=encode_reference(model,selected['bindings'],materials,textures,locals_by_name)
        joint_local_source='library reference TRS; only unweighted bones carry bind shear that glTF nodes cannot hold'
    doc,binary=split_glb(base)
    for node in doc['nodes']:
        if 'mesh' in node:node['name']=character_name+'Mesh'
    # Use mesh locals only as the encoder's temporary matrix input; replace the
    # unanimated defaults with full source TRS after animation channels are added.
    base=pack_glb(doc,binary)
    clip=dict(name=clip_name,values=values,
        frames=metadata['samples'],rate=metadata['sample_rate'],pose_sha256=file_sha256(pose_path),
        metadata_sha256=file_sha256(metadata_path),metadata=metadata,
        mapping=metadata['bone_mappings'][mesh_path])
    animated,reports,_=encode(base,[clip]);doc,binary=split_glb(animated)
    for index in doc['skins'][0]['joints']:
        node=doc['nodes'][index];p=reference[node['name']]
        node.pop('matrix',None);node.update(translation=list(p[:3]),rotation=list(p[3:7]),scale=list(p[7:10]))
    doc['extras'].pop('knownBindDifference',None)
    doc['extras']['referenceSkeletonPolicy']='Full original local reference TRS, including unweighted ancestors; original inverse bind matrices unchanged'
    doc['extras']['character']=character_name
    animated=pack_glb(doc,binary)
    verified=validate_roundtrip(base,animated,[clip])
    output=OUT/(character_name.lower()+'-idle.colour-reference.glb');output.write_bytes(animated)
    report=dict(output=str(output),sha256=digest(animated),bytes=len(animated),reference_skin=bind,
        animations=reports,verification=verified,textures=textures,colour_adaptations=colour_adaptations,
        unresolved_no_shader_slots=no_shader,joint_local_source=joint_local_source,
        limits=['Unlit Tex0 reference only; original emission/toon/lighting not reproduced.',
            'Source LOD model chosen for inspection, not verified runtime selection.',
            'No browser or native engine playback verified.'])
    write_json(OUT/'export-report.json',report)
    print(json.dumps(dict(output=str(output),bytes=len(animated),verification=verified)))

def main():
    export_character(ROOT/'analysis/characters/lynn/export','character/player/lin/lin.gim',
        'character\\player\\lin\\lin.gisacl','idle_1','Lynn')

if __name__=='__main__':main()
