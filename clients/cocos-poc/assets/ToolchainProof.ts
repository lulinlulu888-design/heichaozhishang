import { _decorator, BlockInputEvents, Color, Component, Graphics, Label, Layers, Node, profiler,
    ResolutionPolicy, resources, Sprite, SpriteFrame, UITransform, view } from 'cc';
import { RecoveredCharacterView } from './RecoveredCharacterView';
import { BattleRequestError, TutorialBattleController } from './TutorialBattleController';
import { TutorialBattleView } from './TutorialBattleView';
import { PrologueSceneView } from './PrologueSceneView';
import { CitySceneView } from './CitySceneView';

const { ccclass } = _decorator;
// Browser query selects the initial service. The menu also works in native builds.
// All endpoints remain loopback; device transport setup is separate.
function localApiBase(): string {
    const search = typeof location === 'undefined' ? '' : location.search;
    const match = /(?:^\?|&)apiPort=([0-9]{1,5})(?:&|$)/.exec(search);
    const requested = match ? Number(match[1]) : 7458;
    const port = requested >= 1 && requested <= 65535 ? requested : 7458;
    return `http://127.0.0.1:${port}/api/rebuild/v1`;
}
const C = {
    background: new Color(12, 23, 33), panel: new Color(20, 37, 49), border: new Color(46, 69, 79),
    ink: new Color(237, 238, 229), muted: new Color(144, 168, 177), mint: new Color(109, 214, 199),
    gold: new Color(222, 189, 127), error: new Color(244, 145, 145), selected: new Color(36, 76, 80),
};
type Character = { id: number; name: string; englishName: string; portraitPath: string };
type Card = { id: number; name: string; cost: number; level: number; story: string };
type Catalog = { contentId: string; characters: Character[]; cards: Card[] };
type Profile = { id: string; displayName: string; selectedCharacterId: number | null; revision: number };
type Action = { node: Node; label: Label; background: Graphics };

/** Recovered catalog and local reconstruction tutorial; no legacy account login. */
@ccclass('ToolchainProof')
export class ToolchainProof extends Component {
    private api = localApiBase();
    private catalog: Catalog | null = null;
    private profile: Profile | null = null;
    private selectedId: number | null = null;
    private busy = false;
    private portraitRequest = 0;
    private count = 0;
    private portrait!: Sprite;
    private characterName!: Label;
    private englishName!: Label;
    private status!: Label;
    private profileLabel!: Label;
    private connection!: Label;
    private cardsRoot!: Node;
    private charactersRoot!: Node;
    private saveAction!: Action;
    private characterActions = new Map<number, Action>();
    private modelView!: RecoveredCharacterView;
    private modelViews = new Map<number, RecoveredCharacterView>();
    private appearanceRequest = 0;
    private appearance: 'portrait' | 'model' = 'portrait';
    private pauseAction!: Action;
    private tutorialController!: TutorialBattleController;
    private tutorialView!: TutorialBattleView;
    private tutorialOpen = false;
    private prologueView!: PrologueSceneView;
    private cityViews: CitySceneView[] = [];

