import { AnimationClip, Camera, Color, director, Director, instantiate, JsonAsset, Mat4, MeshRenderer, Node,
    Prefab, Quat, RenderTexture, resources, SkeletalAnimation, Sprite, SpriteFrame, UITransform, Vec3, view } from 'cc';
import { installHallBaseMaterials, installHallCharacterBaseMaterials, installHallLighting, HallLightmapData } from './HallLighting';
import { attachShiranuiFlames } from './ShiranuiFlames';

type HallView = 'camera_1' | 'camera_upstairs' | 'camera_negative' | 'close';
interface SourceCamera { Name: string; Transform: string; Fov: string; Near: string; Far: string; }
interface HallData {
    cameras: SourceCamera[];
    player: { matrix: number[]; scale: number };
    hiddenNodes: string[];
    opaque: { nodeName: string; slot: number; cullBack: boolean }[];
    characterMaterials: Record<'actor' | 'weapon', {slot: number; alphaMode: 'OPAQUE' | 'MASK'; alphaCutoff: number}[]>;
}
const LAYER = 1 << 3;
const IDLE = 'home_stand_idle_1';

/** Shared native-capable Cocos scene. Reference adapters do not claim original renderer parity. */
export class HallSceneView {
    private stage: Node | null = null;
    private camera: Camera | null = null;
    private texture: RenderTexture | null = null;
    private frame: SpriteFrame | null = null;
    private prefabs: Prefab[] = [];
    private animations: SkeletalAnimation[] = [];
    private lighting: Awaited<ReturnType<typeof installHallLighting>> | null = null;
    private baseMaterials: Awaited<ReturnType<typeof installHallBaseMaterials>> | null = null;
    private characterMaterials: Awaited<ReturnType<typeof installHallCharacterBaseMaterials>>[] = [];
    private flames: Awaited<ReturnType<typeof attachShiranuiFlames>> | null = null;
    private data: HallData | null = null;
    private closeCenter: Vec3 | null = null;
    private loading: Promise<void> | null = null;
    private cancelPoseWait: (() => void) | null = null;
    private disposed = false;
    private visible = false;
    private paused = false;
    private lightingEnabled = true;
    private flamesEnabled = true;
    private view: HallView = 'camera_1';
    private diagnosticWeapon: Node | null = null;
    private diagnosedMotion = false;
    private renderQuality: 1 | 2 = 2;
    private readonly resizeTarget = (): void => { if (this.visible) this.syncRenderTarget(); };

