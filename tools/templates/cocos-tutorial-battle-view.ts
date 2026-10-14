import { BitmapFont, BlockInputEvents, Color, EventTouch, Graphics, Label, Layers, Node,
    resources, Sprite, SpriteFrame, UITransform, Vec3 } from 'cc';
import { TutorialBattleController } from './TutorialBattleController';
import { PrologueSceneView } from './PrologueSceneView';
import { TargetArrowView } from './TargetArrowView';
import { EndTurnView } from './EndTurnView';
import { CardSelectionView } from './CardSelectionView';
import { VictoryTitleView } from './VictoryTitleView';
import { BattleAudio } from './BattleAudio';
import { actionSegments, beforeEnemyAction } from './EnemyTurnPresentation';
import type { BattleViewState } from './TutorialBattleController';

type Battle = NonNullable<BattleViewState['battle']>;
type Effect = Battle['scenario']['definition']['cards'][string]['effects'][number];
type Event = BattleViewState['events'][number];
type Health = Battle['state']['player']['hp'];
type HealthEvent = Extract<Event, { type: 'DamageApplied' | 'ShieldAdded' | 'ShieldCleared' | 'HealthRestored' }>;
type Action = { node: Node; label: Label; background: Graphics; enabled: boolean;
    pressedId: number | null; width: number; height: number; sourceCard?: boolean; sourceControl?: boolean };
type CardSlot = { action: Action; art: Sprite; cost: Label; description: Label; hint: Label; instanceId: string | null };
const C = {
    background: new Color(12, 23, 33), panel: new Color(20, 37, 49), border: new Color(46, 69, 79),
    ink: new Color(237, 238, 229), muted: new Color(144, 168, 177), mint: new Color(109, 214, 199),
    gold: new Color(222, 189, 127), error: new Color(244, 145, 145), selected: new Color(36, 76, 80),
    disabled: new Color(24, 33, 41), disabledInk: new Color(104, 124, 136),
};

/** Presentation only: all authoritative actions and retry identity live in the controller. */
export class TutorialBattleView {
    private root: Node;
    private visible = false;
    private disposed = false;
    private generation = 0;
    private heading: Label;
    private notice: Label;
    private sceneView: PrologueSceneView;
    private sceneSurface: Sprite;
    private cityBattle = false;
    private playerStats: Label;
    private playerName: Label;
    private enemyName: Label;
    private headerArt: Record<'player' | 'enemy', Sprite[]> = { player: [], enemy: [] };
    private playerShield: Label;
    private playerShieldIcon: Sprite;
    private enemyStats: Label;
    private enemyShield: Label;
    private enemyShieldIcon: Sprite;
    private breakdownIcons: Record<'player' | 'enemy', Sprite>;
    private breakdownLabels: Record<'player' | 'enemy', Label>;
    private breakdownDisplay: Record<'player' | 'enemy', number> | null = null;
    private round: Label;
    private energy: Label;
    private intent: Label;
    private result: Label;
    private message: Label;
    private eventLog: Label;
    private pileCounts: Label;
    private pilePanel: Node;
    private pileTab = 0;
    private pileByCharacter = false;
    private pileModeAction: Action;
    private pilePage = 0;
    private pileBattle: Battle | null = null;
    private pileEmpty: Label;
    private pilePageLabel: Label;
    private pilePrevious: Action;
    private pileNext: Action;
    private pileTabs: Action[] = [];
    private pileHighlights: Node[] = [];
    private pileCards: { node: Node; art: Sprite; name: Label; cost: Label; description: Label; cardId: string | null }[] = [];
    private pileDetail: Node;
    private detailCardId: string | null = null;
    private detailArt: Sprite;
    private detailName: Label;
    private detailCost: Label;
    private detailEffects: Label;
    private actions: Action[] = [];
    private slots: CardSlot[] = [];
    private cardArt = new Map<string, SpriteFrame>();
    private uiFrames: SpriteFrame[] = [];
    private costFont: BitmapFont | null = null;
    private dragTarget: Node;
    private targetArrow: TargetArrowView;
    private cardSelection: CardSelectionView;
    private gesture: { pointer: number; instanceId: string; battleId: string; revision: number;
        startX: number; startY: number; arrowX: number; arrowY: number; name: string; detail: string } | null = null;
    private playerHpBar: Sprite;
    private enemyHpBar: Sprite;
    private presentationBusy = false;
    private presentationActor: 'player' | 'enemy' | null = null;
    private lastReceivedBattle: Battle | null = null;
    private enemyPresentation: Battle | null = null;
    private healthDisplay: Partial<Record<'player' | 'enemy', { hp: Health; shield: Health }>> | null = null;
    private lastBattleId: string | null = null;
    private lastRevision = 0;
    private endAction: Action;
    private endTurnView: EndTurnView;
    private refreshAction: Action;
    private retryAction: Action;
    private startAction: Action;
    private victoryPanel: Node;
    private victorySummary: Label;
    private victoryTitle: VictoryTitleView;
    private resultAudio: BattleAudio;
    private voicedVictory: string | null = null;

