import test from 'node:test';
import assert from 'node:assert/strict';
import { prologueBossIntention, prologueBossLimits, guide1001, prologueAvg138 } from '../src/prologue-source-rules.js';

test('the prologue boss follows the verified behavior-tree order and keeps target type 9 marked unresolved', () => {
  assert.deepEqual([1, 2, 3, 4, 5, 30].map(prologueBossIntention), [74503, 74501, 74502, 74503, 74502, 74503]);
  assert.equal(prologueBossLimits.damageTarget, 'unresolved-skill-target-type-9');
  assert.equal(prologueBossLimits.reconstructedDamageTarget, 'first-living-in-formation');
  assert.throws(() => prologueBossIntention(0), TypeError);
  assert.throws(() => prologueBossIntention(31), TypeError);
});

test('guide 1001 round-start copy stays separate from the worldline entry', () => {
  assert.equal(guide1001.separateFromWorldlineEntry, true);
  assert.equal(guide1001.originalCourseTrigger, 'unverified-false-stub');
  assert.equal(guide1001.mazeCondition.mazeId, 3997);
  assert.equal(guide1001.roundStartStep.trigger, 'T_BATTLE_ROUND_START');
  assert.equal(guide1001.roundStartStep.dialogue, '攻击类型的卡牌，在卡面上有“攻”的标识');
  assert.equal(guide1001.cardPlayedDetail.detail, 'D_OUT_CARD');
  assert.equal(guide1001.endRoundDetail.detail, 'D_END_ROUND');
  assert.equal(guide1001.unresolvedTriggerValue, 999);
  assert.equal(prologueAvg138.length, 9);
  assert.equal(prologueAvg138[0].text, '就是“这里”了吗？');
  assert.equal(prologueAvg138[6].voice, 'future_voice');
  assert.equal(prologueAvg138.at(-1).text, '打败我？那就试试看吧！');
});
