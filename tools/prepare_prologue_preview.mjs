import { mkdir, copyFile, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dest=path.join(root,'clients/cocos-poc/build/web-desktop/prologue');
const vendor=path.join(root,'tools/runtime/scene-preview/node_modules/three');
const pkg=JSON.parse(await readFile(path.join(vendor,'package.json'),'utf8'));
if(pkg.version!=='0.180.0')throw new Error('Expected pinned three 0.180.0');
for(const [source,target] of [
 ['tools/templates/prologue-preview.html','index.html'],
 ['tools/templates/prologue-lightmaps.js','prologue-lightmaps.js'],
 ['analysis/battle-visual/scene-export/prologue-scene.glb','prologue-scene.glb'],
 ['analysis/battle-visual/actor/prologue-elsa.glb','prologue-elsa.glb'],
 ...['three.module.js','three.core.js'].map(f=>[`tools/runtime/scene-preview/node_modules/three/build/${f}`,`vendor/${f}`]),
 ...['loaders/GLTFLoader.js','controls/OrbitControls.js','utils/BufferGeometryUtils.js'].map(f=>[`tools/runtime/scene-preview/node_modules/three/examples/jsm/${f}`,`vendor/${f}`]),
 ['tools/runtime/scene-preview/node_modules/three/LICENSE','vendor/LICENSE'],
]){await mkdir(path.dirname(path.join(dest,target)),{recursive:true});await copyFile(path.join(root,source),path.join(dest,target));}
console.log('Scene preview: http://127.0.0.1:7456/prologue/');
const lighting=JSON.parse(await readFile(path.join(root,'analysis/battle-visual/lightmaps/bindings.json'),'utf8'));
const images=[];
for(let i=0;i<lighting.decoded_images.length;i++){
 const name=`lightmap-${i}.png`;
 await copyFile(path.resolve(root,lighting.decoded_images[i].outputs[0].png),path.join(dest,name));images.push(name);
}
await writeFile(path.join(dest,'lightmaps.json'),JSON.stringify({images,bindings:lighting.bindings}));
