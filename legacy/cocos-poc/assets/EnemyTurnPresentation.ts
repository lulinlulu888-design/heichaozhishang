import type { BattleEvent, BattleState } from './TutorialBattleController';

export type PresentedAction = Extract<BattleEvent, { type: 'CardPlayed' | 'EnemySkillUsed' | 'BreakdownTriggered' }>;
export function actionSegments(events: readonly BattleEvent[]): { action: PresentedAction; events: readonly BattleEvent[] }[] {
    const starts: number[] = [];
    events.forEach((event,index) => {
        if (event.type === 'CardPlayed' || event.type === 'EnemySkillUsed' || event.type === 'BreakdownTriggered') starts.push(index);
    });
    return starts.map((start,index) => ({ action: events[start] as PresentedAction,
        events: events.slice(index === 0 ? 0 : start, starts[index+1] ?? events.length) }));
}

/** Replay only the committed prefix before the first enemy animation.
 * No damage arithmetic or authoritative changes; unknown prefixes use the old state.
 */
export function beforeEnemyAction(previous: BattleState, events: readonly BattleEvent[]): BattleState {
    let state = previous;
    for (const event of events) {
        if (event.type === 'EnemySkillUsed') return state;
        if (event.type === 'EnergyChanged') state = { ...state, energy: event.finalValue };
        else if (event.type === 'CardMoved') {
            if (event.from !== 'hand' || state.piles.hand.indexOf(event.instanceId) < 0) return previous;
            state = { ...state, piles: { ...state.piles,
                hand: state.piles.hand.filter(id => id !== event.instanceId),
                discard: [...state.piles.discard,event.instanceId] } };
        } else if (event.type === 'ShieldCleared' || event.type === 'DamageApplied' || event.type === 'HealthRestored') {
            state = { ...state, [event.target]: { hp:event.finalHp, shield:event.finalShield } };
        } else if (event.type === 'BreakdownChanged' && state.breakdown) {
            state = { ...state, breakdown: { ...state.breakdown, [event.target]: event.finalStacks } };
        } else if (event.type === 'BreakdownTriggered') {
            // Notification only; subsequent committed DamageApplied carries HP/shield.
            continue;
        } else return previous;
    }
    return previous;
}