    constructor(parent: Node, private controller: TutorialBattleController, private onClose: () => void) {
        this.root = this.node(parent, 'TutorialBattleOverlay', 0, 0, 1280, 720);
        this.root.active = false;
        // An opaque full-canvas hit target blocks the catalog, including spaces between controls.
        this.root.addComponent(BlockInputEvents);
        this.paint(this.root.addComponent(Graphics), 1280, 720, C.background, C.background, 0);
        const surface = this.node(this.root, 'BattleScene', 0, 0, 1280, 720).addComponent(Sprite);
        surface.sizeMode = Sprite.SizeMode.CUSTOM;
        this.sceneSurface = surface;
        this.sceneView = new PrologueSceneView(parent.scene, surface, true);
        this.heading = this.text(this.root, '序章首战', -380, 326, 470, 32, 24, C.ink);
        this.notice = this.text(this.root, '', 0, 0, 1, 1, 1, C.muted);
        this.notice.node.active = false;
        // Source sprite art, with temporary reconstructed screen placement.
        // Local single-player preview chooses posIndex=0. The original slot
        // order is left_3,left_2,left_1; original server posIndex is unresolved.
        const playerHeaderX = [460, 290, 120][0] - 640;
        const playerArtStart = this.root.children.length;
        this.skin('head-back', playerHeaderX, 314, 154, 92);
        // PlayerHeadArea uses BattleIcon 212x124 at .75 scale, flipped X.
        this.skin('player-head', playerHeaderX + 1, 314.5, 159, 93).node.setScale(-1, 1);
        const playerHeadOverlay = this.skin('head-back', playerHeaderX - 1, 314, 154, 92);
        playerHeadOverlay.color = new Color(255, 255, 255, 51);
        this.skin('head-front', playerHeaderX, 302, 154, 68);
        this.skin('player-hp-bg', playerHeaderX, 274, 154, 18);
        this.headerArt.player = this.root.children.slice(playerArtStart).map(node => node.getComponent(Sprite)!).filter(Boolean);
        // Monster 991 is Elite (difficulty_type=1), not Boss (2).
        // Single enemy uses right_2: 1280-290. Panel anchor (.5,1),
        // size 180x140 and child (90,84) give a local origin at (0,-56).
        // hp_bg (0,-30) therefore maps to centered-canvas (350,274).
        // MonsterHeadArea HeadIconNode: original layer order, bottom anchors,
        // flipped background panels and half-scale 180x180 MonsterHead image.
        const enemyArtStart = this.root.children.length;
        this.skin('head-back', 350, 314, 154, 92).node.setScale(-1, 1);
        this.skin('monster-head', 382, 313, 90, 90);
        const headOverlay = this.skin('head-back', 349, 314, 154, 92);
        headOverlay.node.setScale(-1, 1);
        headOverlay.color = new Color(255, 255, 255, 51);
        this.skin('head-front', 350, 302, 154, 68).node.setScale(-1, 1);
        this.skin('monster-hp-bg', 350, 274, 154, 18);
        this.headerArt.enemy = this.root.children.slice(enemyArtStart).map(node => node.getComponent(Sprite)!).filter(Boolean);
        this.playerHpBar = this.skin('player-hp', playerHeaderX, 274, 154, 18, true);
        this.enemyHpBar = this.skin('monster-hp', 350, 274, 154, 18, true);
        this.playerName = this.text(this.root, '艾尔莎', playerHeaderX, 293, 148, 22, 18, C.mint);
        this.enemyName = this.text(this.root, '幻眼魔方', 350, 293, 148, 22, 18, C.gold);
        this.enemyName.horizontalAlign = Label.HorizontalAlign.RIGHT;
        this.playerStats = this.text(this.root, '', playerHeaderX, 274, 154, 20, 16, C.ink);
        this.playerStats.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.playerShieldIcon = this.skin('shield-icon', playerHeaderX - 66, 258, 32, 32);
        this.playerShield = this.text(this.root, '', playerHeaderX - 18, 258, 56, 20, 16, C.ink);
        this.enemyStats = this.text(this.root, '', 350, 274, 154, 20, 16, C.ink);
        this.enemyStats.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.enemyShieldIcon = this.skin('shield-icon', 420, 258, 32, 32);
        // Numeric supplement until the original shield capacity mapping is recovered.
        this.enemyShield = this.text(this.root, '', 375, 258, 52, 20, 16, C.ink);
        this.enemyShield.horizontalAlign = Label.HorizontalAlign.RIGHT;
        this.breakdownIcons = { player: this.skin('breakdown-icon', -102, 244, 32, 32),
            enemy: this.skin('breakdown-icon', 449, 274, 32, 32) };
        this.breakdownLabels = { player: this.text(this.root, '', -77, 244, 32, 24, 18, C.gold),
            enemy: this.text(this.root, '', 475, 274, 32, 24, 18, C.gold) };
        for (const side of ['player', 'enemy'] as const) {
            this.breakdownIcons[side].node.active = false;
            this.breakdownLabels[side].node.active = false;
        }
        this.round = this.text(this.root, '', -65, 294, 125, 32, 22, C.ink);
        // Original OwnCardArea -> EnteranceFEnergy at (0,165), design 1280x720.
        // Source bg anchor (1,.5), position (130,0), size (226,78).
        this.skin('energy-bg', -623, -195, 226, 78);
        this.skin('energy-icon', -604.424, -190.7303, 58, 66);
        // Combined readable counter; original separate font/animated layers remain unresolved.
        this.energy = this.text(this.root, '', -550, -210, 65, 32, 26, C.ink);
        this.intent = this.text(this.root, '', 420, 214, 386, 32, 16, C.gold);
        this.result = this.text(this.root, '', -370, 213, 490, 32, 20, C.mint);
        this.eventLog = this.text(this.root, '', -440, -16, 350, 68, 15, C.ink);
        this.message = this.text(this.root, '', 145, -30, 670, 26, 14, C.ink);
        this.pileCounts = this.text(this.root, '', 390, -58, 450, 26, 14, C.ink);
        for (let index = 0; index < 10; index++) {
            const x = -488 + (index % 5) * 244;
            const y = -182;
            let slot: CardSlot;
            const action = this.button('', x, y, 182, 234, () => {
                const state = this.controller.snapshot;
                if (!slot.instanceId || !this.canAct(state)) return;
                this.invoke(() => this.controller.play(slot.instanceId!));
            });
            action.sourceCard = true;
            // Canvas owns card gestures so an outside-card release is not confused with cancellation.
            action.node.off(Node.EventType.TOUCH_START);
            action.node.off(Node.EventType.TOUCH_END);
            action.node.off(Node.EventType.TOUCH_CANCEL);
            action.background.clear();
            action.label.node.setPosition(0, -40);
            action.label.getComponent(UITransform)!.setContentSize(120, 24);
            action.label.horizontalAlign = Label.HorizontalAlign.CENTER;
            action.label.fontSize = 16;
            action.label.lineHeight = 23;
            const art = this.node(action.node, 'OriginalCardArt', -1, 19, 120, 120).addComponent(Sprite);
            art.sizeMode = Sprite.SizeMode.CUSTOM;
            art.node.setRotationFromEuler(0, 0, -90);
            art.node.active = false;
            // Original FightSmallCard: card image precedes the rotated transparent frame.
            const frame = this.skin('atk', 0, 0, 234, 182, false, action.node, 'card-frames');
            frame.node.setRotationFromEuler(0, 0, -90);
            action.label.node.setSiblingIndex(action.node.children.length - 1);
            // Original kafei project has scale .5; its background is 70x82.
            this.skin('cost', -46, 70, 35, 41, false, action.node, 'card-frames');
            const cost = this.text(action.node, '', -45.4, 69.6, 26, 27, 16, C.ink);
            cost.horizontalAlign = Label.HorizontalAlign.CENTER;
            const description = this.text(action.node, '', 0, -62, 102, 24, 12, C.ink);
            const hint = this.text(action.node, '', 0, -108, 138, 18, 11, C.muted);
            slot = { action, art, cost, description, hint, instanceId: null };
            this.slots.push(slot);
        }
        this.dragTarget = this.node(this.root, 'DragEnemyTarget', 245, 60, 300, 280);
        const targetInk = this.dragTarget.addComponent(Graphics);
        targetInk.strokeColor = C.gold; targetInk.lineWidth = 3;
        targetInk.roundRect(-150, -140, 300, 280, 24); targetInk.stroke();
        this.text(this.dragTarget, '松手攻击', 0, 122, 160, 26, 20, C.gold);
        this.dragTarget.active = false;
        this.root.on(Node.EventType.TOUCH_START, this.beginCardGesture, this);
        this.root.on(Node.EventType.TOUCH_MOVE, this.moveCardGesture, this);
        this.root.on(Node.EventType.TOUCH_END, this.endCardGesture, this);
        this.root.on(Node.EventType.TOUCH_CANCEL, this.cancelCardGesture, this);
        this.endAction = this.button('回合结束', 590, -195, 116, 100,
            () => { if (this.canAct(this.controller.snapshot) && this.endTurnView.acceptsInput) this.invoke(() => this.controller.endTurn()); });
        this.endAction.sourceControl = true;
        // Source RightBottom(1280,0) + EnteranceFEndTurn(0,165); local origin shifted
        // by -50 to center the reconstructed touch region over the original artwork.
        const endNode = this.endAction.node;
        const endBg = this.skin('end-bg',55,0,226,78,false,endNode);
        const endIcon = this.skin('end-icon-normal',4,12,84,84,false,endNode);
        endIcon.node.setScale(-1,1);
        const endGlow = this.skin('end-icon-active',3,13,84,84,false,endNode);
        endGlow.node.setScale(-1,1); endGlow.color = new Color(255,255,255,127);
        this.endAction.label.node.setPosition(-.0327,-17.8561);
        this.endAction.label.node.getComponent(UITransform)!.setContentSize(82,21);
        this.endAction.label.fontSize = 20;
        this.endAction.label.node.setSiblingIndex(endNode.children.length-1);
        this.endTurnView = new EndTurnView(endNode,[endBg.node,endIcon.node,endGlow.node,this.endAction.label.node],
            () => this.enable(this.endAction,this.canAct(this.controller.snapshot) && this.endTurnView.acceptsInput));
        this.refreshAction = this.button('刷新战斗', -248, -318, 232, 42,
            () => this.invoke(() => this.controller.refresh()));
        this.retryAction = this.button('重试上次操作', 0, -318, 232, 42,
            () => this.invoke(() => this.controller.retry()));
        this.startAction = this.button('开始战斗', 248, -318, 232, 42,
            () => this.invoke(() => this.controller.startNew()));
        this.button('返回图鉴', 496, -318, 232, 42, () => { this.hide(); this.onClose(); });
        this.targetArrow = new TargetArrowView(this.root);
        this.cardSelection = new CardSelectionView(this.root);
        // Source OwnCardArea DeckNode (118,70), btn_card Panel 72x72 with centered 56x56 icon.
        const deck = this.button('牌堆', -522, -290, 72, 72, () => {
            this.clearCardGesture(); this.pilePanel.active = true;
            this.pilePanel.setSiblingIndex(this.root.children.length - 1);
        });
        deck.sourceControl = true; this.enable(deck, true);
        this.skin('deck-icon', 0, 0, 56, 56, false, deck.node);
        deck.label.node.setPosition(0, -30); deck.label.fontSize = 20;
        deck.label.color = new Color(255, 255, 255, 153);
        deck.label.node.setSiblingIndex(deck.node.children.length - 1);
        this.pilePanel = this.node(this.root, 'CardPileOverview', 0, 0, 1280, 720);
        this.pilePanel.addComponent(BlockInputEvents);
        this.paint(this.pilePanel.addComponent(Graphics), 1280, 720, new Color(10, 12, 20, 250), new Color(0,0,0,0), 0);
        const sheet = this.node(this.pilePanel, 'PileSheet', 0, 0, 1280, 720);
        this.text(sheet, '牌堆', -540, 325, 100, 32, 26, C.ink);
        this.pileCounts.node.parent = sheet; this.pileCounts.node.setPosition(0, 328);
        // Five columns follow CardDeckItem's 185-unit spacing. Card visuals reuse the
        // recovered FightSmallCard renderer; the original runtime CardShowListArea is not restored.
        for (let index = 0; index < 10; index++) {
            const action = this.button('', -370 + index % 5 * 185,
                166 - Math.floor(index / 5) * 246, 148, 200, () => {
                    this.detailCardId = this.pileCards[index].cardId;
                    this.renderPileDetail();
                });
            const node = action.node;
            node.parent = sheet; node.name = 'PileCard-' + index;
            action.sourceControl = true; this.enable(action, true); action.label.node.active = false;
            const art = this.node(node, 'Art', -1, 19, 120, 120).addComponent(Sprite);
            art.sizeMode = Sprite.SizeMode.CUSTOM; art.node.setRotationFromEuler(0, 0, -90);
            const frame = this.skin('atk', 0, 0, 234, 182, false, node, 'card-frames');
            frame.node.setRotationFromEuler(0, 0, -90);
            this.skin('cost', -46, 70, 35, 41, false, node, 'card-frames');
            const cost = this.text(node, '', -45, 70, 26, 27, 16, C.ink);
            const name = this.text(node, '', 0, -40, 120, 24, 16, C.background);
            name.horizontalAlign = cost.horizontalAlign = Label.HorizontalAlign.CENTER;
            const description = this.text(node, '', 0, -65, 106, 30, 12, C.background);
            this.pileCards.push({ node, art, name, cost, description, cardId: null });
        }
        this.pileEmpty = this.text(sheet, '', 0, 30, 800, 60, 24, C.ink);
        this.pileEmpty.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.skin('bottom-mask', 0, -330, 1280, 60, false, sheet, 'pile-ui');
        this.skin('tab-background', 0, -326, 966, 102, false, sheet, 'pile-ui');
        ['draw', 'discard', 'consumed'].forEach((name, index) => {
            const x = -320 + index * 320;
            this.pileHighlights.push(this.skin('tab-' + name + '-selected', x, -316, 308, 54,
                false, sheet, 'pile-ui').node);
            const tab = this.button('', x, -316, 308, 54, () => {
                if (this.pileByCharacter) return;
                this.pileTab = index; this.pilePage = 0; this.renderPile();
            });
            tab.node.parent = sheet; tab.sourceControl = true; this.enable(tab, true);
            this.pileTabs.push(tab);
        });
        const previous = this.button('上一页', -480, -248, 108, 36, () => {
            this.pilePage = Math.max(0, this.pilePage - 1); this.renderPile();
        });
        const next = this.button('下一页', 480, -248, 108, 36, () => {
            this.pilePage++; this.renderPile();
        });
        previous.node.parent = next.node.parent = sheet;
        this.pilePrevious = previous; this.pileNext = next;
        this.pilePageLabel = this.text(sheet, '', 0, -248, 700, 30, 16, C.muted);
        this.pilePageLabel.horizontalAlign = Label.HorizontalAlign.CENTER;
        // Recovered change-view artwork, moved to the header to leave room for pagination.
        this.pileModeAction = this.button('按角色查看', 380, 325, 148, 38, () => {
            this.pileByCharacter = !this.pileByCharacter; this.pilePage = 0; this.renderPile();
        });
        const mode = this.pileModeAction;
        mode.node.parent = sheet; mode.sourceControl = true; this.enable(mode, true);
        this.skin('change-view-button', 0, 0, 148, 38, false, mode.node, 'pile-ui');
        this.skin('change-view-icon', -54, 0, 24, 22, false, mode.node, 'pile-ui');
        mode.label.node.setPosition(12, 0);
        mode.label.node.getComponent(UITransform)!.setContentSize(104, 26);
        mode.label.fontSize = 18; mode.label.node.setSiblingIndex(mode.node.children.length - 1);
        const closePile = this.button('关闭', 540, 325, 100, 36, () => { this.pilePanel.active = false; });
        closePile.node.parent = sheet;
        // Click-to-inspect follows CardItem.onGetCardTouchUp. CardInfoShowPanel's
        // centered CardNode scale .9 and CommonBigCard geometry come from the source CSBs.
        this.pileDetail = this.node(this.pilePanel, 'PileCardDetail', 0, 0, 1280, 720);
        this.pileDetail.addComponent(BlockInputEvents);
        this.paint(this.pileDetail.addComponent(Graphics), 1280, 720,
            new Color(10, 12, 20, 252), new Color(0,0,0,0), 0);
        const largeCard = this.node(this.pileDetail, 'EnlargedCard', 0, 0, 360, 560);
        largeCard.setScale(.9, .9, 1);
        this.detailArt = this.node(largeCard, 'Art', -2, 76, 286, 286).addComponent(Sprite);
        this.detailArt.sizeMode = Sprite.SizeMode.CUSTOM;
        this.detailArt.node.setRotationFromEuler(0, 0, -90);
        const detailFrame = this.skin('big-atk', 0, 0, 612, 432, false, largeCard, 'card-frames');
        // Source layout dimensions include the atlas's transparent margins.
        detailFrame.trim = false;
        detailFrame.node.setRotationFromEuler(0, 0, -90);
        this.skin('cost', -115, 200, 70, 82, false, largeCard, 'card-frames');
        this.detailCost = this.text(largeCard, '', -115, 200, 41, 46, 32, C.ink);
        this.detailCost.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.detailName = this.text(largeCard, '', 0, -64, 258, 34, 30, C.background);
        this.detailName.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.detailEffects = this.text(largeCard, '', 0, -139, 242, 94, 24, C.background);
        this.detailEffects.verticalAlign = Label.VerticalAlign.TOP;
        const closeDetail = this.button('返回牌堆', 470, -280, 180, 44, () => {
            this.detailCardId = null; this.pileDetail.active = false;
        });
        closeDetail.node.parent = this.pileDetail;
        this.pileDetail.active = false;
        this.pilePanel.active = false;
        this.victoryPanel = this.node(this.root, 'OriginalVictoryLettering', 0, 0, 1280, 720);
        // BattleWin -> ResultDialog -> SingelResultArea, Panel_1 at (-423,122)
        // relative to RightMiddle. Child coordinates subtract its (346,121) anchor.
        // Static final-pose fallback while the title-only source timeline loads.
        const victoryFallback = [
            this.skin('victory-title', 225, 116, 664, 214, false, this.victoryPanel, 'result-ui').node,
            this.skin('victory-shadow', 216, 118, 700, 242, false, this.victoryPanel, 'result-ui').node,
            this.skin('victory-lettering', 226, 114, 664, 214, false, this.victoryPanel, 'result-ui').node,
        ];
        this.victoryTitle = new VictoryTitleView(this.victoryPanel, victoryFallback);
        // No MISSION AWARD label: this reconstruction does not grant rewards.
        this.victorySummary = this.text(this.victoryPanel, '', 225, -225, 640, 50, 22, C.ink);
        this.victorySummary.horizontalAlign = Label.HorizontalAlign.CENTER;
        this.victoryPanel.active = false;
        this.resultAudio = new BattleAudio(this.root, 'recovered/result-audio/cues');
        void this.resultAudio.load().then(() => { if (!this.disposed) this.render(this.controller.snapshot); })
            .catch(error => { if (!this.disposed) console.warn('[HCZS_RESULT_AUDIO]', String(error)); });
        this.render(controller.snapshot);
        resources.load('recovered/card-frames/cost_normal', BitmapFont, (error, font) => {
            if (this.disposed) return;
            if (error) { console.warn('[HCZS_UI] cost font unavailable', String(error)); return; }
            font.addRef(); this.costFont = font;
            for (const slot of this.slots) { slot.cost.font = font; slot.cost.fontSize = 16; }
            this.render(this.controller.snapshot);
        });
        for (const id of ['110001', '110009', '210003', '410101', '410102']) {
            resources.load(`recovered/cards/${id}/spriteFrame`, SpriteFrame, (error, frame) => {
                if (this.disposed) return;
                if (error) { console.warn('[HCZS_BATTLE] card-art-load-failed', id, String(error)); return; }
                frame.addRef();
                this.cardArt.set(id, frame);
                this.render(this.controller.snapshot);
            });
        }
    }