    start(): void {
        view.setDesignResolutionSize(1280, 720, ResolutionPolicy.SHOW_ALL);
        profiler.hideStats();
        this.panel(this.node, 0, 0, 1280, 720, C.background, C.background, 0);
        this.panel(this.node, -331, -14, 582, 505, new Color(15, 29, 39), C.border, 18);
        this.text(this.node, '黑潮之上', -332, 303, 570, 46, 34, C.ink);
        this.text(this.node, '重逢之时  /  本地重建', -332, 264, 570, 28, 16, C.muted);
        this.connection = this.text(this.node, '正在连接本地服务…', 320, 300, 560, 34, 17, C.muted);
        this.text(this.node, '角色图鉴', 320, 231, 558, 32, 20, C.ink);
        this.text(this.node, '卡牌图鉴 · 恢复样本', 320, 119, 558, 30, 18, C.ink);
        this.charactersRoot = this.createNode(this.node, 'Characters');
        this.cardsRoot = this.createNode(this.node, 'Cards');
        const portraitNode = this.createNode(this.node, 'CharacterPortrait', -331, 10, 558, 462);
        this.portrait = portraitNode.addComponent(Sprite);
        this.portrait.sizeMode = Sprite.SizeMode.CUSTOM;
        this.portrait.trim = true;
        const modelNode = this.createNode(this.node, 'CharacterModel', -331, 10, 558, 462);
        const modelSurface = modelNode.addComponent(Sprite);
        modelSurface.sizeMode = Sprite.SizeMode.CUSTOM;
        this.modelView = new RecoveredCharacterView(this.node.scene, modelSurface);
        this.modelViews.set(1, this.modelView);
        const lynnSurface = this.createNode(this.node, 'LynnModel', -331, 10, 558, 462).addComponent(Sprite);
        lynnSurface.sizeMode = Sprite.SizeMode.CUSTOM;
        this.modelViews.set(2, new RecoveredCharacterView(this.node.scene, lynnSurface, {
            folder: 'recovered/models/lynn', name: 'RecoveredLynn', idle: 'idle_1', layer: 1 << 0,
            centerY: 7, distance: 35, orthoHeight: 8, width: 1116, height: 924, initialYaw: 90,
        }));
        this.button(this.node, '立绘', -541, -240, 112, 34, () => this.showPortrait());
        this.button(this.node, '模型', -401, -240, 112, 34, () => void this.showModel());
        this.pauseAction = this.button(this.node, '暂停动作', -261, -240, 112, 34, () => {
            if (this.appearance === 'model') this.pauseAction.label.string = this.modelView.togglePause() ? '继续动作' : '暂停动作';
        });
        this.button(this.node, '转向', -121, -240, 112, 34, () => this.modelView.rotate());
        this.characterName = this.text(this.node, '等待角色资料', -331, -289, 570, 42, 30, C.ink);
        this.englishName = this.text(this.node, '', -331, -325, 570, 24, 14, C.muted);
        this.panel(this.node, 320, -245, 558, 110, C.panel, C.border, 12);
        this.profileLabel = this.text(this.node, '本地档案尚未载入', 320, -211, 524, 26, 15, C.muted);
        this.saveAction = this.button(this.node, '创建并保存', 179, -250, 240, 40, () => void this.save());
        this.button(this.node, '重新读取', 463, -250, 240, 40, () => void this.reload());
        this.status = this.text(this.node, '正在读取角色与卡牌资料…', 320, -287, 524, 26, 14, C.muted);
        this.button(this.node, '进入战斗', 320, -330, 558, 34, () => void this.openTutorial());
        this.createBattleClient();
        [ ['序章', 7458], ['分解试炼', 7459], ['城市试战', 7460] ].forEach(([name, port], index) => {
            this.button(this.node, String(name), 130 + index * 190, 264, 178, 28,
                () => void this.switchService(Number(port)));
        });
        const prologueRoot = this.createNode(this.node, 'PrologueOverlay', 0, 0, 1280, 720);
        const prologueSurface = this.createNode(prologueRoot, 'SceneSurface', 0, 0, 1280, 720).addComponent(Sprite);
        prologueSurface.sizeMode = Sprite.SizeMode.CUSTOM;
        this.prologueView = new PrologueSceneView(this.node.scene, prologueSurface);
        this.text(prologueRoot, '序章场景 · 光照与特效接入中', -350, 320, 530, 36, 22, C.ink);
        this.button(prologueRoot, '返回', 540, 320, 120, 40, () => {
            prologueRoot.active = false; this.prologueView.hide();
        });
        prologueRoot.active = false;
        this.button(this.node, '查看序章场景', -130, 305, 160, 36, () => {
            prologueRoot.setSiblingIndex(this.node.children.length - 1);
            prologueRoot.active = true;
            void this.prologueView.show().catch(error => {
                prologueRoot.active = false; this.feedback(String(error), C.error);
                console.error('[HCZS_PROLOGUE] load-failed', String(error));
            });
        });
        const cityRoot = this.createNode(this.node, 'CityOverlay', 0, 0, 1280, 720);
        cityRoot.addComponent(BlockInputEvents);
        this.panel(cityRoot, 0, 0, 1280, 720, C.background, C.background, 0);
        const citySurfaces: Node[] = [];
        for (let i = 0; i < 3; i++) {
            const node = this.createNode(cityRoot, 'CitySurface' + i, 0, 0, 1280, 720);
            const sprite = node.addComponent(Sprite); sprite.sizeMode = Sprite.SizeMode.CUSTOM;
            citySurfaces.push(node);
            this.cityViews.push(new CitySceneView(this.node.scene, sprite, 'city_battle_' + (i === 2 ? 2 : i + 1), i === 2));
        }
        const cityTitle = this.text(cityRoot, '城市景观', -340, 320, 530, 36, 22, C.ink);
        let cityRequest = 0;
        let cityIndex = -1;
        const showCity = (index: number): void => {
            const token = ++cityRequest;
            cityIndex = index;
            this.cityViews.forEach(v => v.hide()); citySurfaces.forEach(n => n.active = false);
            cityTitle.string = '正在加载城市…';
            void this.cityViews[index].show().then(() => {
                if (token !== cityRequest) return;
                citySurfaces[index].active = true;
                cityTitle.string = index === 2 ? '城市对阵 · 站位预览' : '城市景观 · ' + (index + 1);
            }).catch(error => {
                if (token === cityRequest) cityTitle.string = '城市加载失败';
                console.error('[HCZS_CITY] load-failed', String(error));
            });
        };
        this.button(cityRoot, '城市一', 270, 320, 100, 40, () => showCity(0));
        this.button(cityRoot, '城市二', 385, 320, 100, 40, () => showCity(1));
        this.button(cityRoot, '城市对阵', 130, 320, 140, 40, () => showCity(2));
        for (let slot = 0; slot < 3; slot++) {
            this.button(cityRoot, '站位 ' + (slot + 1), -130 + slot * 130, -320, 110, 40, () => {
                this.cityViews[2].setPlayerSlot(slot); showCity(2);
            });
        }
        let cityAction = 0;
        ['鞭笞', '痛击', '防御', '分解视线'].forEach((name, i) => {
            this.button(cityRoot, name, -205 + i * 140, -265, 130, 40, () => {
                if (cityIndex !== 2) return;
                const token = ++cityAction, request = cityRequest;
                cityTitle.string = '动作预览 · ' + name;
                void this.cityViews[2].playEnemySkill(String(66051 + i)).then(() => {
                    if (token === cityAction && request === cityRequest) cityTitle.string = '城市对阵 · 站位预览';
                }).catch(error => {
                    if (token === cityAction && request === cityRequest) cityTitle.string = '动作加载失败';
                    console.error('[HCZS_CITY_ACTION]', String(error));
                });
            });
        });
        this.button(cityRoot, '返回', 540, 320, 120, 40, () => {
            ++cityRequest; cityRoot.active = false; this.cityViews.forEach(v => v.hide());
        });
        cityRoot.active = false;
        this.button(this.node, '城市景观', -130, 264, 160, 36, () => {
            cityRoot.setSiblingIndex(this.node.children.length - 1); cityRoot.active = true; showCity(0);
        });
        console.info('[HCZS_POC] scene-ready; Creator=3.8.8');
        void this.reload();
    }

