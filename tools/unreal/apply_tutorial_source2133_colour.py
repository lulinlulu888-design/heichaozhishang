"""Source2133 linear Tex0 colour adapter; default native run is read-only.

Use --plan offline. Parent executes inside a dedicated UE5.8 Editor and supplies
-HczsTutorialSource2133ColourApply to create owned derived textures/materials
and change only L_TutorialSource2133 component overrides. No engine is launched.
Source maps, source UAssets, APK/GLB/PNG and camera/lighting are never changed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'clients/unreal5 5.8'
OUT=ROOT/'analysis/unreal/tutorial-source2133/colour'
MAP='/Game/Recovered/Battle/Maps/L_TutorialSource2133'
SOURCE='/Game/Recovered/SourceStages/RuinedCity/'
META='HczsSource2133ColourRecipeSHA256'
ORIGINAL='HczsSource2133OriginalMaterial'
CACHE=None
sys.path.insert(0,str(ROOT/'tools/unreal'))
from import_recovered_assets import read_glb
from repair_battle_visual_materials import create_material,node,link,prop,source_colour_emissive,save_material


def check(condition,message):
    if not condition: raise RuntimeError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def plan():
    global CACHE
    if CACHE is not None: return CACHE
    base=ROOT/'analysis/battle-visual/prologue-theatre/pszdu_battle_1'
    blob=(base/'scene.glb').read_bytes()
    check(sha(blob)=='56ce6a0565ae113a709c6ab882f93eb91a6e9a6a7ef12b9bd5486f30c93f3828','Source GLB changed')
    doc=read_glb(blob); textures=[]
    for index,(folder,name) in enumerate((('a24b5548d87ce01c936e','fg'),('c9d0b55d02a4f707d555','bg'))):
        manifest_path=base/'png'/folder/'manifest.json'; raw=manifest_path.read_bytes(); entry=json.loads(raw)['textures'][0]
        check(entry['texture']['profile']=='linear' and entry['texture']['internal_format']==0x93b7
              and len(entry['outputs'])==1 and entry['outputs'][0]['decoder_mode']=='-dl','Expected original linear LDR ASTC8x8 decode')
        image=entry['outputs'][0]; png=ROOT/image['png']
        check(sha(png.read_bytes())==image['png_sha256'] and sha((ROOT/entry['source']).read_bytes())==entry['source_sha256'], 'Original texture bytes changed')
        textures.append(dict(index=index,name=name,sourceTexture=SOURCE+'pszdu_battle_1-import_texture_'+str(index)+'.pszdu_battle_1-import_texture_'+str(index),
            manifest=manifest_path.relative_to(ROOT).as_posix(),manifestSha256=sha(raw),png=image['png'],pngSha256=image['png_sha256'],
            originalKtx=entry['source'],originalKtxSha256=entry['source_sha256'],sourceProfile='linear',sourceInternalFormat=0x93b7))
    names=['01_-_Default','Material__12','Material__441','Material__4411']; rows=[]
    for index,material in enumerate(doc['materials']):
        check(material['extras']['sourceTechnique'] in ('shader/common_nolight.fx::TShader','shader/common_nolightuv.fx::TShader')
              and material.get('alphaMode') in ('OPAQUE','BLEND') and material['pbrMetallicRoughness'].get('baseColorFactor',[1,1,1,1])==[1,1,1,1], 'Unknown source colour branch')
        texture=material['pbrMetallicRoughness']['baseColorTexture']['index']
        rows.append(dict(index=index,sourceMaterial=SOURCE+names[index]+'.'+names[index],textureIndex=texture,
            sourceModel=material['extras']['sourceModel'],sourceTechnique=material['extras']['sourceTechnique'],blend=material['alphaMode'],
            twoSided=material['doubleSided'],params=material['extras']['sourceParams'],sourceXML=material['extras']['sourceMaterialXML']))
    shader_pins={
        'analysis/battle-visual/prologue-theatre/source/da23d4cfcfaad0a94e46.fx':'44716e01d5fabbe219b7517b6adb609f0bd65447677110715d0580f89e5cebd6',
        'analysis/battle-visual/prologue-theatre/source/21cc2fea30e763833105.fx':'3eea66d36ef1938a467ee23d58750c95f226b00a48e365bd79a5d51f3b5d92ce'}
    for name,digest in shader_pins.items(): check(sha((ROOT/name).read_bytes())==digest,'Source fixed-function shader changed')
    result=dict(version='source2133-linear-tex0-v1',map=MAP,sourceGLBSha256=sha(blob),textures=textures,materials=rows,shaderPins=shader_pins,
        scope='Native linear texture sampling, original alpha, exposure-independent unlit colour reference; not original NeoX rendering parity.',
        lightOrCameraChanges=False,arbitraryBrightnessMultiplier=False,uvAnimationRecovered=False)
    result['recipe_sha256']=sha(json.dumps(result,sort_keys=True,separators=(',',':')).encode())
    result['destination']='/Game/Recovered/Battle/Source2133Colour/v_'+result['recipe_sha256'][:16]
    CACHE=result; return result


def derived_texture_path(p,index): return p['destination']+'/T_'+p['textures'][index]['name']+'_OriginalLinear'
def derived_material_path(p,index): return p['destination']+'/M_SourceLinear_'+str(index)


def validate_owned_material(u,material,row,p=None):
    p=p or plan(); library=u.MaterialEditingLibrary
    check(isinstance(material,u.Material) and material.get_path_name().split('.')[0]==derived_material_path(p,row['index'])
          and u.EditorAssetLibrary.get_metadata_tag(material,META)==p['recipe_sha256']
          and u.EditorAssetLibrary.get_metadata_tag(material,ORIGINAL)==row['sourceMaterial']
          and u.EditorAssetLibrary.get_metadata_tag(material,'HczsBattleVisualBuildState')=='complete', 'Unowned/incomplete source2133 colour material')
    expected=u.BlendMode.BLEND_OPAQUE if row['blend']=='OPAQUE' else u.BlendMode.BLEND_TRANSLUCENT
    check(material.get_editor_property('shading_model')==u.MaterialShadingModel.MSM_UNLIT
          and material.get_editor_property('blend_mode')==expected and bool(material.get_editor_property('two_sided'))==row['twoSided'], 'Derived colour/blend state differs')
    expressions=list(library.get_material_expressions(material))
    samples=[e for e in expressions if isinstance(e,u.MaterialExpressionTextureSampleParameter2D)]
    inverses=[e for e in expressions if isinstance(e,u.MaterialExpressionEyeAdaptationInverse)]
    constants=[e for e in expressions if isinstance(e,u.MaterialExpressionConstant)]
    check(len(expressions)==3 and len(samples)==len(inverses)==len(constants)==1,'Unknown derived colour graph')
    sample,inverse,strength=samples[0],inverses[0],constants[0]
    tex=sample.get_editor_property('texture')
    check(tex.get_path_name().split('.')[0]==derived_texture_path(p,row['textureIndex'])
          and not tex.get_editor_property('srgb') and not tex.get_editor_property('compression_no_alpha')
          and tex.get_editor_property('compression_settings')==u.TextureCompressionSettings.TC_DEFAULT
          and sample.get_editor_property('sampler_type')==u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
          and u.EditorAssetLibrary.get_metadata_tag(tex,META)==p['recipe_sha256'], 'Derived texture sampling is not the preserved linear colour/alpha')
    check(abs(strength.get_editor_property('r')-1.)<.000001
          and library.get_material_property_input_node(material,u.MaterialProperty.MP_EMISSIVE_COLOR)==inverse
          and list(library.get_inputs_for_material_expression(material,inverse))==[sample,strength], 'Exposure inverse graph does not preserve the sampled source colour')
    connection=library.get_input_node_output_name_for_material_expression(inverse,sample)
    check((connection[-1] if isinstance(connection,tuple) and connection[0] else connection)=='RGB','Source RGB channel path differs')
    if row['blend']=='BLEND':
        check(library.get_material_property_input_node(material,u.MaterialProperty.MP_OPACITY)==sample
              and library.get_material_property_input_node_output_name(material,u.MaterialProperty.MP_OPACITY)=='A','Original source alpha path changed')
    return dict(material=material.get_path_name(),sourceMaterial=row['sourceMaterial'],texture=tex.get_path_name(),srgb=False,
                linearSampler=True,exposureInverseAlpha=1.,blend=row['blend'],graphVerified=True)


def source_binding(u,material):
    """Canonical source identity for setup's idempotent geometry/binding check.

    This accepts only this owned, fully validated graph. It is not a claim that
    an adapted material is byte-identical or visually equivalent to the source.
    """
    p=plan(); candidates=[row for row in p['materials'] if material.get_path_name().split('.')[0]==derived_material_path(p,row['index'])]
    check(len(candidates)==1,'Unknown derived source2133 binding')
    validate_owned_material(u,material,candidates[0],p)
    return candidates[0]['sourceMaterial']


def main():
    import unreal as u
    p=plan(); apply='-HczsTutorialSource2133ColourApply' in u.SystemLibrary.get_command_line().split()
    check(Path(u.Paths.project_dir()).resolve()==PROJECT.resolve() and u.SystemLibrary.get_engine_version().startswith('5.8.'),'Wrong project/engine')
    check(not u.get_editor_subsystem(u.UnrealEditorSubsystem).get_game_world(),'Do not run colour setup during PIE')
    check(not u.EditorLoadingAndSavingUtils.get_dirty_map_packages(),'Retain unsaved editor maps first')
    world=u.EditorLoadingAndSavingUtils.load_map(MAP); check(world and world.get_path_name().split('.')[0]==MAP,'Load exact source2133 target')
    subsystem=u.get_editor_subsystem(u.EditorActorSubsystem); all_actors=list(subsystem.get_all_level_actors())
    map_file=PROJECT/'Content/Recovered/Battle/Maps/L_TutorialSource2133.umap'
    before={str(file):sha(file.read_bytes()) for file in (PROJECT/'Content/Recovered/SourceStages').rglob('*') if file.is_file()}
    for file in (PROJECT/'Content/Recovered/Battle').rglob('*'):
        if file.is_file() and file!=map_file and not file.is_relative_to(PROJECT/'Content'/p['destination'][6:]):
            before[str(file)]=sha(file.read_bytes())
    camera=next(a for a in all_actors if a.actor_has_tag('HCZSBattleCamera')).get_component_by_class(u.CameraComponent)
    camera_settings=str(camera.get_editor_property('post_process_settings'))
    report=dict(schemaVersion=1,mode='source2133-native-linear-colour',passed=False,apply=apply,recipe=p,
                sourceRuntimeExecuted=False,visualMatchVerified=False,probe=[],after=[],assetsModified=False)
    OUT.mkdir(parents=True,exist_ok=True); output=OUT/('native-colour-'+str(time.time_ns())+'.json')
    bindings=[]
    try:
        by_original={r['sourceMaterial']:r for r in p['materials']}
        for actor in all_actors:
            for c in actor.get_components_by_class(u.StaticMeshComponent):
                mesh=c.get_editor_property('static_mesh')
                if not mesh or not mesh.get_path_name().startswith(SOURCE): continue
                for slot in range(c.get_num_materials()):
                    material=c.get_material(slot); original=material.get_path_name()
                    if original not in by_original: original=source_binding(u,material)
                    row=by_original[original]; check(row['sourceModel'].replace('/','_').replace('.','_')==mesh.get_name(),'Wrong original model/material pair')
                    bindings.append((c,slot,row)); interface=u.load_asset(original)
                    texture=u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(interface,'BaseColorTexture')
                    check(texture and texture.get_path_name()==p['textures'][row['textureIndex']]['sourceTexture'],'Actual imported Tex0 reference differs')
                    base=interface; parents=[]
                    while isinstance(base,u.MaterialInstance):
                        parents.append(base.get_path_name()); base=base.get_editor_property('parent')
                    expressions=list(u.MaterialEditingLibrary.get_material_expressions(base)); functions=set()
                    for expression in expressions:
                        if isinstance(expression,u.MaterialExpressionMaterialFunctionCall):
                            function=expression.get_editor_property('material_function')
                            if function and function.get_path_name() not in functions:
                                functions.add(function.get_path_name())
                                expressions.extend(u.MaterialEditingLibrary.get_material_function_expressions(function))
                                check(len(expressions)<1024 and len(functions)<32,'Unexpected unbounded imported shader graph')
                    report['probe'].append(dict(mesh=mesh.get_path_name(),slot=slot,currentMaterial=material.get_path_name(),sourceMaterial=original,
                        importedTexture=texture.get_path_name(),actualSrgb=bool(texture.get_editor_property('srgb')),
                        actualCompression=str(texture.get_editor_property('compression_settings')),
                        baseColourFactor=str(u.MaterialEditingLibrary.get_material_instance_vector_parameter_value(interface,'BaseColorFactor')),
                        parentChain=parents+[base.get_path_name()],baseShadingModel=str(base.get_editor_property('shading_model')),
                        baseGraphClasses=[e.get_class().get_name() for e in expressions],
                        functionsInspected=sorted(functions),exposureInversePresent=any(isinstance(e,u.MaterialExpressionEyeAdaptationInverse) for e in expressions)))
        check(len(bindings)==4,'Expected exactly four source material slots on three surfaces')
        if apply:
            check(all(r['actualSrgb'] and not r['exposureInversePresent'] for r in report['probe']),
                  'Native imported state differs from the diagnosed sRGB/exposure path; inspect read-only probe before applying')
            backup=OUT/'backups'/('pre-colour-'+sha(map_file.read_bytes())+'.umap'); backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists(): backup.write_bytes(map_file.read_bytes())
            check(backup.read_bytes()==map_file.read_bytes(),'Versioned backup bytes differ')
            report['mapBackup']=str(backup); textures={}
            for row in p['textures']:
                dest=derived_texture_path(p,row['index'])
                texture=u.load_asset(dest) if u.EditorAssetLibrary.does_asset_exist(dest) else None
                if texture: check(u.EditorAssetLibrary.get_metadata_tag(texture,META)==p['recipe_sha256'],'Unowned derived texture')
                else: texture=u.EditorAssetLibrary.duplicate_asset(row['sourceTexture'],dest)
                check(isinstance(texture,u.Texture2D),'Cannot create independent linear texture')
                texture.set_editor_property('compression_settings',u.TextureCompressionSettings.TC_DEFAULT)
                texture.set_editor_property('compression_no_alpha',False)
                texture.set_editor_property('virtual_texture_streaming',False)
                texture.set_editor_property('srgb',False)
                u.EditorAssetLibrary.set_metadata_tag(texture,META,p['recipe_sha256'])
                u.EditorAssetLibrary.set_metadata_tag(texture,'HczsSource2133OriginalTexture',row['sourceTexture'])
                check(u.EditorAssetLibrary.save_loaded_asset(texture,False),'Cannot save linear texture')
                textures[row['index']]=texture
            for component,slot,row in bindings:
                material,build=create_material(u,p,'M_SourceLinear_'+str(row['index']),row['blend'])
                if build:
                    material.set_editor_property('two_sided',row['twoSided'])
                    sample=node(u,material,u.MaterialExpressionTextureSampleParameter2D,-500,0,
                        parameter_name='OriginalLinearTex0',texture=textures[row['textureIndex']],sampler_type=u.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                    source_colour_emissive(u,material,sample,'RGB')
                    if row['blend']=='BLEND': prop(u,sample,'A',u.MaterialProperty.MP_OPACITY)
                    u.EditorAssetLibrary.set_metadata_tag(material,META,p['recipe_sha256'])
                    u.EditorAssetLibrary.set_metadata_tag(material,ORIGINAL,row['sourceMaterial'])
                    save_material(u,material,p)
                report['after'].append(validate_owned_material(u,material,row,p)); component.set_material(slot,material)
            check(str(camera.get_editor_property('post_process_settings'))==camera_settings,'Camera exposure changed unexpectedly')
            check(u.EditorLoadingAndSavingUtils.save_map(world,MAP),'Cannot save target-only material overrides')
            report['assetsModified']=True
        check(all(Path(file).is_file() and sha(Path(file).read_bytes())==digest for file,digest in before.items()),'Original/shared protected asset changed')
        report.update(passed=True,protectedFilesUnchanged=True,protectedFileCount=len(before),mapSha256=sha(map_file.read_bytes()),
                      cameraPostProcessUnchanged=str(camera.get_editor_property('post_process_settings'))==camera_settings,
                      rootCauseNativeSrgbConfirmed=all(r['actualSrgb'] for r in report['probe']))
    except Exception:
        report['error']=traceback.format_exc(); raise
    finally:
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),'utf8')
        u.log('HCZS source2133 colour report: '+str(output))


if __name__=='__main__':
    if '--plan' in sys.argv: print(json.dumps(plan(),ensure_ascii=False,indent=2))
    else: main()
