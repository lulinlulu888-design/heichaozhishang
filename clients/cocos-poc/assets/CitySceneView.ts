import { Animation, AnimationClip, Camera, Color, EffectAsset, instantiate, JsonAsset, Mat4, Material,
    MeshRenderer, Node, Prefab, Quat, RenderTexture, resources, SkeletalAnimation, Sprite,
    SpriteFrame, Texture2D, Vec3, Vec4 } from 'cc';

/** Original environment; optional statically derived PVE placement preview. */
export class CitySceneView {
    private stage: Node | null = null;
    private camera: Camera | null = null;
    private texture: RenderTexture | null = null;
    private frame: SpriteFrame | null = null;
    private prefabs: Prefab[] = [];
    private materials: Material[] = [];
    private disposed = false;
    private visible = false;
    private loading: Promise<void> | null = null;
    private playerPlacement: Node | null = null;
    private playerSlots: {position: number[]; rotation_radians: number[]; base_scale: number[]}[] = [];
    private slot = 1;
    private enemyAnimation: SkeletalAnimation | null = null;
    private battleActors: {player: Node; enemy: Node; playerAnimation: SkeletalAnimation; enemyAnimation: SkeletalAnimation} | null = null;
    getBattleActors(): NonNullable<CitySceneView['battleActors']> {
        if (!this.battleActors) throw new Error('城市角色尚未加载');
        return this.battleActors;
    }
    private enemyActions: Record<string, { name: string; clips: string[] }> = {};
    private cancelAction: (() => void) | null = null;
    constructor(private scene: Node, private surface: Sprite, private name: string, private formation = false) {}
    setPlayerSlot(slot: number): void {
        if (!Number.isInteger(slot) || slot < 0 || slot > 2) throw new Error('队伍槽位无效');
        this.slot = slot;
        if (this.playerPlacement && this.playerSlots.length) this.placeActor(this.playerPlacement, this.playerSlots[slot]);
    }
    private placeActor(node: Node, row: {position: number[]; rotation_radians: number[]; base_scale: number[]}): void {
        const values = [...row.position, ...row.rotation_radians, ...row.base_scale];
        if (values.length !== 9 || values.some(v => !Number.isFinite(v))) throw new Error('战斗变换无效');
        node.setPosition(...row.position as [number, number, number]);
        node.setRotationFromEuler(...row.rotation_radians.map(v => v * 180 / Math.PI) as [number, number, number]);
        node.setScale(...row.base_scale as [number, number, number]);
    }
    async show(): Promise<void> {
        this.visible = true;
        if (!this.loading) this.loading = this.load().catch(e => { this.release(); this.loading = null; throw e; });
        await this.loading;
        if (!this.disposed && this.stage) this.stage.active = this.visible;
    }
    hide(): void { this.visible = false; this.cancelAction?.(); if (this.stage) this.stage.active = false; }
    destroy(): void { this.disposed = true; this.release(); }
    /** Animation-only source mapping; no damage, event timing or SFX inferred. */
    async playEnemySkill(skillId: string): Promise<void> {
        await this.loading;
        const animation = this.enemyAnimation, action = this.enemyActions[skillId];
        if (!this.visible || this.disposed) return;
        if (!animation || !action || !action.clips.length) throw new Error('城市技能动画未恢复');
        if (action.clips.some(name => !animation.clips.some(c => c?.name === name))) throw new Error('城市技能动画缺失');
        this.cancelAction?.();
        await new Promise<void>(resolve => {
            let index = 0, ended = false;
            const finish = (): void => {
                if (ended) return;
                ended = true; animation.off(Animation.EventType.FINISHED, next); this.cancelAction = null;
                animation.getState('idle').wrapMode = AnimationClip.WrapMode.Loop; animation.play('idle'); resolve();
            };
            const next = (): void => {
                if (index === action.clips.length) { finish(); return; }
                const clip = action.clips[index++];
                animation.getState(clip).wrapMode = AnimationClip.WrapMode.Normal; animation.play(clip);
                console.info('[HCZS_CITY_ACTION]', skillId, clip);
            };
            this.cancelAction = finish; animation.on(Animation.EventType.FINISHED, next); next();
        });
    }
    private async prefab(path: string): Promise<Prefab> {
        const entries = resources.getDirWithPath(path, Prefab);
        if (entries.length !== 1) throw new Error('城市资源未导入：' + path);
        return new Promise((resolve, reject) => resources.load(entries[0].path!, Prefab,
            (e, a) => e ? reject(e) : resolve(a)));
    }
    private json(path: string): Promise<JsonAsset> {
        return new Promise((resolve, reject) => resources.load(path, JsonAsset, (e, a) => e ? reject(e) : resolve(a)));
    }
    private transform(node: Node, values: number[]): void {
        if (values.length !== 16 || values.some(v => !Number.isFinite(v))) throw new Error('城市矩阵无效');
        const rotation = new Quat(), position = new Vec3(), scale = new Vec3();
        Mat4.toRTS(Mat4.fromArray(new Mat4(), values), rotation, position, scale);
        node.setRTS(rotation, position, scale);
    }
    private async load(): Promise<void> {
        const base = 'recovered/city/' + this.name;
        const [environment, actor, weapon, data, binding, effect, opaqueEffect] = await Promise.all([
            this.prefab(base + '/scene'), this.prefab('recovered/prologue/actor'),
            this.prefab('recovered/prologue/weapon'), this.json(base + '/scene-data'),
            this.json('recovered/prologue/weapon-binding'),
            new Promise<EffectAsset>((resolve, reject) => resources.load('recovered/city/cloud', EffectAsset,
                (e, a) => e ? reject(e) : resolve(a))),
            new Promise<EffectAsset>((resolve, reject) => resources.load('recovered/city/opaque', EffectAsset,
                (e, a) => e ? reject(e) : resolve(a))),
        ]);
        if (this.disposed) return;
        if (!data.json || !binding.json) throw new Error('城市元数据缺失');
        this.prefabs = [environment, actor, weapon]; this.prefabs.forEach(p => p.addRef());
        const stage = this.stage = new Node('RecoveredCity_' + this.name);
        stage.active = false; this.scene.addChild(stage);
        const world = instantiate(environment); stage.addChild(world);
        for (const row of data.json.opaque) {
            const nodes: Node[] = [];
            const visit = (n: Node): void => { if (n.name === row.node) nodes.push(n); n.children.forEach(visit); }; visit(world);
            if (nodes.length !== 1) throw new Error('不透明场景节点不唯一');
            const renderers = nodes[0].getComponentsInChildren(MeshRenderer);
            if (renderers.length !== 1) throw new Error('不透明场景网格不唯一');
            const texture = renderers[0].getSharedMaterial(row.slot)?.getProperty('mainTexture');
            if (!(texture instanceof Texture2D)) throw new Error('城市颜色贴图缺失');
            const material = new Material(); this.materials.push(material);
            material.initialize({ effectAsset: opaqueEffect }); material.setProperty('mainTexture', texture);
            renderers[0].setSharedMaterial(material, row.slot);
        }
        for (const row of data.json.clouds) {
            const nodes: Node[] = [];
            const visit = (n: Node): void => { if (n.name === row.node) nodes.push(n); n.children.forEach(visit); }; visit(world);
            if (nodes.length !== 1) throw new Error('云层节点不唯一');
            const renderers = nodes[0].getComponentsInChildren(MeshRenderer);
            if (renderers.length !== 1) throw new Error('云层网格不唯一');
            const textures = await Promise.all(['mainTexture', 'noiseTexture', 'maskTexture'].map(key =>
                new Promise<Texture2D>((resolve, reject) => resources.load(row.textures[key] + '/texture', Texture2D,
                    (e, a) => e ? reject(e) : resolve(a)))));
            if (this.disposed) return;
            const material = new Material(); this.materials.push(material); material.initialize({ effectAsset: effect });
            ['mainTexture', 'noiseTexture', 'maskTexture'].forEach((key, i) => material.setProperty(key, textures[i]));
            const p = row.parameters;
            const nums = (key: string): number[] => p[key].split(',').map(Number);
            const vec = (a: number[]): Vec4 => new Vec4(a[0], a[1], a[2], a[3]);
            material.setProperty('tint', vec(nums('g_colFloatingColor1')));
            material.setProperty('flow', vec([...nums('g_vFloatingTiling1'), ...nums('g_vFloatingSpeed1')]));
            material.setProperty('distortionFlow', vec([...nums('g_vDistortionTiling'), ...nums('g_vDistortionSpeed')]));
            material.setProperty('strengths', new Vec4(Number(p.g_fDistortionStrength), Number(p.g_AlphaMaskStrength), 0, 0));
            renderers[0].setSharedMaterial(material, row.slot);
        }
        const animations: SkeletalAnimation[] = [];
        let enemyAnimation: SkeletalAnimation | null = null;
        let enemyNode: Node | null = null;
        let actorRows = data.json.actors;
        if (this.formation) {
            if (this.name !== 'city_battle_2') throw new Error('战斗站位与场景不匹配');
            const [formation, enemyPrefab] = await Promise.all([
                this.json('recovered/city/formation-10405'), this.prefab('recovered/prologue/enemy')]);
            if (this.disposed) return;
            const f = formation.json;
            if (!f || f.encounter !== 10405 || f.players.length !== 3) throw new Error('战斗站位数据缺失');
            this.playerSlots = f.players;
            this.enemyActions = f.actions;
            actorRows = [{path: 'character/player/ailisha/ailisha.gim', sourceInstance: {UUID: 'BattleSlot'}}];
            enemyPrefab.addRef(); this.prefabs.push(enemyPrefab);
            const enemy = instantiate(enemyPrefab); world.addChild(enemy);
            enemyNode = enemy;
            this.placeActor(enemy, {...f.enemy, base_scale: f.enemy.entity_base_scale});
            const list = enemy.getComponentsInChildren(SkeletalAnimation);
            if (list.length !== 1 || !list[0].clips.some(c => c?.name === 'idle')) throw new Error('城市敌人待机缺失');
            enemyAnimation = list[0]; enemyAnimation.playOnLoad = false; enemyAnimation.useBakedAnimation = false;
            this.enemyAnimation = enemyAnimation;
        }
        const b = binding.json;
        if (!b.all_vertices_single_joint_unit_weight || b.used_bones?.length !== 1) throw new Error('武器绑定无效');
        for (const row of actorRows) {
            if (row.path !== 'character/player/ailisha/ailisha.gim') continue;
            const placement = new Node('SourceElsa_' + row.sourceInstance.UUID); world.addChild(placement);
            if (this.formation) {
                this.playerPlacement = placement; this.setPlayerSlot(this.slot);
            } else this.transform(placement, row.matrix);
            const character = instantiate(actor); placement.addChild(character);
            const list = character.getComponentsInChildren(SkeletalAnimation);
            if (list.length !== 1 || !list[0].clips.some(c => c?.name === 'idle_1')) throw new Error('城市角色待机缺失');
            list[0].playOnLoad = false; list[0].useBakedAnimation = false; animations.push(list[0]);
            if (this.formation && enemyNode && enemyAnimation) this.battleActors = {
                player: character, enemy: enemyNode, playerAnimation: list[0], enemyAnimation };
            const bones: Node[] = [];
            const visit = (n: Node): void => { if (n.name === b.used_bones[0].name) bones.push(n); n.children.forEach(visit); }; visit(character);
            if (bones.length !== 1) throw new Error('城市角色武器骨骼缺失');
            const matrix = Mat4.fromArray(new Mat4(), b.used_bones[0].source_bind); Mat4.invert(matrix, matrix);
            const values: number[] = []; Mat4.toArray(values, matrix);
            const attachment = new Node('WeaponInverseBind'); bones[0].addChild(attachment);
            this.transform(attachment, values); attachment.addChild(instantiate(weapon));
        }
        const layer = (n: Node): void => { n.layer = 1 << 3; n.children.forEach(layer); }; layer(world);
        const cameraNode = new Node('SourceCityCamera'); stage.addChild(cameraNode);
        const row = data.json.cameras[0];
        this.transform(cameraNode, row.Transform.split(',').map(Number)); cameraNode.setScale(1, 1, 1);
        cameraNode.rotate(Quat.fromEuler(new Quat(), 0, 180, 0));
        const camera = this.camera = cameraNode.addComponent(Camera); camera.visibility = 1 << 3;
        camera.fov = Number(row.Fov); camera.near = Number(row.Near); camera.far = Number(row.Far);
        camera.clearFlags = Camera.ClearFlag.SOLID_COLOR; camera.clearColor = new Color(98, 116, 144, 255); camera.priority = -20;
        this.texture = new RenderTexture(); this.texture.reset({ width: 1280, height: 720 }); camera.targetTexture = this.texture;
        this.frame = new SpriteFrame(); this.frame.texture = this.texture;
        // Y180 adapts forward Z but also reverses source camera X. Correct the
        // rendered projection as a whole; source geometry and actor poses stay intact.
        // Historical gameplay supplied by the user confirms allies left/enemies right.
        this.frame.flipUVX = true; this.surface.spriteFrame = this.frame;
        stage.active = true;
        for (const animation of animations) {
            animation.getState('idle_1').wrapMode = AnimationClip.WrapMode.Loop; animation.play('idle_1');
        }
        if (enemyAnimation) {
            enemyAnimation.getState('idle').wrapMode = AnimationClip.WrapMode.Loop; enemyAnimation.play('idle');
        }
        stage.active = this.visible;
        console.info('[HCZS_CITY] loaded', this.name, 'actors=' + animations.length);
    }
    private release(): void {
        this.cancelAction?.(); this.enemyAnimation = null; this.enemyActions = {};
        this.battleActors = null;
        if (this.camera) this.camera.targetTexture = null;
        this.surface.spriteFrame = null; this.stage?.destroy(); this.frame?.destroy(); this.texture?.destroy();
        this.prefabs.forEach(p => p.decRef()); this.materials.forEach(m => m.destroy());
        this.prefabs = []; this.materials = []; this.stage = null; this.camera = null; this.frame = null; this.texture = null;
        this.playerPlacement = null; this.playerSlots = [];
    }
}