    private renderPile(): void {
        const battle = this.pileBattle;
        const piles = battle?.state.piles;
        // Current scenario has one player actor: all its actual instances, including hand cards.
        // Multi-character filtering requires an owner on each card and is not inferred from art.
        const ids = this.pileByCharacter ? battle?.state.cards.map(card => card.instanceId) ?? []
            : this.pileTab === 0 ? piles?.draw ?? [] : this.pileTab === 1 ? piles?.discard ?? [] : [];
        // Sort copies by card identity, never expose authoritative draw order.
        const cards = ids.map(id => battle!.state.cards.find(card => card.instanceId === id))
            .filter((card): card is NonNullable<typeof card> => !!card)
            .sort((a, b) => a.cardId.localeCompare(b.cardId));
        const pages = Math.max(1, Math.ceil(cards.length / 10));
        this.pilePage = Math.min(this.pilePage, pages - 1);
        this.pileTabs.forEach((tab, index) => {
            tab.node.active = !this.pileByCharacter || index === 1;
            tab.label.string = index === 0 ? `抽牌堆  ${piles?.draw.length ?? '—'}`
                : index === 1 ? `弃牌堆  ${piles?.discard.length ?? '—'}` : '湮灭牌堆';
            if (this.pileByCharacter && index === 1) tab.label.string = `艾尔莎 · ${cards.length} 张`;
            const selected = index === (this.pileByCharacter ? 1 : this.pileTab);
            this.pileHighlights[index].active = selected;
            tab.label.color = selected ? C.background : C.ink;
        });
        this.pileModeAction.label.string = this.pileByCharacter ? '按牌堆查看' : '按角色查看';
        this.pilePrevious.node.active = this.pileNext.node.active = pages > 1;
        this.enable(this.pilePrevious, this.pilePage > 0);
        this.enable(this.pileNext, this.pilePage < pages - 1);
        this.pileEmpty.string = !battle ? '等待战斗' : !this.pileByCharacter && this.pileTab === 2 ? '湮灭牌堆规则尚未恢复'
            : cards.length ? '' : '此牌堆为空';
        this.pilePageLabel.string = !this.pileByCharacter && this.pileTab === 2 ? ''
            : `${this.pilePage + 1} / ${pages}　${this.pileByCharacter ? '当前角色的全部战斗卡牌' : '按卡牌归类，不显示抽取顺序'}`;
        this.pileCards.forEach((slot, index) => {
            const instance = cards[this.pilePage * 10 + index];
            const card = instance ? battle?.scenario.definition.cards[instance.cardId] : undefined;
            slot.cardId = instance?.cardId ?? null;
            slot.node.active = !!card;
            slot.art.spriteFrame = instance ? this.cardArt.get(instance.cardId) ?? null : null;
            slot.art.node.active = !!slot.art.spriteFrame;
            slot.name.string = card?.name ?? '';
            slot.cost.string = card ? String(card.cost) : '';
            slot.description.string = card ? this.effects(card.effects, false) : '';
        });
        this.renderPileDetail();
    }

