// Explicit allowlist for isolated test evidence. Never record whole responses,
// request headers, auth material, profile data, or arbitrary nested event fields.
export function projectVisualTimingReceipt(result) {
  const fields=['type','actor','target','effectIndex','cardId','instanceId','skillId','status','reason'];
  const types=new Set(['CardPlayed','DamageApplied','BattleEnded','EnemySkillUsed']);
  const events=Array.isArray(result?.events)?result.events:[];
  if(events.length>128)throw Error('Test receipt event bound exceeded');
  const receiptEvents=events.filter(event=>types.has(event?.type)).map(event=>Object.fromEntries(fields
    .filter(key=>Object.hasOwn(event,key)&&((typeof event[key]==='string'&&event[key].length<=128)||
      (key==='effectIndex'&&Number.isSafeInteger(event[key])&&event[key]>=0)))
    .map(key=>[key,event[key]])));
  const battleStatus=result?.battle?.state?.status;
  if(!['player-turn','won','lost'].includes(battleStatus))throw Error('Invalid isolated receipt battle status');
  return {receiptEvents,battleStatus};
}
