import { Camera, Color, EffectAsset, gfx, Material, Mesh, MeshRenderer, Node, RenderTexture,
    resources, Sprite, SpriteFrame, UITransform, utils } from 'cc';
import { ArrowPoint, createTargetArrowGeometry } from './TargetArrowGeometry';

/** Source geometry/textures rendered into an isolated transparent UI surface. */
export class TargetArrowView {
    private stage: Node;
    private surface: Sprite;
    private head: Sprite;
    private renderer: MeshRenderer;
    private texture: RenderTexture;
    private frame: SpriteFrame;
    private material: Material | null = null;
    private mesh: Mesh | null = null;
    private assets: (SpriteFrame | EffectAsset)[] = [];
    private disposed = false;
    private pending: { start: ArrowPoint; end: ArrowPoint } | null = null;

    constructor(parent: Node) {
        const surfaceNode = new Node('TargetArrowSurface'); surfaceNode.layer = parent.layer;
        parent.addChild(surfaceNode); surfaceNode.addComponent(UITransform).setContentSize(1280,720);
        this.surface = surfaceNode.addComponent(Sprite); this.surface.sizeMode = Sprite.SizeMode.CUSTOM;
        // The render texture already contains the source SRC_ALPHA/ONE composite.
        // Pinned Creator 3.8.8 UIRenderer serialized blend fields (not in public typings).
        const blend = this.surface as unknown as { _srcBlendFactor: gfx.BlendFactor; _dstBlendFactor: gfx.BlendFactor };
        blend._srcBlendFactor = gfx.BlendFactor.ONE; blend._dstBlendFactor = gfx.BlendFactor.ONE;
        const headNode = new Node('TargetArrowHead'); headNode.layer = parent.layer;
        parent.addChild(headNode); headNode.addComponent(UITransform).setContentSize(256*.7,128*.7);
        this.head = headNode.addComponent(Sprite); this.head.sizeMode = Sprite.SizeMode.CUSTOM;
        this.stage = new Node('TargetArrowRenderStage'); parent.scene.addChild(this.stage);
        const cameraNode = new Node('TargetArrowCamera'); this.stage.addChild(cameraNode);
        cameraNode.setPosition(0,0,100);
        const camera = cameraNode.addComponent(Camera);
        camera.projection = Camera.ProjectionType.ORTHO; camera.orthoHeight = 360;
        camera.near = .1; camera.far = 200; camera.visibility = 1 << 4; camera.priority = -15;
        camera.clearFlags = Camera.ClearFlag.SOLID_COLOR; camera.clearColor = new Color(0,0,0,0);
        this.texture = new RenderTexture(); this.texture.reset({width:1280,height:720});
        camera.targetTexture = this.texture;
        this.frame = new SpriteFrame(); this.frame.texture = this.texture; this.surface.spriteFrame = this.frame;
        const ribbon = new Node('SourceTargetArrowRibbon'); ribbon.layer = 1 << 4;
        this.stage.addChild(ribbon); this.renderer = ribbon.addComponent(MeshRenderer);
        this.hide();
        void this.load().catch(error => { if (!this.disposed) console.warn('[HCZS_ARROW] load failed', error); });
    }

    private asset<T extends SpriteFrame | EffectAsset>(path: string, type: typeof SpriteFrame | typeof EffectAsset): Promise<T> {
        return new Promise((resolve,reject) => resources.load(path, type as typeof SpriteFrame, (error,asset) => {
            if (error || !asset) { reject(error || new Error(path)); return; }
            if (this.disposed) { reject(new Error('Arrow view disposed')); return; }
            asset.addRef(); this.assets.push(asset); resolve(asset as T);
        }));
    }

    private async load(): Promise<void> {
        const base = 'recovered/target-arrow/';
        const [effect,flow,bg,head] = await Promise.all([
            this.asset<EffectAsset>(base+'target-arrow',EffectAsset),
            this.asset<SpriteFrame>(base+'arrowflow/spriteFrame',SpriteFrame),
            this.asset<SpriteFrame>(base+'arrowbg/spriteFrame',SpriteFrame),
            this.asset<SpriteFrame>(base+'arrowhead/spriteFrame',SpriteFrame),
        ]);
        if (this.disposed) return;
        this.material = new Material(); this.material.initialize({effectAsset:effect});
        this.material.setProperty('flowTexture',flow.texture); this.material.setProperty('backgroundTexture',bg.texture);
        this.renderer.setMaterial(this.material,0); this.head.spriteFrame = head;
        if (this.pending) this.show(this.pending.start,this.pending.end);
    }

    show(start: ArrowPoint, end: ArrowPoint): void {
        if (this.disposed) return;
        this.pending = {start:{...start},end:{...end}};
        if (!this.material) return;
        const geometry = createTargetArrowGeometry(start,end);
        if (!geometry) { this.hide(); return; }
        const next = utils.createMesh({positions:geometry.positions,uvs:geometry.uvs,indices:geometry.indices},undefined,{calculateBounds:true});
        this.renderer.mesh = next; this.mesh?.destroy(); this.mesh = next;
        this.head.node.setPosition(end.x,end.y,0);
        // Old cocos clockwise rotation becomes Creator's counterclockwise rotation.
        this.head.node.setRotationFromEuler(0,0,-geometry.nativeHeadRotationDegrees);
        this.stage.active = this.surface.node.active = this.head.node.active = true;
    }

    hide(): void {
        this.pending = null;
        this.stage.active = this.surface.node.active = this.head.node.active = false;
    }

    destroy(): void {
        if (this.disposed) return;
        this.hide(); this.disposed = true;
        this.renderer.mesh = null; this.surface.spriteFrame = null; this.head.spriteFrame = null;
        this.stage.destroy(); this.surface.node.destroy(); this.head.node.destroy();
        this.mesh?.destroy(); this.material?.destroy(); this.frame.destroy(); this.texture.destroy();
        this.assets.forEach(asset=>asset.decRef()); this.assets=[];
    }
}
