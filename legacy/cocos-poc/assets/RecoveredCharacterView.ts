import { AnimationClip, Camera, Color, instantiate, Node, Prefab, RenderTexture,
    resources, SkeletalAnimation, Sprite, SpriteFrame, Vec3 } from 'cc';

export interface RecoveredModelOptions {
    readonly folder: string; readonly name: string; readonly idle: string; readonly layer: number;
    readonly centerY: number; readonly distance: number; readonly orthoHeight: number;
    readonly width: number; readonly height: number; readonly initialYaw?: number;
}
const ELSA: RecoveredModelOptions = {
    folder: 'recovered/models/elsa', name: 'RecoveredElsa', idle: 'stand_idle', layer: 1 << 0,
    centerY: 8.1, distance: 35, orthoHeight: 9.4, width: 1116, height: 924,
};

/** A local, isolated 3D stage rendered into the character portrait area. */
export class RecoveredCharacterView {
    private stage: Node | null = null;
    private model: Node | null = null;
    private camera: Camera | null = null;
    private texture: RenderTexture | null = null;
    private frame: SpriteFrame | null = null;
    private prefab: Prefab | null = null;
    private animation: SkeletalAnimation | null = null;
    private loading: Promise<void> | null = null;
    private disposed = false;
    private visible = false;
    private paused = false;
    private angle = 0;

    constructor(private scene: Node, private surface: Sprite, private options: RecoveredModelOptions = ELSA) {
        surface.node.active = false;
    }

    async show(): Promise<void> {
        if (this.disposed) throw new Error('角色视图已关闭');
        this.visible = true;
        if (!this.loading) {
            this.loading = this.load().catch(error => {
                this.releaseStage();
                this.loading = null;
                throw error;
            });
        }
        await this.loading;
        if (this.disposed || !this.visible) return;
        this.stage!.active = true;
        this.surface.node.active = true;
        if (this.paused) this.animation!.pause();
        else this.animation!.resume();
    }

    hide(): void {
        this.visible = false;
        this.surface.node.active = false;
        this.animation?.pause();
        if (this.stage) this.stage.active = false;
    }

    togglePause(): boolean {
        if (!this.animation || !this.visible) return this.paused;
        this.paused = !this.paused;
        if (this.paused) this.animation.pause();
        else this.animation.resume();
        console.info(`[HCZS_MODEL] paused=${this.paused}`);
        return this.paused;
    }

    rotate(): void {
        if (!this.model || !this.visible) return;
        this.angle = (this.angle + 45) % 360;
        this.model.setRotationFromEuler(0, this.angle, 0);
        console.info(`[HCZS_MODEL] yaw=${this.angle}`);
    }

    destroy(): void {
        this.disposed = true;
        this.visible = false;
        this.releaseStage();
    }

    private async load(): Promise<void> {
        // Enumerate the imported prefab subasset; glTF main assets are not Prefab.
        const entries = resources.getDirWithPath(this.options.folder, Prefab);
        if (entries.length !== 1) throw new Error('角色模型资源尚未准备好');
        const prefab = await new Promise<Prefab>((resolve, reject) => {
            resources.load(entries[0].path!, Prefab, (error, asset) => error ? reject(error) : resolve(asset));
        });
        if (this.disposed) return;
        prefab.addRef();
        this.prefab = prefab;
        const stage = this.stage = new Node(this.options.name + 'Stage');
        stage.active = false;
        this.scene.addChild(stage);
        this.model = instantiate(prefab);
        stage.addChild(this.model);
        this.angle = this.options.initialYaw ?? 0;
        this.model.setRotationFromEuler(0, this.angle, 0);
        const layer = (node: Node): void => {
            node.layer = this.options.layer;
            for (const child of node.children) layer(child);
        };
        layer(this.model);
        const animations = this.model.getComponentsInChildren(SkeletalAnimation);
        if (animations.length !== 1) throw new Error('角色骨骼动画载入失败');
        this.animation = animations[0];
        this.animation.playOnLoad = false;
        this.animation.useBakedAnimation = false;

        const cameraNode = new Node(this.options.name + 'Camera');
        stage.addChild(cameraNode);
        cameraNode.setPosition(0, this.options.centerY, this.options.distance);
        cameraNode.lookAt(new Vec3(0, this.options.centerY, 0));
        const camera = this.camera = cameraNode.addComponent(Camera);
        camera.visibility = this.options.layer;
        camera.projection = Camera.ProjectionType.ORTHO;
        camera.orthoHeight = this.options.orthoHeight;
        camera.near = 0.1;
        camera.far = 80;
        camera.clearFlags = Camera.ClearFlag.SOLID_COLOR;
        camera.clearColor = new Color(15, 29, 39, 255);
        camera.priority = -10;
        this.texture = new RenderTexture();
        this.texture.reset({ name: this.options.name + 'View', width: this.options.width, height: this.options.height });
        camera.targetTexture = this.texture;
        this.frame = new SpriteFrame();
        this.frame.texture = this.texture;
        this.surface.spriteFrame = this.frame;

        // Activating once runs onLoad and creates imported animation states.
        stage.active = true;
        const clip = this.animation.clips.find(item => item?.name === this.options.idle);
        if (!clip) throw new Error('角色待机动作尚未准备好');
        const state = this.animation.getState(clip.name);
        if (!state) throw new Error('无法创建角色动作');
        state.wrapMode = AnimationClip.WrapMode.Loop;
        this.animation.play(clip.name);
        if (!this.visible) this.hide();
        console.info(`[HCZS_MODEL] asset-ready; model=${this.options.name}; clip=${clip.name}; duration=${clip.duration}`);
    }

    private releaseStage(): void {
        if (this.camera) this.camera.targetTexture = null;
        this.surface.spriteFrame = null;
        this.surface.node.active = false;
        this.stage?.destroy();
        this.frame?.destroy();
        this.texture?.destroy();
        this.prefab?.decRef();
        this.stage = this.model = null;
        this.camera = null;
        this.animation = null;
        this.texture = null;
        this.frame = null;
        this.prefab = null;
    }
}
