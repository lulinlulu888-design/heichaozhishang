import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import { readCocosTestBuild } from './load_cocos_test_module.mjs';

// Exercise Creator's actual System.register output as well as TypeScript source.
// Only the audio module and its emitted Babel helper dependency are instantiated.
const compiled = process.argv.includes('--compiled');
const build = compiled ? await readCocosTestBuild() : null;
const buildInputs = build?.buildInputs ?? [];

const source = await readFile(new URL('./templates/cocos-battle-audio.ts',import.meta.url),'utf8');
assert.equal(source,await readFile(new URL('../legacy/cocos-poc/assets/BattleAudio.ts',import.meta.url),'utf8'));
const cue = {clip:'crit_1',ratio:.25,event:'original',resource:'audio/test',volume:.5};
class Clip { refs=0; addRef(){this.refs++;} decRef(){this.refs--;} }
class AudioSource {
    static EventType={ENDED:'ended',STARTED:'started'};
    playing=false;
    play(){this.playing=true;this.node.emit('started');}
    stop(){this.playing=false;}
}
class Node {
    children=[]; handlers=new Map(); destroyed=false;
    addChild(node){this.children.push(node);}
    addComponent(Type){this.audio=new Type();this.audio.node=this;return this.audio;}
    getComponent(){return this.audio;}
    once(event,callback){this.handlers.set(event,callback);}
    emit(event){const callback=this.handlers.get(event);this.handlers.delete(event);callback?.();}
    destroy(){this.destroyed=true;}
}
class Scheduler {
    jobs=new Map();
    getState(){return {duration:2};}
    scheduleOnce(f,delay){this.jobs.set(f,delay);}
    unschedule(f){this.jobs.delete(f);}
    run(){for(const f of [...this.jobs.keys()]){this.jobs.delete(f);f();}}
}
function harness({deferred=false,ratio=.25,cues,master=1}={}){
    const clip=new Clip(), parent=new Node(); let complete;
    let now=0; const tweens=new Set();
    class Tween {
        constructor(target){this.target=target;this.steps=[];}
        delay(seconds){this.steps.push({seconds});return this;}
        to(seconds,props){this.steps.push({seconds,props});return this;}
        call(fn){this.steps.push({seconds:0,fn});return this;}
        start(){this.at=now;this.index=0;tweens.add(this);return this;}
        static stopAllByTarget(target){for(const t of tweens)if(t.target===target)tweens.delete(t);}
    }
    function advance(seconds){
        now+=seconds;
        for(const t of [...tweens])while(tweens.has(t)&&t.index<t.steps.length){
            const step=t.steps[t.index]; if(t.at+step.seconds>now+1e-9)break;
            t.at+=step.seconds;t.index++;if(step.props)Object.assign(t.target,step.props);step.fn?.();
            if(t.index===t.steps.length)tweens.delete(t);
        }
    }
    const cc={AudioClip:Clip,AudioSource,JsonAsset:class{},Node,SkeletalAnimation:Scheduler,
        cclegacy:{_RF:{push(){},pop(){}}},
        Tween,tween:target=>new Tween(target),
        resources:{load(path,Type,callback){
            if(path.endsWith('/cues'))callback(null,{json:{cues:cues??[{...cue,ratio}],master_volume:master}});
            else if(deferred)complete=()=>callback(null,clip);
            else callback(null,clip);
        }}};
    const js=stripTypeScriptTypes(source.replace(/import \{([^}]+)\} from 'cc';/,'const {$1} = cc;')
        .replace('export class BattleAudio','class BattleAudio'),{mode:'transform'});
    const Type=build?build.load('BattleAudio.ts',cc).BattleAudio:new Function('cc',js+'\nreturn BattleAudio;')(cc);
    return {audio:new Type(parent),clip,parent,complete:()=>complete(),advance,tweens};
}

