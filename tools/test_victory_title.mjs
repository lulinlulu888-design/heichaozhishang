// Actual Creator module with a small cc harness: lifecycle and source keyframe behavior,
// not renderer validation. Browser observations cover the visible result separately.
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import {readCocosTestBuild} from './load_cocos_test_module.mjs';

const manifest=JSON.parse(await readFile(new URL('../clients/cocos-poc/assets/resources/recovered/result-ui/victory-title.json',import.meta.url),'utf8'));
const allocated=[], callbacks=new Map();
class Asset { refs=0; constructor(){allocated.push(this);} addRef(){this.refs++;} decRef(){this.refs--;} }
class JsonAsset extends Asset { json=manifest; }
class SpriteFrame extends Asset {}
class Node {
    children=[]; components=new Map(); active=true; parent=null; layer=1;
    constructor(name){this.name=name;}
    addChild(node){node.parent=this;this.children.push(node);}
    addComponent(C){const c=new C();this.components.set(C,c);return c;}
    setPosition(x,y){this.position=[x,y];}
    setScale(x,y){this.scale=[x,y];}
    get activeInHierarchy(){return this.active&&(!this.parent||this.parent.activeInHierarchy);}
    destroy(){this.active=false;}
}
class UITransform {setContentSize(x,y){this.size=[x,y];}setAnchorPoint(x,y){this.anchor=[x,y];}}
class UIOpacity {opacity=255;}
class Sprite {static SizeMode={CUSTOM:1};}
class Color {constructor(...args){this.values=args;}}
const game={deltaTime:0};
const director={on(event,fn,owner){callbacks.set(owner,fn);},off(event,fn,owner){assert.equal(callbacks.get(owner),fn);callbacks.delete(owner);}};
const cc={Asset,JsonAsset,SpriteFrame,Node,UITransform,UIOpacity,Sprite,Color,game,director,
    cclegacy:{_RF:{push(){},pop(){}}},
    Director:{EVENT_BEFORE_UPDATE:'update'},resources:{load(path,C,callback){queueMicrotask(()=>callback(null,new C()));}}};
const build=await readCocosTestBuild();
const {VictoryTitleView}=build.load('VictoryTitleView.ts',cc);
const checks=[];
const record=(name,fn)=>{fn();checks.push(name);};
const flush=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
const parent=new Node('parent'),fallback=[new Node('fallback')];
const view=new VictoryTitleView(parent,fallback);view.setVisible(true);await flush();
function find(node,name){if(node.name===name)return node;for(const child of node.children){const found=find(child,name);if(found)return found;}}
const letter=find(parent,'img_event_win_up');
const tick=dt=>{game.deltaTime=dt;callbacks.get(view).call(view);};
record('Entry starts at source frame 5 without final-title flash',()=>{
    assert.equal(letter.components.get(UIOpacity).opacity,0);assert.deepEqual(letter.scale,[1.5,1.5]);
    assert.equal(fallback[0].active,false);
});
tick(.7);
record('Source alpha/scale interpolate during entry',()=>{
    const alpha=letter.components.get(UIOpacity).opacity;
    assert.ok(alpha>0&&alpha<255);assert.ok(letter.scale[0]>1&&letter.scale[0]<1.5);
});
view.setVisible(true);
record('Repeated state delivery does not restart entry',()=>assert.ok(letter.components.get(UIOpacity).opacity>0));
tick(4);
record('Entry holds exact final pose',()=>{
    assert.equal(letter.components.get(UIOpacity).opacity,255);assert.deepEqual(letter.scale,[1,1]);
    assert.deepEqual(letter.position,[9,-8]);
});
view.setVisible(false);tick(5);view.setVisible(true);
record('Leaving and re-entering resets the title animation',()=>assert.equal(letter.components.get(UIOpacity).opacity,0));
tick(Number.NaN);
record('Invalid frame delta does not corrupt state',()=>assert.equal(letter.components.get(UIOpacity).opacity,0));
view.destroy();
record('Destroy releases assets and engine callback',()=>{
    assert.equal(callbacks.size,0);assert.ok(allocated.every(a=>a.refs===0));
});
const late=new VictoryTitleView(new Node('late'),[]);late.setVisible(true);late.setVisible(false);await flush();
record('Load completion cannot reopen a hidden result',()=>assert.equal(late.root.active,false));
late.destroy();
await writeFile(new URL('../analysis/battle-ui/result/title-animation-tests.json',import.meta.url),JSON.stringify({
    scope:'Actual Creator emitted module with mocked cc; not original/runtime/rendering parity',buildInputs:build.buildInputs,checks,
},null,2));
console.log('Passed '+checks.length+' victory title checks');