    private createBattleClient(): void {
        const endpoint = this.api;
        this.tutorialController = new TutorialBattleController(
            (method, path, body) => this.request<unknown>(method, path, body, endpoint),
            state => { if (this.isValid) this.tutorialView?.render(state); },
        );
        this.tutorialView = new TutorialBattleView(this.node, this.tutorialController, () => {
            this.tutorialView.hide();
            this.tutorialOpen = false;
        });
        this.tutorialView.render(this.tutorialController.snapshot);
    }

    private async switchService(port: number): Promise<void> {
        if (this.busy || this.tutorialOpen) return;
        const state = this.tutorialController.snapshot;
        if (state.pending || state.canRetry || state.phase === 'uncertain') {
            this.feedback('请先进入当前战斗，核对未确认的操作后再切换', C.gold);
            return;
        }
        const endpoint = `http://127.0.0.1:${port}/api/rebuild/v1`;
        if (endpoint === this.api) { await this.reload(); return; }
        this.tutorialController.dispose();
        this.tutorialView.destroy();
        this.api = endpoint;
        this.profile = null;
        this.catalog = null;
        this.selectedId = null;
        for (const root of [this.charactersRoot, this.cardsRoot]) {
            for (const child of [...root.children]) child.destroy();
        }
        this.characterActions.clear();
        this.updateProfile();
        this.connection.string = '正在切换试玩…';
        this.createBattleClient();
        await this.reload();
    }

