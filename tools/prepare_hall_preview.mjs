import {readFile,copyFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url),dest=new URL('legacy/cocos-poc/build/web-desktop/hall/',root);
const source=new URL('analysis/hall/midgard_home_3d/scene.glb',root);
const report=JSON.parse(await readFile(new URL('analysis/hall/midgard_home_3d/export.json',root),'utf8'));
if(createHash('sha256').update(await readFile(source)).digest('hex')!==report.sha256)throw Error('Hall export changed');
if(JSON.parse(await readFile(new URL('tools/runtime/scene-preview/node_modules/three/package.json',root),'utf8')).version!=='0.180.0')throw Error('Three version changed');
await mkdir(dest,{recursive:true});await copyFile(source,new URL('hall.glb',dest));await copyFile(new URL('tools/templates/hall-preview.html',root),new URL('index.html',dest));
await copyFile(new URL('tools/templates/hall-preview.js',root),new URL('hall-preview.js',dest));
const characterSource=new URL('analysis/characters/shiranui/export/shiranui-idle.colour-reference.glb',root);
const characterReport=JSON.parse(await readFile(new URL('analysis/characters/shiranui/export/export-report.json',root),'utf8'));
if(createHash('sha256').update(await readFile(characterSource)).digest('hex')!==characterReport.sha256)throw Error('Shiranui export changed');
await copyFile(characterSource,new URL('shiranui.glb',dest));
const weaponSource=new URL('analysis/characters/shiranui/export-weapon/shiranuiweapon-idle.colour-reference.glb',root);
const weaponReport=JSON.parse(await readFile(new URL('analysis/characters/shiranui/export-weapon/export-report.json',root),'utf8'));
if(createHash('sha256').update(await readFile(weaponSource)).digest('hex')!==weaponReport.sha256)throw Error('Shiranui weapon export changed');
await copyFile(weaponSource,new URL('shiranui-weapon.glb',dest));
for(const [a,b] of [['build/three.module.js','three.module.js'],['build/three.core.js','three.core.js'],['examples/jsm/loaders/GLTFLoader.js','loaders/GLTFLoader.js'],['examples/jsm/utils/BufferGeometryUtils.js','utils/BufferGeometryUtils.js'],['examples/jsm/controls/OrbitControls.js','controls/OrbitControls.js']]){const target=new URL('vendor/'+b,dest);await mkdir(new URL('./',target),{recursive:true});await copyFile(new URL('tools/runtime/scene-preview/node_modules/three/'+a,root),target);}
const uiReportBytes=await readFile(new URL('analysis/hall/ui-dependencies/report.json',root));
const uiSprites=JSON.parse(await readFile(new URL('analysis/hall/ui-sprites/report.json',root),'utf8'));
if(createHash('sha256').update(uiReportBytes).digest('hex')!==uiSprites.dependency_report_sha256)throw Error('Hall UI dependency report changed');
await mkdir(new URL('ui/',dest),{recursive:true});
await copyFile(new URL('analysis/hall/ui-dependencies/report.json',root),new URL('ui/layout.json',dest));
const uiManifest=[];
for(const row of uiSprites.frames){
  const bytes=await readFile(new URL(row.png.replaceAll('\\','/'),root));
  if(createHash('sha256').update(bytes).digest('hex')!==row.sha256)throw Error('Hall UI sprite changed');
  const file=row.sha256+'.png';
  await copyFile(new URL(row.png.replaceAll('\\','/'),root),new URL('ui/'+file,dest));
  uiManifest.push({...row,file});
}
const {writeFile}=await import('node:fs/promises');
await writeFile(new URL('ui/sprites.json',dest),JSON.stringify(uiManifest));
const fonts=[];
for(const font of uiSprites.fonts){
  const source=new URL(font.path.replaceAll('\\','/'),root);
  if(createHash('sha256').update(await readFile(source)).digest('hex')!==font.sha256)throw Error('Hall font changed');
  const file=font.sha256+'.ttf';await copyFile(source,new URL('ui/'+file,dest));
  fonts.push({path:font.logical_path,file,family:'HallFont'+fonts.length});
}
await writeFile(new URL('ui/fonts.json',dest),JSON.stringify(fonts));
await copyFile(new URL('tools/templates/hall-ui-preview.js',root),new URL('hall-ui-preview.js',dest));
await copyFile(new URL('tools/templates/hall-local-state.js',root),new URL('hall-local-state.js',dest));
const lightingBase=new URL('analysis/hall/lighting/',root);
const lighting=JSON.parse(await readFile(new URL('lighting.json',lightingBase),'utf8'));
if(lighting.scene_glb_sha256!==report.sha256)throw Error('Hall lighting targets another scene');
await mkdir(new URL('lighting/',dest),{recursive:true});
for(const texture of lighting.textures){
  if(!/^lightmap_\d+\.png$/.test(texture.file))throw Error('Invalid lightmap filename');
  const bytes=await readFile(new URL(texture.file,lightingBase));
  if(createHash('sha256').update(bytes).digest('hex')!==texture.sha256)throw Error('Hall lightmap changed');
  await writeFile(new URL('lighting/'+texture.file,dest),bytes);
}
await copyFile(new URL('lighting.json',lightingBase),new URL('lighting/lighting.json',dest));
await copyFile(new URL('tools/templates/hall-lighting.js',root),new URL('hall-lighting.js',dest));
// The main hall loads the shared flame module; stage its pinned inputs too.
await import('./prepare_flame_preview.mjs');
console.log('http://127.0.0.1:7456/hall/');
