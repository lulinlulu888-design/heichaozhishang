import {copyFile,readFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
// Uses the pinned vendor directory staged by prepare_prologue_preview.mjs.
const dest=path.join(root,'legacy/cocos-poc/build/web-desktop/prologue');
await mkdir(dest,{recursive:true});
for(const [folder,file,reportName,target] of [
 ['weapon','elsa-weapon-static.glb','static-export-report.json','elsa-weapon-static.glb'],
 ['actor-attacks','prologue-elsa.glb','report.json','weapon-actor.glb'],
]){
 const base=path.join(root,'analysis/battle-visual',folder);
 const report=JSON.parse(await readFile(path.join(base,reportName),'utf8'));
 const bytes=await readFile(path.join(base,file));
 if(createHash('sha256').update(bytes).digest('hex')!==report.glb_sha256)throw Error('Source GLB changed: '+file);
 await copyFile(path.join(base,file),path.join(dest,target));
}
await copyFile(path.join(root,'analysis/battle-visual/weapon/binding-report.json'),path.join(dest,'weapon-binding.json'));
await copyFile(path.join(root,'tools/templates/weapon-preview.html'),path.join(dest,'weapon.html'));
const effectDir=path.join(root,'analysis/battle-visual/weapon/effect');
const effect=JSON.parse(await readFile(path.join(effectDir,'report.json'),'utf8'));
const overlay=await readFile(path.join(effectDir,'weapon-overlay.glb'));
if(createHash('sha256').update(overlay).digest('hex')!==effect.glb_sha256)throw Error('Overlay changed');
await copyFile(path.join(effectDir,'weapon-overlay.glb'),path.join(dest,'weapon-overlay.glb'));
for(const texture of effect.textures){
 const output=texture.outputs[0];
 const source=path.resolve(root,output.png);
 const bytes=await readFile(source);
 if(createHash('sha256').update(bytes).digest('hex')!==output.png_sha256)throw Error('Noise PNG changed');
 const name=texture.provenance.logical_path.includes('gq_rlt')?'weapon-distortion.png':'weapon-noise.png';
 await copyFile(source,path.join(dest,name));
}
console.log('Weapon inspection: http://127.0.0.1:7456/prologue/weapon.html');