// Cancelling a scheduled source cue must prevent playback, including a callback
// already dequeued by the engine before cancellation.
{
    const h=harness();await h.audio.load();const scheduler=new Scheduler();
    const cancel=h.audio.schedule(scheduler,'crit_1');
    const [callback,delay]=[...scheduler.jobs][0];assert.equal(delay,.5);
    cancel();assert.equal(scheduler.jobs.size,0);callback();
    assert.equal(h.parent.children.length,0);h.audio.destroy();assert.equal(h.clip.refs,0);
}
// Normal animation completion cancels future cues but preserves a started tail.
{
    const h=harness();await h.audio.load();const scheduler=new Scheduler();
    const cancel=h.audio.schedule(scheduler,'crit_1');scheduler.run();cancel();
    const node=h.parent.children[0];assert.equal(node.audio.volume,.5);assert.equal(node.audio.playing,true);
    assert.equal(node.destroyed,false);node.emit('ended');assert.equal(node.destroyed,true);
    h.audio.destroy();assert.equal(h.clip.refs,0);
}
// Exit stops active voices and removes later triggers; repeated cleanup is safe.
{
    const h=harness();await h.audio.load();const scheduler=new Scheduler();
    h.audio.schedule(scheduler,'crit_1');scheduler.run();h.audio.schedule(scheduler,'crit_1');
    h.audio.stop();assert.equal(scheduler.jobs.size,0);assert.equal(h.parent.children[0].audio.playing,false);
    assert.equal(h.parent.children[0].destroyed,true);h.audio.destroy();h.audio.destroy();assert.equal(h.clip.refs,0);
}
// A load completing after destruction must not retain clips or create a voice.
{
    const h=harness({deferred:true});const loading=h.audio.load();await Promise.resolve();
    h.audio.destroy();h.complete();await loading;assert.equal(h.clip.refs,0);
    const scheduler=new Scheduler();h.audio.schedule(scheduler,'crit_1');scheduler.run();assert.equal(h.parent.children.length,0);
}
{
    const h=harness({ratio:NaN});await assert.rejects(h.audio.load(),/声音配置无效/);
}
console.log('BattleAudio: cancellation, tail preservation, stop/cleanup, late load and invalid cue tests passed.');

const voice={clip:'crit_1',ratio:.25,event:'voice',group:'elsa',sequence:'heavy',delay:.2,fade:.2,
    variants:[{resource:'voice/a',volume:.5},{resource:'voice/b',volume:.75}]};
// An emitted Wwise event survives normal animation end, including its authored delay.
{
    const h=harness({cues:[voice]});await h.audio.load();const s=new Scheduler();
    const cancel=h.audio.schedule(s,'crit_1');s.run();cancel();
    h.advance(.199);assert.equal(h.parent.children.length,0);
    h.advance(.001);assert.equal(h.parent.children.length,1);assert.equal(h.parent.children[0].audio.volume,.5);
    h.audio.schedule(s,'crit_1');s.run();h.advance(.2);
    assert.equal(h.parent.children[0].destroyed,true);assert.equal(h.parent.children[1].audio.volume,.75);
    h.audio.schedule(s,'crit_1');s.run();h.advance(.2);assert.equal(h.parent.children[2].audio.volume,.5);
    h.audio.destroy();assert.equal(h.tweens.size,0);assert.equal(h.clip.refs,0);
}
// Repeated group events invalidate an older queued play; unrelated SFX continue.
{
    const h=harness({cues:[voice,cue]});await h.audio.load();const s=new Scheduler();
    h.audio.schedule(s,'crit_1');s.run();h.advance(.1);
    h.audio.schedule(s,'crit_1');s.run();h.advance(.1);
    assert.equal(h.parent.children.length,2); // only two immediate SFX
    h.advance(.1);assert.equal(h.parent.children.length,3);assert.equal(h.parent.children[2].audio.volume,.75);
    assert.equal(h.parent.children[0].audio.playing,true);
    h.audio.schedule(s,'crit_1');s.run();h.audio.stop();h.advance(1);
    assert.equal(h.parent.children.length,4);assert.ok(h.parent.children.every(n=>n.destroyed));
    assert.equal(h.tweens.size,0);h.audio.destroy();assert.equal(h.clip.refs,0);
}
// Positive source gain is preserved with explicit headroom, never silently clamped.
{
    const h=harness({cues:[{...cue,volume:1.05}],master:.8});await h.audio.load();const s=new Scheduler();
    h.audio.schedule(s,'crit_1');s.run();assert.equal(h.parent.children[0].audio.volume,1.05*.8);h.audio.destroy();
    await assert.rejects(harness({cues:[{...cue,volume:1.05}]}).audio.load(),/声音配置无效/);
}
console.log('Voice delay, sequence wrap, group replacement, scene cleanup and headroom checks passed.');
// Result events use explicit event identity, without a skeletal animation scheduler.
{
    const result={clip:'result',ratio:0,event:'ailisha_battle_win_normal',resource:'result/normal',volume:.7};
    const h=harness({cues:[result]});
    assert.equal(h.audio.playEvent(result.event),false);
    await h.audio.load();assert.equal(h.audio.playEvent('missing'),false);
    assert.equal(h.parent.children.length,0);
    assert.equal(h.audio.playEvent(result.event),true);
    assert.equal(h.parent.children.length,1);assert.equal(h.parent.children[0].audio.playing,true);
    h.audio.stop();assert.equal(h.parent.children[0].destroyed,true);
    h.audio.destroy();assert.equal(h.audio.playEvent(result.event),false);assert.equal(h.clip.refs,0);
}
console.log('Explicit result event identity and cleanup checks passed.');
console.log(JSON.stringify({mode:compiled?'actual-Creator-Web-bundle':'source',buildInputs,
    limitation:'Mock engine services and scheduler; not device/audio/rendering verification.'}));
