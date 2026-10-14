# @hczs/battle-session

可逐回合推进并保存为 JSON 的重建战斗状态机。提供纯 ESM 和 TypeScript 声明，无引擎、Node、时间或全局随机数依赖。数值依赖同仓 `battle-core`（源码相对 import），因此**运行时需要原生 BigInt**；HP/盾在公共接口中使用 TaggedScalar，跨 JSON 不携带 bigint。

这是新项目明确选择的一套最小规则，不声称恢复了原服调度、伤害穿盾、随机数、Buff 优先级或完整技能图。调用方负责从已恢复数据和公式装配 definition；本包不包含原卡牌、怪物数值或默认难度。本次测试只有合成定义。

## 接口

```js
import { createBattle, playCard, endTurn, validateState } from './src/index.js';

// definition 必须由调用方提供，不能省略初始/回合抽牌数、能量、手牌与回合上限。
const initial = createBattle(definition, 123); // seed 是 [0, 2^32-1] 内的整数。
const played = playCard(definition, initial.state, initial.state.piles.hand[0]);
const next = endTurn(definition, played.state);
const savedJson = JSON.stringify(next.state);
const resumed = validateState(definition, JSON.parse(savedJson));
// 下一次操作继续使用同一版本的 definition 和 resumed。
```

`createBattle / playCard / endTurn` 均返回 `{state, events}`。输入不修改，返回图递归冻结；任何参数、状态或效果计算错误均抛出，调用方只在成功返回后提交新状态。没有副作用回调。`validateDefinition` 返回校验后的不可变定义，`validateState` 返回校验后的不可变存档副本。

入口和精确字段见 `src/index.d.ts`。根工作区/服务器/客户端集成由调用方处理；本目录不提供网络接口或持久化 IO。

## 定义和存档

状态扩展通过可选 `statusRules` 显式启用，政策名必须为 `breakdown-reconstruction-v1`，同时提供 `attack.player/enemy` 两个已解析 TaggedScalar 攻击值。它生成 `hczs-battle-session-v2`，存档增加 `breakdown: {player, enemy}`；没有 statusRules 的定义与旧 v1 存档保持原行为，不能混用两个格式。

服务端持久化补充验证：`node --test server/test/status-persistence.test.js` 通过2项真实SQLite集成检查，包括关闭连接后由新Node进程继续、治疗/结算重试幂等、场景快照隔离、写入失败原子回滚。使用合成定义，不更改本地正在运行的首战服务。Cocos控制器源码已支持v2数据校验，`node tools/test_status_client.mjs` 通过真实状态机/合成传输检查；图标、状态事件演出顺序与浏览器/原生运行尚未验证，不能视作图形关卡验收。

v2 新增 `breakdown`（只对 opponent，增加1..999层，累计上限999）及 `heal` 效果。一次正的实际生命恢复减1层，零恢复或满血不减；治疗不超过最大生命，盾不变。每个持有者回合结束结算：玩家在弃牌前，敌人在技能序列后。数值为 `floor(配置的施加者攻击 × (当前层数 × 20) / 100.0)`，经现有盾/HP结算，致死立即停止后续操作。原始攻击数值从定义的不可变快照取得，当前不支持动态攻击Buff或同阵营多个施加者。

**这些调度、治疗筛选、盾/HP结算及单来源合并是显式重建政策，不是恢复的原服事件系统。** 百分比/取整节点有源脚本证据，但完整原 fakeMultiDamage 仍缺失。新事件为 BreakdownChanged、BreakdownTriggered、HealthRestored；尚未开放到现有 Cocos 首战入口或宣称城市关卡可玩。6项新增测试覆盖JSON续战、治疗、盾、双方致死顺序、上限及格式拒绝；旧19项仍通过。

