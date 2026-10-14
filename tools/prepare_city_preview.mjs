import {mkdir,copyFile,readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dest=path.join(root,'clients/cocos-poc/build/web-desktop/city');
const vendor='tools/runtime/scene-preview/node_modules/three';
if(JSON.parse(await readFile(path.join(root,vendor,'package.json'),'utf8')).version!=='0.180.0')throw Error('Three version mismatch');
const files=[['tools/templates/city-preview.html','index.html'],['tools/templates/city-materials.js','city-materials.js']];
files.push(['tools/templates/city-weapon.js','city-weapon.js']);
async function verifiedFile(source,target,hash){
 if(createHash('sha256').update(await readFile(path.join(root,source))).digest('hex')!==hash)throw Error('Source changed: '+source);
 files.push([source,target]);
}
const weaponBase='analysis/battle-visual/weapon';
const weaponReport=JSON.parse(await readFile(path.join(root,weaponBase,'static-export-report.json'),'utf8'));
await verifiedFile(`${weaponBase}/elsa-weapon-static.glb`,'elsa-weapon-static.glb',weaponReport.glb_sha256);
files.push([`${weaponBase}/binding-report.json`,'weapon-binding.json']);
const effect=JSON.parse(await readFile(path.join(root,weaponBase,'effect/report.json'),'utf8'));
await verifiedFile(`${weaponBase}/effect/weapon-overlay.glb`,'weapon-overlay.glb',effect.glb_sha256);
for(const texture of effect.textures){
 const output=texture.outputs[0];
 const name=texture.provenance.logical_path.includes('gq_rlt')?'weapon-distortion.png':'weapon-noise.png';
 await verifiedFile(path.relative(root,path.resolve(root,output.png)),name,output.png_sha256);
}
const actor='analysis/battle-visual/actor-battle-idle/prologue-elsa.glb';
if(createHash('sha256').update(await readFile(path.join(root,actor))).digest('hex')!=='acc7bbaa00b66a60165ce56341021055b55f1f73ca4c6af154e63036ee789463')throw Error('Actor GLB changed');
files.push([actor,'elsa.glb']);
for(const name of ['city_battle_1','city_battle_2']){
 const source=`analysis/battle-visual/city-scenes/${name}/scene.glb`;
 const report=JSON.parse(await readFile(path.join(root,`analysis/battle-visual/city-scenes/${name}/export.json`),'utf8'));
 if(createHash('sha256').update(await readFile(path.join(root,source))).digest('hex')!==report.sha256)throw Error('City GLB changed');
 files.push([source,`${name}.glb`]);
}
files.push(...['three.module.js','three.core.js'].map(f=>[`${vendor}/build/${f}`,`vendor/${f}`]),
 ...['loaders/GLTFLoader.js','controls/OrbitControls.js','utils/BufferGeometryUtils.js'].map(f=>[`${vendor}/examples/jsm/${f}`,`vendor/${f}`]),[`${vendor}/LICENSE`,'vendor/LICENSE']);
for(const [source,target] of files){await mkdir(path.dirname(path.join(dest,target)),{recursive:true});await copyFile(path.join(root,source),path.join(dest,target));}
console.log('City environment preview: http://127.0.0.1:7456/city/');