    private renderPileDetail(): void {
        const card = this.detailCardId ? this.pileBattle?.scenario.definition.cards[this.detailCardId] : undefined;
        this.pileDetail.active = !!card;
        if (!card) { this.detailCardId = null; return; }
        this.detailArt.spriteFrame = this.cardArt.get(this.detailCardId!) ?? null;
        this.detailArt.node.active = !!this.detailArt.spriteFrame;
        this.detailName.string = card.name;
        this.detailCost.string = String(card.cost);
        this.detailEffects.string = this.effects(card.effects, false);
    }

    private skin(name: string, x: number, y: number, width: number, height: number, filled = false,
        parent = this.root, folder = 'battle-ui'): Sprite {
        const sprite = this.node(parent, 'OriginalUI-' + name, x, y, width, height).addComponent(Sprite);
        sprite.sizeMode = Sprite.SizeMode.CUSTOM;
        // Recovered card PNGs restore sourceSize, including sourceColorRect margins.
        // CSB sizes refer to that complete canvas, not Creator's trimmed opaque bounds.
        if (folder === 'card-frames' || folder === 'result-ui') sprite.trim = false;
        resources.load(`recovered/${folder}/${name}/spriteFrame`, SpriteFrame, (error, frame) => {
            if (this.disposed) return;
            if (error) { console.warn('[HCZS_UI] sprite unavailable', name, String(error)); return; }
            frame.addRef(); this.uiFrames.push(frame); sprite.spriteFrame = frame;
            if (filled) {
                sprite.type = Sprite.Type.FILLED;
                sprite.fillType = Sprite.FillType.HORIZONTAL;
                sprite.fillStart = 0; sprite.fillRange = 1;
            }
            this.render(this.controller.snapshot);
        });
        return sprite;
    }