    private async reload(): Promise<void> {
        if (this.busy) return;
        this.busy = true;
        this.feedback('正在读取本地档案…', C.muted);
        try {
            const [catalog, saved] = await Promise.all([
                this.request<Catalog>('GET', '/catalog'),
                this.request<{ profiles: Profile[] }>('GET', '/profiles'),
            ]);
            if (!this.isValid) return;
            if (!catalog.characters?.length || !Array.isArray(catalog.cards) || !Array.isArray(saved.profiles)) {
                throw new Error('本地资料格式不正确');
            }
            this.catalog = catalog;
            this.profile = saved.profiles[0] ?? null;
            this.drawCatalog();
            const recovered = catalog.characters.find(item => item.id === this.profile?.selectedCharacterId);
            this.selectCharacter((recovered ?? catalog.characters[0]).id, false);
            this.connection.string = (this.api.indexOf(':7460/') >= 0 ? '城市试战' : this.api.indexOf(':7459/') >= 0 ? '分解试炼' : '序章') + ' · 已连接';
            this.connection.color = C.mint;
            this.updateProfile();
            this.feedback(recovered ? `已恢复保存的角色：${recovered.name}` : '浏览角色后，点击下方按钮保存选择', C.mint);
            console.info(`[HCZS_POC] catalog-ready; characters=${catalog.characters.length}; cards=${catalog.cards.length}`);
            console.info(`[HCZS_POC] profile-loaded; revision=${this.profile?.revision ?? 0}; selected=${this.profile?.selectedCharacterId ?? 'none'}`);
        } catch (error) {
            if (this.isValid) {
                this.connection.string = '本地服务未连接';
                this.connection.color = C.error;
                this.feedback(`${String(error).replace(/^Error: /, '')}；可点击重新读取`, C.error);
            }
            console.error('[HCZS_POC] load-failed', String(error));
        } finally {
            this.busy = false;
        }
    }

    private drawCatalog(): void {
        for (const root of [this.charactersRoot, this.cardsRoot]) {
            for (const child of [...root.children]) {
                child.removeFromParent();
                child.destroy();
            }
        }
        this.characterActions.clear();
        this.catalog!.characters.forEach((character, index) => {
            const action = this.button(this.charactersRoot, character.name, 130 + index * 190, 178, 178, 54,
                () => { if (!this.busy) this.selectCharacter(character.id, true); });
            this.characterActions.set(character.id, action);
        });
        this.catalog!.cards.forEach((card, index) => {
            const x = index % 2 ? 465 : 176;
            const y = 39 - Math.floor(index / 2) * 128;
            const cardNode = this.createNode(this.cardsRoot, `Card-${card.id}`, x, y, 270, 114);
            this.panel(cardNode, 0, 0, 270, 114, C.panel, C.border, 10);
            this.text(cardNode, card.name, -27, 34, 184, 27, 20, C.ink);
            this.text(cardNode, `消耗 ${card.cost}`, 95, 34, 58, 26, 14, C.gold);
            this.text(cardNode, `等级 ${card.level}`, 0, 7, 238, 20, 12, C.muted);
            this.text(cardNode, card.story, 0, -28, 238, 47, 14, C.muted);
        });
    }

    private selectCharacter(id: number, userAction: boolean): void {
        const character = this.catalog?.characters.find(item => item.id === id);
        if (!character) return;
        this.selectedId = id;
        this.showPortrait();
        this.characterName.string = character.name;
        this.englishName.string = character.englishName;
        for (const [characterId, action] of this.characterActions) {
            this.drawPanel(action.background, 178, 54, characterId === id ? C.selected : C.panel,
                characterId === id ? C.mint : C.border, 8);
            action.label.color = characterId === id ? C.mint : C.ink;
        }
        const request = ++this.portraitRequest;
        this.portrait.spriteFrame = null;
        resources.load(`recovered/characters/${id}/spriteFrame`, SpriteFrame, (error, frame) => {
            if (!this.isValid || request !== this.portraitRequest) return;
            if (error) {
                this.feedback('此角色立绘载入失败，请检查本地资源', C.error);
                console.error(`[HCZS_POC] portrait-load-failed; character=${id}`, error);
                return;
            }
            this.portrait.spriteFrame = frame;
            // Fit the trimmed artwork uniformly; filling the panel stretches tall portraits.
            const { width, height } = frame.rect;
            const scale = Math.min(558 / width, 462 / height);
            this.portrait.getComponent(UITransform)!.setContentSize(width * scale, height * scale);
            console.info(`[HCZS_POC] portrait-ready; character=${id}`);
        });
        if (userAction) {
            this.count += 1;
            this.feedback(this.profile?.selectedCharacterId === id ? `已选择 ${character.name} · 与保存一致` : `已选择 ${character.name} · 尚未保存`, C.gold);
            console.info(`[HCZS_POC] interaction=${this.count}; character=${id}`);
        }
    }

