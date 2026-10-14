import { createBattle, playCard, endTurn, validateState, BattleDefinition, BattleEvent } from '../src/index.js';
import { float, int, toTagged } from '../../battle-core/src/index.js';
const definition: BattleDefinition = {
  id: 'synthetic-v1', player: { id: 'p', name: 'Player', maxHp: toTagged(float(1768.8)) },
  enemy: { id: 'e', name: 'Enemy', maxHp: toTagged(int(100)) },
  deck: [{ instanceId: 'c1', cardId: 'attack' }],
  cards: { attack: { name: 'Attack', cost: 1, effects: [{ type: 'damage', target: 'opponent', amount: '1' }] } },
  enemySkills: { wait: { effects: [] } }, enemyIntents: [], enemyFallback: ['wait'],
  initialDraw: 1, roundDraw: 1, energyPerRound: 1, handLimit: 1, maxRounds: 3,
};
const battle = createBattle(definition, 0);
const played = playCard(definition, battle.state, 'c1');
const saved = validateState(definition, JSON.parse(JSON.stringify(played.state)));
const next = endTurn(definition, saved);
function eventText(event: BattleEvent): string {
  return event.type === 'StateUpdated' ? event.state.player.hp.decimal : event.type;
}
next.events.map(eventText);
// @ts-expect-error HP carries an explicit Python numeric type, never an untagged string.
definition.player.maxHp = '1768';
// @ts-expect-error Saved output is immutable.
next.state.piles.hand.push('other');
