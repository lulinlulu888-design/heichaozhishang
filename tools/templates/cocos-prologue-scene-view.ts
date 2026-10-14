import { Animation, AnimationClip, Camera, Color, instantiate, JsonAsset, Mat4, Node, Prefab,
    Quat, RenderTexture, resources, SkeletalAnimation, Sprite, SpriteFrame, Vec3, Material } from 'cc';
import { applyPrologueLighting } from './PrologueLighting';
import { BattleAudio } from './BattleAudio';
import { CitySceneView } from './CitySceneView';

/** Original scene geometry in the shared engine. Lighting/effects still pending. */
export class PrologueSceneView {
    private stage: Node | null = null;
    private camera: Camera | null = null;
    private texture: RenderTexture | null = null;
    private frame: SpriteFrame | null = null;
    private prefabs: Prefab[] = [];
    private disposed = false;
    private loading: Promise<void> | null = null;
    private visible = false;
    private materials: Material[] = [];
    private character: Node | null = null;
    private enemy: Node | null = null;
    private actorAnimations: SkeletalAnimation[] = [];
    private playerAnimation: SkeletalAnimation | null = null;
    private enemyAnimation: SkeletalAnimation | null = null;
    private cancelAttack: (() => void) | null = null;
    private cancelReaction: (() => void) | null = null;
    private reaction: Promise<void> = Promise.resolve();
    private enemyDead = false;
    private playerDead = false;
    private presentationPending = false;
    private audio: BattleAudio | null = null;
    private cityView: CitySceneView | null = null;
    private get playerIdle(): string { return this.battle ? 'idle_1' : 'stand_idle'; }
    private outcome: 'playing' | 'won' | 'defeated' | 'limit' = 'playing';
    constructor(private scene: Node, private surface: Sprite, private battle = false, private city = false) {}

