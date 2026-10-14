/** Pure client coordinator. No cc, Node, battle-core runtime, or local damage calculation.
 * Paths passed to transport are relative to /api/rebuild/v1. Transport supplies
 * timeouts and throws BattleRequestError for HTTP/network failures.
 */
export type TaggedScalar = Readonly<{ numeric_type: 'integer'; decimal: string }> |
    Readonly<{ numeric_type: 'binary64'; decimal: string; hex: string }>;
export type BattleSide = 'player' | 'enemy';
export type BattleStatus = 'player-turn' | 'won' | 'lost';
export type BattleEffect = Readonly<{ type: 'damage' | 'shield'; target: 'self' | 'opponent'; amount: string }> |
    Readonly<{ type: 'heal'; target: 'self' | 'opponent'; amount: string }> |
    Readonly<{ type: 'breakdown'; target: 'opponent'; stacks: number }> |
    Readonly<{ type: 'draw'; count: number }>;
export interface BattleCardInstance { readonly instanceId: string; readonly cardId: string }
export interface BattleCard { readonly name: string; readonly cost: number; readonly effects: readonly BattleEffect[] }
export interface BattleEntityDefinition { readonly id: string; readonly name: string; readonly maxHp: TaggedScalar }
export interface BattleDefinition {
    readonly statusRules?: Readonly<{ policy: 'breakdown-reconstruction-v1'; attack: Readonly<Record<BattleSide, TaggedScalar>> }>;
    readonly id: string; readonly player: BattleEntityDefinition; readonly enemy: BattleEntityDefinition;
    readonly deck: readonly BattleCardInstance[]; readonly cards: Readonly<Record<string, BattleCard>>;
    readonly enemySkills: Readonly<Record<string, Readonly<{ effects: readonly BattleEffect[] }>>>;
    readonly enemyIntents: readonly (readonly string[])[]; readonly enemyFallback: readonly string[];
    readonly initialDraw: number; readonly roundDraw: number; readonly energyPerRound: number;
    readonly handLimit: number; readonly maxRounds: number;
}
export interface BattleEntityState { readonly hp: TaggedScalar; readonly shield: TaggedScalar }
export type BattlePileZone = 'hand' | 'draw' | 'discard' | 'exhausted' | 'powerUsed' | 'removed';
export interface BattleState {
    readonly format: 'hczs-battle-session-v1' | 'hczs-battle-session-v2'; readonly definitionId: string;
    readonly breakdown?: Readonly<Record<BattleSide, number>>;
    readonly round: number; readonly status: BattleStatus;
    readonly outcomeReason: null | 'enemy-defeated' | 'player-defeated' | 'round-limit';
    readonly energy: number; readonly player: BattleEntityState; readonly enemy: BattleEntityState;
    readonly cards: readonly BattleCardInstance[]; readonly piles: Readonly<Record<BattlePileZone, readonly string[]>>;
    readonly rng: Readonly<{ algorithm: 'mulberry32-v1'; state: number }>; readonly actionIndex: number;
}
export interface BattleScenario {
    readonly definition: BattleDefinition; readonly title: string; readonly notice: string;
    readonly policies?: unknown; readonly provenance?: unknown;
}
export interface BattleRecord {
    readonly id: string; readonly profileId: string; readonly revision: number;
    readonly scenario: BattleScenario; readonly state: BattleState;
    readonly createdAt: number; readonly updatedAt: number;
}
interface HealthChange {
    readonly previousHp: TaggedScalar; readonly finalHp: TaggedScalar;
    readonly previousShield: TaggedScalar; readonly finalShield: TaggedScalar;
}
export type BattleEvent =
    Readonly<{ type: 'BreakdownChanged'; actor: BattleSide; target: BattleSide; previousStacks: number; finalStacks: number; reason: 'applied' | 'healed' }> |
    Readonly<{ type: 'BreakdownTriggered'; actor: BattleSide; target: BattleSide; stacks: number; amount: string }> |
    Readonly<{ type: 'HealthRestored'; actor: BattleSide; target: BattleSide; effectIndex: number; amount: string; restored: TaggedScalar } & HealthChange> |
    Readonly<{ type: 'BattleStarted'; definitionId: string; seed: number }> |
    Readonly<{ type: 'TurnStarted'; round: number }> |
    Readonly<{ type: 'CardPlayed'; instanceId: string; cardId: string; cost: number }> |
    Readonly<{ type: 'CardMoved'; instanceId: string; from: 'hand' | 'in-flight'; to: 'discard' }> |
    Readonly<{ type: 'CardDrawn'; instanceId: string }> |
    Readonly<{ type: 'DiscardRecycled'; order: readonly string[]; rngBefore: number; rngAfter: number }> |
    Readonly<{ type: 'EnergyChanged'; previousValue: number; finalValue: number }> |
    Readonly<{ type: 'DamageApplied'; actor: BattleSide; target: BattleSide; effectIndex: number;
        amount: string; absorbed: TaggedScalar; hpLost: TaggedScalar } & HealthChange> |
    Readonly<{ type: 'ShieldAdded'; actor: BattleSide; target: BattleSide; effectIndex: number; amount: string } & HealthChange> |
    Readonly<{ type: 'ShieldCleared'; target: BattleSide } & HealthChange> |
    Readonly<{ type: 'EnemySkillUsed'; skillId: string; round: number }> |
    Readonly<{ type: 'BattleEnded'; status: 'won' | 'lost'; reason: string; round: number }> |
    Readonly<{ type: 'StateUpdated'; state: BattleState }>;
