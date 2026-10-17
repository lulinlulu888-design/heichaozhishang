/** Pinned prologue rules that are safe to name and unsafe to play.
 * Battle 1703 stays out of the encounter directory: damage target type 9 has no caller.
 * Guide 1001 stays off the worldline button: its original course trigger is a false stub,
 * and trigger value 999 is outside GuideTriggerType. */

export function prologueBossIntention(round) {
  if (!Number.isSafeInteger(round) || round < 1 || round > 30) {
    throw new TypeError('prologue boss round is outside MaxRoundFail');
  }
  // Selector order in bt/xinshou_zhongyanshizhe.xml: round 1, round 2, then odd, then even.
  if (round === 1) return 74503;
  if (round === 2) return 74501;
  return round % 2 === 1 ? 74502 : 74503;
}

export const prologueBossLimits = Object.freeze({
  battleId: 1703,
  monsterId: 2013,
  maxRoundFail: 30,
  party: Object.freeze([{ characterId: 1, level: 100 }, { characterId: 3, level: 100 }]),
  damageTarget: 'unresolved-skill-target-type-9',
  executable: false,
});

export const guide1001 = Object.freeze({
  groupId: 1001,
  name: '序章-第一场战斗',
  mazeCondition: Object.freeze({ type: 'MazeId', mazeId: 3997 }),
  separateFromWorldlineEntry: true,
  originalCourseTrigger: 'unverified-false-stub',
  roundStartStep: Object.freeze({
    id: 1851,
    trigger: 'T_BATTLE_ROUND_START',
    dialogue: '攻击类型的卡牌，在卡面上有“攻”的标识',
    gesture: 'not-imported',
  }),
  cardPlayedDetail: Object.freeze({ id: 1852, detail: 'D_OUT_CARD' }),
  endRoundDetail: Object.freeze({ id: 1857, detail: 'D_END_ROUND' }),
  unresolvedTriggerValue: 999,
});