    render(snapshot: BattleViewState): void {
        if (snapshot.battle) this.selectBattleScene(snapshot.battle.scenario.definition.id.startsWith('city-preview-10405-'));
        if (this.disposed) return;
        this.clearCardGesture();
        // A state refresh must never turn a touch begun on one card into a different card play.
        for (const action of this.actions) action.pressedId = null;
        const receivedBattle = snapshot.battle;
        const previousBattle = this.lastReceivedBattle;
        this.lastReceivedBattle = receivedBattle;
        if (this.enemyPresentation && (!receivedBattle || receivedBattle.id !== this.enemyPresentation.id ||
            receivedBattle.revision !== this.enemyPresentation.revision)) {
            this.generation++; this.presentationBusy = false; this.presentationActor = null;
            this.healthDisplay = null; this.breakdownDisplay = null; this.enemyPresentation = null;
        }
        let battle = receivedBattle;
        const isNewAction = !!battle && battle.id === this.lastBattleId && battle.revision > this.lastRevision;
        this.lastBattleId = battle?.id ?? null;
        this.lastRevision = battle?.revision ?? 0;
        const played = isNewAction ? snapshot.events.find(event => event.type === 'CardPlayed' || event.type === 'EnemySkillUsed' || event.type === 'BreakdownTriggered') : undefined;
        if (played && this.visible && !this.presentationBusy) {
            this.presentationBusy = true;
            this.presentationActor = played.type === 'BreakdownTriggered' ? null : played.type === 'EnemySkillUsed' ? 'enemy' : 'player';
            if (played.type === 'EnemySkillUsed' && previousBattle && battle && previousBattle.id === battle.id &&
                previousBattle.revision + 1 === battle.revision) {
                this.enemyPresentation = { ...battle, state: beforeEnemyAction(previousBattle.state,snapshot.events) };
            }
            const generation = this.generation;
            const healthEvents = snapshot.events.filter((event): event is HealthEvent =>
                event.type === 'DamageApplied' || event.type === 'ShieldAdded' || event.type === 'ShieldCleared' || event.type === 'HealthRestored');
            this.healthDisplay = {};
            this.breakdownDisplay = { player: previousBattle?.state.breakdown?.player ?? 0,
                enemy: previousBattle?.state.breakdown?.enemy ?? 0 };
            for (const event of healthEvents) if (!this.healthDisplay[event.target])
                this.healthDisplay[event.target] = { hp: event.previousHp, shield: event.previousShield };
            const applyHealth = (event: HealthEvent): void => {
                this.healthDisplay![event.target] = { hp: event.finalHp, shield: event.finalShield };
                if (event.type === 'DamageApplied' &&
                    (Number(event.hpLost.decimal) > 0 || Number(event.absorbed.decimal) > 0)) {
                    if (event.target === 'enemy') this.sceneView.playEnemyReaction(Number(event.finalHp.decimal) === 0);
                    else this.sceneView.playPlayerReaction(Number(event.finalHp.decimal) === 0);
                }
            };
            const playback = async (): Promise<void> => {
              for (const segment of actionSegments(snapshot.events)) {
                if (this.disposed || generation !== this.generation || !this.healthDisplay) return;
                const segmentHealth = segment.events.filter((event): event is HealthEvent =>
                    event.type === 'DamageApplied' || event.type === 'ShieldAdded' || event.type === 'ShieldCleared' || event.type === 'HealthRestored');
                let healthIndex = 0;
                const onHit = (): void => {
                if (this.disposed || generation !== this.generation || !this.healthDisplay) return;
                while (healthIndex < segmentHealth.length) {
                    const event = segmentHealth[healthIndex++];
                    applyHealth(event);
                    if (event.type !== 'ShieldCleared') break;
                }
                console.info('[HCZS_HIT] health cue', JSON.stringify(this.healthDisplay));
                this.render(this.controller.snapshot);
                };
                const action = segment.action;
                this.presentationActor = action.type === 'BreakdownTriggered' ? null : action.type === 'EnemySkillUsed' ? 'enemy' : 'player';
                console.info('[HCZS_ACTION_QUEUE]', action.type, action.type === 'EnemySkillUsed' ? action.skillId : action.type === 'CardPlayed' ? action.cardId : action.target);
                if (action.type === 'CardPlayed') await this.sceneView.playCard(action.cardId,onHit);
                else if (action.type === 'EnemySkillUsed') await this.sceneView.playEnemySkill(action.skillId,onHit);
                // Status ticks settle in their own segment without borrowing an attack animation.
                if (this.disposed || generation !== this.generation || !this.healthDisplay) return;
                // Some source effects have no recovered cue; settle their authoritative
                // values at this action's boundary, never during a later skill's hit.
                while (healthIndex < segmentHealth.length) applyHealth(segmentHealth[healthIndex++]);
                for (const event of segment.events) if (event.type === 'BreakdownChanged' && this.breakdownDisplay)
                    this.breakdownDisplay[event.target] = event.finalStacks;
                this.render(this.controller.snapshot);
              }
            };
            void playback().catch(error => {
                console.error('[HCZS_ATTACK] playback failed', String(error));
            }).then(() => {
                if (this.disposed || generation !== this.generation) return;
                this.presentationBusy = false;
                this.presentationActor = null;
                this.enemyPresentation = null;
                this.healthDisplay = null;
                this.breakdownDisplay = null;
                this.render(this.controller.snapshot);
            });
        }
        battle = this.enemyPresentation ?? receivedBattle;
        for (const side of ['player', 'enemy'] as const) {
            const stacks = this.breakdownDisplay?.[side] ?? battle?.state.breakdown?.[side] ?? 0;
            this.breakdownIcons[side].node.active = !!battle && stacks > 0;
            this.breakdownLabels[side].node.active = !!battle && stacks > 0;
            this.breakdownLabels[side].string = String(stacks);
        }
        this.sceneView.setOutcome(battle?.state.status === 'won' ? 'won'
            : battle?.state.status === 'lost' ? (battle.state.outcomeReason === 'player-defeated' ? 'defeated' : 'limit')
                : 'playing', this.presentationBusy);
        this.heading.string = battle?.scenario.title ?? '本地战斗';
        this.notice.string = battle?.scenario.notice ?? '开始后显示关卡来源与规则说明 · 暂不发放奖励';
        const active = this.canAct(snapshot);
        const terminal = !!battle && battle.state.status !== 'player-turn' && !this.presentationBusy;
        const victory = terminal && battle?.state.status === 'won';
        this.victoryPanel.active = victory;
        this.victoryTitle.setVisible(victory && this.visible);
        if (!victory) this.voicedVictory = null;
        if (victory && this.visible && battle && battle.scenario.definition.id.startsWith('tutorial-5000-')
            && this.voicedVictory !== battle.id && this.resultAudio.playEvent('ailisha_battle_win_normal')) {
            this.voicedVictory = battle.id;
        }
        this.victorySummary.string = victory ? `第 ${battle!.state.round} 回合 · 战斗进度已保存` : '';
        this.result.node.active = !victory;
        this.eventLog.node.active = !victory;
        this.intent.node.active = !victory;
        const busy = snapshot.pending || this.presentationBusy;
        this.message.string = snapshot.message || (busy ? '正在处理…' : active ? '点击手牌出牌，或结束回合。' : '');
        this.message.color = snapshot.phase === 'error' || snapshot.phase === 'uncertain' ? C.error : C.muted;
        this.message.node.active = !victory || snapshot.phase === 'error' || snapshot.phase === 'uncertain';
        if (battle) {
            const { state, scenario: { definition } } = battle;
            this.playerName.string = definition.player.name;
            this.enemyName.string = definition.enemy.name;
            const playerHealth = this.healthDisplay?.player ?? state.player;
            const enemyHealth = this.healthDisplay?.enemy ?? state.enemy;
            if (this.playerHpBar.spriteFrame) this.playerHpBar.fillRange = Math.max(0, Math.min(1, Number(playerHealth.hp.decimal) / Number(definition.player.maxHp.decimal)));
            if (this.enemyHpBar.spriteFrame) this.enemyHpBar.fillRange = Math.max(0, Math.min(1, Number(enemyHealth.hp.decimal) / Number(definition.enemy.maxHp.decimal)));
            this.playerStats.string = this.amount(playerHealth.hp);
            const hasPlayerShield = Number(playerHealth.shield.decimal) > 0;
            this.playerShieldIcon.node.active = this.playerShield.node.active = hasPlayerShield;
            this.playerShield.string = this.amount(playerHealth.shield);
            this.enemyStats.string = this.amount(enemyHealth.hp);
            const hasEnemyShield = Number(enemyHealth.shield.decimal) > 0;
            this.enemyShieldIcon.node.active = this.enemyShield.node.active = hasEnemyShield;
            this.enemyShield.string = this.amount(enemyHealth.shield);
            this.setHeaderLife('player', Number(playerHealth.hp.decimal) <= 0);
            this.setHeaderLife('enemy', Number(enemyHealth.hp.decimal) <= 0);
            this.round.string = `回合 ${state.round}`;
            this.energy.string = `${state.energy}/${battle.scenario.definition.energyPerRound}`;
            this.pileCounts.string = `手牌 ${state.piles.hand.length} / ${definition.handLimit}    抽牌 ${state.piles.draw.length}    弃牌 ${state.piles.discard.length}`;
            this.pileBattle = battle; this.renderPile();
            this.result.string = this.presentationBusy ? '动作播放中…' : state.status === 'won' ? `胜利 · ${definition.enemy.name}已被击败`
                : state.status === 'lost' ? (state.outcomeReason === 'round-limit' ? '战败 · 已到回合上限' : '战败 · 艾尔莎倒下了')
                    : busy ? '正在处理行动…' : snapshot.phase === 'uncertain' ? '操作待确认' : '艾尔莎的回合';
            this.result.color = state.status === 'lost' ? C.error : C.mint;
            this.intent.string = terminal ? '战斗已结束'
                : (definition.enemyIntents[state.round - 1] || definition.enemyFallback)
                    .map(id => this.effects(definition.enemySkills[id].effects, true)).join('\n');
            const lines = this.presentationBusy ? ['动作播放中…'] : this.eventLines(snapshot.events, battle).slice(-3);
            this.eventLog.string = lines.length ? lines.join('\n') : terminal ? '可以重开战斗，或返回图鉴。'
                : '已恢复当前战斗。选择手牌，继续这一回合。';
        } else {
            this.playerStats.string = '—';
            this.playerShieldIcon.node.active = this.playerShield.node.active = false;
            this.enemyStats.string = '—';
            this.enemyShieldIcon.node.active = this.enemyShield.node.active = false;
            this.setHeaderLife('player', false);
            this.setHeaderLife('enemy', false);
            this.round.string = '回合 —'; this.energy.string = '能量 —'; this.pileCounts.string = '等待战斗';
            this.pileBattle = null; this.renderPile();
            this.result.string = busy ? '正在读取战斗…' : snapshot.phase === 'uncertain' ? '操作待确认' : '准备进入战斗';
            this.result.color = C.mint;
            this.intent.string = '开始后显示本回合意图';
            this.eventLog.string = '艾尔莎对阵幻眼魔方\n开始后读取当前配置的卡组与规则。';
        }
        for (let index = 0; index < this.slots.length; index++) {
            const slot = this.slots[index];
            const instanceId = battle?.state.piles.hand[index];
            const cardId = instanceId ? battle!.state.cards.find(card => card.instanceId === instanceId)?.cardId : undefined;
            const card = cardId ? battle!.scenario.definition.cards[cardId] : undefined;
            slot.instanceId = instanceId ?? null;
            slot.action.node.active = !!card && !victory;
            const count = battle?.state.piles.hand.length ?? 0;
            // Original CardTools single-owner group geometry. Multi-owner grouping is not yet ported.
            // Source R=2800, D=R-90, thetaMax=3 degrees, beta=acos(D/R)-1 degree.
            const radius = 2800;
            const beta = Math.acos((radius - 90) / radius) * 180 / Math.PI - 1;
            const step = count > 1 ? Math.min(3, beta / (count - 1)) : 0;
            const angle = (index - (count - 1) / 2) * step;
            const radians = angle * Math.PI / 180;
            // Screen translation is reconstructed to clear the remaining preview controls.
            slot.action.node.setPosition(radius * Math.sin(radians), -152 + radius * (Math.cos(radians) - 1));
            slot.action.node.setRotationFromEuler(0, 0, -angle);
            slot.action.node.setScale(1, 1, 1);
            slot.art.spriteFrame = cardId ? this.cardArt.get(cardId) ?? null : null;
            slot.art.node.active = !!slot.art.spriteFrame;
            const affordable = !!card && card.cost <= battle!.state.energy;
            this.enable(slot.action, !!card && active && affordable);
            slot.action.label.string = card?.name ?? '—';
            slot.cost.string = card ? `${card.cost}` : '';
            slot.description.string = card ? this.effects(card.effects, false) : '';
            slot.description.color = slot.action.enabled ? C.background : C.disabledInk;
            slot.cost.color = slot.action.enabled ? Color.WHITE : C.disabledInk;
            slot.hint.string = !card ? '' : busy ? '正在处理…' : terminal ? '战斗已结束'
                : !active ? '请先确认当前进度' : !affordable ? '能量不足' : '拖向敌人出牌';
        }
        this.enable(this.endAction, active && this.endTurnView.acceptsInput);
        const noPlayableCards = !!battle && !battle.state.piles.hand.some(id => {
            const cardId=battle.state.cards.find(card=>card.instanceId===id)?.cardId;
            return !!cardId && battle.scenario.definition.cards[cardId].cost<=battle.state.energy;
        });
        this.endTurnView.setState(this.visible && !!battle && !terminal,noPlayableCards,this.presentationActor==='enemy');
        // Original EndArea LabelText: DesignStatus=回合结束, s2=敌方回合.
        // The server commits a full round atomically, so show the presentation actor
        // while enemy playback is in progress rather than the already-next-turn snapshot.
        this.endAction.label.string = this.presentationActor === 'enemy' ? '敌方回合' : '回合结束';
        this.enable(this.refreshAction, !!snapshot.profileId && !busy);
        this.retryAction.node.active = snapshot.canRetry;
        this.enable(this.retryAction, snapshot.canRetry && !busy);
        this.startAction.node.active = !battle || terminal;
        this.startAction.label.string = battle ? '重开战斗' : '开始战斗';
        this.enable(this.startAction, !!snapshot.profileId && !busy && snapshot.phase === 'ready' && !snapshot.canRetry && (!battle || terminal));
    }

