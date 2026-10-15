"""Source-textured derived battle materials; root serializes full Editor execution.

Ordinary Python --plan is read-only. In Editor the default is a read-only
material/texture/exposure probe. -HczsBattleVisualApply creates a new owned
namespace and changes only this saved map's material overrides. Camera exposure,
tone mapping and lighting are inspected but never changed to conceal bad shading.
No original APK/GLB/PNG, source UE texture/material/mesh or engine asset changes.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/unreal'))
sys.path.insert(0,str(ROOT/'tools'))
from verify_battle_scene import input_plan,content_hashes,obj_path
from export_elsa_model import split_glb
from repair_battle_alpha import params

PROJECT=ROOT/'clients/unreal5 5.8/Hczs.uproject'
MAP='/Game/Recovered/Battle/Maps/L_TutorialBattle'
SHADER=ROOT/'analysis/battle-visual/weapon/effect/lancer2.fx'
RECIPE_VERSION='source-rgba-and-lancer-mask-v3-exposure-independent-colour'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def source_plan():
    staged=input_plan()
    native=json.loads((ROOT/'analysis/unreal/battle-inputs/native-readback.json').read_text('utf8'))
    if native['manifest_sha256']!=staged['manifest_sha256']:
        raise ValueError('Actual actor/material inventory belongs to another staged input')
    imported=json.loads((ROOT/'analysis/unreal/battle-inputs/import-result.json').read_text('utf8'))
    imported_rows={r['id']:r for r in imported['results']}
    result=[]
    for side in ('player','enemy'):
        doc=staged['rows'][side]['document']
        textures={r['name']:r['path'] for r in imported_rows[side]['assets'] if r['class_name']=='Texture2D'}
        for actual in native['combatants'][side]['materials']:
            material=actual['staged_source_material']
            index=doc['materials'].index(material)
            pbr=material['pbrMetallicRoughness']
            texture=pbr['baseColorTexture']
            image=doc['images'][doc['textures'][texture['index']]['source']]
            if image.get('name')not in textures or texture.get('texCoord',0)!=0:
                raise ValueError('Unverified source colour texture or UV set')
            result.append(dict(side=side,component_slot=actual['slot'],source_material=index,
                source_name=material['name'],current_interface=actual['path'],
                texture=textures[image['name']],tint=pbr.get('baseColorFactor',[1,1,1,1]),
                blend=material.get('alphaMode','OPAQUE'),cutoff=material.get('alphaCutoff',.5),
                two_sided=material.get('doubleSided',False)))
    cloud=staged['rows']['stage']['document']['materials'][0]
    original=ET.fromstring(cloud['extras']['sourceMaterialXML'])
    macros={x.attrib['Key']:x.attrib['Val']for x in original.findall('ShaderMacro/*')}
    source_params=cloud['extras']['sourceParams']
    if (cloud['extras']['sourceModel']!='effects/modeleffect/scene/plane_yun.gim'
        or original.find('RenderStates/TransparentMode').attrib['TransparentMode']!='5'
        or macros!={'ALPHA_MASK':'TRUE'}
        or float(source_params['g_AlphaMaskStrength'])!=.2):
        raise ValueError('Reviewed cloud shader branch/source fields changed')
    shader=SHADER.read_bytes()
    # Source expressions are a shader port boundary, not an invented effect.
    for expression in (b'local_12.w * local_54.x * g_AlphaMaskStrength',
                       b'local_31 * g_colFloatingColor1_linear.xyz',
                       b'vsIN.a_texture0.xy * g_vDistortionTiling'):
        if expression not in shader:raise ValueError('Reviewed original cloud shader expression missing')
    clouds=[r for r in native['stage_instances']if 'effects_modeleffect_scene_plane_yun_gim' in r['mesh']]
    if len(clouds)!=2:raise ValueError('Expected two original cloud-plane instances')
    stage_assets=imported_rows['stage']['assets']
    stage_textures={r['name']:r['path']for r in stage_assets if r['class_name']=='Texture2D'}
    for name in ('city_battle_1_texture_0','city_battle_1_texture_1','city_battle_1_texture_2'):
        if name not in stage_textures:raise ValueError('Actual imported cloud texture reference missing')
    recipe=dict(version=RECIPE_VERSION,manifest_sha256=staged['manifest_sha256'],
        actor_materials=result,cloud_actors=[c['actor']for c in clouds],
        cloud_source_params=source_params,cloud_shader_sha256=sha(shader),
        cloud_textures=[stage_textures['city_battle_1_texture_'+str(i)]for i in range(3)],
        exposure='Preserved; fix texture/material wiring without changing exposure, tone mapping or lighting',
        source_color_scope='Existing staged original-colour references; original NeoX character shading is separate',
        cloud_blend_scope='Recovered source alpha-mask/panner/distortion branch using UE translucent; native NeoX mode5 blend equality unverified')
    previous={**recipe,'version':'source-rgba-and-lancer-mask-v2-preserve-camera'}
    previous_digest=sha(json.dumps(previous,sort_keys=True,separators=(',',':')).encode())
    recipe['colour_display_adapter']='Source linear RGB * EyeAdaptationInverse(alpha=1); preserve source alpha and UE camera/lighting. This is UE adaptation, not recovered NeoX lighting.'
    digest=sha(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode())
    return {**recipe,'recipe_sha256':digest,'destination':'/Game/Recovered/Battle/VisualFix/v3_'+digest[:16],
        'previous_recipe_sha256':previous_digest,'previous_destination':'/Game/Recovered/Battle/VisualFix/v2_'+previous_digest[:16]}


def context(unreal):
    if Path(unreal.Paths.get_project_file_path()).resolve()!=PROJECT or not unreal.SystemLibrary.get_engine_version().startswith('5.8.'):
        raise RuntimeError('Use current project in full UE5.8 Editor')
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.')[0]!=MAP:
        raise RuntimeError('Open existing saved tutorial map, outside PIE')
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    def tagged(tag):
        matches=[a for a in actors if a.actor_has_tag(tag)]
        if len(matches)!=1:raise RuntimeError('Missing/ambiguous actor '+tag)
        return matches[0]
    components={side:tagged(tag).get_component_by_class(unreal.SkeletalMeshComponent)
        for side,tag in [('player','HCZSBattlePlayer'),('enemy','HCZSBattleEnemy')]}
    if not components['player']or not components['enemy']or components['player'].get_num_materials()!=9 or components['enemy'].get_num_materials()!=1:
        raise RuntimeError('Original actor slot inventory changed')
    camera=tagged('HCZSBattleCamera').get_component_by_class(unreal.CameraComponent)
    if not camera:raise RuntimeError('Owned source battle camera missing')
    return world,actors,components,camera


def material_params(unreal,interface):
    if isinstance(interface,unreal.MaterialInstanceConstant):return params(unreal,interface)
    if not isinstance(interface,unreal.Material):return {'class':interface.get_class().get_name(),'unsupported':True}
    edit=unreal.MaterialEditingLibrary
    vectors={}
    for name in edit.get_vector_parameter_names(interface):
        v=edit.get_material_default_vector_parameter_value(interface,name);vectors[str(name)]=[v.r,v.g,v.b,v.a]
    return dict(vector=vectors,scalar={str(n):edit.get_material_default_scalar_parameter_value(interface,n)
        for n in edit.get_scalar_parameter_names(interface)},texture={str(n):obj_path(edit.get_material_default_texture_parameter_value(interface,n))
        for n in edit.get_texture_parameter_names(interface)})


def probe(unreal,components,camera,actors):
    report={'actors':[],'clouds':[],'camera':{},'textures':{}}
    for side,component in components.items():
        for i in range(component.get_num_materials()):
            interface=component.get_material(i)
            snapshot=material_params(unreal,interface)
            row=dict(side=side,slot=i,path=obj_path(interface),parameters=snapshot)
            report['actors'].append(row)
            unreal.log('HCZS VISUAL PROBE '+json.dumps(row,ensure_ascii=False))
            for path in snapshot.get('texture',{}).values():
                texture=unreal.load_asset(path)if path else None
                if not isinstance(texture,unreal.Texture2D):continue
                values={}
                for name in ('srgb','compression_settings','compression_no_alpha','virtual_texture_streaming','lod_bias'):
                    try:values[name]=str(texture.get_editor_property(name))
                    except Exception as exc:values[name]={'unavailable':str(exc)}
                report['textures'][path]=values
    for actor in actors:
        component=actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh=None
        if component:
            try:mesh=component.get_editor_property('static_mesh')
            except Exception:pass  # Editor camera proxy components can omit this property/API.
        if mesh and 'plane_yun' in mesh.get_name():
            row=dict(actor=actor.get_path_name(),material=obj_path(component.get_material(0)),parameters=material_params(unreal,component.get_material(0)))
            report['clouds'].append(row);unreal.log('HCZS VISUAL CLOUD '+json.dumps(row,ensure_ascii=False))
    settings=camera.get_editor_property('post_process_settings')
    for name in ('override_auto_exposure_method','auto_exposure_method','override_auto_exposure_bias','auto_exposure_bias',
                 'override_auto_exposure_apply_physical_camera_exposure','auto_exposure_apply_physical_camera_exposure',
                 'override_tone_curve_amount','tone_curve_amount','override_color_gain','color_gain'):
        try:
            raw=settings.get_editor_property(name)
            value=[float(getattr(raw,c))for c in ('x','y','z','w')]if all(hasattr(raw,c)for c in ('x','y','z','w'))else str(raw)
        except Exception as exc:value={'unavailable':str(exc)}
        report['camera'][name]=value
        unreal.log('HCZS VISUAL CAMERA '+name+'='+str(value))
    return report


def create_material(unreal,plan,name,blend,cutoff=0):
    path=plan['destination']+'/'+name
    existing=unreal.load_asset(path)if unreal.EditorAssetLibrary.does_asset_exist(path)else None
    if existing:
        if not isinstance(existing,unreal.Material)or unreal.EditorAssetLibrary.get_metadata_tag(existing,'HczsBattleVisualRecipeSHA256')!=plan['recipe_sha256']:
            raise RuntimeError('Refuse to overwrite unrelated material '+path)
        if unreal.EditorAssetLibrary.get_metadata_tag(existing,'HczsBattleVisualBuildState')=='complete':return existing,False
        # Resume only our own partial graph; original/shared materials are untouched.
        unreal.MaterialEditingLibrary.delete_all_material_expressions(existing)
        asset=existing
    else:
        asset=unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,plan['destination'],unreal.Material,unreal.MaterialFactoryNew())
    if not asset:raise RuntimeError('Could not create independent material '+name)
    unreal.EditorAssetLibrary.set_metadata_tag(asset,'HczsBattleVisualRecipeSHA256',plan['recipe_sha256'])
    unreal.EditorAssetLibrary.set_metadata_tag(asset,'HczsBattleVisualBuildState','building')
    asset.set_editor_property('blend_mode',dict(OPAQUE=unreal.BlendMode.BLEND_OPAQUE,MASK=unreal.BlendMode.BLEND_MASKED,BLEND=unreal.BlendMode.BLEND_TRANSLUCENT)[blend])
    asset.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    asset.set_editor_property('two_sided',True)
    asset.set_editor_property('opacity_mask_clip_value',cutoff)
    unreal.MaterialEditingLibrary.set_base_material_usage(asset,unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH,True)
    return asset,True


def node(unreal,material,kind,x,y,**properties):
    obj=unreal.MaterialEditingLibrary.create_material_expression(material,kind,x,y)
    if not obj:raise RuntimeError('Could not create material expression')
    for key,value in properties.items():obj.set_editor_property(key,value)
    return obj


def link(unreal,source,output,target,input_name):
    if not unreal.MaterialEditingLibrary.connect_material_expressions(source,output,target,input_name):
        raise RuntimeError('Material connection failed '+input_name)


def prop(unreal,source,output,property_id):
    if not unreal.MaterialEditingLibrary.connect_material_property(source,output,property_id):
        raise RuntimeError('Material property connection failed')


def source_colour_emissive(unreal,material,source,output):
    # UE5.8 EyeAdaptationCommon.ush: Alpha=1 gives exp(-log(Exposure))=1/Exposure.
    # This removes scene exposure amplification of the unlit colour reference,
    # without changing the camera or attenuating source alpha/mask values.
    inverse=node(unreal,material,unreal.MaterialExpressionEyeAdaptationInverse,450,-100)
    strength=node(unreal,material,unreal.MaterialExpressionConstant,200,-300,r=1.0)
    names=[str(n)for n in unreal.MaterialEditingLibrary.get_material_expression_input_names(inverse)]
    def pin(prefix):
        matches=[name for name in names if ''.join(c for c in name.lower()if c.isalnum()).startswith(prefix)]
        if len(matches)!=1:raise RuntimeError('Unexpected UE EyeAdaptationInverse input pins: '+repr(names))
        return matches[0]
    link(unreal,source,output,inverse,pin('lightvalue'))
    link(unreal,strength,'',inverse,pin('alpha'))
    prop(unreal,inverse,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)


def save_material(unreal,material,plan):
    result=unreal.MaterialEditingLibrary.recompile_material(material)
    # UE5.8.3 header returns TArray<FString>; older Python wrappers may return None.
    if result is None:raise RuntimeError('Material compiler provided no diagnostic result; do not mark material complete')
    errors=list(result)
    if errors:raise RuntimeError('Source material compile failed '+repr(errors))
    unreal.EditorAssetLibrary.set_metadata_tag(material,'HczsBattleVisualRecipeSHA256',plan['recipe_sha256'])
    unreal.EditorAssetLibrary.set_metadata_tag(material,'HczsBattleVisualBuildState','complete')
    if not unreal.EditorAssetLibrary.save_loaded_asset(material,False):raise RuntimeError('Derived material save failed')


def duplicate_texture(unreal,plan,path,numeric=False):
    suffix='_Numeric'if numeric else '_Colour'
    dest=plan['destination']+'/T_'+path.rsplit('/',1)[-1].split('.')[0]+suffix
    if unreal.EditorAssetLibrary.does_asset_exist(dest):
        texture=unreal.load_asset(dest)
        if not isinstance(texture,unreal.Texture2D)or unreal.EditorAssetLibrary.get_metadata_tag(texture,'HczsBattleVisualRecipeSHA256')!=plan['recipe_sha256']:
            raise RuntimeError('Unexpected derived texture exists')
        if unreal.EditorAssetLibrary.get_metadata_tag(texture,'HczsBattleVisualOriginalTexture')!=path:
            raise RuntimeError('Existing owned texture has a different source')
    else:
        texture=unreal.EditorAssetLibrary.duplicate_asset(path,dest)
    if not isinstance(texture,unreal.Texture2D):raise RuntimeError('Cannot duplicate imported source texture')
    # UE resets SRGB while changing normal-map compression. Normalize compression
    # first, then explicitly restore SRGB last, including owned partial retries.
    texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS if numeric else unreal.TextureCompressionSettings.TC_DEFAULT)
    texture.set_editor_property('compression_no_alpha',False)
    texture.set_editor_property('virtual_texture_streaming',False)
    texture.set_editor_property('srgb',not numeric)
    # set_editor_property dispatches PostEditChangeProperty; some engine wrappers
    # also expose the explicit final PostEditChange hook, so use it when present.
    if hasattr(texture,'post_edit_change'):texture.post_edit_change()
    expected=unreal.TextureCompressionSettings.TC_MASKS if numeric else unreal.TextureCompressionSettings.TC_DEFAULT
    if bool(texture.get_editor_property('srgb'))!=(not numeric)or texture.get_editor_property('compression_settings')!=expected:
        raise RuntimeError('Derived texture failed color-space/compression readback: '+dest)
    unreal.EditorAssetLibrary.set_metadata_tag(texture,'HczsBattleVisualRecipeSHA256',plan['recipe_sha256'])
    unreal.EditorAssetLibrary.set_metadata_tag(texture,'HczsBattleVisualOriginalTexture',path)
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture,False):raise RuntimeError('Derived texture save failed')
    if bool(texture.get_editor_property('srgb'))!=(not numeric)or texture.get_editor_property('compression_settings')!=expected:
        raise RuntimeError('Saving derived texture changed color-space/compression: '+dest)
    return texture


def source_colour_material(unreal,plan,row,texture):
    name='M_'+row['side']+'_'+str(row['component_slot'])+'_SourceRGBA'
    material,build=create_material(unreal,plan,name,row['blend'],row['cutoff']if row['blend']=='MASK'else 0)
    if not build:return material
    material.set_editor_property('two_sided',row['two_sided'])
    sample=node(unreal,material,unreal.MaterialExpressionTextureSampleParameter2D,-700,-100,
        parameter_name='SourceColorTexture',texture=texture,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    tint=node(unreal,material,unreal.MaterialExpressionVectorParameter,-700,100,
        parameter_name='SourceColorFactor',default_value=unreal.LinearColor(*row['tint']))
    multiply=node(unreal,material,unreal.MaterialExpressionMultiply,-350,-100)
    link(unreal,sample,'RGB',multiply,'A');link(unreal,tint,'RGB',multiply,'B')
    source_colour_emissive(unreal,material,multiply,'')
    if row['blend']!='OPAQUE':
        alpha=node(unreal,material,unreal.MaterialExpressionMultiply,-350,150)
        link(unreal,sample,'A',alpha,'A');link(unreal,tint,'A',alpha,'B')
        prop(unreal,alpha,'',unreal.MaterialProperty.MP_OPACITY_MASK if row['blend']=='MASK'else unreal.MaterialProperty.MP_OPACITY)
    save_material(unreal,material,plan)
    return material


def cloud_material(unreal,plan,textures):
    material,build=create_material(unreal,plan,'M_OriginalCloudMaskedFlow','BLEND')
    if not build:return material
    p=plan['cloud_source_params']
    def numbers(key):return [float(v)for v in p[key].split(',')]
    def srgb_to_linear(x):return x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4
    tint=[srgb_to_linear(x)for x in numbers('g_colFloatingColor1')[:3]]
    code='''float2 noiseUV = UV * float2(%s,%s) + Time * float2(%s,%s);
float n = Texture2DSample(Noise,NoiseSampler,noiseUV).r;
float2 colorUV = UV * float2(%s,%s) + n * %s + Time * float2(%s,%s);
float4 c = Texture2DSample(Color,ColorSampler,colorUV);
float mask = Texture2DSample(Mask,MaskSampler,UV).r;
return float4(c.rgb * float3(%s,%s,%s), saturate(c.a * mask * %s));'''%tuple(
        numbers('g_vDistortionTiling')+numbers('g_vDistortionSpeed')+numbers('g_vFloatingTiling1')+
        [float(p['g_fDistortionStrength'])]+numbers('g_vFloatingSpeed1')+tint+[float(p['g_AlphaMaskStrength'])])
    expression=node(unreal,material,unreal.MaterialExpressionCustom,-100,-100,
        code=code,output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT4,description='Source lancer2 ALPHA_MASK branch')
    names=('UV','Time','Color','Noise','Mask')
    inputs=[]
    for name in names:
        value=unreal.CustomInput();value.set_editor_property('input_name',name);inputs.append(value)
    expression.set_editor_property('inputs',inputs)
    uv=node(unreal,material,unreal.MaterialExpressionTextureCoordinate,-600,-500,coordinate_index=0)
    time=node(unreal,material,unreal.MaterialExpressionTime,-600,-350)
    link(unreal,uv,'',expression,'UV');link(unreal,time,'',expression,'Time')
    for i,name in enumerate(('Color','Noise','Mask')):
        texture=node(unreal,material,unreal.MaterialExpressionTextureObjectParameter,-600,i*150,
            parameter_name='Source'+name,texture=textures[i],
            sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if i==0 else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        link(unreal,texture,'',expression,name)
    rgb=node(unreal,material,unreal.MaterialExpressionComponentMask,150,-150,r=True,g=True,b=True,a=False)
    alpha=node(unreal,material,unreal.MaterialExpressionComponentMask,150,150,r=False,g=False,b=False,a=True)
    link(unreal,expression,'',rgb,'');link(unreal,expression,'',alpha,'')
    source_colour_emissive(unreal,material,rgb,'');prop(unreal,alpha,'',unreal.MaterialProperty.MP_OPACITY)
    save_material(unreal,material,plan)
    return material


def write_report(name,report):
    folder=ROOT/'analysis/unreal/battle-color';folder.mkdir(parents=True,exist_ok=True)
    (folder/name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


def derived_path(plan,row):
    name='M_'+row['side']+'_'+str(row['component_slot'])+'_SourceRGBA'
    return plan['destination']+'/'+name+'.'+name


def allowed_previous_binding(unreal,plan,row,interface):
    name='M_'+row['side']+'_'+str(row['component_slot'])+'_SourceRGBA'
    expected=plan['previous_destination']+'/'+name+'.'+name
    return (obj_path(interface)==expected and
        unreal.EditorAssetLibrary.get_metadata_tag(interface,'HczsBattleVisualRecipeSHA256')==plan['previous_recipe_sha256'] and
        unreal.EditorAssetLibrary.get_metadata_tag(interface,'HczsBattleVisualBuildState')=='complete')


def verify_bindings(unreal,plan,components,clouds):
    for row in plan['actor_materials']:
        material=components[row['side']].get_material(row['component_slot'])
        if obj_path(material)!=derived_path(plan,row):raise RuntimeError('Wrong derived actor binding')
        if unreal.EditorAssetLibrary.get_metadata_tag(material,'HczsBattleVisualBuildState')!='complete':raise RuntimeError('Incomplete material binding')
        if unreal.EditorAssetLibrary.get_metadata_tag(material,'HczsBattleVisualRecipeSHA256')!=plan['recipe_sha256']:raise RuntimeError('Wrong material recipe')
        source=unreal.MaterialEditingLibrary.get_material_default_texture_parameter_value(material,'SourceColorTexture')
        if not source or unreal.EditorAssetLibrary.get_metadata_tag(source,'HczsBattleVisualOriginalTexture')!=row['texture']:
            raise RuntimeError('Source texture binding no longer matches the recovery plan')
        if not source.get_editor_property('srgb')or source.get_editor_property('compression_settings')!=unreal.TextureCompressionSettings.TC_DEFAULT:
            raise RuntimeError('Source colour texture uses wrong color space/compression')
        tint=unreal.MaterialEditingLibrary.get_material_default_vector_parameter_value(material,'SourceColorFactor')
        if any(abs(a-b)>1e-5 for a,b in zip((tint.r,tint.g,tint.b,tint.a),row['tint'])):
            raise RuntimeError('Source material colour factor changed')
        mode={'OPAQUE':unreal.BlendMode.BLEND_OPAQUE,'MASK':unreal.BlendMode.BLEND_MASKED,'BLEND':unreal.BlendMode.BLEND_TRANSLUCENT}[row['blend']]
        if material.get_editor_property('blend_mode')!=mode:raise RuntimeError('Source blend mode changed')
        if row['blend']=='MASK'and abs(material.get_editor_property('opacity_mask_clip_value')-row['cutoff'])>1e-6:
            raise RuntimeError('Source alpha threshold changed')
    cloud_path=plan['destination']+'/M_OriginalCloudMaskedFlow.M_OriginalCloudMaskedFlow'
    for component in clouds:
        material=component.get_material(0)
        if obj_path(material)!=cloud_path or material.get_editor_property('blend_mode')!=unreal.BlendMode.BLEND_TRANSLUCENT:
            raise RuntimeError('Original cloud mask material missing')
        for i,name in enumerate(('Color','Noise','Mask')):
            texture=unreal.MaterialEditingLibrary.get_material_default_texture_parameter_value(material,'Source'+name)
            if not texture or unreal.EditorAssetLibrary.get_metadata_tag(texture,'HczsBattleVisualOriginalTexture')!=plan['cloud_textures'][i]:
                raise RuntimeError('Cloud source texture binding changed')
            if bool(texture.get_editor_property('srgb'))!=(i==0):raise RuntimeError('Cloud colour/numeric texture spaces changed')


def run(apply=False):
    import unreal
    plan=source_plan();before=content_hashes();world,actors,components,camera=context(unreal)
    captured=probe(unreal,components,camera,actors)
    report=dict(schema='hczs-battle-visual-material-repair-v3',recipe=plan,apply=apply,
        engine_version=unreal.SystemLibrary.get_engine_version(),before=captured,passed=False,map_saved=False,
        camera_changed=False,original_neox_character_shading_restored=False)
    write_report('native-material-probe.json',report)
    if not apply:
        if before!=content_hashes():raise RuntimeError('Read-only probe changed content')
        report['passed']=True;write_report('native-material-probe.json',report)
        unreal.log('HCZS VISUAL read-only probe complete; no asset/map write')
        return report
    if unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():raise RuntimeError('Unsaved map changes exist')
    clouds=[]
    for path in plan['cloud_actors']:
        matches=[a for a in actors if a.get_path_name()==path]
        if len(matches)!=1:raise RuntimeError('Original cloud actor missing')
        component=matches[0].get_component_by_class(unreal.StaticMeshComponent)
        if not component or component.get_num_materials()!=1:raise RuntimeError('Original cloud slot count changed')
        clouds.append(component)
    for row in plan['actor_materials']:
        interface=components[row['side']].get_material(row['component_slot'])
        if obj_path(interface)not in (row['current_interface'],derived_path(plan,row))and not allowed_previous_binding(unreal,plan,row,interface):
            raise RuntimeError('Source actor binding changed since native readback')
        if not isinstance(unreal.load_asset(row['texture']),unreal.Texture2D):raise RuntimeError('Actual source texture missing')
    # A fully applied retry only verifies the owned bindings; no map save required.
    if all(obj_path(components[r['side']].get_material(r['component_slot']))==derived_path(plan,r)for r in plan['actor_materials']):
        verify_bindings(unreal,plan,components,clouds)
        report.update(passed=True,already_applied=True)
        write_report('material-repair-result.json',report)
        return report
    # Preserve the first saved map for this recipe. A failed partial build is resumable.
    backup=ROOT/'analysis/unreal/battle-color/backups'/plan['recipe_sha256']
    backup.mkdir(parents=True,exist_ok=True)
    map_file=PROJECT.parent/'Content/Recovered/Battle/Maps/L_TutorialBattle.umap'
    if not (backup/'L_TutorialBattle.umap').exists():
        (backup/'L_TutorialBattle.umap').write_bytes(map_file.read_bytes())
    report['map_backup']=str(backup/'L_TutorialBattle.umap')
    originals={c:list(c.get_editor_property('override_materials'))for c in list(components.values())+clouds}
    saved=False
    try:
        created=[]
        for row in plan['actor_materials']:
            texture=duplicate_texture(unreal,plan,row['texture'])
            created.append((components[row['side']],row['component_slot'],source_colour_material(unreal,plan,row,texture)))
        cloud_textures=[duplicate_texture(unreal,plan,path,numeric=i>0)for i,path in enumerate(plan['cloud_textures'])]
        cloud=cloud_material(unreal,plan,cloud_textures)
        for component,slot,material in created:component.set_material(slot,material)
        for component in clouds:component.set_material(0,cloud)
        verify_bindings(unreal,plan,components,clouds)
        after=content_hashes();prefix=plan['destination'].split('/Game/Recovered/Battle/',1)[1]+'/'
        if any(after.get(k)!=before.get(k)for k in set(before)|set(after)if k!='Maps/L_TutorialBattle.umap'and not k.startswith(prefix)):
            raise RuntimeError('Protected source UE Battle content changed before map save')
        if not unreal.EditorLoadingAndSavingUtils.save_map(world,MAP):raise RuntimeError('Bounded battle map save failed')
        saved=True
        after=content_hashes()
        if any(after.get(k)!=before.get(k)for k in set(before)|set(after)if k!='Maps/L_TutorialBattle.umap'and not k.startswith(prefix)):
            raise RuntimeError('Protected source UE Battle content changed')
        source_plan()
        report.update(passed=True,map_saved=True,after=probe(unreal,components,camera,actors))
        if report['before']['camera']!=report['after']['camera']:raise RuntimeError('Camera changed during material-only repair')
        write_report('material-repair-result.json',report)
        unreal.log('HCZS VISUAL source-derived materials saved; exposure/lighting preserved: '+plan['destination'])
        unreal.log('HCZS VISUAL original cloud mask/panner port uses UE translucent; source NeoX blend5/character shading not claimed equivalent')
        unreal.log('HCZS VISUAL fresh-process frame required; current running game remains unchanged until controlled reload')
        return report
    except Exception as exc:
        report.update(error=repr(exc),map_saved=saved)
        write_report('material-repair-result.json',report)
        if not saved:
            for component,materials in originals.items():component.set_editor_property('override_materials',materials)
        raise


if __name__=='__main__':
    if '--plan'in sys.argv:
        plan=source_plan()
        print(json.dumps({k:plan[k]for k in ('recipe_sha256','destination','actor_materials','cloud_actors','cloud_source_params','exposure','cloud_blend_scope')},ensure_ascii=False,indent=2))
    else:
        import unreal
        run(apply=' -HczsBattleVisualApply 'in ' '+unreal.SystemLibrary.get_command_line()+' ')
