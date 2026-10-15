// Bounded original-resource reference player. See docs/shiranui-flame-attachment.md.
import * as T from 'three';
import {GLTFLoader} from './vendor/loaders/GLTFLoader.js';
 const vertex=`varying vec2 sourceUV;void main(){sourceUV=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
 const fragment=`varying vec2 sourceUV;uniform sampler2D baseTex,distortTex,maskTex,dissolveTex;uniform float time,distortion,strength,alphaMtl,maskIntensity,dissolveStrength,hardness;uniform vec2 distortTiling,distortSpeed,floatTiling,floatSpeed,dissolveTiling,dissolveSpeed;uniform vec3 tint;
 vec3 linearize(vec3 c){return mix(c/12.92,pow((c+0.055)/1.055,vec3(2.4)),step(vec3(0.04045),c));}
 void main(){float d=texture2D(distortTex,sourceUV*distortTiling+time*distortSpeed).r;vec2 uv=sourceUV*floatTiling+vec2(d*distortion)+time*floatSpeed;vec4 base=texture2D(baseTex,uv);float mask=pow(texture2D(maskTex,sourceUV).r+0.01,maskIntensity);float dissolve=pow(clamp((texture2D(dissolveTex,sourceUV*dissolveTiling+time*dissolveSpeed).r-dissolveStrength+0.1)*5.0,0.0,1.0),hardness);gl_FragColor=vec4(linearize(base.rgb)*tint*strength,base.a*mask*dissolve*alphaMtl);
 #include <colorspace_fragment>
 }`;

export async function attachShiranuiFlames({weaponRoot,baseUrl='./flame/'}) {
 const base=new URL(baseUrl,location.href);
 async function json(name){const r=await fetch(new URL(name,base));if(!r.ok)throw Error('Flame input unavailable: '+name);return r.json();}
 const [data,attachment]=await Promise.all([json('manifest.json'),json('attachment.json')]);
 const boneMap=new Map();weaponRoot.traverse(n=>{if(n.isBone){if(boneMap.has(n.name))throw Error('Duplicate flame bone '+n.name);boneMap.set(n.name,n);}});
 for(const s of attachment.sockets)if(!boneMap.has(s.bone))throw Error('Missing flame bone '+s.bone);
 const loader=new T.TextureLoader();const maps=await Promise.all([0,1,2,3].map(async i=>{const t=await loader.loadAsync(new URL('texture-'+i+'.png',base).href);t.flipY=false;t.wrapS=t.wrapT=T.RepeatWrapping;t.minFilter=t.magFilter=T.LinearFilter;t.generateMipmaps=false;return t;}));
 const asset=await new GLTFLoader().loadAsync(new URL('flame-01.glb',base).href);
 const defaults=Object.fromEntries(Object.entries(data.defaults).map(([key,row])=>[key,row.value]));
 for(const [key,value] of Object.entries(data.material.params)){if(key in defaults){const v=value.split(',').map(Number);defaults[key]=v.length===1?v[0]:v;}}
 const materials=[],roots=[];let time=0,enabled=true,disposed=false,meshCount=0;
 function makeMaterial(node){
 const p={...defaults,...node.uniforms};const mode=Number(node.attributes.TransparentMode);
 if(![0,2].includes(mode)||p.alphaMtl===null)throw Error('Unsupported flame blend/alpha');
 for(const key of ['mirror_u','mirror_v','rotation_floatTex01','offset_u','offset_v','alpha_mirror_u','alpha_mirror_v','alpha_rotation'])if(p[key]!==0)throw Error('未支持非零UV旋转/镜像');
 const c=p.g_colFloatingColor1;const tint=new T.Color(c[1]/255,c[2]/255,c[3]/255).convertSRGBToLinear();
 const uniforms={time:{value:0},baseTex:{value:maps[0]},distortTex:{value:maps[1]},maskTex:{value:maps[2]},dissolveTex:{value:maps[3]},tint:{value:tint}};
 for(const [name,key] of Object.entries({distortion:'g_fDistortionStrength1',strength:'g_fFloatingStrength1',alphaMtl:'alphaMtl',maskIntensity:'alpha_mask_intensity',dissolveStrength:'g_DissolveStrength',hardness:'g_dissolve_hardness'}))uniforms[name]={value:p[key]};
 for(const [name,value] of Object.entries({distortTiling:p.g_vDistortionTiling,distortSpeed:p.g_vDistortionSpeed,floatTiling:[p.g_vFloatingTilingU1,p.g_vFloatingTilingV1],floatSpeed:p.g_vFloatingSpeed1,dissolveTiling:p.g_vDissolveTiling,dissolveSpeed:[p.g_vDissolveSpeedU,p.g_vDissolveSpeedV]}))uniforms[name]={value:new T.Vector2(...value)};
 const material=new T.ShaderMaterial({vertexShader:vertex,fragmentShader:fragment,uniforms,transparent:true,depthWrite:false,side:T.DoubleSide,blending:mode===0?T.AdditiveBlending:T.NormalBlending});

 materials.push(material);return material;
 }
 function instantiate(node){
 const group=new T.Group();group.name=node.attributes.Name;group.userData.sourceFX=node.attributes;
 group.position.fromArray(node.position);group.scale.fromArray(node.scale);
 if(node.forward){const [x,y,z,angle]=node.forward;const axis=new T.Vector3(x,y,z);if(axis.lengthSq()<1e-12)throw Error('Zero effect axis');group.quaternion.setFromAxisAngle(axis.normalize(),T.MathUtils.degToRad(angle));}
 if(node.tag==='Model'){
  const model=asset.scene.clone(true),material=makeMaterial(node);model.scale.multiplyScalar(node.model_scale??1);
  model.traverse(n=>{if(n.isMesh){n.material=material;n.renderOrder=Number(node.attributes.RenderOrder||0)+Number(node.attributes.RenderBias||0);meshCount++;}});group.add(model);
 }
 for(const c of node.children)group.add(instantiate(c));return group;
 }
 try {
  for(const socket of attachment.sockets){
   const root=new T.Group();root.name=socket.name;root.matrixAutoUpdate=false;root.matrix.fromArray(socket.matrix);
   root.userData.sourceSocket=socket.source_attributes;root.add(instantiate(attachment.effects[socket.effect]));roots.push({root,bone:boneMap.get(socket.bone)});
  }
  // Attach only after the entire hierarchy validates, so failure cannot leave half an effect.
  for(const {root,bone} of roots)bone.add(root);
 }catch(error){for(const m of materials)m.dispose();for(const t of maps)t.dispose();throw error;}
 const report={sockets:roots.length,meshes:meshCount,assumptions:attachment.assumptions,source:attachment.source};
 return {report,update(dt){if(disposed||!enabled)return;if(!Number.isFinite(dt)||dt<0)throw Error('Invalid flame delta');time+=dt;for(const m of materials)m.uniforms.time.value=time;},setEnabled(value){enabled=Boolean(value);for(const {root} of roots)root.visible=enabled;},dispose(){if(disposed)return;disposed=true;for(const {root} of roots)root.removeFromParent();for(const m of materials)m.dispose();for(const t of maps)t.dispose();asset.scene.traverse(n=>{if(n.isMesh){n.geometry.dispose();for(const m of Array.isArray(n.material)?n.material:[n.material])m.dispose();}});}};
}