客户端表现分段已将 BreakdownTriggered 与 CardPlayed/EnemySkillUsed 分开；分解在自己的事件段提交生命变化，不调用角色攻击动画。`tools/test_enemy_turn_presentation.mjs` 使用真实状态机结果验证“玩家状态→敌技能→敌状态”的伤害归属及致死状态独立分段。Web已重新构建，`node tools/test_status_client.mjs --compiled` 和原15组 Creator 控制器集成检查通过；仍未验证浏览器状态效果、层数图标和原版演出。

definition 的所有字段都必需：

| 字段 | 内容 |
| --- | --- |
| `id` | 规范化、不可变版本的定义 ID。修改规则或参数时应更换 ID。 |
| `player / enemy` | `{id, name, maxHp}`；双方 ID 不同，maxHp 为正的 TaggedScalar。 |
| `deck` | 1–64 个 `{instanceId, cardId}`，按此顺序初次抽牌；不硬编码某关的七张牌。 |
| `cards` | cardId 映射到 `{name, cost, effects}`。多个实例可引用相同牌型。 |
| `enemySkills` | skillId 映射到 `{effects}`。 |
| `enemyIntents` | `string[][]`；索引 0 是第 1 回合，每项是该敌回合按顺序执行的技能 ID 列表。 |
| `enemyFallback` | 显式后续技能 ID 列表；意图表用完后每回合使用它。每个意图列表非空；等待可建一个 `effects:[]` 技能。 |
| `initialDraw / roundDraw / energyPerRound / handLimit / maxRounds` | 明确的有效值，不从旧常量或卡名推断。 |

effects 保持列表顺序：

- `{type:'damage', target:'self'|'opponent', amount:'123'}`。
- `{type:'shield', target:'self'|'opponent', amount:'123'}`。
- `{type:'draw', count:2}`，仅玩家卡牌支持；没有敌牌库模型，敌技能 draw 明确拒绝。

damage/shield amount 必须是规范非负整数文本，计算时用 `battle-core.int`；HP 和盾保持整数或 binary64 类型。例如 `1768.8` 的 maxHp 使用 core.toTagged(core.float(1768.8))，不会预先取整。混合算术、比较和加减复用 core，不另外实现一套浮点/大整数规则。不支持治疗、复活、动态增卡、移除/湮灭、额外费用或多单位目标。

完整存档字段为：

```text
format: 'hczs-battle-session-v1'
definitionId
round
status: 'player-turn' | 'won' | 'lost'
outcomeReason: null | 'enemy-defeated' | 'player-defeated' | 'round-limit'
energy
player/enemy: {hp: TaggedScalar, shield: TaggedScalar}
cards: [{instanceId, cardId}]          // 固定为 definition.deck registry 及顺序
piles: {hand,draw,discard,exhausted,powerUsed,removed} // 每区为实例 ID 列表
rng: {algorithm:'mulberry32-v1', state:uint32}
actionIndex                         // 创建时为0，每次成功出牌/结束回合加1
```

每个实例必须且只能属于一个区，未知、重复、遗漏实例均拒绝。当前规则仅使用 hand/draw/discard，其余三个区必须显式为空，为以后扩展保留名称，不表示已实现对应规则。存档校验同时检查定义 ID、版本、HP 上限、数值类型、手牌/能量/回合界限和终态一致性。

验证是结构和当前状态一致性检查，**不是存档签名或历史真实性证明**；它无法证明 HP、随机状态等来自真实操作序列。不能更改 definition 内容却复用同一 ID。可信定义版本选择、用户存档归属、请求幂等与持久化事务由外层负责。

## 明确的重建规则