    private setHeaderLife(actor: 'player' | 'enemy', dead: boolean): void {
        // Original alive/dead widget states: Color.black=[255,128,128,128],
        // hide name and shield, replace txt_hp with txt_dead. Preserve layer alpha.
        const channel = dead ? 128 : 255;
        for (const art of this.headerArt[actor]) art.color = new Color(channel, channel, channel, art.color.a);
        const player = actor === 'player';
        (player ? this.playerName : this.enemyName).node.active = !dead;
        const health = player ? this.playerStats : this.enemyStats;
        health.color = dead ? new Color(128, 128, 128) : C.ink;
        if (dead) {
            health.string = player ? '重创' : '消灭';
            (player ? this.playerShield : this.enemyShield).node.active = false;
            (player ? this.playerShieldIcon : this.enemyShieldIcon).node.active = false;
        }
    }

    private selectBattleScene(city: boolean): void {
        if (city === this.cityBattle || this.disposed) return;
        this.sceneView.destroy();
        this.cityBattle = city;
        this.sceneView = new PrologueSceneView(this.root.scene, this.sceneSurface, true, city);
        // Both source HUD and historical gameplay place allies left, enemies right.
        this.dragTarget.setPosition(city ? 280 : 245, 60, 0);
        // Reconstruction HUD follows the active side layout; source intent widget is not recovered.
        this.intent.node.setPosition(city ? 280 : 420, 214, 0);
        this.result.node.setPosition(city ? -300 : -370, 213, 0);
        if (this.visible) void this.sceneView.show().catch(error => {
            this.message.string = '战斗场景加载失败，请返回重试';
            console.error('[HCZS_BATTLE] scene-load-failed', String(error));
        });
    }

