import {readFile,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url), dest=new URL('legacy/cocos-poc/build/web-desktop/prologue/',root);
const source=new URL('analysis/characters/lynn/export/lynn-idle.colour-reference.glb',root);
const report=JSON.parse(await readFile(new URL('analysis/characters/lynn/export/export-report.json',root),'utf8'));
if(createHash('sha256').update(await readFile(source)).digest('hex')!==report.sha256)throw Error('Lynn export changed');
await copyFile(source,new URL('lynn-idle.glb',dest));
await copyFile(new URL('tools/templates/lynn-preview.html',root),new URL('lynn.html',dest));
console.log('http://127.0.0.1:7456/prologue/lynn.html');
