import { Asset, Color, director, Director, game, gfx, JsonAsset, Node, resources, Sprite, SpriteFrame, UITransform } from 'cc';

type SourceNode = { name: string; action_tag: number; classname: string; position: number[];
    scale: number[]; rotation_skew: number[]; anchor: number[]; size: number[];
    children: SourceNode[]; resource?: { path: string }; color_argb: number[] };
type Frame = { index: number; value: number[] | { path: string } };
type Manifest = { hierarchy: SourceNode; speed: number; duration: number;
    timing: { native_frame_interval: number }; colors: Record<string, { argb: number[] }>;
    frames: { source_path: string; resource: string }[];
    timelines: { action_tag: number; property: string; frames: Frame[] }[] };

/** Source sprites/layout/timeline. Loader speed and native rendering parity remain unverified. */
export class CardSelectionView {
    private root: Node;
    private manifest: Manifest | null = null;
    private assets: Asset[] = [];
    private frames = new Map<string, SpriteFrame>();
    private nodes = new Map<number, Node>();
    private reflections = new Map<number, number[]>();
    private disposed = false;
    private selected: Node | null = null;
    private originalIndex = 0;
    private elapsed = 0;
    private currentFrame = -1;

    constructor(private parent: Node) {
        this.root = new Node('OriginalCardSelection'); this.root.layer = parent.layer;
        parent.addChild(this.root); this.root.active = false;
        director.on(Director.EVENT_BEFORE_UPDATE, this.update, this);
        void this.load().catch(error => { if (!this.disposed) console.warn('[HCZS_SELECTION]',error); });
    }

    private asset<T extends Asset>(path: string, type: new (...args: any[]) => T): Promise<T> {
        return new Promise((resolve,reject) => resources.load(path,type,(error,asset) => {
            if (error || !asset || this.disposed) { reject(error || new Error('Selection load cancelled')); return; }
            asset.addRef(); this.assets.push(asset); resolve(asset);
        }));
    }

    private async load(): Promise<void> {
        const base = 'recovered/card-selection/';
        const data = await this.asset(base+'selection', JsonAsset);
        const manifest = data.json as Manifest;
        await Promise.all(manifest.frames.map(async frame => {
            this.frames.set(frame.source_path, await this.asset(base+frame.resource+'/spriteFrame',SpriteFrame));
        }));
        if (this.disposed) return;
        this.build(manifest.hierarchy,this.root,manifest);
        this.manifest = manifest;
        if (this.selected?.isValid) { this.root.active = true; this.applyFrame(0); }
    }

    private build(source: SourceNode, parent: Node, manifest: Manifest): void {
        const node = new Node(source.name); node.layer = parent.layer; parent.addChild(node);
        this.nodes.set(source.action_tag,node);
        this.reflections.set(source.action_tag,[source.rotation_skew[1]===180?-1:1,source.rotation_skew[0]===180?-1:1]);
        node.setPosition(source.position[0],source.position[1]);
        // Observed skew pairs are 0/180 degrees, hence a diagonal transform.
        if (source.rotation_skew.some(value => value !== 0 && value !== 180)) throw new Error('Unsupported source skew');
        node.setScale(source.scale[0]*(source.rotation_skew[1]===180?-1:1),
            source.scale[1]*(source.rotation_skew[0]===180?-1:1));
        if (source.classname === 'Sprite') {
            const ui = node.addComponent(UITransform); ui.setContentSize(source.size[0],source.size[1]);
            ui.setAnchorPoint(source.anchor[0],source.anchor[1]);
            const sprite = node.addComponent(Sprite); sprite.sizeMode = Sprite.SizeMode.CUSTOM;
            sprite.spriteFrame = this.frames.get(source.resource!.path)!;
            // Current tutorial cards target the monster: source EffectSelect S11/S12.
            const color = manifest.colors[source.name.startsWith('Sprite_5') || source.name.startsWith('Sprite_6') ? 'S11':'S12'].argb;
            sprite.color = new Color(color[1],color[2],color[3],color[0]);
            // PNG frames are straight-alpha; multiply alpha before additive compositing.
            const blend = sprite as unknown as { _srcBlendFactor: gfx.BlendFactor; _dstBlendFactor: gfx.BlendFactor };
            blend._srcBlendFactor = gfx.BlendFactor.SRC_ALPHA; blend._dstBlendFactor = gfx.BlendFactor.ONE;
        }
        for (const child of source.children) this.build(child,node,manifest);
    }

    show(card: Node): void {
        this.hide(); this.selected = card; this.originalIndex = card.getSiblingIndex();
        card.setSiblingIndex(card.parent!.children.length-1);
        this.root.setParent(card); this.root.setPosition(0,0); this.root.setScale(1,1);
        this.elapsed = 0; this.currentFrame = -1;
        this.root.active = !!this.manifest;
        if (this.manifest) this.applyFrame(0);
    }

    hide(): void {
        this.root.active = false;
        if (this.selected?.isValid) this.selected.setSiblingIndex(this.originalIndex);
        this.selected = null; this.root.setParent(this.parent);
    }

    private update(): void {
        const dt=game.deltaTime;
        const m = this.manifest;
        if (!m || !this.selected || !this.root.activeInHierarchy || !Number.isFinite(dt) || dt < 0) return;
        this.elapsed += Math.fround(dt*m.speed);
        let frame = Math.floor(this.elapsed/m.timing.native_frame_interval);
        if (frame > m.duration) { this.elapsed = 0; frame = 0; }
        this.applyFrame(frame);
    }

    private applyFrame(index: number): void {
        if (index === this.currentFrame || !this.manifest) return;
        this.currentFrame = index;
        for (const track of this.manifest.timelines) {
            const node = this.nodes.get(track.action_tag)!;
            // Source Position/Scale tracks have a single key; no interpolation needed.
            const key = [...track.frames].reverse().find(frame => frame.index <= index) || track.frames[0];
            if (track.property === 'FileData') node.getComponent(Sprite)!.spriteFrame = this.frames.get((key.value as {path:string}).path)!;
            else if (track.property === 'Position') { const p = key.value as number[]; node.setPosition(p[0],p[1]); }
            // Keep source reflection signs when scale keys are applied.
            else if (track.property === 'Scale') {
                const p = key.value as number[]; const sign = this.reflections.get(track.action_tag)!;
                node.setScale(sign[0]*p[0],sign[1]*p[1]);
            }
        }
    }

    destroy(): void {
        this.disposed = true; director.off(Director.EVENT_BEFORE_UPDATE,this.update,this);
        this.hide(); this.root.destroy(); this.frames.clear();
        for (const asset of this.assets) asset.decRef(); this.assets = [];
    }
}