    show(): void {
        if (this.disposed) return;
        this.visible = true;
        this.root.setSiblingIndex(this.root.parent!.children.length - 1);
        this.root.active = true;
        this.render(this.controller.snapshot);
        const generation = ++this.generation;
        void this.sceneView.show().catch(error => {
            if (!this.disposed && this.visible && generation === this.generation) this.message.string = '场景加载失败，请返回后重试';
            console.error('[HCZS_BATTLE] scene-load-failed', String(error));
        });
    }

    hide(): void {
        if (this.disposed) return;
        this.visible = false;
        this.victoryTitle.setVisible(false);
        this.resultAudio.stop(); this.voicedVictory = null;
        this.pilePanel.active = false;
        this.detailCardId = null; this.pileDetail.active = false;
        this.clearCardGesture();
        this.generation++;
        this.presentationBusy = false;
        this.presentationActor = null;
        this.enemyPresentation = null;
        this.healthDisplay = null;
        this.breakdownDisplay = null;
        this.sceneView.hide();
        this.endTurnView.setState(false,false,false);
        for (const action of this.actions) action.pressedId = null;
        this.root.active = false;
    }

    destroy(): void {
        if (this.disposed) return;
        this.hide();
        this.disposed = true;
        this.sceneView.destroy(); this.targetArrow.destroy(); this.cardSelection.destroy(); this.endTurnView.destroy();
        this.victoryTitle.destroy();
        this.resultAudio.destroy();
        this.uiFrames.forEach(frame => frame.decRef()); this.uiFrames = [];
        this.costFont?.decRef(); this.costFont = null;
        this.root.removeFromParent();
        this.root.destroy();
        for (const frame of this.cardArt.values()) frame.decRef();
        this.cardArt.clear();
        this.actions = []; this.slots = [];
    }

    private canAct(snapshot: BattleViewState): boolean {
        return !this.presentationBusy && !snapshot.pending && snapshot.phase === 'ready' && !snapshot.canRetry && snapshot.battle?.state.status === 'player-turn';
    }

    private gesturePoint(event: EventTouch): Vec3 {
        const point = event.getUILocation();
        return this.root.getComponent(UITransform)!.convertToNodeSpaceAR(new Vec3(point.x, point.y, 0));
    }

    private clearCardGesture(): void {
        this.gesture = null;
        this.targetArrow?.hide();
        this.cardSelection?.hide();
        if (this.dragTarget) this.dragTarget.active = false;
    }

    private beginCardGesture(event: EventTouch): void {
        if (this.gesture || !this.visible || !this.canAct(this.controller.snapshot)) return;
        const pointer = event.getID();
        if (pointer === null) return;
        const battle = this.controller.snapshot.battle!;
        const slot = [...this.slots].reverse().find(item => item.instanceId && item.action.node.activeInHierarchy &&
            item.action.node.getComponent(UITransform)!.hitTest(event.getLocation()));
        if (!slot?.instanceId) return;
        const cardId = battle.state.cards.find(card => card.instanceId === slot.instanceId)?.cardId;
        const card = cardId ? battle.scenario.definition.cards[cardId] : undefined;
        if (!card) return;
        this.message.string = `${card.name} · ${card.cost} 能量 · ${this.effects(card.effects, false)}`;
        if (!slot.action.enabled) return;
        const point = this.gesturePoint(event);
        const origin = this.root.getComponent(UITransform)!.convertToNodeSpaceAR(slot.action.node.worldPosition);
        this.gesture = { pointer, instanceId: slot.instanceId, battleId: battle.id,
            revision: battle.revision, startX: point.x, startY: point.y, arrowX: origin.x, arrowY: origin.y,
            name: card.name, detail: this.message.string };
        this.dragTarget.active = true;
        this.cardSelection.show(slot.action.node);
    }

    private moveCardGesture(event: EventTouch): void {
        if (!this.gesture || event.getID() !== this.gesture.pointer) return;
        const point = this.gesturePoint(event);
        const ready = point.y - this.gesture.startY >= 5 && this.overEnemy(point);
        if (point.y - this.gesture.startY >= 5) {
            this.targetArrow.show({ x: this.gesture.arrowX, y: this.gesture.arrowY },point);
        } else this.targetArrow.hide();
        this.message.string = ready ? `松手打出「${this.gesture.name}」` : '拖到敌人框内松手；其他位置松手取消';
    }

    private overEnemy(point: Vec3): boolean {
        // Reconstructed target region for this single-enemy camera, not original native model picking.
        const center = this.cityBattle ? 280 : 245;
        return point.x >= center - 150 && point.x <= center + 150 && point.y >= -80 && point.y <= 200;
    }

    private endCardGesture(event: EventTouch): void {
        const gesture = this.gesture;
        if (!gesture || event.getID() !== gesture.pointer) return;
        const point = this.gesturePoint(event);
        const snapshot = this.controller.snapshot;
        const valid = this.canAct(snapshot) && snapshot.battle?.id === gesture.battleId &&
            snapshot.battle.revision === gesture.revision && snapshot.battle.state.piles.hand.indexOf(gesture.instanceId) !== -1 &&
            point.y - gesture.startY >= 5 && this.overEnemy(point);
        this.clearCardGesture();
        if (valid) this.invoke(() => this.controller.play(gesture.instanceId));
        else this.message.string = Math.abs(point.x - gesture.startX) < 5 && Math.abs(point.y - gesture.startY) < 5
            ? gesture.detail : '已取消出牌';
    }