    async show(): Promise<void> {
        this.visible = true;
        if (!this.loading) this.loading = this.load().catch(e => { this.release(); this.loading = null; throw e; });
        await this.loading;
        if (!this.disposed && this.stage) this.stage.active = this.visible;
        if (!this.disposed && this.cityView && this.visible) await this.cityView.show();
    }
    hide(): void { this.visible = false; this.cancelAttack?.(); this.cancelReaction?.(); this.audio?.stop(); this.cityView?.hide(); if (this.stage) this.stage.active = false; }
    destroy(): void { this.disposed = true; this.release(); }
    setOutcome(outcome: 'playing' | 'won' | 'defeated' | 'limit', presentationPending = this.presentationPending): void {
        this.outcome = outcome;
        this.presentationPending = presentationPending;
        if (presentationPending || this.cancelAttack || this.cancelReaction) return;
        if (outcome === 'playing' && this.enemyDead) {
            this.enemyDead = false;
            this.enemyAnimation?.play('idle');
        }
        if (outcome === 'playing' && this.playerDead) {
            this.playerDead = false;
            this.playerAnimation?.play(this.playerIdle);
        }
        // Reconstruct a terminal save from its outcome without replaying damage or
        // death events. Active action queues must finish before this pose is applied.
        if (outcome === 'won' && !this.enemyDead)
            this.enemyDead = this.restoreDeathPose(this.enemyAnimation);
        if (outcome === 'defeated' && !this.playerDead)
            this.playerDead = this.restoreDeathPose(this.playerAnimation);
        if (this.enemy) this.enemy.active = true;
        if (this.character) this.character.active = true;
        for (const animation of this.actorAnimations) {
            if (outcome === 'playing') animation.resume();
            else animation.pause();
        }
    }
    private restoreDeathPose(animation: SkeletalAnimation | null): boolean {
        if (!animation || !animation.clips.some(c => c?.name === 'death')) return false;
        const state = animation.getState('death');
        state.wrapMode = AnimationClip.WrapMode.Normal;
        animation.play('death');
        state.setTime(state.duration);
        state.sample();
        animation.pause();
        console.info('[HCZS_REACTION] restored terminal death pose');
        return true;
    }
    /** Source poses; local presentation scheduling, not full original effects/focus. */
    async playCard(cardId: string, onHit?: () => void): Promise<void> {
        const sequences: Record<string, string[]> = {
            '110001': ['fire_1'], '110009': ['crit_1'], '210003': ['fire_1'],
            '410101': ['fire_1_1', 'fire_1_3'], '410102': ['fire_1'],
        };
        const sequence = sequences[cardId];
        if (!sequence || !this.battle || !this.visible || this.disposed) return;
        await this.loading;
        await this.playSequence(this.playerAnimation, sequence, this.playerIdle, cardId, onHit);
        await this.reaction;
    }
    playEnemyReaction(lethal: boolean): void {
        this.playReaction('enemy', lethal);
    }
    playPlayerReaction(lethal: boolean): void {
        this.playReaction('player', lethal);
    }
    private playReaction(side: 'player' | 'enemy', lethal: boolean): void {
        const player = side === 'player';
        const animation = player ? this.playerAnimation : this.enemyAnimation;
        if (!animation || !this.visible || this.disposed || (player ? this.playerDead : this.enemyDead)) return;
        const clip = lethal ? 'death' : player ? 'hit_2' : 'hit_1';
        const idle = player ? this.playerIdle : 'idle';
        if (!animation.clips.some(c => c?.name === clip)) throw new Error('原受击动画缺失');
        this.cancelReaction?.();
        this.reaction = new Promise<void>(resolve => {
            let ended = false;
            let cancelSound: (() => void) | null = null;
            const finish = (completed: boolean): void => {
                if (ended) return;
                ended = true;
                cancelSound?.();
                if (!completed) this.audio?.stop();
                animation.off(Animation.EventType.FINISHED, onFinished);
                this.cancelReaction = null;
                const dead = lethal && completed;
                if (player) this.playerDead = dead; else this.enemyDead = dead;
                if (dead) {
                    const state = animation.getState(clip);
                    state.setTime(state.duration); state.sample(); animation.pause();
                } else {
                    animation.getState(idle).wrapMode = AnimationClip.WrapMode.Loop;
                    animation.play(idle);
                }
                this.setOutcome(this.outcome);
                resolve();
            };
            const onFinished = (): void => finish(true);
            this.cancelReaction = () => finish(false);
            const target = player ? this.character : this.enemy;
            if (target) target.active = true;
            animation.getState(clip).wrapMode = AnimationClip.WrapMode.Normal;
            animation.on(Animation.EventType.FINISHED, onFinished);
            animation.play(clip);
            if (player) cancelSound = this.audio?.schedule(animation, clip) ?? null;
            console.info('[HCZS_REACTION] source clip', side, clip);
        });
    }
    async playEnemySkill(skillId: string, onHit?: () => void): Promise<void> {
        // Source timelines 558/559/560 and entity 6605 map these three skills.
        const clips: Record<string, string> = this.city
            ? { '66051': 'fire', '66052': 'fire', '66053': 'skill_3', '66054': 'skill_2' }
            : { '990': 'fire', '991': 'skill_2', '992': 'skill_3' };
        const clip = clips[skillId];
        if (!clip || !this.battle || !this.visible || this.disposed) return;
        await this.loading;
        await this.playSequence(this.enemyAnimation, [clip], 'idle', 'enemy:' + skillId);
        // Enemy hit timing is unresolved; this is an explicit end-of-action fallback.
        if (this.visible && !this.disposed) onHit?.();
        await this.reaction;
    }
    private async playSequence(animation: SkeletalAnimation | null, sequence: string[], idle: string, identity: string, onHit?: () => void): Promise<void> {
        if (!animation || !this.visible || this.disposed) return;
        if (sequence.some(name => !animation.clips.some(c => c?.name === name))) throw new Error('原攻击动画缺失');
        this.cancelAttack?.();
        await new Promise<void>(resolve => {
            let index = 0, ended = false;
            let hitCallback: (() => void) | null = null;
            let cancelSound: (() => void) | null = null;
            const finish = (): void => {
                if (ended) return;
                ended = true;
                cancelSound?.();
                if (hitCallback) animation.unschedule(hitCallback);
                animation.off(Animation.EventType.FINISHED, next);
                this.cancelAttack = null;
                animation.getState(idle).wrapMode = AnimationClip.WrapMode.Loop;
                animation.play(idle);
                this.setOutcome(this.outcome);
                resolve();
            };
            const next = (): void => {
                if (index === sequence.length) { finish(); return; }
                const name = sequence[index++];
                animation.getState(name).wrapMode = AnimationClip.WrapMode.Normal;
                animation.play(name);
                cancelSound?.();
                cancelSound = animation === this.playerAnimation ? this.audio?.schedule(animation, name) ?? null : null;
                // Authored Elsa AGS TimeRatio; ratio*clip.duration is a derived
                // presentation time, not yet validated against native timing.
                const ratios: Record<string, number> = { fire_1: .230700, crit_1: .281831,
                    fire_1_1: .350154, fire_1_3: .409156 };
                if (hitCallback) animation.unschedule(hitCallback);
                hitCallback = null;
                if (onHit && ratios[name] !== undefined) {
                    hitCallback = () => { if (!ended && this.visible && !this.disposed) onHit(); };
                    animation.scheduleOnce(hitCallback, animation.getState(name).duration * ratios[name]);
                }
                console.info('[HCZS_ATTACK] source clip', identity, name);
            };
            this.cancelAttack = () => { this.audio?.stop(); finish(); };
            // Restore a just-defeated target until this committed action finishes visually.
            if (this.enemy) this.enemy.active = true;
            if (this.character) this.character.active = true;
            animation.on(Animation.EventType.FINISHED, next);
            next();
        });
    }
    private async prefab(folder: string): Promise<Prefab> {
        const entries = resources.getDirWithPath(`recovered/prologue/${folder}`, Prefab);
        if (entries.length !== 1) throw new Error('序章资源未导入：' + folder);
        return new Promise((resolve, reject) => resources.load(entries[0].path!, Prefab,
            (e, p) => e ? reject(e) : resolve(p)));
    }
    private async load(): Promise<void> {
        if (this.city) {
            const city = this.cityView = new CitySceneView(this.scene, this.surface, 'city_battle_2', true);
            await city.show();
            if (this.disposed) return;
            const actors = city.getBattleActors();
            this.character = actors.player; this.enemy = actors.enemy;
            this.playerAnimation = actors.playerAnimation; this.enemyAnimation = actors.enemyAnimation;
            this.actorAnimations = [actors.playerAnimation, actors.enemyAnimation];
            this.audio = new BattleAudio(this.scene); await this.audio.load();
            if (this.disposed) return;
            this.setOutcome(this.outcome);
            if (!this.visible) city.hide();
            return;
        }
        if (this.battle) {
            this.audio = new BattleAudio(this.scene);
            await this.audio.load();
            if (this.disposed) return;
        }
        const [environment, actor, cameraAsset] = await Promise.all([
            this.prefab('scene'), this.prefab('actor'),
            new Promise<JsonAsset>((resolve, reject) => resources.load('recovered/prologue/cameras', JsonAsset,
                (e, a) => e ? reject(e) : resolve(a))),
        ]);
        if (this.disposed) return;
        environment.addRef(); actor.addRef(); this.prefabs = [environment, actor];
        const stage = this.stage = new Node('OriginalPrologue');
        stage.active = false; this.scene.addChild(stage);
        const world = instantiate(environment); stage.addChild(world);
        const materials = await applyPrologueLighting(world);
        if (this.disposed) { materials.forEach(m => m.destroy()); return; }
        this.materials = materials;
        const actors: Node[] = [];
        const visit = (n: Node): void => { if (n.name === 'ailisha_1565') actors.push(n); n.children.forEach(visit); };
        visit(world);
        if (actors.length !== 1) throw new Error('原场景人物节点不唯一');
        const source = actors[0], character = instantiate(actor);
        this.character = character;
        // Configure while the stage is inactive. Activating it first initializes baked
        // states; Creator 3.8.8 does not recreate their evaluator on this mode switch.
        const animations = character.getComponentsInChildren(SkeletalAnimation);
        if (animations.length !== 1) throw new Error('序章动画组件不唯一');
        const animation = animations[0]; animation.playOnLoad = false; animation.useBakedAnimation = false;
        this.playerAnimation = animation;
        source.parent!.addChild(character);
        character.setPosition(source.position); character.setRotation(source.rotation); character.setScale(source.scale);
        source.active = false;
        if (this.battle) {
            const orientation = await new Promise<JsonAsset>((resolve, reject) =>
                resources.load('recovered/prologue/player-orientation', JsonAsset,
                    (e, a) => e ? reject(e) : resolve(a)));
            if (this.disposed) return;
            if (!orientation.json) throw new Error('原战斗玩家朝向数据缺失');
            const radians = orientation.json.rotationEulerRadians;
            if (orientation.json.entityId !== 0 || !Array.isArray(radians) ||
                radians.length !== 3 || radians.some((v: unknown) => typeof v !== 'number' || !Number.isFinite(v)))
                throw new Error('原战斗玩家朝向数据无效');
            // BattlePlayerEntity overwrites the scene rotation with EntityData.ROTATION.
            // Original scene 2081 places enemies toward negative X. This local
            // prologue formation places them at positive X, so adapt facing by
            // 180 degrees. This is a reconstruction offset, not source rotOffset.
            character.setRotationFromEuler(radians[0] * 180 / Math.PI,
                radians[1] * 180 / Math.PI + 180, radians[2] * 180 / Math.PI);
            const [weaponPrefab, bindingAsset] = await Promise.all([
                this.prefab('weapon'),
                new Promise<JsonAsset>((resolve, reject) => resources.load('recovered/prologue/weapon-binding', JsonAsset,
                    (e, asset) => e ? reject(e) : resolve(asset))),
            ]);
            if (this.disposed) return;
            const binding = bindingAsset.json;
            if (!binding || !binding.all_vertices_single_joint_unit_weight || binding.used_bones?.length !== 1)
                throw new Error('武器骨骼数据不匹配');
            const row = binding.used_bones[0], bones: Node[] = [];
            const findBone = (node: Node): void => { if (node.name === row.name) bones.push(node); node.children.forEach(findBone); };
            findBone(character);
            if (bones.length !== 1 || !Array.isArray(row.source_bind) || row.source_bind.length !== 16)
                throw new Error('武器挂点缺失');
            // Reconstructed rigid attachment: all source vertices have weight 1
            // on prop1. Preserve the weapon's inverse bind, not the actor's.
            // Native BindType/auxiliary bounds semantics remain unresolved.
            const inverse = Mat4.fromArray(new Mat4(), row.source_bind);
            Mat4.invert(inverse, inverse);
            const rotation = new Quat(), position = new Vec3(), scale = new Vec3();
            Mat4.toRTS(inverse, rotation, position, scale);
            const attachment = new Node('RecoveredWeaponInverseBind');
            attachment.setRTS(rotation, position, scale); bones[0].addChild(attachment);
            weaponPrefab.addRef(); this.prefabs.push(weaponPrefab);
            attachment.addChild(instantiate(weaponPrefab));
        }
        const setLayer = (n: Node): void => { n.layer = 1 << 2; n.children.forEach(setLayer); }; setLayer(world);
        const cameraNode = new Node('OriginalPrologueCamera'); stage.addChild(cameraNode);
        if (!Array.isArray(cameraAsset.json) || !cameraAsset.json[1]) throw new Error('原镜头数据缺失');
        const row = cameraAsset.json[1];
        const matrix = Mat4.fromArray(new Mat4(), row.Transform.split(',').map(Number));
        const rotation = new Quat(), position = new Vec3(); Mat4.toRTS(matrix, rotation, position, null);
        Quat.multiply(rotation, rotation, Quat.fromEuler(new Quat(), 0, 180, 0));
        cameraNode.setPosition(position); cameraNode.setRotation(rotation);
        const camera = this.camera = cameraNode.addComponent(Camera);
        camera.visibility = 1 << 2; camera.fov = Number(row.Fov);
        camera.near = Number(row.Near); camera.far = Number(row.Far);
        if (this.battle) {
            // Reconstructed local battle framing; not an original scripted camera/placement.
            cameraNode.setPosition(source.position.x + 14, source.position.y + 25, source.position.z + 62);
            cameraNode.lookAt(new Vec3(source.position.x + 14, source.position.y + 8, source.position.z));
            camera.fov = 42; camera.near = .1;
            const prefab = await this.prefab('enemy');
            if (this.disposed) return;
            prefab.addRef(); this.prefabs.push(prefab);
            const enemy = instantiate(prefab); world.addChild(enemy);
            this.enemy = enemy;
            enemy.setPosition(source.position.x + 29, source.position.y, source.position.z);
            setLayer(enemy);
            const animations = enemy.getComponentsInChildren(SkeletalAnimation);
            if (animations.length !== 1) throw new Error('敌人动画缺失');
            const animation = animations[0]; animation.playOnLoad = false; animation.useBakedAnimation = false;
            this.enemyAnimation = animation;
            stage.active = true;
            const clip = animation.clips.find(c => c?.name === 'idle');
            if (!clip) throw new Error('敌人待机缺失');
            animation.getState(clip.name).wrapMode = AnimationClip.WrapMode.Loop; animation.play(clip.name);
            // Sample before a terminal save can pause this newly loaded actor.
            if (this.outcome !== 'won') animation.getState(clip.name).sample();
            this.actorAnimations.push(animation);
        }
        camera.clearFlags = Camera.ClearFlag.SOLID_COLOR; camera.clearColor = new Color(21, 22, 27, 255);
        camera.priority = -20;
        this.texture = new RenderTexture(); this.texture.reset({ width: 1280, height: 720 });
        camera.targetTexture = this.texture;
        this.frame = new SpriteFrame(); this.frame.texture = this.texture; this.surface.spriteFrame = this.frame;
        stage.active = true;
        const clip = animation.clips.find(c => c?.name === this.playerIdle);
        if (!clip) throw new Error('序章待机动画缺失');
        animation.getState(clip.name).wrapMode = AnimationClip.WrapMode.Loop; animation.play(clip.name);
        // Sample before a terminal save can pause this newly loaded actor.
        if (this.outcome !== 'defeated') animation.getState(clip.name).sample();
        this.actorAnimations.push(animation);
        this.setOutcome(this.outcome);
        stage.active = this.visible;
        console.info('[HCZS_PROLOGUE] scene and original actor loaded; camera=' + (this.battle ? 'reconstructed battle' : 'source 2'));
    }
    private release(): void {
        this.audio?.destroy(); this.audio = null;
        this.cancelAttack?.();
        this.cancelReaction?.();
        this.cityView?.destroy(); this.cityView = null;
        this.enemyDead = false;
        this.playerDead = false;
        if (this.camera) this.camera.targetTexture = null;
        this.surface.spriteFrame = null; this.stage?.destroy(); this.frame?.destroy(); this.texture?.destroy();
        this.prefabs.forEach(p => p.decRef()); this.prefabs = [];
        this.materials.forEach(m => m.destroy()); this.materials = [];
        this.stage = null; this.camera = null; this.frame = null; this.texture = null;
        this.character = null; this.enemy = null; this.actorAnimations = [];
        this.playerAnimation = null; this.enemyAnimation = null;
    }
}