export interface BattleViewState {
    readonly phase: 'idle' | 'loading' | 'ready' | 'error' | 'uncertain';
    readonly profileId: string | null; readonly battle: BattleRecord | null;
    readonly message: string; readonly pending: boolean; readonly canRetry: boolean;
    readonly events: readonly BattleEvent[];
}
export type BattleTransport = (method: string, path: string, body?: object) => Promise<unknown>;
export class BattleRequestError extends Error {
    constructor(public readonly status: number, public readonly code: string, message: string) {
        super(message); this.name = 'BattleRequestError';
    }
}
interface PendingWrite {
    readonly profileId: string; readonly path: string; readonly body: Readonly<Record<string, unknown>>;
    readonly battleId: string | null;
    receipt?: { battleId: string; revision: number; events: readonly BattleEvent[] };
}
interface Summary { id: string; status: BattleStatus; createdAt: number; updatedAt: number; revision: number }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$/;
const PILES: readonly BattlePileZone[] = ['hand', 'draw', 'discard', 'exhausted', 'powerUsed', 'removed'];
const STATUSES = ['player-turn', 'won', 'lost'];
let requestSequence = 0;
function defaultRequestId(): string {
    requestSequence += 1;
    return `battle-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${requestSequence.toString(36)}`;
}
function invalid(): never { throw new BattleRequestError(0, 'INVALID_RESPONSE', '本地服务返回了无效战斗资料'); }
function object(value: unknown): Record<string, any> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) invalid();
    return value as Record<string, any>;
}
function text(value: unknown): string { if (typeof value !== 'string') invalid(); return value; }
function natural(value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): number {
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) invalid(); return value;
}
function uuid(value: unknown): string { const result = text(value); if (!UUID.test(result)) invalid(); return result; }
function binary64Hex(value: number): string {
    const bits = new DataView(new ArrayBuffer(8)); bits.setFloat64(0, value, false);
    const high = bits.getUint32(0, false), low = bits.getUint32(4, false);
    const sign = high >>> 31 ? '-' : '', exponent = (high >>> 20) & 0x7ff;
    const fraction = ('00000' + (high & 0xfffff).toString(16)).slice(-5) + ('00000000' + low.toString(16)).slice(-8);
    if (!exponent && !(high & 0xfffff) && !low) return `${sign}0x0.0p+0`;
    const power = exponent ? exponent - 1023 : -1022;
    return `${sign}0x${exponent ? 1 : 0}.${fraction}p${power < 0 ? '' : '+'}${power}`;
}
function tagged(input: unknown): void {
    const value = object(input);
    if (value.numeric_type === 'integer') {
        if (typeof value.decimal !== 'string' || value.decimal.length > 128 || !/^(?:0|[1-9][0-9]*)$/.test(value.decimal)) invalid();
    } else if (value.numeric_type === 'binary64') {
        if (typeof value.decimal !== 'string' || value.decimal.length > 64 ||
            !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(value.decimal)) invalid();
        const number = Number(value.decimal);
        if (!Number.isFinite(number) || number < 0 || binary64Hex(number) !== value.hex) invalid();
    } else invalid();
}
function array(input: unknown, max = 16384): any[] {
    if (!Array.isArray(input) || input.length > max) invalid(); return input as any[];
}
function amount(input: unknown): void {
    if (typeof input !== 'string' || input.length > 64 || !/^(?:0|[1-9][0-9]*)$/.test(input)) invalid();
}
function readEffects(input: unknown, enemy: boolean, statusRules: boolean): void {
    for (const entry of array(input, 32)) {
        const effect = object(entry);
        if (effect.type === 'draw' && !enemy) natural(effect.count, 0, 64);
        else if (effect.type === 'damage' || effect.type === 'shield' || (effect.type === 'heal' && statusRules)) {
            if (effect.target !== 'self' && effect.target !== 'opponent') invalid();
            amount(effect.amount);
        } else if (effect.type === 'breakdown' && statusRules) {
            if (effect.target !== 'opponent') invalid();
            natural(effect.stacks, 1, 999);
        } else invalid();
    }
}
function deepFreeze<T>(value: T): T {
    if (value && typeof value === 'object') {
        for (const key of Object.keys(value)) deepFreeze((value as any)[key]);
        Object.freeze(value);
    }
    return value;
}
// Responses are JSON from the injected transport. Copy before publishing so a
// transport/test owner cannot later mutate the view. This is not a JS sandbox.
function jsonCopy(input: unknown): any {
    try { return JSON.parse(JSON.stringify(input)); } catch { return invalid(); }
}
function readBattle(input: unknown, profileId: string, expectedId?: string): BattleRecord {
    const value = object(jsonCopy(input));
    const battleId = uuid(value.id);
    if (uuid(value.profileId) !== profileId || (expectedId && battleId !== expectedId)) invalid();
    natural(value.revision, 1); natural(value.createdAt); natural(value.updatedAt);
    const scenario = object(value.scenario), definition = object(scenario.definition), state = object(value.state);
    text(scenario.title); text(scenario.notice); text(definition.id);
    const statusRules = Object.prototype.hasOwnProperty.call(definition, 'statusRules');
    if (statusRules) {
        const rules = object(definition.statusRules), attack = object(rules.attack), stacks = object(state.breakdown);
        if (rules.policy !== 'breakdown-reconstruction-v1') invalid();
        for (const side of ['player', 'enemy']) { tagged(attack[side]); natural(stacks[side], 0, 999); }
    } else if (Object.prototype.hasOwnProperty.call(state, 'breakdown')) invalid();
    if (state.format !== (statusRules ? 'hczs-battle-session-v2' : 'hczs-battle-session-v1') ||
        state.definitionId !== definition.id || STATUSES.indexOf(state.status) < 0) invalid();
    natural(state.round, 1, 1000); natural(state.energy, 0, 1000000); natural(state.actionIndex, 0, 1000000);
    for (const side of ['player', 'enemy']) {
        const description = object(definition[side]), entity = object(state[side]);
        text(description.id); text(description.name); tagged(description.maxHp); tagged(entity.hp); tagged(entity.shield);
        if (Number(description.maxHp.decimal) === 0) invalid();
    }
    for (const key of ['initialDraw', 'roundDraw', 'handLimit']) natural(definition[key], 0, 64);
    natural(definition.energyPerRound, 0, 1000000); natural(definition.maxRounds, 1, 1000);
    if (state.round > definition.maxRounds || state.energy > definition.energyPerRound) invalid();
    if ((state.status === 'player-turn' && state.outcomeReason !== null) ||
        (state.status === 'won' && state.outcomeReason !== 'enemy-defeated') ||
        (state.status === 'lost' && state.outcomeReason !== 'player-defeated' && state.outcomeReason !== 'round-limit')) invalid();
    const rng = object(state.rng);
    if (rng.algorithm !== 'mulberry32-v1') invalid(); natural(rng.state, 0, 0xffffffff);
    const cards = object(definition.cards), knownInstances = new Set<string>();
    if (!Object.keys(cards).length || Object.keys(cards).length > 256) invalid();
    for (const key of Object.keys(cards)) {
        const card = object(cards[key]); text(card.name); natural(card.cost, 0, 1000000); readEffects(card.effects, false, statusRules);
    }
    const deck = array(definition.deck, 64), registry = array(state.cards, 64);
    if (!deck.length || registry.length !== deck.length) invalid();
    for (let index = 0; index < registry.length; ++index) {
        const item = registry[index], expected = object(deck[index]);
        const card = object(item); text(card.instanceId); text(card.cardId);
        if (card.instanceId !== expected.instanceId || card.cardId !== expected.cardId ||
            knownInstances.has(card.instanceId) || !Object.prototype.hasOwnProperty.call(cards, card.cardId)) invalid();
        knownInstances.add(card.instanceId);
    }
    const piles = object(state.piles), assigned = new Set<string>();
    for (const key of PILES) for (const cardId of array(piles[key], 64)) {
        if (typeof cardId !== 'string' || !knownInstances.has(cardId) || assigned.has(cardId)) invalid();
        assigned.add(cardId);
    }
    if (assigned.size !== knownInstances.size || piles.hand.length > definition.handLimit) invalid();
    const enemySkills = object(definition.enemySkills), skillIds = Object.keys(enemySkills);
    if (!skillIds.length || skillIds.length > 128) invalid();
    for (const key of skillIds) readEffects(object(enemySkills[key]).effects, true, statusRules);
    const intents = array(definition.enemyIntents, 1000).concat([definition.enemyFallback]);
    for (const intent of intents) {
        const skillOrder = array(intent, 16);
        if (!skillOrder.length) invalid();
        for (const id of skillOrder) if (typeof id !== 'string' || !Object.prototype.hasOwnProperty.call(enemySkills, id)) invalid();
    }
    return deepFreeze(value as unknown as BattleRecord);
}
function readEvents(input: unknown, battle: BattleRecord): readonly BattleEvent[] {
    const events = array(jsonCopy(input));
    const side = (value: unknown): void => { if (value !== 'player' && value !== 'enemy') invalid(); };
    const health = (event: Record<string, any>): void => {
        for (const key of ['previousHp', 'finalHp', 'previousShield', 'finalShield']) tagged(event[key]);
    };
    for (const item of events) {
        const event = object(item);
        switch (event.type) {
            case 'BreakdownChanged':
                if (!battle.scenario.definition.statusRules) invalid();
                side(event.actor); side(event.target); natural(event.previousStacks, 0, 999); natural(event.finalStacks, 0, 999);
                if (event.reason !== 'applied' && event.reason !== 'healed') invalid(); break;
            case 'BreakdownTriggered':
                if (!battle.scenario.definition.statusRules) invalid();
                side(event.actor); side(event.target); natural(event.stacks, 1, 999); amount(event.amount); break;
            case 'HealthRestored':
                if (!battle.scenario.definition.statusRules) invalid();
                side(event.actor); side(event.target); natural(event.effectIndex, 0, 31); amount(event.amount);
                tagged(event.restored); health(event); break;
            case 'BattleStarted':
                if (event.definitionId !== battle.state.definitionId) invalid(); natural(event.seed, 0, 0xffffffff); break;
            case 'TurnStarted': natural(event.round, 1, 1000); break;
            case 'CardPlayed':
                text(event.instanceId); text(event.cardId); natural(event.cost, 0, 1000000);
                if (!Object.prototype.hasOwnProperty.call(battle.scenario.definition.cards, event.cardId)) invalid(); break;
            case 'CardMoved':
                text(event.instanceId);
                if ((event.from !== 'hand' && event.from !== 'in-flight') || event.to !== 'discard') invalid(); break;
            case 'CardDrawn': text(event.instanceId); break;
            case 'DiscardRecycled':
                for (const id of array(event.order, 64)) text(id);
                natural(event.rngBefore, 0, 0xffffffff); natural(event.rngAfter, 0, 0xffffffff); break;
            case 'EnergyChanged': natural(event.previousValue, 0, 1000000); natural(event.finalValue, 0, 1000000); break;
            case 'DamageApplied':
                side(event.actor); side(event.target); natural(event.effectIndex, 0, 31); amount(event.amount);
                tagged(event.absorbed); tagged(event.hpLost); health(event); break;
            case 'ShieldAdded':
                side(event.actor); side(event.target); natural(event.effectIndex, 0, 31); amount(event.amount); health(event); break;
            case 'ShieldCleared': side(event.target); health(event); break;
            case 'EnemySkillUsed':
                text(event.skillId); natural(event.round, 1, 1000);
                if (!Object.prototype.hasOwnProperty.call(battle.scenario.definition.enemySkills, event.skillId)) invalid(); break;
            case 'BattleEnded':
                if (event.status !== 'won' && event.status !== 'lost') invalid();
                if (['enemy-defeated', 'player-defeated', 'round-limit'].indexOf(event.reason) < 0) invalid();
                natural(event.round, 1, 1000); break;
            case 'StateUpdated': readBattle({ ...battle, state: event.state }, battle.profileId, battle.id); break;
            default: invalid();
        }
    }
    return deepFreeze(events as BattleEvent[]);
}
function failure(error: unknown): BattleRequestError {
    return error instanceof BattleRequestError ? error : new BattleRequestError(0, 'NETWORK_ERROR',
        error instanceof Error ? error.message : '无法确认本地服务的响应');
}

