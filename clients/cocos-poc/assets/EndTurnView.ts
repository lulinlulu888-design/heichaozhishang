import { Asset, Color, director, Director, game, gfx, JsonAsset, Label, Node, ParticleAsset,
    ParticleSystem2D, resources, Sprite, SpriteFrame, UIOpacity, UITransform } from 'cc';

type SourceNode = { name: string; action_tag: number; classname: string; position: number[];
    scale: number[]; rotation_skew: number[]; anchor: number[]; size: number[];
    children: SourceNode[]; resource?: { path: string }; color_argb: number[]; blend_func?: number[] };
type Frame = { index: number; tween: boolean; easing_type: number; value: number | number[] | boolean | { path: string } };
type Track = { action_tag: number; property: string; frames: Frame[] };
type Clip = { name: string; start: number; end: number };
type Manifest = { hierarchy: SourceNode; speed: number; frame_interval: number; animations: Clip[];
    timelines: Track[]; frames: { source_path: string; resource: string }[]; particles: string[] };
type Bound = { node: Node; source: SourceNode; offset: number[]; opacity: UIOpacity; sprite?: Sprite; particle?: ParticleSystem2D };

// Standard cocos2d-x 3.17.2 CCTweenFunction enum. Native-fork equivalence unverified.
function ease(t: number, kind: number): number {
    switch (kind) {
        case -1: case 0: return t;
        case 2: return Math.sin(t*Math.PI/2);
        case 5: return t*(2-t);
        case 8: return 1+Math.pow(t-1,3);
        case 14: return 1+Math.pow(t-1,5);
        case 16: return t===0?0:Math.pow(2,10*(t-1))-.001;
        case 20: return Math.sqrt(1-(t-1)*(t-1));
        default: throw new Error(`Unsupported EndArea easing ${kind}`);
    }
}
function sample(track: Track, frame: number): Frame['value'] {
    let a=track.frames[0], b=a;
    for (const key of track.frames) {
        if (key.index<=frame) a=key;
        else { b=key; break; }
        b=a;
    }
    if (!a.tween || b.index<=a.index || frame<a.index) return a.value;
    const t=ease((frame-a.index)/(b.index-a.index),a.easing_type);
    if (typeof a.value==='number' && typeof b.value==='number') return a.value+(b.value-a.value)*t;
    if (Array.isArray(a.value) && Array.isArray(b.value)) {
        const end=b.value; return a.value.map((v,i)=>v+(end[i]-v)*t);
    }
    return a.value;
}

