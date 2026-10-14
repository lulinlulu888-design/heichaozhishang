import {readFile,copyFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url),dest=new URL('clients/cocos-poc/build/web-desktop/hall/',root);
const source=new URL('analysis/hall/midgard_home_3d/scene.glb',root);
const report=JSON.parse(await readFile(new URL('analysis/hall/midgard_home_3d/export.json',root),'utf8'));
if(createHash('sha256').update(await readFile(source)).digest('hex')!==report.sha256)throw Error('Hall export changed');
if(JSON.parse(await readFile(new URL('tools/runtime/scene-preview/node_modules/three/package.json',root),'utf8')).version!=='0.180.0')throw Error('Three version changed');
await mkdir(dest,{recursive:true});await copyFile(source,new URL('hall.glb',dest));await copyFile(new URL('tools/templates/hall-preview.html',root),new URL('index.html',dest));
const characterSource=new URL('analysis/characters/shiranui/export/shiranui-idle.colour-reference.glb',root);
const characterReport=JSON.parse(await readFile(new URL('analysis/characters/shiranui/export/export-report.json',root),'utf8'));
if(createHash('sha256').update(await readFile(characterSource)).digest('hex')!==characterReport.sha256)throw Error('Shiranui export changed');
await copyFile(characterSource,new URL('shiranui.glb',dest));
const weaponSource=new URL('analysis/characters/shiranui/export-weapon/shiranuiweapon-idle.colour-reference.glb',root);
const weaponReport=JSON.parse(await readFile(new URL('analysis/characters/shiranui/export-weapon/export-report.json',root),'utf8'));
if(createHash('sha256').update(await readFile(weaponSource)).digest('hex')!==weaponReport.sha256)throw Error('Shiranui weapon export changed');
await copyFile(weaponSource,new URL('shiranui-weapon.glb',dest));
for(const [a,b] of [['build/three.module.js','three.module.js'],['build/three.core.js','three.core.js'],['examples/jsm/loaders/GLTFLoader.js','loaders/GLTFLoader.js'],['examples/jsm/utils/BufferGeometryUtils.js','utils/BufferGeometryUtils.js'],['examples/jsm/controls/OrbitControls.js','controls/OrbitControls.js']]){const target=new URL('vendor/'+b,dest);await mkdir(new URL('./',target),{recursive:true});await copyFile(new URL('tools/runtime/scene-preview/node_modules/three/'+a,root),target);}
console.log('http://127.0.0.1:7456/hall/');
