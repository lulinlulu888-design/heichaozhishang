import * as THREE from 'three';
// Restricted source branch: plane_yun's ALPHA_MASK only, no dissolve/fresnel/TWO_FLOAT.
export async function prepareCityMaterials(gltf){
 const updates=[];
 for(const [index,row] of gltf.parser.json.materials.entries()){
  const data=row.extras;if(data?.sourceModel!=='effects/modeleffect/scene/plane_yun.gim')continue;
  const p=data.sourceParams;
  const vector=key=>new THREE.Vector2(...p[key].split(',').map(Number));
  const [diffuse,noise,mask]=await Promise.all([row.pbrMetallicRoughness.baseColorTexture.index,data.extraTextures.TexDistortion,data.extraTextures.TexMask].map(i=>gltf.parser.getDependency('texture',i)));
  for(const t of [diffuse,noise,mask]){t.wrapS=t.wrapT=THREE.RepeatWrapping;t.needsUpdate=true;}
  // Colour texture is already decoded to linear by Three; mask/distortion use raw samples.
  noise.colorSpace=mask.colorSpace=THREE.NoColorSpace;
  const tint=new THREE.Color().setRGB(...p.g_colFloatingColor1.split(',').slice(0,3).map(Number),THREE.SRGBColorSpace);
  const uniforms={time:{value:0},diffuse:{value:diffuse},noise:{value:noise},mask:{value:mask},tint:{value:tint},
   tiling:{value:vector('g_vFloatingTiling1')},speed:{value:vector('g_vFloatingSpeed1')},distortionTiling:{value:vector('g_vDistortionTiling')},distortionSpeed:{value:vector('g_vDistortionSpeed')},
   distortionStrength:{value:Number(p.g_fDistortionStrength)},maskStrength:{value:Number(p.g_AlphaMaskStrength)}};
  const material=new THREE.ShaderMaterial({uniforms,transparent:true,depthWrite:false,side:THREE.DoubleSide,
   vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
   fragmentShader:`uniform float time,distortionStrength,maskStrength;uniform sampler2D diffuse,noise,mask;uniform vec3 tint;uniform vec2 tiling,speed,distortionTiling,distortionSpeed;varying vec2 vUv;
    void main(){float n=texture2D(noise,vUv*distortionTiling+time*distortionSpeed).r;
    vec4 c=texture2D(diffuse,vUv*tiling+vec2(n*distortionStrength)+time*speed);
    gl_FragColor=vec4(c.rgb*tint,clamp(c.a*texture2D(mask,vUv).r*maskStrength,0.0,1.0));
    #include <colorspace_fragment>
    }`});
  const original=await gltf.parser.getDependency('material',index);
  const matches=m=>m===original||m.userData?.sourceModel===data.sourceModel;
  gltf.scene.traverse(node=>{if(node.isMesh){if(Array.isArray(node.material))node.material=node.material.map(m=>matches(m)?material:m);else if(matches(node.material))node.material=material;}});
  updates.push(time=>uniforms.time.value=time);
 }
 return time=>updates.forEach(update=>update(time));
}
