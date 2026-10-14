import * as THREE from 'three';
import {GLTFLoader} from './vendor/loaders/GLTFLoader.js';

// Rigid attachment derived from source single-joint weights. Native BindType
// and the source bind/AABB discrepancy remain unresolved; see binding report.
export async function attachElsaWeapon(actor){
 const loader=new GLTFLoader();
 const [attachment,response]=await Promise.all([loader.loadAsync('./elsa-weapon-static.glb'),fetch('./weapon-binding.json')]);
 if(!response.ok)throw Error('Weapon binding unavailable');
 const report=await response.json(),row=report.used_bones?.[0];
 if(report.used_bones?.length!==1||!report.all_vertices_single_joint_unit_weight||
    !Array.isArray(row.source_bind)||row.source_bind.length!==16||!row.source_bind.every(Number.isFinite))throw Error('Invalid rigid binding');
 const indices=actor.parser.json.nodes.flatMap((node,index)=>node.name===row.name?[index]:[]);
 if(indices.length!==1)throw Error('Attachment bone missing or ambiguous');
 const bone=await actor.parser.getDependency('node',indices[0]);
 const weapon=new THREE.Group();weapon.name='RecoveredWeaponInverseBind';weapon.matrixAutoUpdate=false;
 weapon.matrix.fromArray(row.source_bind);
 if(Math.abs(weapon.matrix.determinant())<1e-10)throw Error('Singular weapon bind');
 weapon.matrix.invert();weapon.add(attachment.scene);bone.add(weapon);
 const [overlay,noise,distortion]=await Promise.all([loader.loadAsync('./weapon-overlay.glb'),new THREE.TextureLoader().loadAsync('./weapon-noise.png'),new THREE.TextureLoader().loadAsync('./weapon-distortion.png')]);
 for(const texture of [noise,distortion]){texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.flipY=false;}
 // Existing recovered noise flow branch; gamma/blend are reference choices,
 // not a claim of original HDR/bloom or native blend-state equivalence.
 const material=new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,
  uniforms:{noise:{value:noise},distortion:{value:distortion},time:{value:0}},
  vertexShader:`varying vec2 uv0;void main(){uv0=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
  fragmentShader:`uniform sampler2D noise;uniform sampler2D distortion;uniform float time;varying vec2 uv0;
   void main(){float offset=texture2D(distortion,uv0+time*vec2(.1,-.1)).r*.1;
   vec4 n=texture2D(noise,uv0+vec2(offset)+time*vec2(.1,.2));
   gl_FragColor=vec4(pow(n.rgb,vec3(2.2))*3.0*pow(vec3(1.,.207843,.470588),vec3(2.2)),n.a);
   #include <colorspace_fragment>
   }`});
 overlay.scene.traverse(node=>{if(node.isMesh)node.material=material;});weapon.add(overlay.scene);
 return time=>{material.uniforms.time.value=time;};
}