    private showPortrait(): void {
        this.appearanceRequest += 1;
        this.appearance = 'portrait';
        this.modelView.hide();
        this.portrait.node.active = true;
    }

    private async showModel(): Promise<void> {
        const selectedView = this.modelViews.get(this.selectedId ?? -1);
        if (!selectedView) {
            this.feedback('该角色模型尚未恢复', C.muted);
            return;
        }
        this.modelView.hide();
        this.modelView = selectedView;
        const name = this.catalog?.characters.find(item => item.id === this.selectedId)?.name ?? '';
        const request = ++this.appearanceRequest;
        this.feedback(`正在载入${name}模型…`, C.muted);
        try {
            await this.modelView.show();
            if (!this.isValid || request !== this.appearanceRequest) return;
            this.appearance = 'model';
            this.portrait.node.active = false;
            this.feedback(`${name} · 原待机动作`, C.mint);
        } catch (error) {
            if (!this.isValid || request !== this.appearanceRequest) return;
            this.showPortrait();
            this.feedback('模型载入未完成，请稍后重试', C.error);
            console.error('[HCZS_MODEL] load-failed', String(error));
        }
    }

    onDestroy(): void {
        this.appearanceRequest += 1;
        this.tutorialController?.dispose();
        this.tutorialView?.destroy();
        for (const model of this.modelViews.values()) model.destroy();
        this.prologueView?.destroy();
        this.cityViews.forEach(v => v.destroy());
    }

    private async openTutorial(): Promise<void> {
        if (this.busy || this.tutorialOpen) return;
        this.busy = true;
        this.feedback('正在读取战斗…', C.muted);
        try {
            const status = await this.request<{ capabilities: string[] }>('GET', '/status');
            if (!status.capabilities || status.capabilities.indexOf('tutorial-battles') < 0) {
                throw new Error('当前服务尚未开放首战，请启动包含教程的新版本地服务');
            }
            if (!this.isValid) return;
            if (!this.profile) {
                // Read before creating so a prior lost profile-create response
                // can be recovered instead of blindly creating another profile.
                const saved = await this.request<{ profiles: Profile[] }>('GET', '/profiles');
                if (!this.isValid) return;
                this.profile = saved.profiles[0] ?? null;
                if (!this.profile) {
                    this.profile = (await this.request<{ profile: Profile }>('POST', '/profiles', { displayName: '本地旅人' })).profile;
                }
            }
            if (!this.isValid) return;
            this.updateProfile();
            this.showPortrait();
            this.tutorialOpen = true;
            this.tutorialView.show();
            await this.tutorialController.open(this.profile.id);
        } catch (error) {
            if (this.isValid) this.feedback(error instanceof Error ? error.message : String(error), C.error);
            console.error('[HCZS_BATTLE] open-failed', String(error));
        } finally { this.busy = false; }
    }

    private async save(): Promise<void> {
        if (this.busy || !this.catalog || this.selectedId === null) return;
        if (this.profile?.selectedCharacterId === this.selectedId) {
            this.feedback('当前选择已保存，无需重复保存', C.mint);
            return;
        }
        this.busy = true;
        this.feedback('正在保存…', C.muted);
        try {
            if (!this.profile) {
                const created = await this.request<{ profile: Profile }>('POST', '/profiles', { displayName: '本地旅人' });
                if (!this.isValid) return;
                this.profile = created.profile;
                this.updateProfile();
            }
            const result = await this.request<{ profile: Profile }>('PATCH', `/profiles/${this.profile.id}`, {
                expectedRevision: this.profile.revision, selectedCharacterId: this.selectedId,
            });
            if (!this.isValid) return;
            this.profile = result.profile;
            this.updateProfile();
            const name = this.catalog.characters.find(item => item.id === this.profile!.selectedCharacterId)!.name;
            this.feedback(`已保存：${name} · 下次打开将恢复`, C.mint);
            console.info(`[HCZS_POC] profile-saved; revision=${this.profile.revision}; selected=${this.profile.selectedCharacterId}`);
        } catch (error) {
            if (this.isValid) this.feedback(String(error).replace(/^Error: /, ''), C.error);
            console.error('[HCZS_POC] save-failed', String(error));
        } finally {
            this.busy = false;
        }
    }

