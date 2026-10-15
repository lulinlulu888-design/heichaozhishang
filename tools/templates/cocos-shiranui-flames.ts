import { EffectAsset, instantiate, JsonAsset, Mat4, Material, MeshRenderer, Node, Prefab, Quat, resources, Texture2D, Vec3, Vec4 } from 'cc';

type FXNode = {tag: string; attributes: Record<string,string>; position: number[]; scale: number[]; forward?: number[]; model_scale?: number; uniforms?: Record<string,number|number[]>; children: FXNode[]};
type Attachment = {sockets: {name:string;bone:string;matrix:number[];effect:string}[];effects:Record<string,FXNode>;assumptions:string[]};
type Params = Record<string,number|number[]|null>;
export interface ShiranuiFlameHandle {
    update(dt:number):void; setEnabled(value:boolean):void; dispose():void;
    report:{sockets:number;meshes:number;assumptions:string[]};
}
/** Original-resource reference adaptation. Native blend/Forward/lifecycle semantics remain unverified. */
export async function attachShiranuiFlames({weaponRoot,layer}:{weaponRoot:Node;layer:number}):Promise<ShiranuiFlameHandle> {
    const base='recovered/hall/flame/';
    const json=(name:string):Promise<JsonAsset>=>new Promise((resolve,reject)=>resources.load(base+name,JsonAsset,(e,a)=>e?reject(e):resolve(a)));
    const entries=resources.getDirWithPath(base+'geometry',Prefab);
    if(entries.length!==1)throw new Error('原火焰Prefab不唯一');
    const [manifest,attachmentAsset,prefab,effect,textures]=await Promise.all([
        json('manifest'),json('attachment'),
        new Promise<Prefab>((resolve,reject)=>resources.load(entries[0].path!,Prefab,(e,a)=>e?reject(e):resolve(a))),
        new Promise<EffectAsset>((resolve,reject)=>resources.load(base+'flame',EffectAsset,(e,a)=>e?reject(e):resolve(a))),
        Promise.all([0,1,2,3].map(i=>new Promise<Texture2D>((resolve,reject)=>resources.load(base+'texture-'+i+'/texture',Texture2D,(e,a)=>e?reject(e):resolve(a))))),
    ]);
    if(!weaponRoot.isValid)throw new Error('原扇子节点已销毁');
    // Source GLSL decodes colour manually. Keep imported PNG textures in RGBA8, not SRGBA8.
    textures.forEach(t=>{t.setWrapMode(Texture2D.WrapMode.REPEAT,Texture2D.WrapMode.REPEAT);t.setFilters(Texture2D.Filter.LINEAR,Texture2D.Filter.LINEAR);t.setMipFilter(Texture2D.Filter.NONE);});
    const data=manifest.json as {defaults:Record<string,{value:number|number[]|null}>;material:{params:Record<string,string>}};
    const attachment=attachmentAsset.json as Attachment;
    if(!data||!attachment||attachment.sockets.length!==4)throw new Error('原火焰元数据缺失');
    const refs=[manifest,attachmentAsset,prefab,effect,...textures];refs.forEach(a=>a.addRef());
    const defaults:Params={};Object.keys(data.defaults).forEach(k=>defaults[k]=data.defaults[k].value);
    for(const key of Object.keys(data.material.params))if(key in defaults){const v=data.material.params[key].split(',').map(Number);defaults[key]=v.length===1?v[0]:v;}
    const materials:Material[]=[],roots:Node[]=[];let clock=0,enabled=true,disposed=false,meshCount=0;
    const clockValues:{material:Material;value:Vec4}[]=[];
    const number=(p:Params,k:string):number=>{const v=p[k];if(typeof v!=='number'||!Number.isFinite(v))throw new Error('原火焰参数无效 '+k);return v;};
    const array=(p:Params,k:string,n:number):number[]=>{const v=p[k];if(!Array.isArray(v)||v.length!==n||v.some(x=>!Number.isFinite(x)))throw new Error('原火焰向量无效 '+k);return v;};
    const vec=(v:number[]):Vec4=>new Vec4(v[0],v[1],v[2],v[3]);
    const findBone=(name:string):Node=>{const found:Node[]=[];const visit=(n:Node):void=>{if(n.name===name)found.push(n);n.children.forEach(visit);};visit(weaponRoot);if(found.length!==1)throw new Error('原扇骨不唯一 '+name);return found[0];};
    function makeMaterial(node:FXNode):Material {
        const p:Params={...defaults,...node.uniforms},mode=Number(node.attributes.TransparentMode);
        if([0,2].indexOf(mode)<0)throw new Error('未知原火焰混合');
        for(const k of ['mirror_u','mirror_v','rotation_floatTex01','offset_u','offset_v','alpha_mirror_u','alpha_mirror_v','alpha_rotation'])if(number(p,k)!==0)throw new Error('未支持火焰UV变换 '+k);
        const priority=128+Number(node.attributes.RenderOrder||0)+Number(node.attributes.RenderBias||0);
        if(!Number.isInteger(priority)||priority<0||priority>255)throw new Error('火焰排序超界');
        const m=new Material();materials.push(m);m.initialize({effectAsset:effect,technique:mode===0?1:0,states:{priority}});
        ['mainTexture','distortionTexture','maskTexture','dissolveTexture'].forEach((key,i)=>m.setProperty(key,textures[i]));
        const c=array(p,'g_colFloatingColor1',4);m.setProperty('tint',new Vec4(c[1]/255,c[2]/255,c[3]/255,1));
        m.setProperty('floatFlow',vec([number(p,'g_vFloatingTilingU1'),number(p,'g_vFloatingTilingV1'),...array(p,'g_vFloatingSpeed1',2)]));
        m.setProperty('distortionFlow',vec([...array(p,'g_vDistortionTiling',2),...array(p,'g_vDistortionSpeed',2)]));
        m.setProperty('dissolveFlow',vec([...array(p,'g_vDissolveTiling',2),number(p,'g_vDissolveSpeedU'),number(p,'g_vDissolveSpeedV')]));
        m.setProperty('strengths',vec([number(p,'g_fDistortionStrength1'),number(p,'g_fFloatingStrength1'),number(p,'alphaMtl'),number(p,'alpha_mask_intensity')]));
        const value=new Vec4(number(p,'g_DissolveStrength'),number(p,'g_dissolve_hardness'),0,0);m.setProperty('dissolveClock',value);clockValues.push({material:m,value});

        return m;
    }
    function build(node:FXNode,parent:Node):Node {
        const group=new Node(node.attributes.Name);parent.addChild(group);group.layer=layer;
        group.setPosition(...node.position as [number,number,number]);group.setScale(...node.scale as [number,number,number]);
        if(node.forward){const [x,y,z,angle]=node.forward;const axis=new Vec3(x,y,z);if(axis.lengthSqr()<1e-12)throw new Error('火焰旋转轴无效');axis.normalize();group.setRotation(Quat.fromAxisAngle(new Quat(),axis,angle*Math.PI/180));}
        if(node.tag==='Model'){
            const model=instantiate(prefab);group.addChild(model);const scale=node.model_scale??1;model.setScale(Vec3.multiplyScalar(new Vec3(),model.scale,scale));
            const material=makeMaterial(node);const renderers=model.getComponentsInChildren(MeshRenderer);if(renderers.length!==1)throw new Error('原火焰几何布局变化');
            for(const renderer of renderers){renderer.setSharedMaterial(material,0);meshCount++;}
            const layerNodes=(n:Node):void=>{n.layer=layer;n.children.forEach(layerNodes);};layerNodes(model);
        }
        for(const child of node.children)build(child,group);return group;
    }
    function dispose():void {if(disposed)return;disposed=true;roots.forEach(n=>n.destroy());materials.forEach(m=>m.destroy());refs.forEach(a=>a.decRef());}
    try {
        const pending:{root:Node;bone:Node}[]=[];
        for(const socket of attachment.sockets){
            const bone=findBone(socket.bone),root=new Node(socket.name);roots.push(root);root.layer=layer;
            if(socket.matrix.length!==16||socket.matrix.some(v=>!Number.isFinite(v)))throw new Error('原挂点矩阵无效');
            const rotation=new Quat(),position=new Vec3(),scale=new Vec3();Mat4.toRTS(Mat4.fromArray(new Mat4(),socket.matrix),rotation,position,scale);root.setRTS(rotation,position,scale);
            build(attachment.effects[socket.effect],root);pending.push({root,bone});
        }
        if(meshCount!==20)throw new Error('原火焰层数变化');
        pending.forEach(({root,bone})=>bone.addChild(root));
    }catch(error){dispose();throw error;}
    const report={sockets:roots.length,meshes:meshCount,assumptions:[...attachment.assumptions,'Cocos socket uses TRS decomposition; equal-priority transparency uses engine sorting, not verified original renderer.']};
    return {report,update(dt:number):void{if(disposed||!enabled)return;if(!Number.isFinite(dt)||dt<0)throw new Error('火焰时间无效');clock+=dt;for(const {material,value} of clockValues){value.z=clock;material.setProperty('dissolveClock',value);}},setEnabled(value:boolean):void{enabled=Boolean(value);roots.forEach(n=>n.active=enabled);},dispose};
}
