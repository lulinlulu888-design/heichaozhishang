// Load selected project modules from an actual Creator build, without running the engine.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

export async function readCocosTestBuild() {
    const registrations=new Map(),buildInputs=[];
    for(const name of ['src/chunks/bundle.js','assets/main/index.js']) {
        const code=await readFile(new URL('../legacy/cocos-poc/build/web-desktop/'+name,import.meta.url),'utf8');
        buildInputs.push({name,sha256:createHash('sha256').update(code).digest('hex')});
        new Function('System',code)({register(id,deps,factory){
            if(Array.isArray(id)) {
                assert.equal(id.length,0,'Anonymous envelope must have no dependencies');
                deps(()=>{},{}).execute();return;
            }
            assert.equal(registrations.has(id),false,'duplicate compiled module '+id);
            registrations.set(id,{deps,factory});
        }});
    }
    return {buildInputs,load(name,cc) {
        assert.ok(['BattleAudio.ts','TutorialBattleController.ts','VictoryTitleView.ts'].includes(name),'Unapproved test entry');
        const entry='chunks:///_virtual/'+name;
        const loaded=new Map([['cc',cc]]);
        function load(id) {
            if(loaded.has(id))return loaded.get(id);
            assert.ok(id===entry||id==='chunks:///_virtual/rollupPluginModLoBabelHelpers.js',
                'Unexpected compiled dependency '+id);
            const definition=registrations.get(id);assert.ok(definition,'Missing compiled module '+id);
            const values={};loaded.set(id,values);
            const module=definition.factory((key,value)=>{
                if(typeof key==='string')values[key]=value;else Object.assign(values,key);
                return value;
            });
            definition.deps.forEach((dep,i)=>module.setters[i](load(dep.startsWith('.')?new URL(dep,id).href:dep)));
            module.execute();return values;
        }
        return load(entry);
    }};
}