    private cancelCardGesture(event: EventTouch): void {
        if (!this.gesture || event.getID() !== this.gesture.pointer) return;
        this.clearCardGesture();
        this.message.string = '已取消出牌';
    }

    private invoke(operation: () => Promise<void>): void {
        if (!this.visible || this.disposed) return;
        // Controller normally reports failures through snapshot; guard unexpected rejections too.
        void operation().catch(() => {
            if (!this.disposed && this.visible) { this.message.string = '操作未完成，请刷新战斗后继续。'; this.message.color = C.error; }
        });
    }

    private amount(value: Health): string {
        if (value.numeric_type === 'integer') return value.decimal;
        // Display formatting only. Full tagged binary64 values stay untouched in the controller/save.
        const number = Number(value.decimal);
        return Math.abs(number) < 1e8 ? number.toFixed(1).replace(/\.0$/, '') : number.toPrecision(5);
    }

    private effects(effects: readonly Effect[], enemy: boolean): string {
        const lines = effects.map(effect => effect.type === 'draw' ? `抽 ${effect.count} 张牌`
            : effect.type === 'damage' ? `${effect.target === 'self' ? '自身' : enemy ? '对艾尔莎' : '对敌'}伤害 ${effect.amount}`
                : effect.type === 'breakdown' ? `施加分解 ${effect.stacks} 层`
                    : effect.type === 'heal' ? `${effect.target === 'self' ? '自身' : '目标'}恢复生命 ${effect.amount}`
                        : `${effect.target === 'self' ? '' : enemy ? '艾尔莎' : '敌方'}护盾 +${effect.amount}`);
        if (!lines.length) return '本次不产生效果';
        if (lines.length > 1 && lines.every(line => line === lines[0])) return `${lines[0]} × ${lines.length}`;
        return lines.slice(0, 3).join('\n') + (lines.length > 3 ? '\n…' : '');
    }

    private eventText(event: Event, battle: Battle): string {
        const target = (side: string): string => side === 'player' ? battle.scenario.definition.player.name : battle.scenario.definition.enemy.name;
        switch (event.type) {
            case 'BreakdownChanged': return `${target(event.target)} 分解 ${event.finalStacks} 层`;
            case 'BreakdownTriggered': return `${target(event.target)} 分解触发`;
            case 'HealthRestored': return `${target(event.target)} 恢复生命 ${this.amount(event.restored)}`;
            case 'CardPlayed': return `打出「${battle.scenario.definition.cards[event.cardId]?.name ?? '卡牌'}」`;
            case 'DamageApplied': {
                const lost = Number(event.hpLost.decimal) > 0;
                const absorbed = Number(event.absorbed.decimal) > 0;
                return lost ? `${target(event.target)} 生命 -${this.amount(event.hpLost)}${absorbed ? ` · 护盾 -${this.amount(event.absorbed)}` : ''}`
                    : absorbed ? `${target(event.target)} 护盾吸收 ${this.amount(event.absorbed)}` : `${target(event.target)} 未损失生命`;
            }
            case 'ShieldAdded': return `${target(event.target)} 获得 ${event.amount} 护盾`;
            case 'CardDrawn': return '抽取一张牌';
            case 'DiscardRecycled': return '弃牌已洗回抽牌堆';
            case 'BattleEnded': return event.status === 'won' ? '战斗胜利' : event.reason === 'round-limit' ? '已达到本场回合上限' : '战斗失败';
            default: return '';
        }
    }

    private eventLines(events: readonly Event[], battle: Battle): string[] {
        const lines: string[] = [];
        let draws = 0;
        const flushDraws = (): void => { if (draws) { lines.push(`抽取 ${draws} 张牌`); draws = 0; } };
        for (const event of events) {
            if (event.type === 'CardDrawn') { draws++; continue; }
            flushDraws();
            const line = this.eventText(event, battle);
            if (line) lines.push(line);
        }
        flushDraws();
        return lines;
    }

    private node(parent: Node, name: string, x: number, y: number, width: number, height: number): Node {
        const node = new Node(name);
        node.layer = Layers.Enum.UI_2D;
        parent.addChild(node); node.setPosition(x, y, 0);
        node.addComponent(UITransform).setContentSize(width, height);
        return node;
    }

    private text(parent: Node, content: string, x: number, y: number, width: number, height: number, size: number, color: Color): Label {
        const label = this.node(parent, 'BattleText', x, y, width, height).addComponent(Label);
        label.string = content; label.fontFamily = 'Microsoft YaHei'; label.fontSize = size; label.lineHeight = size + 5;
        label.color = color; label.horizontalAlign = Label.HorizontalAlign.LEFT; label.verticalAlign = Label.VerticalAlign.CENTER;
        label.overflow = Label.Overflow.SHRINK; label.enableWrapText = true;
        return label;
    }

    private panel(x: number, y: number, width: number, height: number): void {
        this.paint(this.node(this.root, 'BattlePanel', x, y, width, height).addComponent(Graphics), width, height, C.panel, C.border, 10);
    }

    private paint(graphics: Graphics, width: number, height: number, fill: Color, stroke: Color, radius = 8): void {
        graphics.clear(); graphics.fillColor = fill; graphics.strokeColor = stroke; graphics.lineWidth = 1;
        graphics.roundRect(-width / 2, -height / 2, width, height, radius); graphics.fill(); graphics.stroke();
    }

    private enable(action: Action, enabled: boolean): void {
        action.enabled = enabled;
        if (action.sourceCard || action.sourceControl) action.background.clear();
        else this.paint(action.background, action.width, action.height, enabled ? C.selected : C.disabled, enabled ? C.mint : C.border);
        action.label.color = enabled ? (action.sourceCard ? C.background : C.ink) : C.disabledInk;
    }

    private button(title: string, x: number, y: number, width: number, height: number, callback: () => void): Action {
        const node = this.node(this.root, 'BattleAction', x, y, width, height);
        const background = node.addComponent(Graphics);
        const label = this.text(node, title, 0, 0, width - 18, height - 4, 17, C.ink);
        label.horizontalAlign = Label.HorizontalAlign.CENTER;
        const action: Action = { node, label, background, enabled: true, pressedId: null, width, height };
        this.actions.push(action); this.enable(action, true);
        node.on(Node.EventType.TOUCH_START, (event: EventTouch) => {
            event.propagationStopped = true;
            if (this.visible && !this.disposed && action.enabled && action.pressedId === null) action.pressedId = event.getID();
        });
        node.on(Node.EventType.TOUCH_CANCEL, (event: EventTouch) => {
            event.propagationStopped = true;
            if (event.getID() === action.pressedId) action.pressedId = null;
        });
        node.on(Node.EventType.TOUCH_END, (event: EventTouch) => {
            event.propagationStopped = true;
            const pressed = action.pressedId !== null && action.pressedId === event.getID();
            if (pressed) action.pressedId = null;
            if (pressed && this.visible && !this.disposed && action.enabled && node.activeInHierarchy &&
                node.getComponent(UITransform)!.hitTest(event.getLocation())) callback();
        });
        return action;
    }
}
