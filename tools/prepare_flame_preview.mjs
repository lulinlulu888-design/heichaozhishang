import {readFile,writeFile,copyFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url),base=new URL('analysis/characters/shiranui/effects/render-inputs/',root),dest=new URL('legacy/cocos-poc/build/web-desktop/hall/',root);
const report=JSON.parse(await readFile(new URL('manifest.json',base),'utf8'));
const digest=b=>createHash('sha256').update(b).digest('hex');
await mkdir(new URL('flame/',dest),{recursive:true});
const mesh=await readFile(new URL('flame-01.glb',base));if(digest(mesh)!==report.geometry_sha256)throw Error('Flame geometry changed');
await writeFile(new URL('flame/flame-01.glb',dest),mesh);
for(const [i,texture] of report.textures.entries()){const image=texture.outputs[0];const bytes=await readFile(new URL(image.png.replaceAll('\\','/'),root));if(digest(bytes)!==image.png_sha256)throw Error('Flame pixels changed');await writeFile(new URL('flame/texture-'+i+'.png',dest),bytes);}
await copyFile(new URL('manifest.json',base),new URL('flame/manifest.json',dest));
await copyFile(new URL('tools/templates/shiranui-flame-preview.html',root),new URL('flame.html',dest));
console.log('http://127.0.0.1:7456/hall/flame.html');
await copyFile(new URL('attachment.json',base),new URL('flame/attachment.json',dest));
await copyFile(new URL('tools/templates/shiranui-flame-runtime.js',root),new URL('shiranui-flame-runtime.js',dest));
