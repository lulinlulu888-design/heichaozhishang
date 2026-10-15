import { Asset, Color, director, Director, game, JsonAsset, Node, resources,
    Sprite, SpriteFrame, UIOpacity, UITransform } from 'cc';

type Source = { name: string; action_tag: number; position: number[]; scale: number[];
    anchor: number[]; size: number[]; alpha: number; color_argb: number[];
    children: Source[]; resource?: { path: string } };
type Key = { index: number; tween: boolean; easing_type: number; value: number | number[] };
type Track = { action_tag: number; property: string; frames: Key[] };
type Manifest = { hierarchy: Source; speed: number; frame_interval: number;
    animations: { name: string; start: number; end: number }[]; timelines: Track[];
    frames: { source_path: string; resource: string }[] };
type Bound = { node: Node; ui: UITransform; opacity: UIOpacity; offset: number[] };

/** Source title tracks only. Original particles and reward flow are not emulated. */
export class VictoryTitleView {
    private root: Node;
    private assets: Asset[] = [];
    private nodes = new Map<number, Bound>();
    private manifest: Manifest | null = null;
    private disposed = false;
    private visible = false;
    private elapsed = 0;
    private complete = false;

    constructor(parent: Node, private fallback: Node[]) {
        this.root = new Node('OriginalVictoryTitleTimeline'); this.root.layer = parent.layer;
        parent.addChild(this.root); this.root.setPosition(640, 0); this.root.active = false;
        director.on(Director.EVENT_BEFORE_UPDATE, this.update, this);
        void this.load().catch(error => { if (!this.disposed) console.warn('[HCZS_VICTORY]', String(error)); });
    }
    private asset<T extends Asset>(path: string, type: new (...args: any[]) => T): Promise<T> {
        return new Promise((resolve, reject) => resources.load(path, type, (error, value) => {
            if (error || !value || this.disposed) { reject(error || new Error('Victory load cancelled')); return; }
            value.addRef(); this.assets.push(value); resolve(value);
        }));
    }
    private async load(): Promise<void> {
        const base = 'recovered/result-ui/';
        const m = (await this.asset(base + 'victory-title', JsonAsset)).json as Manifest;
        const frames = new Map<string, SpriteFrame>();
        await Promise.all(m.frames.map(async f => frames.set(f.source_path,
            await this.asset(base + f.resource + '/spriteFrame', SpriteFrame))));
        if (this.disposed) return;
        this.build(m.hierarchy, this.root, [0, 0], frames); this.manifest = m;
        this.fallback.forEach(n => n.active = false);
        this.root.active = this.visible;
        if (this.visible) this.start();
    }
    private build(s: Source, parent: Node, offset: number[], frames: Map<string, SpriteFrame>): void {
        const node = new Node(s.name); node.layer = parent.layer; parent.addChild(node);
        const ui = node.addComponent(UITransform); ui.setContentSize(s.size[0], s.size[1]);
        ui.setAnchorPoint(s.anchor[0], s.anchor[1]);
        node.setPosition(s.position[0] - offset[0], s.position[1] - offset[1]);
        node.setScale(s.scale[0], s.scale[1]);
        const opacity = node.addComponent(UIOpacity); opacity.opacity = s.alpha;
        this.nodes.set(s.action_tag, { node, ui, opacity, offset });
        if (s.resource) {
            const sprite = node.addComponent(Sprite); sprite.sizeMode = Sprite.SizeMode.CUSTOM;
            sprite.trim = false; sprite.spriteFrame = frames.get(s.resource.path)!;
            sprite.color = new Color(s.color_argb[1], s.color_argb[2], s.color_argb[3], 255);
        }
        for (const child of s.children) this.build(child, node,
            [s.anchor[0] * s.size[0], s.anchor[1] * s.size[1]], frames);
    }
    setVisible(visible: boolean): void {
        const changed = visible !== this.visible; this.visible = visible;
        this.root.active = visible && !!this.manifest;
        if (changed && visible && this.manifest) this.start();
        if (!visible) { this.elapsed = 0; this.complete = false; }
    }
    private start(): void {
        this.elapsed = 0; this.complete = false;
        this.apply(this.manifest!.animations.find(c => c.name === 'in')!.start);
    }
    private update(): void {
        const m = this.manifest, dt = game.deltaTime;
        if (!m || !this.visible || !this.root.activeInHierarchy || this.complete || !Number.isFinite(dt) || dt < 0) return;
        this.elapsed += Math.fround(dt * m.speed);
        const clip = m.animations.find(c => c.name === 'in')!;
        const frame = Math.min(clip.end, clip.start + Math.floor(this.elapsed / m.frame_interval));
        this.apply(frame); this.complete = frame === clip.end;
    }
    private apply(frame: number): void {
        for (const track of this.manifest!.timelines) {
            const b = this.nodes.get(track.action_tag)!;
            let a = track.frames[0], z = a;
            for (const key of track.frames) {
                if (key.index <= frame) a = key; else { z = key; break; }
                z = a;
            }
            let v = a.value;
            if (a.tween && z.index > a.index && frame >= a.index) {
                let t = (frame - a.index) / (z.index - a.index);
                // Standard cocos2d-x enum; native-fork equivalence remains unverified.
                if (a.easing_type === 2) t = Math.sin(t * Math.PI / 2);
                else if (a.easing_type === 14) t = 1 + Math.pow(t - 1, 5);
                else if (a.easing_type === 20) t = Math.sqrt(1 - (t - 1) * (t - 1));
                if (typeof a.value === 'number' && typeof z.value === 'number') v = a.value + (z.value - a.value) * t;
                else if (Array.isArray(a.value) && Array.isArray(z.value)) {
                    const end = z.value; v = a.value.map((n, i) => n + (end[i] - n) * t);
                }
            }
            if (track.property === 'Alpha') b.opacity.opacity = Math.max(0, Math.min(255, Math.round(v as number)));
            else {
                const p = v as number[];
                if (track.property === 'Position') b.node.setPosition(p[0] - b.offset[0], p[1] - b.offset[1]);
                else if (track.property === 'Scale') b.node.setScale(p[0], p[1]);
                else if (track.property === 'AnchorPoint') b.ui.setAnchorPoint(p[0], p[1]);
            }
        }
    }
    destroy(): void {
        this.disposed = true; director.off(Director.EVENT_BEFORE_UPDATE, this.update, this);
        this.root.destroy(); this.assets.forEach(a => a.decRef()); this.assets = [];
    }
}