export class TutorialBattleController {
    private value: BattleViewState = deepFreeze({ phase: 'idle', profileId: null, battle: null,
        message: '', pending: false, canRetry: false, events: [] });
    private generation = 0;
    private busy = false;
    private operation: 'read' | 'write' | null = null;
    private disposed = false;
    private readonly pendingWrites = new Map<string, PendingWrite>();
    private readonly records = new Map<string, BattleRecord>();
    private readonly usedRequestIds = new Set<string>();
    constructor(private readonly request: BattleTransport,
        private readonly onChange: (snapshot: BattleViewState) => void,
        private readonly requestIdFactory: () => string = defaultRequestId) {}
    get snapshot(): BattleViewState { return this.value; }
    private alive(generation: number): boolean { return !this.disposed && this.generation === generation; }
    private publish(change: Partial<BattleViewState>): void {
        if (this.disposed) return;
        this.value = deepFreeze({ ...this.value, ...change });
        // A rendering failure cannot turn a confirmed HTTP write into a retry.
        try { this.onChange(this.value); } catch { /* rendering is the host's responsibility */ }
    }
    private begin(message: string, operation: 'read' | 'write'): number {
        const generation = ++this.generation; this.busy = true; this.operation = operation;
        this.publish({ phase: 'loading', pending: true, canRetry: false, message, events: [] });
        return generation;
    }
    private finish(generation: number): void {
        if (this.alive(generation)) { this.busy = false; this.operation = null; this.publish({ pending: false }); }
    }
    private base(profileId: string): string { return `/profiles/${profileId}/battles`; }
    private remember(record: BattleRecord): BattleRecord {
        const old = this.records.get(record.id);
        if (old && old.profileId === record.profileId && old.revision > record.revision) return old;
        this.records.set(record.id, record); return record;
    }
    private async getBattle(profileId: string, id: string): Promise<BattleRecord> {
        const data = object(await this.request('GET', `${this.base(profileId)}/${id}`));
        return readBattle(data.battle, profileId, id);
    }
    private async latest(profileId: string): Promise<BattleRecord | null> {
        const response = object(await this.request('GET', this.base(profileId)));
        const summaries: Summary[] = array(response.battles).map(value => {
            const item = object(value);
            if (STATUSES.indexOf(item.status) < 0) invalid();
            return { id: uuid(item.id), status: item.status, revision: natural(item.revision, 1),
                createdAt: natural(item.createdAt), updatedAt: natural(item.updatedAt) };
        });
        // Server list uses created_at/id order. Select newest unfinished first;
        // with no unfinished battle, retain the newest completed one for review.
        summaries.sort((a, b) => a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        const active = summaries.filter(item => item.status === 'player-turn');
        const selected = (active.length ? active : summaries).slice(-1)[0];
        return selected ? this.getBattle(profileId, selected.id) : null;
    }
    async open(profileId: string): Promise<void> {
        if (this.disposed) return;
        if (this.value.profileId === profileId) {
            // Reopening can supersede an old read, but never start another write
            // or discard an in-flight/uncertain command for this profile.
            if (this.busy && this.operation === 'write') return;
            if (this.busy) { ++this.generation; this.busy = false; this.operation = null; }
            await this.load(true); return;
        }
        if (!UUID.test(profileId)) { this.publish({ phase: 'error', message: '档案编号无效', canRetry: false }); return; }
        // Profile changes supersede reads; outstanding writes remain retained per
        // profile. Returning to that profile still requires confirmation/retry.
        ++this.generation; this.busy = false; this.operation = null;
        this.publish({ profileId, battle: null, phase: 'idle', message: '', pending: false, canRetry: false, events: [] });
        await this.load(true);
    }
    async refresh(): Promise<void> { await this.load(false); }
    private async load(selectLatest: boolean): Promise<void> {
        const profileId = this.value.profileId;
        if (this.disposed || this.busy || !profileId) return;
        const command = this.pendingWrites.get(profileId), current = this.value.battle;
        const generation = this.begin('正在读取战斗存档…', 'read');
        try {
            const knownId = command?.receipt?.battleId || command?.battleId;
            const battle = knownId ? await this.getBattle(profileId, knownId) :
                !selectLatest && current ? await this.getBattle(profileId, current.id) : await this.latest(profileId);
            if (!this.alive(generation)) return;
            if (command?.receipt && (!battle || battle.revision < command.receipt.revision)) invalid();
            if (command?.receipt) this.pendingWrites.delete(profileId);
            const uncertain = this.pendingWrites.has(profileId);
            this.publish({ battle: battle ? this.remember(battle) : null, phase: uncertain ? 'uncertain' : 'ready',
                message: uncertain ? '已读取当前存档，但先前写入仍未确认；请重试原请求完成对账' : battle ? '已读取战斗存档' : '此档案还没有战斗，请显式开始新战斗',
                canRetry: uncertain, events: [] });
        } catch (error) {
            if (this.alive(generation)) this.publish({ phase: command ? 'uncertain' : 'error', canRetry: true,
                message: command ? '写入仍未确认，读取也失败；请重试原请求' : failure(error).message });
        } finally { this.finish(generation); }
    }
    private newId(): string {
        const id = this.requestIdFactory();
        if (typeof id !== 'string' || !REQUEST_ID.test(id) || this.usedRequestIds.has(id)) {
            throw new BattleRequestError(400, 'INVALID_REQUEST_ID', '无法生成新的请求编号，请刷新后重试');
        }
        this.usedRequestIds.add(id); return id;
    }
    private canWrite(): boolean {
        if (this.disposed || this.busy || !this.value.profileId) return false;
        if (this.pendingWrites.has(this.value.profileId)) {
            this.publish({ phase: 'uncertain', canRetry: true, message: '先前写入尚未确认，请先重试原请求或读取对账' }); return false;
        }
        if (this.value.phase !== 'ready') return false;
        return true;
    }
    async startNew(): Promise<void> {
        if (!this.canWrite()) return;
        if (this.value.battle?.state.status === 'player-turn') {
            this.publish({ message: '当前战斗尚未结束，请继续这场战斗', canRetry: false }); return;
        }
        const profileId = this.value.profileId!;
        try {
            const command: PendingWrite = { profileId, battleId: null, path: this.base(profileId),
                body: deepFreeze({ requestId: this.newId() }) };
            this.pendingWrites.set(profileId, command); await this.send(command);
        } catch (error) { this.publish({ phase: 'error', canRetry: false, message: failure(error).message }); }
    }
    async play(instanceId: string): Promise<void> { await this.action('play-card', instanceId); }
    async endTurn(): Promise<void> { await this.action('end-turn'); }
    private async action(type: 'play-card' | 'end-turn', instanceId?: string): Promise<void> {
        if (!this.canWrite()) return;
        const battle = this.value.battle, profileId = this.value.profileId!;
        if (!battle || battle.state.status !== 'player-turn') {
            this.publish({ message: '当前没有可操作的战斗', canRetry: false }); return;
        }
        if (type === 'play-card' && (typeof instanceId !== 'string' || battle.state.piles.hand.indexOf(instanceId) < 0)) {
            this.publish({ message: '这张卡牌不在当前手牌中', canRetry: false }); return;
        }
        try {
            const body = deepFreeze({ requestId: this.newId(), expectedRevision: battle.revision, type,
                ...(type === 'play-card' ? { instanceId } : {}) });
            const command: PendingWrite = { profileId, battleId: battle.id, path: `${this.base(profileId)}/${battle.id}/actions`, body };
            this.pendingWrites.set(profileId, command); await this.send(command);
        } catch (error) { this.publish({ phase: 'error', canRetry: false, message: failure(error).message }); }
    }
    async retry(): Promise<void> {
        if (this.disposed || this.busy || !this.value.profileId) return;
        const command = this.pendingWrites.get(this.value.profileId);
        if (command) await this.send(command);
        else if (this.value.canRetry) await this.refresh();
    }
    private async send(command: PendingWrite): Promise<void> {
        const generation = this.begin('正在提交战斗操作…', 'write');
        try {
            const response = object(await this.request('POST', command.path, command.body));
            if (!this.alive(generation)) return;
            const receipt = readBattle(response.battle, command.profileId, command.battleId || undefined);
            const events = readEvents(response.events, receipt);
            if (typeof response.replayed !== 'boolean') invalid();
            command.receipt = { battleId: receipt.id, revision: receipt.revision, events };
            // Even a successful retry can return a historic idempotency receipt.
            // Never publish it as current state; reconcile by GET first.
            const latest = await this.getBattle(command.profileId, receipt.id);
            if (!this.alive(generation)) return;
            if (latest.revision < receipt.revision) invalid();
            const current = this.remember(latest);
            this.pendingWrites.delete(command.profileId);
            this.publish({ phase: 'ready', battle: current, canRetry: false,
                message: current.revision > receipt.revision ? '操作已确认，已同步到更新的战斗状态' : response.replayed ? '原请求已确认，没有重复执行' : '战斗操作已保存',
                events: current.revision === receipt.revision ? command.receipt.events : [] });
        } catch (error) {
            if (!this.alive(generation)) return;
            const problem = failure(error);
            // Once POST is acknowledged, any failed follow-up GET keeps its
            // receipt for refresh; a GET 404 must not erase a committed command.
            if (command.receipt || problem.status === 0 || problem.status >= 500 || problem.status === 408) {
                this.publish({ phase: 'uncertain', canRetry: true, message: command.receipt
                    ? '操作已有收据，但最新状态尚未确认；请重试或读取对账'
                    : '服务响应未确认；请重试原请求，避免重复创建或扣费' });
            } else {
                this.pendingWrites.delete(command.profileId);
                if (problem.status === 409 && command.battleId) {
                    try {
                        const current = await this.getBattle(command.profileId, command.battleId);
                        if (this.alive(generation)) this.publish({ phase: 'ready', battle: this.remember(current), canRetry: false, events: [],
                            message: '战斗版本已变化，已读取最新状态；请重新选择操作' });
                    } catch {
                        if (this.alive(generation)) this.publish({ phase: 'error', canRetry: true, events: [],
                            message: '战斗版本冲突，最新状态读取失败；请刷新后再操作' });
                    }
                } else this.publish({ phase: 'error', canRetry: false, events: [], message: problem.message });
            }
        } finally { this.finish(generation); }
    }
    dispose(): void {
        if (this.disposed) return;
        this.disposed = true; ++this.generation; this.busy = false; this.operation = null;
        this.pendingWrites.clear(); this.records.clear(); this.usedRequestIds.clear();
    }
}
