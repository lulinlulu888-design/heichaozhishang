"""Export original boss 2013's skinned colour reference and seven ACL motions.

Requires audit_prologue_boss_resources.py output and the existing pinned local
ASTC/ACL toolchains. Writes only analysis/prologue-boss/glb; never runs a game,
Unreal, Blender, or source APK code. No source bind/axis/actor correction.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
from decode_ktx import convert, DEFAULT_DECODER, DEFAULT_INSPECTOR
from export_elsa_animation import (quaternion_matrix, encode as encode_animation,
    validate_roundtrip, load_clip, accessor_array)
from export_elsa_model import split_glb, pack_glb, bind_materials, parse_materials, extract
from export_neox_gltf import encode_glb, flatten_columns
from export_tutorial_enemy import append_accessor, SHADERS, shader_evidence
from extract_texture_samples import APK_SHA256
from inspect_neox_animation import parse_library, parse_clip, map_bones, sample_clip
from inspect_neox_model import parse_model, matrix_rows, inverse4, multiply4, validate_bind_pose, ModelError
from neox_resource_paths import read_catalogue

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'analysis/prologue-boss/resource-audit'
OUT=ROOT/'analysis/prologue-boss/glb'
RUNTIME=ROOT/'tools/runtime/acl-1.2.0'
PREFIX='character/boss/muoumaxituan/muoumaxituan'
PINS={
 'muoumaxituan_idle':'34f94ded82b2288e56313c6b419af098802e39da2186fb5966aef0d752313c3b',
 'muoumaxituan_skill_3':'8f1f941fcf6da827ba32a98af78f49d16067d878ae3b7bced17f1d6a6c4092cf',
 'muoumaxituan_skill_2':'b25d2c152450027001872a239e1d139b7f00c59d6a233e520454d11db9712aba',
 'muoumaxituan_skill_4':'1b318ad6b8605ba570d6b11685ec5d3d098f0638773c226616dec4ff9e1a5f48',
 'muoumaxituan_hit_1':'cc7f8c4edaa8ee3ca08b0f492c2d96c130831ddf73a85e2f7a4db00830e36f16',
 'muoumaxituan_hit_2':'8d0636232a412147c7658e355dca1285f794f0e365698a7c7757a6c30df2570e',
 'muoumaxituan_death':'b506de4981135b2314c97476d5e2172a04f90c10af3d1a9fe922bb03066a5dae',
}


def sha(blob):return hashlib.sha256(blob).hexdigest()
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf8')


def verified_source(logical):
    path=AUDIT/'source'/logical
    raw=path.read_bytes();source=json.loads(Path(str(path)+'.provenance.json').read_text('utf8'))
    if source['apk_sha256']!=APK_SHA256 or source['logical_path']!=logical or sha(raw)!=source['sha256']:
        raise ValueError('Source provenance mismatch: '+logical)
    return raw,source


def validate_library_bind(model,library):
    names=[b['name'] for b in model['bones']]
    if len(names)!=123 or set(names)!=set(library['bone_names']):raise ModelError('Skeleton identity mismatch')
    poses=dict(zip(library['bone_names'],library['reference_pose']))
    local=[]
    for name in names:
        p=poses[name];m=np.eye(4);m[:3,:3]=quaternion_matrix(p[3:7])*p[7:10];m[:3,3]=p[:3];local.append(m)
    worlds={};visiting=set()
    def world(i):
        if i in visiting:raise ModelError('Cycle in source hierarchy')
        if i not in worlds:
            visiting.add(i);parent=model['bones'][i]['parent']
            worlds[i]=local[i] if parent is None else world(parent)@local[i];visiting.remove(i)
        return worlds[i]
    records=[]
    for i,b in enumerate(model['bones']):
        raw=np.array(matrix_rows(b['matrix_raw']));parent=b['parent']
        rawlocal=raw if parent is None else np.linalg.inv(matrix_rows(model['bones'][parent]['matrix_raw']))@raw
        local_error=float(np.max(np.abs(rawlocal-local[i])))
        global_error=float(np.max(np.abs(raw-world(i))))
        # Both inputs are independent stored float32 values. Accumulation of the
        # longer 123-bone hierarchy adds rounding; this is 0.00002 source units,
        # not an authored rotation/pose correction. Local tolerance stays 1e-5.
        if not np.isfinite([local_error,global_error]).all() or local_error>1e-5 or global_error>2e-5:
            raise ModelError(f'Independent bind mismatch: {b["name"]}: {local_error}, {global_error}')
        records.append({'index':i,'name':b['name'],'parent':parent,'localError':local_error,'globalError':global_error})
    try:aabb=validate_bind_pose(model)
    except ModelError as error:aabb={'validated':False,'reason':str(error),'scope':'Unknown auxiliary bone block semantics; not used as the independent validation gate.'}
    return {'validated':True,'method':'All mesh global binds equal independently stored GISACL local reference poses accumulated through the named hierarchy.',
            'localTolerance':1e-5,'globalTolerance':2e-5,'maxLocalError':max(r['localError'] for r in records),
            'maxGlobalError':max(r['globalError'] for r in records),'bones':records,'auxiliaryAabbCheck':aabb}


def encode_base(model,library,material,binding,png,texture_source,validation):
    # Static geometry writer remains unchanged; attach a skin only after the
    # independent reference-library validation above. Never bypass its skin gate.
    raw,_,_=encode_glb(model,'PrologueBoss2013Mesh',skin=False)
    doc,binary=split_glb(raw);matrices=[matrix_rows(b['matrix_raw']) for b in model['bones']]
    inverses=[inverse4(m) for m in matrices];roots=[];shears=[]
    for i,b in enumerate(model['bones']):
        local=matrices[i] if b['parent'] is None else multiply4(inverses[b['parent']],matrices[i])
        rot=np.asarray(local)[:3,:3];norm=np.linalg.norm(rot,axis=0)
        if np.any(norm<1e-8):raise ModelError('Singular local bind')
        shear=float(np.max(np.abs((rot/norm).T@(rot/norm)-np.eye(3))))
        if shear>1e-4:raise ModelError('Unsupported local bind shear')
        shears.append(shear);node={'name':b['name'],'matrix':flatten_columns(local)}
        children=[j+1 for j,other in enumerate(model['bones']) if other['parent']==i]
        if children:node['children']=children
        doc['nodes'].append(node)
        if b['parent'] is None:roots.append(i+1)
    skeleton=len(doc['nodes']);doc['nodes'].append({'name':'PrologueBoss2013Skeleton','children':roots})
    doc['scenes'][0]['nodes'].append(skeleton)
    ibm=append_accessor(doc,binary,[flatten_columns(m) for m in inverses],16)
    doc['skins']=[{'name':'PrologueBoss2013Bind','joints':list(range(1,len(model['bones'])+1)),
                   'skeleton':skeleton,'inverseBindMatrices':ibm}];doc['nodes'][0]['skin']=0
    for sub,primitive in zip(model['submeshes'],doc['meshes'][0]['primitives']):
        start=sub['vertex_start'];stop=start+sub['vertex_count']
        primitive['attributes']['JOINTS_0']=append_accessor(doc,binary,[tuple(0 if j==255 else j for j in row) for row in model['joints'][start:stop]],4,'B',34962)
        primitive['attributes']['WEIGHTS_0']=append_accessor(doc,binary,[tuple(w/sum(row) for w in row) for row in model['weights'][start:stop]],4,target=34962)
        # All source bytes are white, so this colour's channel order is unambiguous.
        colour=bytes.fromhex(sub['colors_raw_hex'])
        if len(colour)!=sub['vertex_count']*4 or set(colour)!={255}:raise ModelError('Unreviewed vertex colour data')
        colour_index=append_accessor(doc,binary,[(255,255,255,255)]*sub['vertex_count'],4,'B',34962)
        doc['accessors'][colour_index]['normalized']=True;primitive['attributes']['COLOR_0']=colour_index
        primitive['material']=binding['material_slot'];primitive['extras']['sourceSubmeshName']=binding['name']
    blob=png.read_bytes();binary.extend(b'\0'*(-len(binary)%4))
    doc['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(blob)});binary.extend(blob)
    doc['images']=[{'name':'Boss2013Tex0Colour','mimeType':'image/png','bufferView':len(doc['bufferViews'])-1,
                   'extras':{'sourceKtxSha256':texture_source['sha256'],'pngSha256':sha(blob)}}]
    doc['textures']=[{'source':0,'sampler':0}]
    doc['samplers']=[{'magFilter':9729,'minFilter':9987,'wrapS':10497,'wrapT':10497}]
    doc['extensionsUsed']=['KHR_materials_unlit']
    doc['materials']=[{'name':'Boss2013ColourReference','alphaMode':'OPAQUE','doubleSided':True,
       'pbrMetallicRoughness':{'baseColorTexture':{'index':0,'texCoord':0},'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1},
       'extensions':{'KHR_materials_unlit':{}},'extras':{'sourceMaterial':material,
         'scope':'UV0 Tex0 albedo reference only; no source emission/lighting/normal/mix reproduction.',
         'alphaEvidence':'Decoded Tex0 alpha is uniformly 255; source BaseColor default alpha=1.'}}]
    doc['extras'].update(monsterId=2013,entityId=2003,sourceGim=PREFIX+'.gim',
       bindPoseEvidence={k:v for k,v in validation.items() if k!='bones'},localMatrixMaxOrthogonalityError=max(shears),
       coordinatePolicy='Source XYZ, unit scale, winding, UV and image rows unchanged; no actor/bind rotation.',
       missing=['Original emission/normal/mix materials, particles, scene, events, audio and gameplay are not included in this colour reference.'])
    return pack_glb(doc,binary)


def audit_base(glb,model):
    doc,binary=split_glb(glb);skin=doc['skins'][0];joints=skin['joints'];count=len(model['bones'])
    if joints!=list(range(1,count+1)) or skin['skeleton']!=count+1:raise ValueError('Wrong joint ordering')
    parents={child:i for i,n in enumerate(doc['nodes']) for child in n.get('children',[])};worlds={}
    def world(i):
        if i not in worlds:
            m=np.array(matrix_rows(doc['nodes'][i]['matrix'])) if 'matrix' in doc['nodes'][i] else np.eye(4)
            worlds[i]=world(parents[i])@m if i in parents else m
        return worlds[i]
    ibms=accessor_array(doc,binary,skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
    transforms=[];global_error=0.0;identity_error=0.0
    for i,b in enumerate(model['bones']):
        node=joints[i]
        if doc['nodes'][node]['name']!=b['name'] or parents[node]!=(skin['skeleton'] if b['parent'] is None else b['parent']+1):raise ValueError('Source joint hierarchy changed')
        raw=np.array(matrix_rows(b['matrix_raw']));expected=np.asarray(inverse4(raw),dtype=np.float32)
        if not np.array_equal(ibms[i],expected):raise ValueError('Inverse bind differs from source inverse')
        global_error=max(global_error,float(np.abs(world(node)-raw).max()));transforms.append(world(node)@ibms[i])
        identity_error=max(identity_error,float(np.abs(transforms[-1]-np.eye(4)).max()))
    if global_error>1e-10 or identity_error>1e-5:raise ValueError('GLB bind transform mismatch')
    p=doc['meshes'][0]['primitives'][0];a=p['attributes']
    for key,expected in [('POSITION',model['positions']),('NORMAL',model['normals']),('TEXCOORD_0',model['submeshes'][0]['uvs'][0])]:
        if not np.array_equal(accessor_array(doc,binary,a[key]),np.asarray(expected,dtype=np.float32)):raise ValueError('Source array changed: '+key)
    if not np.array_equal(accessor_array(doc,binary,p['indices'])[:,0],model['indices']):raise ValueError('Source winding/indices changed')
    js=accessor_array(doc,binary,a['JOINTS_0']);ws=accessor_array(doc,binary,a['WEIGHTS_0'])
    expected_js=np.array([[0 if j==255 else j for j in row] for row in model['joints']],dtype=np.uint8)
    expected_ws=np.array([[w/sum(row) for w in row] for row in model['weights']],dtype=np.float32)
    if not np.array_equal(js,expected_js) or not np.array_equal(ws,expected_ws):raise ValueError('Skin influence mismatch')
    if np.any(js>=count) or np.max(np.abs(ws.sum(axis=1)-1))>1e-6:raise ValueError('Skin influence invalid')
    if not np.all(accessor_array(doc,binary,a['COLOR_0'])==255):raise ValueError('White source colours changed')
    vertices=np.column_stack((model['positions'],np.ones(model['vertex_count'])))
    posed=np.einsum('vjik,vk->vji',np.asarray(transforms)[js],vertices)
    positions=np.sum(posed*ws[:,:,None],axis=1)[:,:3];error=float(np.max(np.abs(positions-np.asarray(model['positions']))))
    if not np.all(np.isfinite(positions)) or error>1e-5:raise ValueError('Rest CPU skin differs from original mesh')
    image=doc['images'][0];view=doc['bufferViews'][image['bufferView']]
    if sha(binary[view['byteOffset']:view['byteOffset']+view['byteLength']])!=image['extras']['pngSha256']:raise ValueError('Embedded image differs')
    return {'vertices':len(vertices),'triangles':len(model['indices'])//3,'bones':count,
       'positionsNormalsUvColorsIndicesExact':True,'normalizedSkinInfluencesExact':True,
       'maxGlobalBindError':global_error,'maxBindIdentityError':identity_error,'maxCpuRestSkinError':error}


def build_sampler():
    wrapper=ROOT/'tools/acl_sample.cpp';archive_path=RUNTIME/'acl-v1.2.0.zip'
    if sha(wrapper.read_bytes())!='c2f3e96fc84a7413fd1b060cbea77b48b3cf3818c8b4fc0a754d9802d2b1fdd8':raise ValueError('Sampler wrapper pin changed')
    if sha(archive_path.read_bytes())!='167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8':raise ValueError('ACL archive pin changed')
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            if entry.filename.startswith('acl-1.2.0/includes/') and not entry.is_dir():
                if (RUNTIME/'source'/entry.filename).read_bytes()!=archive.read(entry):raise ValueError('ACL header differs from archive')
    text=wrapper.read_text('utf8');start=text.index('        if (inputHash == ');end=text.index('        require(clipName != nullptr,',start)
    text=text[:start]+''.join(f'        if (inputHash == "{pin}") clipName = "{name}.acl";\n' for name,pin in PINS.items())+text[end:]
    text=text.replace('four pinned original clips','seven pinned boss2013 clips').replace('exactly four SHA-256-pinned original clips','exactly seven SHA-256-pinned boss2013 clips')
    # ACL ClipHeader::segment_range_reduction follows clip_range_reduction;
    # RangeReductionFlags8::None=0, AllTracks=7. Both pinned 24-frame hit clips
    # contain one segment and intentionally omit segment range reduction.
    # Keep the SHA allowlist, all other format gates, and every bounds/hash test.
    if text.count('raw[24] == 7')!=1:raise ValueError('Sampler format gate changed')
    text=text.replace('raw[24] == 7','(raw[24] == 7 || (raw[24] == 0 && h.num_segments == 1))')
    folder=OUT/'decoder-wrapper';folder.mkdir(parents=True,exist_ok=True)
    (folder/'acl_sample.cpp').write_text(text,'utf8')
    includes=(RUNTIME/'source/acl-1.2.0/includes').as_posix()
    (folder/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.15)\nproject(hczs_boss_acl LANGUAGES CXX)\nadd_executable(acl-sample acl_sample.cpp)\ntarget_compile_features(acl-sample PRIVATE cxx_std_17)\ntarget_include_directories(acl-sample PRIVATE "'+includes+'")\ntarget_link_libraries(acl-sample PRIVATE bcrypt)\n','utf8')
    cmake=Path('C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe')
    build=OUT/'decoder-build'
    for command in [[str(cmake),'-S',str(folder),'-B',str(build),'-G','Visual Studio 17 2022','-A','x64'],
                    [str(cmake),'--build',str(build),'--config','Release','--parallel','2']]:
        result=subprocess.run(command,capture_output=True,timeout=180)
        def text(blob):
            return (blob or b'').decode('utf-8','replace')
        with (OUT/'decoder-build.log').open('a',encoding='utf8') as stream:stream.write(text(result.stdout)+'\n'+text(result.stderr)+'\n')
        if result.returncode:raise RuntimeError('ACL helper build failed; see decoder-build.log')
    executable=build/'Release/acl-sample.exe'
    save(OUT/'sampler-provenance.json',{'acceptedAclHashes':PINS,'sourceWrapperSha256':sha(wrapper.read_bytes()),
         'generatedWrapperSha256':sha((folder/'acl_sample.cpp').read_bytes()),'executableSha256':sha(executable.read_bytes()),
         'archiveSha256':sha(archive_path.read_bytes()),'headerBytesMatchedArchive':True,
         'segmentRangeAdaptation':'Allow None=0 only for single-segment pinned clips, in addition to AllTracks=7.',
         'formatEvidence':['acl/core/compressed_clip.h: ClipHeader::segment_range_reduction',
                           'acl/core/range_reduction_types.h: RangeReductionFlags8::None=0x00, AllTracks=0x07']})
    return executable


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    apk=ROOT/'heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'
    with apk.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=APK_SHA256:raise ValueError('Source APK changed')
    gim,gim_source=verified_source(PREFIX+'.gim');mesh,mesh_source=verified_source(PREFIX+'.mesh')
    mtg,mtg_source=verified_source(PREFIX+'.mtg');lib,lib_source=verified_source(PREFIX+'.gisacl')
    model=parse_model(mesh);library=parse_library(lib,allow_empty_roots=True)
    if (model['vertex_count'],model['triangle_count'],model['submesh_count'],len(model['bones']))!=(5463,8380,1,123):raise ValueError('Reviewed mesh identity changed')
    validation=validate_library_bind(model,library);save(OUT/'bind-validation.json',validation)
    material=parse_materials(mtg,expected_slots=1)[0];binding=bind_materials(model,gim,[material])[0]
    cat=read_catalogue(apk);shader_dir=OUT/'shader-evidence'
    shaders=[extract(apk,cat,p,shader_dir/Path(p).name,APK_SHA256) for p in SHADERS]
    semantics=shader_evidence(shader_dir)
    if semantics['surface_parameters']['BaseColor']['Default'].replace(' ','')!='1,1,1,1':raise ValueError('Source colour default changed')
    tex_path=material['params']['Tex0'].rsplit('.',1)[0]+'.ktx';tex,tex_source=verified_source(tex_path)
    decoded=convert([AUDIT/'source'/tex_path],OUT/'colour-png',DEFAULT_DECODER,inspector=DEFAULT_INSPECTOR)['textures'][0]
    if decoded['texture']['profile']!='srgb' or list(decoded['outputs'][0]['channel_extrema_rgba'][3])!=[255,255]:raise ValueError('Unexpected colour/alpha policy')
    png=Path(decoded['outputs'][0]['png']);png=png if png.is_absolute() else ROOT/png
    base=encode_base(model,library,material,binding,png,tex_source,validation)
    static_audit=audit_base(base,model);base_path=OUT/'boss-2013.colour-reference.glb';base_path.write_bytes(base)
    executable=build_sampler();sample_dir=OUT/'samples';sample_dir.mkdir(exist_ok=True);clips=[]
    for name,pin in PINS.items():
        raw,source=verified_source(PREFIX+'_gis_acl/'+name+'.gisacl');metadata=parse_clip(raw)
        if metadata['acl_sha256']!=pin:raise ValueError('Reviewed animation pin changed: '+name)
        record=next(c for c in library['clips'] if c['name']==name)
        metadata.update(source=source,library_record=record,bone_mapping=map_bones(library,metadata,[b['name'] for b in model['bones']]))
        (sample_dir/(name+'.gisacl')).write_bytes(raw);acl=sample_dir/(name+'.acl');acl.write_bytes(raw[metadata['acl_offset']:])
        metadata.update(sample_clip(executable,acl,sample_dir/(name+'.poses'),metadata))
        metadata['sampler_executable_sha256']=sha(executable.read_bytes());save(sample_dir/(name+'.json'),metadata)
        clips.append(load_clip(sample_dir,name,library,[b['name'] for b in model['bones']]))
    animated,clip_reports,trs_error=encode_animation(base,clips)
    doc,binary=split_glb(animated)
    # The shared historic exporter annotates Elsa's toe difference. It is not
    # evidence about this separate mesh; remove only that unrelated metadata.
    doc['extras'].pop('knownBindDifference',None)
    doc['extras']['animationIdentity']='Original boss2013/entity2003 clips; complete source bone-name mapping.'
    animated=pack_glb(doc,binary)
    verification=validate_roundtrip(base,animated,clips)
    if len(verification)!=len(PINS) or sum(r['sample_count_verified'] for r in verification)!=sum(c['frames']*123 for c in clips):raise ValueError('Incomplete animation validation')
    if any(r['moving_tracks']<1 or r['max_vertex_displacement_from_first_frame']<.001 for r in verification):raise ValueError('Expected source motion absent')
    destination=OUT/'boss-2013.animated.glb';pending=destination.with_suffix('.glb.pending');pending.write_bytes(animated);pending.replace(destination)
    durations=[{'name':c['name'],'sourceSampleFrames':c['frames'],'rate':c['rate'],
       'lastSampleSeconds':(c['frames']-1)/c['rate'],'libraryDurationMs':c['metadata']['library_record']['duration_ms'],
       'libraryMinusLastSampleSeconds':c['metadata']['library_record']['duration_ms']/1000-(c['frames']-1)/c['rate']} for c in clips]
    report={'schemaVersion':1,'apkSha256':APK_SHA256,'monsterId':2013,'entityId':2003,'lod':0,
       'sourceFiles':[gim_source,mesh_source,mtg_source,lib_source,tex_source],'shaderSources':shaders,'shaderSemantics':semantics,
       'baseGlb':str(base_path.resolve()),'baseSha256':sha(base),'animatedGlb':str(destination.resolve()),
       'animatedSha256':sha(animated),'animatedBytes':len(animated),'staticValidation':static_audit,
       'bindValidationFile':'bind-validation.json','maxBindMatrixToTrsError':trs_error,
       'clipDurations':durations,'clips':clip_reports,'animationValidation':verification,'textureConversion':decoded,
       'sampledBoneFramesVerified':sum(r['sample_count_verified'] for r in verification),
       'scope':'Numerical glTF/ACL validation only; no engine playback or visual acceptance.',
       'limitations':['Tex0 colour reference only; emission, normal/mix, lighting, particles and sound await a source shader port.',
          'Original source XYZ/binds and all sampled poses are preserved; no coordinate correction applied.',
          'Library duration and last ACL sample timestamp are recorded separately. The buff clip has a one-frame endpoint gap; no time resampling or invented frame was applied.',
          'glTF LINEAR uses quaternion SLERP between keys, unlike ACL normalized LERP; source keyframes match exactly.']}
    save(OUT/'export-report.json',report)
    save(OUT/'manifest.json',{'schemaVersion':1,'monsterId':2013,'entityId':2003,'baseFile':base_path.name,
        'file':destination.name,'sha256':sha(animated),'bytes':len(animated),'clipNames':list(PINS),'report':'export-report.json',
        'enginePlaybackVerified':False})
    print(json.dumps({'file':str(destination),'bytes':len(animated),'sha256':sha(animated),
        'staticValidation':static_audit,'sampledBoneFramesVerified':report['sampledBoneFramesVerified'],
        'clips':[{'name':r['name'],'movingTracks':r['moving_tracks']} for r in verification]},ensure_ascii=False))


if __name__=='__main__':main()
