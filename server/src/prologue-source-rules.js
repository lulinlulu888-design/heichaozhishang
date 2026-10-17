/** Pinned prologue rules.
 * Battle 1703 damage target type 9 has no recovered caller; prologue-boss.js plays it only
 * under the labelled first-living-in-formation reconstruction.
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
  reconstructedDamageTarget: 'first-living-in-formation',
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

/** Spoken text of dialogue 138, source rows 120-128. The #f(z:0) and #l markup is not part of the spoken line. */
export const prologueAvg138 = Object.freeze([
  ['ailisha_voice', '就是“这里”了吗？'],
  ['mxt_vo', '哦？来人了？没想到，在这最后的时刻，还能拥有演出的机会。'],
  ['mxt_vo', '你们是特意来到这特等席，观赏第三次黑潮的壮丽景象的吗？还是，来阻止的呢？'],
  ['ailisha_voice', '第三次黑潮，并不是什么壮丽景象，它就是一场灾难。'],
  ['ailisha_voice', '这场灾难已经吞噬了琳、诺、瓦列莉亚和佐伊……我不会再让它吞噬更多的人……'],
  ['mxt_vo', '哦，看来是后者了。就凭你们两个人，也想阻止黑潮吗？'],
  ['future_voice', '我们没有选择。'],
  ['ailisha_voice', '是的，我们没有选择，无论如何，我们都必须打败你！'],
  ['mxt_vo', '打败我？那就试试看吧！'],
].map(([voice, text]) => Object.freeze({ voice, text })));