    private updateProfile(): void {
        this.profileLabel.string = this.profile ? `本地档案 · ${this.profile.displayName}` : '尚未创建档案 · 选择只用于预览';
        this.saveAction.label.string = this.profile ? '保存角色选择' : '创建并保存';
    }

    private request<T>(method: string, path: string, body?: object, endpoint = this.api): Promise<T> {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open(method, endpoint + path, true);
            xhr.timeout = 7000;
            xhr.onload = () => {
                let data: any;
                try { data = JSON.parse(xhr.responseText); } catch { reject(new BattleRequestError(502, 'INVALID_RESPONSE', '本地服务返回了无效资料')); return; }
                if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
                else reject(new BattleRequestError(xhr.status, data?.error?.code ?? 'HTTP_ERROR',
                    data?.error?.code === 'REVISION_CONFLICT' ? '存档已在另一窗口更新，正在核对最新状态'
                        : `操作未完成（${xhr.status}）：${data?.error?.message ?? '请重新读取后重试'}`));
            };
            xhr.onerror = () => reject(new BattleRequestError(0, 'NETWORK_ERROR', '无法连接本地服务'));
            xhr.ontimeout = () => reject(new BattleRequestError(0, 'TIMEOUT', '本地服务响应超时'));
            if (body) xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(body ? JSON.stringify(body) : null);
        });
    }

    private feedback(message: string, color: Color): void { this.status.string = message; this.status.color = color; }

    private createNode(parent: Node, name: string, x = 0, y = 0, width = 1, height = 1): Node {
        const node = new Node(name);
        node.layer = Layers.Enum.UI_2D;
        parent.addChild(node);
        node.setPosition(x, y, 0);
        node.addComponent(UITransform).setContentSize(width, height);
        return node;
    }

    private text(parent: Node, text: string, x: number, y: number, width: number, height: number, size: number, color: Color): Label {
        const node = this.createNode(parent, 'Label', x, y, width, height);
        const label = node.addComponent(Label);
        label.string = text;
        label.fontFamily = 'Microsoft YaHei';
        label.fontSize = size;
        label.lineHeight = size + 5;
        label.color = color;
        label.horizontalAlign = Label.HorizontalAlign.LEFT;
        label.verticalAlign = Label.VerticalAlign.CENTER;
        label.overflow = Label.Overflow.SHRINK;
        label.enableWrapText = true;
        return label;
    }

    private panel(parent: Node, x: number, y: number, width: number, height: number, fill: Color, stroke: Color, radius: number): Graphics {
        const graphics = this.createNode(parent, 'Panel', x, y, width, height).addComponent(Graphics);
        this.drawPanel(graphics, width, height, fill, stroke, radius);
        return graphics;
    }

    private drawPanel(graphics: Graphics, width: number, height: number, fill: Color, stroke: Color, radius: number): void {
        graphics.clear();
        graphics.fillColor = fill;
        graphics.strokeColor = stroke;
        graphics.lineWidth = 1;
        graphics.roundRect(-width / 2, -height / 2, width, height, radius);
        graphics.fill();
        graphics.stroke();
    }

    private button(parent: Node, text: string, x: number, y: number, width: number, height: number, callback: () => void): Action {
        const node = this.createNode(parent, text, x, y, width, height);
        const background = node.addComponent(Graphics);
        this.drawPanel(background, width, height, C.panel, C.border, 8);
        const label = this.text(node, text, 0, 0, width - 14, height, 17, C.ink);
        label.horizontalAlign = Label.HorizontalAlign.CENTER;
        node.on(Node.EventType.TOUCH_END, callback);
        return { node, label, background };
    }
}