    constructor(private scene: Node, private surface: Sprite) {
        surface.node.active = false;
        view.on('canvas-resize', this.resizeTarget);
        view.on('design-resolution-changed', this.resizeTarget);
    }
    async show(): Promise<void> {
        if (this.disposed) throw new Error('大厅视图已销毁');
        this.visible = true;
        if (!this.loading) this.loading = this.load().catch(error => {
            this.release(); this.loading = null; throw error;
        });
        await this.loading;
        if (this.disposed || !this.visible || !this.stage) return;
        this.stage.active = true; this.surface.node.active = true;
        this.syncRenderTarget();
        this.syncPause();
    }
    hide(): void {
        this.visible = false;
        this.surface.node.active = false;
        this.syncPause();
        if (this.stage) this.stage.active = false;
    }
    destroy(): void {
        if (this.disposed) return;
        this.disposed = true; this.visible = false;
        view.off('canvas-resize', this.resizeTarget);
        view.off('design-resolution-changed', this.resizeTarget);
        this.release();
    }
    update(dt: number): void {
        if (this.disposed || !this.visible || !this.stage?.active) return;
        this.syncRenderTarget();
        if (this.paused) return;
        if (!Number.isFinite(dt) || dt < 0) throw new Error('大厅时间步无效');
        this.flames?.update(dt);
        if (!this.diagnosedMotion && this.animations.some(a => a.getState(IDLE).time > .25)) {
            this.diagnosedMotion = true; this.logPose('moving');
        }
    }
    togglePause(): boolean {
        if (this.disposed) return this.paused;
        this.paused = !this.paused; this.syncPause(); return this.paused;
    }
    setRenderQuality(scale: 1 | 2): void {
        if (scale !== 1 && scale !== 2) throw new Error('大厅画质倍率仅支持 1 或 2');
        this.renderQuality = scale;
        if (this.visible) this.syncRenderTarget();
    }
    private syncRenderTarget(): void {
        if (this.disposed || !this.camera || !this.frame) return;
        const transform = this.surface.node.getComponent(UITransform);
        if (!transform) throw new Error('大厅显示区域缺失');
        const rect = transform.getBoundingBoxToWorld();
        const pixels = view.getVisibleSizeInPixel(), logical = view.getVisibleSize();
        // getVisibleSizeInPixel already includes the canvas/device pixel scale.
        // Multiplying DPR again would over-allocate on Retina/Android devices.
        const displayWidth = rect.width * pixels.width / logical.width;
        const displayHeight = rect.height * pixels.height / logical.height;
        if (![displayWidth, displayHeight].every(Number.isFinite) || displayWidth <= 0 || displayHeight <= 0) return;
        const deviceLimit = director.root?.device.capabilities.maxTextureSize;
        if (!deviceLimit || deviceLimit < 16) throw new Error('GPU 渲染尺寸上限不可用');
        const maxEdge = Math.min(deviceLimit, 4096), maxPixels = 3840 * 2160;
        // Keep exact 16:9 projection. Cap at 4K pixels (~64 MiB RGBA8+D24S8;
        // replacement may transiently hold both targets), never unbounded SSAA.
        const wanted = Math.ceil(Math.max(displayWidth / 16, displayHeight / 9) * this.renderQuality);
        const units = Math.max(1, Math.min(wanted, Math.floor(maxEdge / 16), Math.floor(maxEdge / 9), Math.floor(Math.sqrt(maxPixels / 144))));
        const width = units * 16, height = units * 9;
        if (this.texture?.width === width && this.texture.height === height) return;
        const next = new RenderTexture();
        try {
            // resize() clamps to 2048 in this engine; reset() creates the bounded target.
            next.reset({ width, height });
            next.setFilters(RenderTexture.Filter.LINEAR, RenderTexture.Filter.LINEAR);
            next.setMipFilter(RenderTexture.Filter.NONE);
        } catch (error) { next.destroy(); throw error; }
        const previous = this.texture;
        this.camera.targetTexture = next;
        this.frame.texture = next; this.frame.flipUVX = true;
        // Force Sprite render data to reference the updated texture while retaining
        // the same Sprite and SpriteFrame objects used by the scene owner.
        this.surface.spriteFrame = null; this.surface.spriteFrame = this.frame;
        this.texture = next; previous?.destroy();
        console.info('[HCZS_HALL_RESOLUTION]', JSON.stringify({ display: [displayWidth, displayHeight],
            target: [width, height], quality: this.renderQuality, dpr: view.getDevicePixelRatio(),
            deviceLimit, capped: units < wanted, estimatedAttachmentBytes: width * height * 8 }));
    }
    setLighting(value: boolean): void {
        this.lightingEnabled = value;
        if (!this.disposed) this.lighting?.setEnabled(value);
    }
    setFlames(value: boolean): void {
        this.flamesEnabled = value;
        if (!this.disposed) this.flames?.setEnabled(value);
    }
    setView(view: HallView): void {
        if (['camera_1', 'camera_upstairs', 'camera_negative', 'close'].indexOf(view) < 0) throw new Error('大厅镜头无效');
        this.view = view;
        if (!this.camera || !this.data || this.disposed) return;
        const name = view === 'close' ? 'camera_1' : view;
        const rows = this.data.cameras.filter(row => row.Name === name);
        if (rows.length !== 1) throw new Error('原大厅镜头缺失或重名：' + name);
        const row = rows[0], camera = this.camera;
        this.transform(camera.node, row.Transform.split(',').map(Number));
        camera.node.setScale(1, 1, 1);
        camera.node.rotate(Quat.fromEuler(new Quat(), 0, 180, 0));
        const fov = Number(row.Fov), near = Number(row.Near), far = Number(row.Far);
        if (![fov, near, far].every(Number.isFinite) || fov <= 0 || fov >= 180 || near <= 0 || far <= near) throw new Error('大厅镜头投影参数无效');
        camera.fov = fov; camera.near = near; camera.far = far;
        if (view === 'close') {
            if (!this.closeCenter) throw new Error('大厅近景边界未准备');
            const forward = Vec3.transformQuat(new Vec3(), new Vec3(0, 0, -1), camera.node.worldRotation);
            camera.node.setWorldPosition(Vec3.scaleAndAdd(new Vec3(), this.closeCenter, forward, -60));
            camera.fov = 18;
        }
    }
    private syncPause(): void {
        for (const animation of this.animations) {
            if (this.paused || !this.visible) animation.pause(); else animation.resume();
        }
    }
    private json(path: string): Promise<JsonAsset> {
        return new Promise((resolve, reject) => resources.load(path, JsonAsset, (e, a) => e ? reject(e) : resolve(a)));
    }
    private async prefab(path: string): Promise<Prefab> {
        const entries = resources.getDirWithPath(path, Prefab);
        if (entries.length !== 1) throw new Error('大厅资源未导入或不唯一：' + path);
        return new Promise((resolve, reject) => resources.load(entries[0].path!, Prefab, (e, a) => e ? reject(e) : resolve(a)));
    }
    private transform(node: Node, values: number[]): void {
        if (values.length !== 16 || values.some(value => !Number.isFinite(value))) throw new Error('大厅矩阵无效');
        const rotation = new Quat(), position = new Vec3(), scale = new Vec3();
        Mat4.toRTS(Mat4.fromArray(new Mat4(), values), rotation, position, scale);
        node.setRTS(rotation, position, scale);
    }
    private layer(node: Node): void { node.layer = LAYER; node.children.forEach(child => this.layer(child)); }
    private prepareIdle(node: Node): void {
        const animations = node.getComponentsInChildren(SkeletalAnimation);
        if (animations.length !== 1 || !animations[0].clips.some(clip => clip?.name === IDLE)) throw new Error('大厅原待机缺失');
        const animation = animations[0];
        animation.playOnLoad = false; animation.useBakedAnimation = false;
        this.animations.push(animation);
    }
    private idle(animation: SkeletalAnimation): void {
        animation.play(IDLE);
        const state = animation.getState(IDLE);
        state.wrapMode = AnimationClip.WrapMode.Loop; state.time = 0; state.sample();
        animation.pause();
    }
    private logPose(phase: string): void {
        const bones: { name: string; position: number[] }[] = [];
        const visit = (node: Node): void => {
            if (node.name === 'shanzi_a_01' || node.name === 'shanzi_b_01') {
                const p = node.position; bones.push({ name: node.name, position: [p.x, p.y, p.z] });
            }
            node.children.forEach(visit);
        };
        if (this.diagnosticWeapon) visit(this.diagnosticWeapon);
        console.info('[HCZS_HALL_POSE]', JSON.stringify({ phase, bones, animations: this.animations.map(a => {
            const s = a.getState(IDLE);
            return { time: s.time, playing: s.isPlaying, paused: s.isPaused, weight: s.weight, baked: a.useBakedAnimation };
        }) }));
    }
    private waitForPose(): Promise<void> {
        // Legacy skeletal samples accumulate into a blend buffer. Wait for the
        // engine to apply it before reading the frame-zero world bounds.
        return new Promise(resolve => {
            const done = (): void => {
                director.off(Director.EVENT_AFTER_UPDATE, done);
                this.cancelPoseWait = null; resolve();
            };
            this.cancelPoseWait = done;
            director.once(Director.EVENT_AFTER_UPDATE, done);
        });
    }
    private captureCenter(placement: Node): Vec3 {
        const minimum = new Vec3(Infinity, Infinity, Infinity), maximum = new Vec3(-Infinity, -Infinity, -Infinity);
        // Match RenderScene.update's frame stamp. A constant zero can reuse the
        // joint cache's initial identity transform (-1 + 1 === 0) or stale stamp 0.
        const stamp = director.getTotalFrames();
        let count = 0;
        for (const renderer of placement.getComponentsInChildren(MeshRenderer)) {
            const model = renderer.model;
            if (!model) throw new Error('大厅角色渲染模型未建立');
            model.transform.updateWorldTransform();
            model.updateTransform(stamp);
            const bounds = model.worldBounds;
            if (!bounds) throw new Error('大厅角色模型边界缺失');
            const lo = Vec3.subtract(new Vec3(), bounds.center, bounds.halfExtents);
            const hi = Vec3.add(new Vec3(), bounds.center, bounds.halfExtents);
            Vec3.min(minimum, minimum, lo); Vec3.max(maximum, maximum, hi); count++;
        }
        if (!count || ![minimum.x, minimum.y, minimum.z, maximum.x, maximum.y, maximum.z].every(Number.isFinite)) throw new Error('大厅近景边界无效');
        const center = Vec3.multiplyScalar(new Vec3(), Vec3.add(new Vec3(), minimum, maximum), .5);
        console.info('[HCZS_HALL_BOUNDS]', JSON.stringify({ stamp, count,
            minimum: [minimum.x, minimum.y, minimum.z], maximum: [maximum.x, maximum.y, maximum.z],
            center: [center.x, center.y, center.z] }));
        return center;
    }
    private async load(): Promise<void> {
        const [environment, actor, weaponPrefab, data, lightingData] = await Promise.all([
            this.prefab('recovered/hall/scene'), this.prefab('recovered/hall/actor'), this.prefab('recovered/hall/weapon'),
            this.json('recovered/hall/scene-data'), this.json('recovered/hall/lighting'),
        ]);
        if (this.disposed) return;
        if (!data.json || !lightingData.json) throw new Error('大厅元数据缺失');
        this.data = data.json as HallData;
        this.prefabs = [environment, actor, weaponPrefab]; this.prefabs.forEach(p => p.addRef());
        const stage = this.stage = new Node('RecoveredHall'); stage.active = false; this.scene.addChild(stage);
        const world = instantiate(environment); stage.addChild(world);
        for (const name of this.data.hiddenNodes) {
            const matches: Node[] = [];
            const visit = (node: Node): void => { if (node.name === name) matches.push(node); node.children.forEach(visit); }; visit(world);
            if (matches.length !== 1) throw new Error('大厅隐藏标记不唯一：' + name);
            matches[0].active = false;
        }
        const placement = new Node('SourceShiranuiHallPlacement'); stage.addChild(placement);
        this.transform(placement, this.data.player.matrix);
        if (!Number.isFinite(this.data.player.scale) || this.data.player.scale <= 0) throw new Error('大厅角色缩放无效');
        placement.setScale(this.data.player.scale, this.data.player.scale, this.data.player.scale);
        const character = instantiate(actor), weapon = instantiate(weaponPrefab);
        placement.addChild(character); placement.addChild(weapon); this.layer(world); this.layer(placement);
        // Must precede component onLoad: initializing a baked SkeletalAnimationState
        // sets _doNotCreateEval. Changing the flag afterwards in 3.8.8 does not
        // clear that flag when setUseBaked(false) calls the base initializer.
        this.prepareIdle(character); this.prepareIdle(weapon); this.diagnosticWeapon = weapon;
        // Activate once to create animation/model components before capturing bounds; no FX included.
        stage.active = true; this.animations.forEach(animation => this.idle(animation));
        // Another view may be rendering on the shared city/hall layer while this
        // async load is hidden. Detach renderers during the one-frame pose wait;
        // MeshRenderer.onDisable retains its model, so bounds remain available.
        const primingRenderers = stage.getComponentsInChildren(MeshRenderer)
            .filter(renderer => renderer.enabled);
        primingRenderers.forEach(renderer => { renderer.enabled = false; });
        await this.waitForPose();
        if (this.disposed) return;
        this.logPose('frame-zero');
        this.closeCenter = this.captureCenter(placement);
        stage.active = false;
        primingRenderers.forEach(renderer => { renderer.enabled = true; });
        const cameraNode = new Node('SourceHallCamera'); stage.addChild(cameraNode);
        const camera = this.camera = cameraNode.addComponent(Camera); camera.visibility = LAYER;
        camera.clearFlags = Camera.ClearFlag.SOLID_COLOR; camera.clearColor = new Color(23, 25, 35, 255); camera.priority = -20;
        this.frame = new SpriteFrame(); this.syncRenderTarget(); this.setView(this.view);
        const baseMaterials = await installHallBaseMaterials(world, this.data.opaque);
        if (this.disposed) { baseMaterials.dispose(); return; }
        this.baseMaterials = baseMaterials;
        for (const [root, name] of [[character, 'actor'], [weapon, 'weapon']] as const) {
            const materials = await installHallCharacterBaseMaterials(root, this.data.characterMaterials[name]);
            if (this.disposed) { materials.dispose(); return; }
            this.characterMaterials.push(materials);
        }
        const lighting = await installHallLighting(world, lightingData.json as HallLightmapData);
        if (this.disposed) { lighting.dispose(); return; }
        this.lighting = lighting; lighting.setEnabled(this.lightingEnabled);
        const flames = await attachShiranuiFlames({ weaponRoot: weapon, layer: LAYER });
        if (this.disposed) { flames.dispose(); return; }
        this.flames = flames; flames.setEnabled(this.flamesEnabled);
        stage.active = this.visible; this.surface.node.active = this.visible; this.syncPause();
        console.info('[HCZS_HALL] loaded', JSON.stringify({ lighting: lighting.report, flames: flames.report }));
    }
    private release(): void {
        this.cancelPoseWait?.();
        this.flames?.dispose(); this.lighting?.dispose(); this.baseMaterials?.dispose();
        this.characterMaterials.forEach(materials => materials.dispose()); this.characterMaterials = [];
        this.flames = null; this.lighting = null; this.baseMaterials = null;
        this.animations.forEach(animation => animation.stop()); this.animations = [];
        if (this.camera) this.camera.targetTexture = null;
        if (this.surface.spriteFrame === this.frame) this.surface.spriteFrame = null;
        this.surface.node.active = false;
        this.stage?.destroy(); this.frame?.destroy(); this.texture?.destroy();
        this.prefabs.forEach(prefab => prefab.decRef()); this.prefabs = [];
        this.stage = null; this.camera = null; this.frame = null; this.texture = null; this.data = null; this.closeCenter = null;
        this.diagnosticWeapon = null; this.diagnosedMotion = false;
    }
}