1. 创建：第 1 回合，双方满 HP、零盾、显式初始能量，从 deck 头部抽 initialDraw 张，最多 handLimit。初始不洗牌，也不消耗 PRNG。
2. 出牌：必须处于玩家回合、实例在手且能量足够。先扣费，将牌移到本次调用内部的 in-flight 位置，再按顺序执行 effects；最后进弃牌。此牌不会被自己同次 draw 效果抽回。即使某效果结束战斗，该牌仍进入弃牌以保持实例完整。
3. 伤害：先消耗目标盾，再扣 HP，HP 最低为零。一个效果导致敌人死亡立即获胜；玩家死亡立即失败。停止余下效果/技能，不额外执行死亡奖励。
4. 结束回合：按当前手牌顺序全部弃牌 → 清敌人旧盾 → 执行该轮敌方意图。
5. 若仍存活且未到 maxRounds：round 加 1 → 清玩家旧盾 → 重置能量 → 发出回合开始事件 → 抽 roundDraw 张。敌人本回合新获得的盾保留到其下次回合开始。
6. 已到 maxRounds 时仍先执行该轮敌人行动；若未结束战斗则判 `round-limit` 失败，不再重置能量或抽牌。最后敌回合内发生胜负优先于上限判负。
7. 终态拒绝任何后续出牌或结束回合。

空牌库不会造牌；有弃牌时才回填。手牌已达上限时停止抽牌，不洗牌或消耗 PRNG。回填使用 mulberry32-v1 的 32 位整数状态和从尾向前 Fisher–Yates。每个索引通过 uint32 rejection sampling 选择：拒绝不满整数倍范围，再取模；不是 `Math.random`，也不是原游戏 RNG 的恢复结果。

seed=0、牌堆 `[i1,i2,i3,i4]` 的第一次回填为 `[i4,i1,i2,i3]`，PRNG 状态为 `1199730143`；将该手牌顺序弃回后，第二次为 `[i2,i1,i3,i4]`，状态为 `2399460286`。测试用独立的 Python 无符号32位计算核对这组序列。

## 事件与接入

所有事件都是新 DTO，严格按执行顺序返回。事件种类：BattleStarted、TurnStarted、CardPlayed、CardMoved、CardDrawn、DiscardRecycled、EnergyChanged、DamageApplied、ShieldAdded、ShieldCleared、EnemySkillUsed、BattleEnded、StateUpdated。

HP/盾事件包含 previousHp/finalHp/previousShield/finalShield；伤害还有 amount、absorbed、hpLost，后两者为 TaggedScalar。能量事件含 previousValue/finalValue。回填事件记录排列和前后随机状态。每次成功操作的最后一个事件固定为 `{type:'StateUpdated',state}`，含完整最终 HP、盾、牌堆、能量和随机状态；可直接持久化或交给客户端归一化层。effects 的 effectIndex 是所在卡牌/技能内的零基索引；并非旧协议动作编号。

CardPlayed 代表该实例进入本次操作的 in-flight 状态，随后 CardMoved 回到 discard。最终存档从不含 in-flight 区，不暴露可恢复的半次结算；客户端若逐事件播放，应保留独立的接收快照与可见状态。

## 输入上限与验证

规范 ID 为 1–128 位 ASCII，首位字母/数字，后续允许字母/数字/点/下划线/冒号/横线；名称允许 1–128 字符，不含控制字符。只接受普通数据记录和普通密集数组，拒绝未知字段、getter、数组子类、自定义迭代器、稀疏数组；不是任意 JavaScript Proxy 的沙箱。

`LIMITS`：64 实例、256 卡定义、128 敌技能、每项32效果、每轮16技能、1000回合、1000000能量及动作次数；抽牌/手牌上限均为64；效果整数最长64位，HP/盾整数最长128位，浮点必须有限且 decimal/hex 一致。超限拒绝，不静默裁剪参数或猜默认值。上游仍应设置 JSON 请求体字节上限。

## 验证范围

```powershell
node --test packages/battle-session/test/session.test.js
node .tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/tsc.js --target ES2015 --module ES2015 --moduleResolution node --strict --isolatedModules --noEmit packages/battle-session/typecheck/consumer.ts
```

19项测试覆盖实际胜负推进、护盾和多段伤害、角色相对目标、最终回合限制、抽牌/回填、洗牌黄金序列、存档续玩一致性、异常原子性、非法存档、精确大整数和小数 HP。类型消费检查通过。当前认证 Node 行为及现有 TypeScript 编译器接口检查，未运行 Cocos UI，也未验证四端原生执行；ES2015 target 不会给客户端补出 BigInt。
