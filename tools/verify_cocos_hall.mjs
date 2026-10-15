/** Static hall import/build audit; does not execute shaders or claim runtime equivalence. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {parseCCON,floatArray,prefabTree,quaternionDifference} from './verify_cocos_character.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),project=path.join(root,'legacy/cocos-poc'),creator=path.join(root,'.tools/cocos/3.8.8');
const assets=path.join(project,'assets/resources/recovered/hall'),bundle=path.join(project,'build/web-desktop/assets/resources');
const output=path.join(root,'analysis/hall/cocos-import-audit.json'),inputs=new Map();
const hash=b=>createHash('sha256').update(b).digest('hex'),ensure=(v,m)=>{if(!v)throw Error(m);};
async function read(p){const b=await fs.readFile(p);inputs.set(p,hash(b));return b;}
const json=async p=>JSON.parse((await read(p)).toString('utf8').replace(/^\uFEFF/,''));
const library=(uuid,ext)=>path.join(project,'library',uuid.slice(0,2),uuid+ext);
const report={passed:false,scope:'Static imported prefab/skeleton/animation/UV1 and Web build inventory',runtimeVerified:false,characters:[],checks:[],limitations:['No shader GPU execution or native device runtime in this audit.','Packed build prefab JSON inventory is checked; packed object equivalence is not decoded.','Animation values compare all GLB exported source keys; prior source ACL export verification remains separate.']};
const check=(name,value,detail={})=>{report.checks.push({name,passed:!!value,...detail});ensure(value,name);};
function glb(raw){const n=raw.readUInt32LE(12),doc=JSON.parse(raw.toString('utf8',20,20+n)),binary=raw.subarray(28+n);return {doc,acc(index){const a=doc.accessors[index],v=doc.bufferViews[a.bufferView],width={SCALAR:1,VEC3:3,VEC4:4}[a.type];ensure(a.componentType===5126&&width&&!v.byteStride,'GLB accessor unsupported');const values=[];for(let i=0;i<a.count*width;i++)values.push(binary.readFloatLE((v.byteOffset||0)+(a.byteOffset||0)+i*4));return values;}};}
try {
 await read(fileURLToPath(import.meta.url));
 const require=createRequire(import.meta.url),ts=require(path.join(creator,'resources/app.asar.unpacked/node_modules/typescript'));
 const decoder=await read(path.join(creator,'resources/resources/3d/engine/external/deserialize/notepack_decode.ts'));
 const emitted=ts.transpileModule(decoder.toString(),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ES2020}}).outputText;
 const {notepackDecode}=await import('data:text/javascript;base64,'+Buffer.from(emitted).toString('base64'));
 const config=await json(path.join(bundle,'config.json'));ensure(config.debug===true&&config.name==='resources','unsupported build config');
 const imports=path.resolve(bundle,config.importBase);ensure(imports.startsWith(bundle+path.sep),'unsafe build import path');
 async function model(name){const file=path.join(assets,name,name+'.glb'),raw=await read(file),meta=await json(file+'.meta');ensure(meta.imported&&meta.importer==='gltf','model import absent '+name);const subs=Object.values(meta.subMetas),scenes=subs.filter(x=>x.importer==='gltf-scene');check(name+':unique_library_prefab',scenes.length===1);const prefab=await json(library(scenes[0].uuid,'.json')),tree=prefabTree(prefab);check(name+':unique_build_prefab',Object.entries(config.paths).filter(([,v])=>v[1]==='cc.Prefab'&&v[0].startsWith('recovered/hall/'+name+'/')).length===1&&config.paths[scenes[0].uuid]?.[1]==='cc.Prefab');return {raw,meta,subs,prefab,tree,source:glb(raw)};}
 for(const name of ['actor','weapon']){
  const m=await model(name);const exportReport=await json(path.join(root,'analysis/characters/shiranui',name==='actor'?'export':'export-weapon','export-report.json'));check(name+':matches_verified_export',hash(m.raw)===exportReport.sha256);const clips=m.subs.filter(s=>s.importer==='gltf-animation'),skeletons=m.subs.filter(s=>s.importer==='gltf-skeleton');check(name+':one_idle_one_skeleton',clips.length===1&&skeletons.length===1);
  const skeleton=await json(library(skeletons[0].uuid,'.json')),joints=skeleton._joints;check(name+':all_bones_resolve',joints.length===(name==='actor'?251:19)&&joints.every(p=>m.tree.resolve(p)));
  const animationComponents=m.prefab.filter(n=>n.__type__==='cc.SkeletalAnimation'),skinRenderers=m.prefab.filter(n=>n.__type__==='cc.SkinnedMeshRenderer');check(name+':skin_and_animation_root_links',animationComponents.length===1&&skinRenderers.length===1&&m.prefab[animationComponents[0].node.__id__]===m.tree.root&&m.prefab[skinRenderers[0]._skinningRoot.__id__]===m.tree.root&&skinRenderers[0]._skeleton.__uuid__===skeletons[0].uuid);
  const bytes=await read(library(clips[0].uuid,'.bin')),{document,chunk}=parseCCON(bytes,notepackDecode),clip=document[0];check(name+':original_idle_name',clip._name==='home_stand_idle_1');
  const deref=r=>{ensure(Number.isInteger(r?.__id__)&&document[r.__id__],'bad animation reference');return document[r.__id__];};
  const nodes=deref(clip._exoticAnimation)._nodeAnimations.map(deref),byName=new Map();for(const n of nodes){const resolved=m.tree.resolve(n._path);ensure(resolved,'unresolved imported animation path');ensure(!byName.has(resolved._name),'duplicate imported animation name');byName.set(resolved._name,n);}
  const prefabNodes=m.prefab.filter(n=>n.__type__==='cc.Node');let maxRestTRSError=0,comparedRestNodes=0;
  const components=(n,k,w)=>w.map(c=>n[k][c]);
  check(name+':import_root_identity',components(m.tree.root,'_lpos',['x','y','z']).every(v=>v===0)&&components(m.tree.root,'_lscale',['x','y','z']).every(v=>v===1)&&quaternionDifference(components(m.tree.root,'_lrot',['x','y','z','w']),[0,0,0,1])===0);
  for(let ni=0;ni<m.source.doc.nodes.length;ni++){
   const sn=m.source.doc.nodes[ni],pn=prefabNodes.filter(n=>n._name===sn.name);ensure(pn.length===1,'source rest node name ambiguous');ensure(!sn.matrix,'rest matrix audit requires TRS');
   for(const [sourceKey,targetKey,axes,fallback] of [['translation','_lpos',['x','y','z'],[0,0,0]],['rotation','_lrot',['x','y','z','w'],[0,0,0,1]],['scale','_lscale',['x','y','z'],[1,1,1]]]){const expected=sn[sourceKey]||fallback,actual=components(pn[0],targetKey,axes);maxRestTRSError=Math.max(maxRestTRSError,sourceKey==='rotation'?quaternionDifference(actual,expected):Math.max(...actual.map((v,i)=>Math.abs(v-expected[i]))));}
   const childNames=pn[0]._children.map(r=>m.prefab[r.__id__]._name).sort();const expectedChildren=(sn.children||[]).map(i=>m.source.doc.nodes[i].name).sort();ensure(JSON.stringify(childNames)===JSON.stringify(expectedChildren),'imported rest hierarchy differs '+sn.name);comparedRestNodes++;
  }
  check(name+':all_rest_TRS_and_hierarchy_match',maxRestTRSError<=2e-6,{comparedRestNodes,maxRestTRSError});
  const original=m.source.doc.animations;ensure(original.length===1&&original[0].name===clip._name,'source animation mismatch');let keys=0,maxValueError=0,maxTimeError=0;
  for(const c of original[0].channels){const sampler=original[0].samplers[c.sampler],sourceName=m.source.doc.nodes[c.target.node].name,node=byName.get(sourceName);ensure(node,'missing imported track '+sourceName);const prop={translation:'position',rotation:'rotation',scale:'scale'}[c.target.path],track=deref(node['_'+prop]),values=deref(track.values);ensure(values._isQuantized===false,'quantized import unsupported');const times=floatArray(track.times,chunk),imported=floatArray(values._values,chunk),expected=m.source.acc(sampler.output),sourceTimes=m.source.acc(sampler.input);ensure(times.length===sourceTimes.length&&imported.length===expected.length,'track dimensions differ');const width=prop==='rotation'?4:3;
   for(let i=0;i<times.length;i++){maxTimeError=Math.max(maxTimeError,Math.abs(times[i]-sourceTimes[i]));const a=imported.slice(i*width,(i+1)*width),b=expected.slice(i*width,(i+1)*width);maxValueError=Math.max(maxValueError,prop==='rotation'?quaternionDifference(a,b):Math.max(...a.map((v,k)=>Math.abs(v-b[k]))));keys++;}
  }
  check(name+':all_exported_pose_keys_match',maxTimeError===0&&maxValueError<=2e-6,{keys,maxValueError,maxTimeError});
  const built=await read(path.join(imports,clips[0].uuid.slice(0,2),clips[0].uuid+'.bin'));check(name+':build_clip_equals_library',built.equals(bytes));
  report.characters.push({name,bones:joints.length,channels:original[0].channels.length,keys,maxValueError,maxTimeError,clipSha256:hash(bytes),glbSha256:hash(m.raw)});
 }
 const scene=await model('scene'),lighting=await json(path.join(assets,'lighting.json'));check('lightmap_bindings_66',lighting.bindings.length===66&&new Set(lighting.bindings.map(b=>b.nodeName+':'+b.primitive)).size===66);const sceneData=await json(path.join(assets,'scene-data.json'));check('scene_matches_staged_digest',hash(scene.raw)===sceneData.staged_sha256);
 const meshCache=new Map();let uvTargets=0;
 for(const binding of lighting.bindings){const nodes=scene.prefab.filter(n=>n.__type__==='cc.Node'&&n._name===binding.nodeName);ensure(nodes.length===1,'lightmap target not unique '+binding.nodeName);const node=nodes[0],renderers=(node._components||[]).map(r=>scene.prefab[r.__id__]).filter(c=>c.__type__==='cc.MeshRenderer');ensure(renderers.length===1,'lightmap renderer missing');const uuid=renderers[0]._mesh.__uuid__;if(!meshCache.has(uuid))meshCache.set(uuid,await json(library(uuid,'.json')));const mesh=meshCache.get(uuid),primitive=mesh._struct.primitives[binding.primitive];ensure(primitive,'missing primitive');const bundles=primitive.vertexBundelIndices.map(i=>mesh._struct.vertexBundles[i]);ensure(bundles.some(b=>b.attributes.some(a=>a.name==='a_texCoord1')),'imported lightmap UV1 missing '+binding.nodeName);uvTargets++;}
 check('all_66_unique_targets_have_imported_UV1',uvTargets===66,{uvTargets,uniqueMeshes:meshCache.size});
 const flameFile=path.join(assets,'flame/geometry/flame.glb');
 const flameNames=await fs.readdir(path.dirname(flameFile));const glbs=flameNames.filter(n=>n.endsWith('.glb'));ensure(glbs.length===1,'flame geometry GLB not unique');const fm=await json(path.join(path.dirname(flameFile),glbs[0]+'.meta')),fp=Object.values(fm.subMetas).filter(x=>x.importer==='gltf-scene');check('flame_prefab_unique',fp.length===1&&Object.entries(config.paths).filter(([,v])=>v[1]==='cc.Prefab'&&v[0].startsWith('recovered/hall/flame/geometry/')).length===1&&config.paths[fp[0].uuid]?.[1]==='cc.Prefab');
 const flameTree=prefabTree(await json(library(fp[0].uuid,'.json')));report.flame={root:flameTree.root._name,prefabUuid:fp[0].uuid};
 for(const resource of ['manifest','attachment'])check('flame_'+resource+'_build',Object.values(config.paths).some(v=>v[0]==='recovered/hall/flame/'+resource&&v[1]==='cc.JsonAsset'));
 for(let i=0;i<4;i++)check('flame_texture_'+i+'_build',Object.values(config.paths).some(v=>v[0]==='recovered/hall/flame/texture-'+i+'/texture'&&v[1]==='cc.Texture2D'));
 check('flame_effect_build',Object.values(config.paths).some(v=>v[0]==='recovered/hall/flame/flame'&&v[1]==='cc.EffectAsset'));
 for(const [p,digest] of inputs)ensure(hash(await fs.readFile(p))===digest,'input changed during audit '+p);
 report.passed=true;
}catch(e){report.error=e.message;}
report.inputs=[...inputs].map(([p,sha256])=>({path:path.relative(root,p).replaceAll('\\','/'),sha256}));
await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({passed:report.passed,error:report.error,checks:report.checks.length,characters:report.characters,output},null,2));if(!report.passed)process.exitCode=1;
