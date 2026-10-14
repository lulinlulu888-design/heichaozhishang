# 已恢复的战斗标量核心

入口为 `@hczs/battle-core`，ESM 实现位于 `src/index.js`，类型声明为 `src/index.d.ts`。无运行依赖，无 Node API，不执行原 APK 的脚本。它计算已经明确解析的数值依赖，不接受 cardId，不结算 HP、护盾、回合或卡组。

另有独立入口 `@hczs/battle-core/piles`，实现确定性牌堆操作。它不经过数值模块初始化、不要求 BigInt；无默认手牌上限、无隐藏随机数、无出牌合法性推断。依据与边界见 [牌堆与回合基础规则](../../docs/battle-foundation.md)。

```js
import { createPiles, drawCards, finishHandRound } from '@hczs/battle-core/piles';
const piles = createPiles({ hand: [], draw: ['card-instance-1'], discard: [],
  exhausted: [], powerUsed: [], removed: [] });
const drawn = drawCards(piles, 1, { handLimit: 10 }); // 10 是调用方明确选择的有效值
const ended = finishHandRound(drawn.piles,
  [{ cardId: 'card-instance-1', destination: 'discard' }]);
```

## 数值接口

```js
import { int, float, fromTagged, toTagged, classicDivide,
  calcDamage, counterRatio, RECOVERED_COUNTER_TABLE } from '@hczs/battle-core';

const exact = int('9007199254740993');
const half = classicDivide(float(100), int(200)); // binary64 0.5
const floored = classicDivide(int(100), int(200)); // integer 0
const ratio = counterRatio({
  srcType: int(1), dstType: int(2), allCounter: false,
  table: RECOVERED_COUNTER_TABLE,
}); // binary64 1.2，原始克制表

const wireValue = toTagged(exact);
// {numeric_type:'integer', decimal:'9007199254740993'}
const restored = fromTagged(wireValue);
```

`int` 接受十进制字符串、bigint 或安全范围内的整数 Number；超过安全范围的 Number 一律拒绝。`float` 只接受有限 binary64。内部 Scalar 是工厂创建的不可变对象，不能直接用裸 Number、对象强制转换或 JSON.parse 后的结构体冒充。JSON 边界必须逐值 `fromTagged/toTagged`；不要直接 JSON.stringify 含 bigint 的 Scalar。

整数加减乘和整数经典除法使用原生 BigInt；两整数除法向负无穷取整，`truncate(float)` 向零截断。混合运算在原 Python 会进入浮点运算的位置转换为 binary64，这时允许按 Python 语义舍入。比较整数与浮点数时不先舍入整数。保留每一步运算顺序和中途 `int()`，包括 `1 - 0.9` 得到的值，不把它改写成 `0.1`。

`toTagged(float)` 写出最短可往返十进制及精确 Python 风格 hex；其十进制排版可能与 Python repr 不同，例如指数前导零。`fromTagged` 检查 decimal 和 hex 表示同一 binary64，保留负零和次正规数。非有限浮点、浮点溢出和除零明确拒绝；未声称恢复原 Python 的 NaN/Infinity 传播行为。

## 公式入口与依赖

`calcDamage(snapshot)` 返回 `{damage, trace}`：最终 damage 是整数 Scalar，trace 是各阶段名称与带类型数值的不可变列表。snapshot 字段与 `analysis/battle-parameters/scalar-vectors.json` 一致：基础动作值、额外基础攻击、攻击类型、克制、防御、攻击/受击 buff、暴击倍率、通用/物理/魔法增减伤、等级倍率、尾部额外值，以及 PVP/预览分支的标志和值。详见 `DamageSnapshot` 声明。

只有当前分支实际读取的依赖必须存在。比如真实攻击跳过克制、防御、buff 和暴击，但仍经过后续倍率与额外值；PVP 开启后缺少 pvpAtkRatio 会抛错。未启用分支不要求虚构占位值。错误不会默认填 0 或 1。

`extraAttackedValue` 必须是“加过 extraAttackValue 后的中间伤害”对应的依赖结果；`slowHp` 必须对应 PVP 后的中间伤害。当前 API 消费这一次调用的已解析快照，不会替调用方寻找实体方法、缓存系数或假定这些依赖与中间伤害无关。

其他入口：

| 函数 | 已恢复范围 |
| --- | --- |
| `calcBlock({basicBlock,source,card,target})` | 7042:11 的护盾标量公式，返回 `{block,trace}`，不直接修改实体护盾 |
| `overwhelmRatio({srcIsPlayer,dstIsPlayer,lvDiff,disabled})` | 7042:8 的等级压制分段；lvDiff 由调用方提供 |
| `counterRatio({srcType,dstType,allCounter,allRatio,table})` | 3510:27/28；OTHER_WORLD=7 全克制例外；两次 if 的覆盖顺序 |
| `defenseRatio({attack,defense,penetration})` | 7042:9；调用方已选择物理/魔法防御；保留经典除法 |
| `basicActionValue({basicDamage,improvement})` | 7042:10；improvement 为明确的 null 或 factor/property/base 三值 |
| `addAttackValue(...)` | 7554:5.0；百分比额外基础攻击中途截断 |
| `attackFactorValue(...)` / `attackedFactorValue(...)` | 7554:5.9/5.4 和 5.8/5.5；两种 common 因子单位不同 |
| `propertyValue({base,modifiers,isPropAtk})` | 7554:5.12/13/14 的已解析属性值与有序 modifier；仅攻击下限 0 |
| `criticalOutcome(...)` | 7042:4；调用方提供 draw，两个区间端点含等号，无随机生成 |