/** Source EndArea layers/tracks rendered by Creator; no claim of original runtime parity. */
export class EndTurnView {
    private root: Node;
    private manifest: Manifest | null=null;
    private assets: Asset[]=[];
    private frames=new Map<string,SpriteFrame>();
    private particles=new Map<string,ParticleAsset>();
    private nodes=new Map<number,Bound>();
    private particleKeys=new Map<number,number>();
    private labels: Label[]=[];
    private disposed=false;
    private desired: 'black'|'white'='black';
    private current: 'black'|'white'='black';
    private clip: Clip | null=null;
    private elapsed=0;
    private visible=false;
    private text='回合结束';
    constructor(parent: Node, private fallback: Node[], private onReadinessChanged: ()=>void) {
        this.root=new Node('OriginalEndArea'); this.root.layer=parent.layer; parent.addChild(this.root);
        this.root.setPosition(50,0); this.root.active=false;
        director.on(Director.EVENT_BEFORE_UPDATE,this.update,this);
        void this.load().catch(error=>{if(!this.disposed) console.warn('[HCZS_END_AREA]',String(error));});
    }
    private asset<T extends Asset>(path: string,type: new (...args: any[])=>T): Promise<T> {
        return new Promise((resolve,reject)=>resources.load(path,type,(error,value)=>{
            if(error||!value||this.disposed){reject(error||new Error('EndArea cancelled'));return;}
            value.addRef();this.assets.push(value);resolve(value);
        }));
    }
    private async load(): Promise<void> {
        const base='recovered/end-turn/';
        const data=await this.asset(base+'end-turn',JsonAsset); const m=data.json as Manifest;
        await Promise.all([
            ...m.frames.map(async f=>this.frames.set(f.source_path,await this.asset(base+f.resource+'/spriteFrame',SpriteFrame))),
            ...m.particles.map(async p=>{
                this.particles.set(p,await this.asset(base+p,ParticleAsset));
                this.frames.set(p,await this.asset(base+p+'/spriteFrame',SpriteFrame));
            }),
        ]);
        if(this.disposed)return;
        for(const t of m.timelines)for(const f of t.frames)if(f.tween) ease(.5,f.easing_type);
        this.build(m.hierarchy,this.root,[0,0]); this.manifest=m;
        this.fallback.forEach(n=>n.active=false);this.root.active=this.visible;
        this.current=this.desired;this.play(this.current+'_in');this.setText();
        console.info('[HCZS_END_AREA] source tracks ready');
    }
    private build(s: SourceNode,parent: Node,offset: number[]): void {
        if(s.classname==='Button'||s.classname==='Panel')return; // transparent hit/layout placeholders; host owns input
        const node=new Node(s.name);node.layer=parent.layer;parent.addChild(node);
        const ui=node.addComponent(UITransform);ui.setContentSize(s.size[0],s.size[1]);ui.setAnchorPoint(s.anchor[0],s.anchor[1]);
        node.setPosition(s.position[0]-offset[0],s.position[1]-offset[1]);node.setScale(s.scale[0],s.scale[1]);
        if(s.rotation_skew[0]!==s.rotation_skew[1])throw new Error('Unsupported EndArea skew');
        node.setRotationFromEuler(0,0,-s.rotation_skew[0]);
        const opacity=node.addComponent(UIOpacity);opacity.opacity=s.color_argb[0];
        const bound: Bound={node,source:s,offset,opacity};this.nodes.set(s.action_tag,bound);
        const color=new Color(s.color_argb[1],s.color_argb[2],s.color_argb[3],255);
        if(s.classname==='Sprite'||s.classname==='ImageView') {
            const sprite=node.addComponent(Sprite);sprite.sizeMode=Sprite.SizeMode.CUSTOM;
            sprite.spriteFrame=this.frames.get(s.resource!.path)!;sprite.color=color;bound.sprite=sprite;
            if(s.blend_func?.[1]===1) {
                const blend=sprite as unknown as {_srcBlendFactor:gfx.BlendFactor;_dstBlendFactor:gfx.BlendFactor};
                blend._srcBlendFactor=gfx.BlendFactor.SRC_ALPHA;blend._dstBlendFactor=gfx.BlendFactor.ONE;
            }
        } else if(s.classname==='Text') {
            const label=node.addComponent(Label);label.string=this.text;label.fontSize=20;label.lineHeight=21;
            label.horizontalAlign=Label.HorizontalAlign.CENTER;label.verticalAlign=Label.VerticalAlign.CENTER;
            label.color=color;this.labels.push(label);
        } else if(s.classname==='Particle') {
            const particle=node.addComponent(ParticleSystem2D);particle.playOnLoad=false;
            particle.file=this.particles.get(s.name)!;particle.spriteFrame=this.frames.get(s.name)!;particle.stopSystem();bound.particle=particle;
        }
        for(const c of s.children)this.build(c,node,[s.anchor[0]*s.size[0],s.anchor[1]*s.size[1]]);
    }
    get acceptsInput(): boolean {
        return this.visible && (!this.manifest || !this.clip || this.clip.name==='white_loop');
    }
    setState(visible: boolean,noPlayableCards: boolean,enemy: boolean): void {
        const wasVisible=this.visible;this.visible=visible;this.text=enemy?'敌方回合':'回合结束';
        this.desired=noPlayableCards&&!enemy?'white':'black';this.setText();
        this.root.active=visible&&!!this.manifest;
        if(!visible) {for(const b of this.nodes.values())b.particle?.stopSystem();this.clip=null;this.onReadinessChanged();return;}
        if(!this.manifest)return;
        if(!wasVisible){this.current=this.desired;this.play(this.current+'_in');}
        else if(this.current!==this.desired&&!this.clip?.name.endsWith('_out'))this.play(this.current+'_out');
    }
    private setText():void {for(const label of this.labels)label.string=this.text;}
    private play(name: string):void {
        this.particleKeys.clear();
        this.clip=this.manifest!.animations.find(c=>c.name===name)!;this.elapsed=0;
        for(const b of this.nodes.values()) {
            if(b.source.name==='Node_s1')b.node.active=name.startsWith('black');
            if(b.source.name==='Node_s2')b.node.active=name.startsWith('white');
            b.particle?.stopSystem();
        }
        this.apply(this.clip.start);this.onReadinessChanged();console.info('[HCZS_END_AREA]',name);
    }
    private update():void {
        const dt=game.deltaTime;
        if(!this.clip||!this.manifest||!this.root.activeInHierarchy||!Number.isFinite(dt)||dt<0)return;
        this.elapsed+=Math.fround(dt*this.manifest.speed);
        const frame=this.clip.start+Math.floor(this.elapsed/this.manifest.frame_interval);
        this.apply(Math.min(frame,this.clip.end));
        if(frame<=this.clip.end)return;
        if(this.clip.name.endsWith('_out')){this.current=this.desired;this.play(this.current+'_in');}
        else if(this.current!==this.desired)this.play(this.current+'_out');
        else if(this.current==='white')this.play('white_loop');
        else {this.clip=null;this.onReadinessChanged();}
    }
    private apply(frame: number):void {
        for(const track of this.manifest!.timelines) {
            const b=this.nodes.get(track.action_tag);if(!b)continue;
            const v=sample(track,frame);
            switch(track.property) {
                case 'Alpha': b.opacity.opacity=Math.max(0,Math.min(255,Math.round(v as number)));break;
                case 'Position': {const p=v as number[];b.node.setPosition(p[0]-b.offset[0],p[1]-b.offset[1]);break;}
                case 'Scale': {const p=v as number[];b.node.setScale(p[0],p[1]);break;}
                case 'RotationSkew': {const p=v as number[];b.node.setRotationFromEuler(0,0,-p[0]);break;}
                case 'CColor': {const c=v as number[];if(b.sprite)b.sprite.color=new Color(c[1],c[2],c[3],255);break;}
                case 'FileData': if(b.sprite)b.sprite.spriteFrame=this.frames.get((v as {path:string}).path)!;break;
                case 'IsPlaying': if(b.particle&&b.node.activeInHierarchy) {
                    const key=track.frames.filter(f=>f.index<=frame).pop()?.index??track.frames[0].index;
                    if(this.particleKeys.get(track.action_tag)!==key) {
                        this.particleKeys.set(track.action_tag,key);
                        if(v)b.particle.resetSystem();else b.particle.stopSystem();
                    }
                } break;
            }
        }
    }
    destroy():void {
        this.disposed=true;director.off(Director.EVENT_BEFORE_UPDATE,this.update,this);
        this.root.destroy();this.assets.forEach(a=>a.decRef());this.assets=[];
    }
}
