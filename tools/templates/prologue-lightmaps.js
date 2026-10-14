import * as THREE from 'three';

// Diffuse-lighting reference; original BRDF and HDR compositing remain unresolved.
export async function prepareLighting(root){
 const data=await (await fetch('./lightmaps.json')).json();
 const textures=await Promise.all(data.images.map(p=>new THREE.TextureLoader().loadAsync(p)));
 for(const tex of textures){tex.colorSpace=THREE.NoColorSpace;tex.flipY=false;}
 const bindings=new Map(data.bindings.map(b=>[b.uuid,b]));
 const entries=[];
 root.traverse(mesh=>{
  if(!mesh.isMesh)return;
  let owner=mesh;while(owner&&!owner.userData.sourceInstance)owner=owner.parent;
  const row=bindings.get(owner?.userData.sourceInstance?.UUID);
  if(!row)return;
  if(row.submesh!==0||!mesh.geometry.getAttribute('uv1'))throw new Error('Unsupported lightmap geometry');
  const p=row.parameters;
  if(p.UE4_lm!=='true'||p.encode_type!=='4')throw new Error('Unsupported lightmap encoding');
  const vec=k=>p[k].split(',').map(Number);
  const old=mesh.material,material=old.clone();
  material.defines={...material.defines,USE_UV1:''};
  material.onBeforeCompile=shader=>{
   Object.assign(shader.uniforms,{
    originalLightmap:{value:textures[Number(p.texture_index)]},
    lmScale:{value:new THREE.Vector3(...vec('lightmap_scale'))},
    lmAdd:{value:new THREE.Vector3(...vec('lightmap_add').slice(0,3))},
    lmUVScale:{value:new THREE.Vector2(...vec('uv_scale'))},
    lmUVOffset:{value:new THREE.Vector2(...vec('uv_ofs'))}
   });
   shader.vertexShader='varying vec2 originalLMUV; uniform vec2 lmUVScale; uniform vec2 lmUVOffset;\n'+shader.vertexShader;
   shader.vertexShader=shader.vertexShader.replace('#include <uv_vertex>','#include <uv_vertex>\noriginalLMUV=uv1*lmUVScale+lmUVOffset;');
   shader.fragmentShader='varying vec2 originalLMUV; uniform sampler2D originalLightmap; uniform vec3 lmScale; uniform vec3 lmAdd;\n'+shader.fragmentShader;
   shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>',`
    vec3 encodedLight=texture2D(originalLightmap,originalLMUV).rgb*lmScale+lmAdd;
    float logL=dot(vec3(0.299,0.587,0.114),encodedLight);
    float luma=(exp2(logL*16.0-8.0)-0.00390625)*0.6;
    outgoingLight*=encodedLight*(luma/max(logL,0.00001));
    #include <opaque_fragment>`);
  };
  material.customProgramCacheKey=()=> 'hczs-ue4-lightmap-reference-v1';
  entries.push({mesh,old,material});
 });
 if(entries.length!==data.bindings.length)throw new Error(`Lightmap binding mismatch ${entries.length}/${data.bindings.length}`);
 return {count:entries.length,set(enabled){for(const e of entries)e.mesh.material=enabled?e.material:e.old;}};
}