有序数组必须保留源端迭代顺序。helpers 里的 cardFactor/battleFactor 等均是已解析值；若确定没有相关对象，由调用方明确传入经过证据支持的零值。`criticalOutcome` 不会自动接到 `calcDamage`，因为尚未证明这条调用链。缺失克制行返回 100/100.0、缺失行内 ratio 默认 100 是原函数明确规则，并非对未恢复系数的猜测。

## 护盾公式与调用参数绑定

`calcBlock` 要求显式的基础值、施放者（或 null）、卡牌（或 null）及目标依赖。施放者属性与目标属性分别除以 `1000.0` 后乘入；盾因子按 `((1 + sourceFactor) + targetFactor) + cardPercent/100.0` 相加，再乘基础值。卡牌附加盾随后加上，PVP 倍率最后乘入，返回 `int(max(0,value))`。其下限是0，与伤害公式的下限1不同。目标必须存在，因为原函数末段无条件读取 `dstEntity.battleInst`。

原调用有一个必须保留的细节：辅助函数实际签名是 `_calcRpgBasicActionValue(basicValue, srcEntity, strengthFactor=None, cardObj=None)`，而 `calcBlock` 只传 `basicBlock, srcEntity, cardObj` 三个位置参数。因此第三个值绑定到未使用的 strengthFactor，辅助函数的 cardObj 保持 None，卡牌强化不会进入护盾基础值。本实现不读取 improvement，也不擅自修复原包这一疑似调用错误。伤害函数传入四个参数，其强化路径不受影响。

默认值证据位于7042模块体 `[0x6a,0x79)`；护盾调用为 `[11]@0x12 CALL_FUNCTION 3`，伤害调用为 `[7]@0x7a CALL_FUNCTION 4`。新增 `tools/trace_shield_formula.py` 锁定模块及函数摘要，并生成17组人工翻译的 Python 合成对照，每一步比较整数/浮点类型及 binary64 位值。20项护盾测试另覆盖缺失依赖、无强化读取、负零和输出不可变。此处没有恢复实体属性提供者或 `addShieldHp` 的完整状态转移。

## Cocos 与运行时边界

运行时代码使用 `BigInt(...)`，没有 BigInt 字面量、Node 内置模块或网络 API。代码中的原生 BigInt 是必需能力；不支持时在模块初始化就明确抛错。仅把 TypeScript target 降低不会提供 BigInt polyfill，也不会让旧 JS 引擎安全运行本包。

本机实际核查：

- `clients/cocos-poc/temp/tsconfig.cocos.json` 当前 target/module 均为 ES2015，isolatedModules=true。本包提供已写好的 JS + d.ts，避免 TypeScript 对低 target 下 BigInt 字面量的限制；消费端只用 `int('...')`，不需要写字面量。
- `.tools/cocos/3.8.8/resources/resources/3d/engine/native/external/win64/include/v8/v8-version.h` 为 V8 11.6.189.22；同目录 `v8-primitive.h` 含 `v8::BigInt`。已有 Windows 原生日志 `analysis/cocos-native/run-windows-proof.stdout.log` 同样记录 V8 11.6.189.22。
- Android arm64 本机 V8 头文件版本也为 11.6.189.22。头文件与已有窗口运行日志不是本包的原生数值测试。

已复用 Creator 本机附带的 TypeScript 5.8.2，通过 ES2015 target/module、strict、isolatedModules 的消费端类型检查（含错误输入的拒绝断言），没有新增编译器依赖。复现命令：

```powershell
node .tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/tsc.js --target ES2015 --module ES2015 --moduleResolution node --strict --isolatedModules --noEmit packages/battle-core/typecheck/consumer.ts
```

本轮只认证 Node 中的公式与类型行为。尚未在 Cocos 原生 Windows/Android 实际运行本包向量，macOS/iOS 尚未验证；不能据此声称四端战斗结果已经一致。后续接入 Cocos 时需要配置包解析或拷入 ESM 源码并运行同一组向量，特别检查 BigInt、binary64 和跨 JS/native 序列化；不得将 bigint 直接交给 native bridge，跨边界使用 tagged JSON。暂未更改客户端。

## 证据与验证

追加 `rpgPropertyPercent`：移植 GetRpgProps 节点的已解析属性×百分比/100.0，再按 method=0 向下取整、1向上取整、其他整数不取整。可与已有 `propertyValue` 合成分解状态的 extraDamage 输入；不负责事件、层数更新、伤害归属或最终扣血。独立 Python 的11组向量覆盖负数、浮点、大整数和取整差异，另有组合及依赖校验2项。生成入口 `tools/trace_city_breakdown_buff.py`；没有将合成样本当作原版实战记录。

```powershell
pnpm test:battle
```

测试直接读取当前工作区 `analysis/battle-parameters/scalar-vectors.json` 中全部 40 项 Python 独立翻译期望，包含 8 个伤害快照的每步 typed trace、经典除法、等级边界、克制和给定采样值的暴击/格挡分支。另验证超过 2^53、负整数除法、输入缺失、顺序差异、负零/次正规数和运行时能力拒绝。

这 40 项来自 `tools/trace_battle_parameters.py` 的独立、人工审查翻译，是合成输入，不是原版战斗录制。生成器锁定 17 个源模块 SHA256；完整函数 index、constant path、bytecode SHA256 和偏移在 `analysis/battle-parameters/function-sources.json`、`calculation-contract.json`。克制表的 7 个数值行来自 index 8750，包内数值逐行与原导出对照；图标和文案没有放入核心。

需要先有该项目的静态恢复证据产物才能运行这些测试；包运行本身不读 analysis 或 APK。原 `cardAction` 构造、`getRpgValue`、动态 card/entity 方法、PVP 赋值、随机状态、护盾/扣血和整场战斗仍是明确未恢复边界。
