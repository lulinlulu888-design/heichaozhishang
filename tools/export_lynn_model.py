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

def drop_unanimated_leaf_bones(model, library_names):
    """Remove mesh bones absent from the animation library that are unweighted leaves.

    No vertex references them, so geometry and skinning are unchanged; joint
    indices above each removed bone shift down by one.
    """
    library_names=set(library_names)
    while True:
        parents={b['parent'] for b in model['bones']}
        drop=next((i for i,b in enumerate(model['bones']) if b['name'] not in library_names
                   and i not in model['used_bones'] and i not in parents),None)
        if drop is None:
            return model
        model.setdefault('dropped_unanimated_leaf_bones',[]).append(model['bones'][drop]['name'])
        shift=lambda j:j-1 if j!=255 and j>drop else j
        del model['bones'][drop]
        for b in model['bones']:
            if b['parent'] is not None and b['parent']>drop:b['parent']-=1
        model['joints']=[tuple(shift(j) for j in js) for js in model['joints']]
        model['used_bones']=[shift(j) for j in model['used_bones']]


def remove_bind_shear(model, frame0, max_displacement_over_height=0.02):
    """Reconstruction: re-bind to the nearest shear-free locals so TRS skeletons can hold the bind.

    Each bind world keeps its position; its axes become the closest rotation
    with one uniform scale, so every local composes identically as TRS in UE.
    Vertices move by the blended old->new bind delta, so single-weight vertices
    skin exactly as before; blended ones are checked on sampled frame 0.
    """
    import copy
    from verify_lynn_idle import skin_vertices
    old=[np.asarray(matrix_rows(b['matrix_raw'])) for b in model['bones']]
    new={}
    def world(i):
        if i not in new:
            u_,_,vh=np.linalg.svd(old[i][:3,:3])
            fixed=old[i].copy();fixed[:3,:3]=(u_@vh)*np.cbrt(abs(np.linalg.det(old[i][:3,:3])))
            new[i]=fixed
        return new[i]
    delta=np.asarray([world(i)@np.linalg.inv(old[i]) for i in range(len(old))])
    weights=np.asarray(model['weights']);joints=np.where(weights>0,np.asarray(model['joints'],dtype=int),0)
    positions=np.column_stack((np.asarray(model['positions']),np.ones(len(model['positions']))))
    moved=np.sum(np.einsum('nvij,nj->nvi',delta[joints],positions)*weights[:,:,None],axis=1)[:,:3]
    linear=np.linalg.inv(delta[:,:3,:3]).transpose(0,2,1)
    normals=np.sum(np.einsum('nvij,nj->nvi',linear[joints],np.asarray(model['normals']))*weights[:,:,None],axis=1)
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    rebound=copy.deepcopy(model)
    rebound['positions']=[tuple(map(float,p)) for p in moved]
    rebound['normals']=[tuple(map(float,n)) for n in normals]
    for i,b in enumerate(rebound['bones']):
        b['matrix_raw']=[float(x) for x in world(i).T.flatten()]
    homogeneous=np.column_stack((moved,np.ones(len(moved))))
    for j in rebound['used_bones']:
        local=(homogeneous[np.any((joints==j)&(weights>0),axis=1)]@np.linalg.inv(world(j)).T)[:,:3]
        centre=(local.min(0)+local.max(0))/2;half=(local.max(0)-local.min(0))/2
        rebound['bones'][j]['auxiliary_unknown']=tuple(map(float,(*centre,*half,np.linalg.norm(half))))
    _,before=skin_vertices(model,frame0);_,after=skin_vertices(rebound,frame0)
    height=float(np.ptp(np.asarray(model['positions'])[:,1]))
    error=float(np.max(np.linalg.norm(after-before,axis=1))/height)
    if error>max_displacement_over_height:
        raise ModelError('shear-free re-bind moves sampled frame-0 vertices too far')
    return rebound,dict(frame0_max_displacement_over_height=error,limit=max_displacement_over_height,
        auxiliary_bounds='recomputed for the re-bound mesh; original bounds validated before re-binding',
        scope='Reconstruction for TRS skeletons, not original bind data')


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
    model=parse_model(read(mesh_path),repair_normals=True)
    library=parse_library(read(library_path),allow_empty_roots=True)
    model=drop_unanimated_leaf_bones(model,library['bone_names'])
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
        weighted_shear=[]
        for i,b in enumerate(model['bones']):
            local=binds[i] if b['parent'] is None else np.linalg.inv(binds[b['parent']])@binds[i]
            axes=local[:3,:3]/np.linalg.norm(local[:3,:3],axis=0)
            if i in model['used_bones'] and np.max(np.abs(axes.T@axes-np.eye(3)))>1e-4:
                weighted_shear.append(b['name'])
        if weighted_shear:
            model,shear_rebind=remove_bind_shear(model,frame0)
            bind['shear_rebind']=dict(shear_rebind,weighted_sheared_bones=weighted_shear)
            base,doc,_=encode_reference(model,selected['bindings'],materials,textures)
            joint_local_source='mesh re-bound to nearest shear-free bind (reconstruction), replaced by reference TRS below'
        else:
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
    # UE bakes skinned vertices into the node rest pose, so a rest pose far from
    # the bind distorts blended vertices; keep bind TRS when the reference differs.
    keep_bind_rest='reference_pose_mismatch' in bind and joint_local_source.startswith('mesh')
    if not keep_bind_rest:
        for index in doc['skins'][0]['joints']:
            node=doc['nodes'][index];p=reference[node['name']]
            node.pop('matrix',None);node.update(translation=list(p[:3]),rotation=list(p[3:7]),scale=list(p[7:10]))
    doc['extras'].pop('knownBindDifference',None)
    doc['extras']['referenceSkeletonPolicy']=('Rest pose is the mesh bind TRS because the library reference differs from it; '
        'every joint is clip-driven' if keep_bind_rest else
        'Full original local reference TRS, including unweighted ancestors; original inverse bind matrices unchanged')
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
