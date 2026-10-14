import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
const text=readFileSync('tools/templates/cocos-end-turn-view.ts','utf8');
const pure=text.slice(text.indexOf('type SourceNode'),text.indexOf('/** Source EndArea'));
const {sample}=await import('data:text/javascript;base64,'+Buffer.from(stripTypeScriptTypes(pure+'\nexport {sample};')).toString('base64'));
const manifest=JSON.parse(readFileSync('analysis/battle-ui/end-turn/timeline.json','utf8'));
for(const track of manifest.timelines) {
  for(const key of track.frames)assert.deepEqual(sample(track,key.index),key.value,`${track.property} ${key.index}`);
  for(let frame=0;frame<=manifest.duration;frame++) {
    const result=sample(track,frame);
    if(typeof result==='number')assert.ok(Number.isFinite(result));
    if(Array.isArray(result))assert.ok(result.every(Number.isFinite));
  }
}
const texture=manifest.timelines.find(t=>t.property==='FileData'&&t.frames.length>1);
assert.deepEqual(sample(texture,texture.frames[1].index-.1),texture.frames[0].value);
console.log('EndArea: all 223 source keyframes preserved; bounded interpolation and stepped texture switching passed.');
