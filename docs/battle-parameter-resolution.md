# 战斗参数覆盖与标量移植边界

已恢复技能参数的读取/覆盖顺序，以及 `calcDamage` 的完整数值运算顺序和直接依赖。可以据此移植一个要求显式提供依赖值的 Node 标量核心；目前仍不能从一张卡牌 ID 独立算出原版扣血。最关键的缺口是 `cardAction` 的实际构造者、`diyActionData` 的赋值和 `getRpgValue` 的实现。

本轮没有重新进行上一轮的 native 名称搜索，也没有运行 APK、UI 或任何游戏字节码。原 marshal 只解码为普通字典；标量验证函数是人工翻译的独立 Python 函数，不是原游戏解释器。

## 复现与机器可读产物

```powershell
python tools/trace_battle_parameters.py
```

工具检查 17 个涉及人工语义结论的模块版本 SHA256，并验证每个实际读取模块的完整 marshal、文件名和解密 SHA256。版本改变时拒绝沿用本轮结论。输出在 `analysis/battle-parameters/`：

- `function-sources.json`：60 个函数/类体/模块体的模块 index、NPK offset、constant path、bytecode SHA256、字段读取偏移、保留原数值类型的常量。
- `*_instructions.json`：选定函数的部分静态反汇编。UNKNOWN 指令仍保留，不将未知指令执行或猜成已确认操作。
- `parameter-chains.json`：升级链、已证明的参数覆盖边、尚未证明的构造边。
- `cards-with-upgrades.json`、`skill-states.json`、`counter-types.json`：有逐行/字段偏移的原始字面量数据。
- `calculation-contract.json`：伤害流水线、每步偏移、依赖来源、数值语义及外部边界。表达式是审查用声明，不是可直接执行的脚本。
- `scalar-vectors.json`：40 个检查，包含 8 组伤害流程向量、缺失依赖拒绝、经典除法、等级压制边界、克制关系和给定随机采样值的暴击/格挡分支。
- `new-boundary-search.json`：只针对本轮新增的参数/系数边界检查直接名称、赋值、字面量；不据此证明动态提供方不存在。

偏移均相对对应 code object，范围的末端不包含在内；用 `index:constant.path` 引用 `function-sources.json`。样本数值是合成输入，不能作为某张卡牌的原版伤害记录。

## 参数覆盖链已经证明的部分

`common/common_storyline.py`，index **618**，`BaseServiceCardActionSL.__init__` `[24,0]`，在 `[0x16,0x23)` 保存调用方传入的 `cardAction`。`setCardContext` `[24,2]` 把它和它的 `cardObj` 放入效果图上下文。这个模块消费已构造对象，没有恢复其实际构造器。

`getCardParamList` `[24,3]` 证明如下顺序：

1. `[0x6,0x33)`：读取 `cardAction.actionData.STORYLINE_PARAM._data`；字段为 None 时使用空字典。
2. `[0x4c,0x89)`：每个默认参数若在非 None 的 `diyActionData` 中存在同名键，改用该值。比较的是键是否存在，数值 **0 不会当成缺失**。
3. `[0x89,0xff)`：根据覆盖后的值生成 `int`、`float`、`str` 参数。顺序先检查 Python 2 `int`，因此 bool 也落在该分支；没有在这段代码中检查 Python 2 `long`。
4. `[0x100,0x15d)`：DIY 中不在默认参数中的键也加入列表，类型标签固定写为 `int`，此处没有执行 `int(value)` 转换。
5. 后续追加 `card/entity/cardObj`。`SServiceCardActionSL.getParamList` `[26,4]` 再追加 times、player、target 与 sharedData；重复参数最终如何处理属于图运行器的另一层，不能简单推成字典最后写入覆盖。`CServiceCardActionSL` 是同模块的另一个类体 `[36]`。

这证明“若 `diyActionData` 含 VALUE=0，则该图的默认 VALUE=1 会被覆盖为 0”。但目前没有证据证明 **卡表的 DIY 列表实际由哪个构造器转换为该字典**，所以不能把条件推论写成已经恢复出的运行行为。

`SKILL_DIY_PARAMETER/VALUE` 在普通卡牌路径可见的明确消费者是 `common/gm_debug/gm_basic.py`，index **8527**，`findRelation` `[507]`：`[0x27c,0x2d1)` 按同下标建立参数字典；`[0x333,0x37d)` 覆盖效果图参数；`[0x37d,0x391)` 把结果交给关系图的 `ConnectSL`。这是 GM 关系分析用途，不能用来证明实际战斗构造采用相同实现，也不能反过来断言 DIY 字段仅供编辑器使用。

`athlete_utils.getCharSpecialSkillDiyDataDict`（index **5973**，`[80]`）读取的是另一张 `speciall_skill_table`，可对其中 callable 值调用 `v(1)`；`iCAvatarSpecialSkill.getStaticSpecialSkillDiyData`（index **9422**，`[3,2]`）会调用它。这里仅静态记录调用，没有求值，也没有把特殊技能的数据结构套到普通卡牌。

## skillTableAdapter 不负责恢复缺失的覆盖策略

`common/skillTableAdapter.py`，index **8010**：

- `getSkillData` `[358]` 用 skill ID 查询 `skill_table`，交给 `OuterAdapter`。
- `OuterAdapter.__getattr__` `[355,1]` 对 `SKILL_STATE_TIMELINE` 委托 `getSkillStateData`，其余字段来自技能表行。
- `getSkillStateData` `[357]` 使用 `skill_state_table.extra_data[skillID]` 的行 ID 列表，再逐行包装。
- `Adapter.__getattr__` `[353,1]` 的优先级是：行顶层同名字段 → `DATA` 子表同名字段 → None。只有字段 `TYPE` 会经 typeDict 转换；`RPG_FORMULA`、`RPG_DEFAULT_FORMULA` 等字符串按原值返回，未观察到在此处按卡等级、DIY 或战斗模式重写。

`data_reader.DataTable.get`（index **4057**，`[25,12]`）在 `_RUNTIMEARGS` 为空时返回原行；非空才走 `AdditionalDict/CreateAdditonalDict`。本轮 6 个卡牌行和 4 个技能状态行没有 `_RUNTIMEARGS`。技能状态读取实际用 `__getitem__` `[25,13]`，这条路径直接取原行，不经过 `.get` 的运行时参数分支。它们仍是当前包内静态快照，不能排除启动后的表替换或外部对象覆盖。

## 卡等级、升阶和模式

升级 ID 取自明确的 `NEXT_LEVEL_ID`，不是按 ID 算术推断。`combatUtils.getNextLevelCardID`（index **3510**，`[14]`）也直接读取该字段。

| 卡牌 ID / LEVEL | skill ID | DIY 参数 | AP 展示默认值 |
| --- | --- | --- | --- |
| 410101 / 1 | 410101 | FACTOR=75 | 75 |
| 610101 / 2 | 410101 | FACTOR=100 | 100 |
| 810101 / 3 | 410101 | FACTOR=125 | 125 |
| 410102 / 1 | 410102 | FACTOR=300、VALUE=0 | 300 |
| 610102 / 2 | 410102 | FACTOR=300 | 300 |
| 810102 / 3 | 410102 | FACTOR=400 | 400 |

两条链的末端均为 `NEXT_LEVEL_ID=-1`。对应 skill ID 未随卡等级改变，技能状态 368 仍保留 `RPG_DEFAULT_FORMULA="200"`，367 保留 `VALUE=1`。这些数据支持存在覆盖层的分析方向，但缺少构造链时，不能选择 200/300/400 之一充当实际伤害。新版文案中的抽牌差异也不能替代执行证据。

`CardDataTools.getCardOrderNextCard`（index **9176**，`[37]`）对普通模式直接返回传入 nextId；rogue 模式会通过稀有度映射和相同初始卡的 item/card 映射选择另一行。`athlete_utils.getPreviewCardReplaceCardIDByData`（index **5973**，`[49]`）还处理最低等级、基础卡替换、模式替换和再升级；这是预览数据路径，不能当作服务端的权威规则实现。

`CardDataTools.getCardNewAthlete/getCardNewDungeon/getCardNewBattle`（index **9176**，`[42]/[43]/[44]`）分别从玩家角色属性、地牢属性或战斗实体 `rpgProp` 取值，再调用展示公式；未在这些函数内修改 DIY 或 skill_state 的 RPG 字段。

更直接的是 `ClientCard.valueList`（index **9137**，`[9,5]`）：它读取 `Globals.BattlePlayer.cardPredictOnHand` 和 `cardPredictRun`。因此原客户端显示的战斗预测依赖已同步的预测数据，不能只把卡表默认文案值当作目标防御结算后的数值。

## calcDamage 的依赖已拆开

`common/formula.py`，index **7042**，`calcDamage` `[7]` 的所有数值步骤已写入契约。入口基础值依次经过额外基础攻击、非真实攻击系数、通用及类型增减伤、等级压制、额外伤害、PVP、预览延迟伤害、最小值与最终 `int`。真实攻击仅跳过克制/防御/buff/暴击这一组，**仍经过通用增减伤、等级压制、额外值和 PVP 等后续步骤**。

| 依赖 | 已恢复的实现及边界 |
| --- | --- |
| 基础动作值 | `7042:10`：有角色卡牌强化数据时加 `factor*属性+base`。参数 strengthFactor 及求得的 levelNum 在这段函数中没有参与运算，不能自行补乘。强化数据的生成仍需外部输入。 |
| 基础额外攻击 | `7554:5.0`：卡牌 additional 值 + 实体 attack-add 值 + `int(基础动作值*(extraBaseDamagePercent/100.0))`。这是一个明确的中途截断点。前两个方法的提供方未恢复。 |
| 克制 | `3510:27/28`：由 `counter_type_table` 或全克制属性决定，分母显式为 `float(100)`；OTHER_WORLD=7 在全克制分支返回 1.0。7 行原表已导出。 |
| 防御 | `7042:9`：保留上一轮恢复的经典除法，实际运行属性的 int/float 类型仍未知。 |
| 攻击 buff | `7554:5.9`：按原迭代顺序累加 `factor.getValue(dst)-1`，再累加 `attackCommonFactors` 每个值减 1。外层 `5.4` 再加卡牌及战斗额外系数。 |
| 受击 buff | `7554:5.8`：累加 `factor.getValue(src)-1`，随后 common 值却除以 100.0。外层 `5.5` 在攻击者未被排除时再减 `reduceDamegedRate/100.0`。与攻击 common 值的单位不同，不能统一处理。 |
| 暴击倍率 | `7042:7 [0x153,0x172)` 优先使用非空 probInfo 的 `CrticalAndBlockRatio`，否则 `7554:5.6` 调卡牌的 `getCriticalDamageRatio()`；无卡返回 1.0。卡牌方法和 probInfo 调度来源未恢复。 |
| 通用属性 | `7554:5.12/13/14`：枚举转属性名；读取基础值并逐项加 modifier；只将 PropAtk 限制不小于 0。没有统一 float 转换。 |
| 等级压制 | `7042:8`：完整分段公式可独立移植；17 个边界向量覆盖四种玩家/怪物组合及禁用开关。 |
| 尾部额外值 | `7554:5.2` 调卡牌 `getExtraDamageValue()`；`5.3` 调实体 `getExtraBeHurtValue()`，共同基类 `5.11` 返回 0，但未证明运行时不存在重写。 |
| PVP 与延迟伤害 | 读取 battleInst.pvpAtkRatio；预览时调 `getCurrentHurtSlowHp`。PVP 表和 UI 显示存在同名字段，但没有证明其如何赋给战斗实例；不能把表值直接接上。 |

`rpgGetCrticalAndBlockRatio`（`7042:4`）也已恢复，可对外部提供的随机采样值确定分支：暴击概率为 `max(0,src.getCritical(card)-抗暴)/1000.0`，格挡概率为格挡属性/1000.0，采样区间上界为 `max(两者之和,1.0)`，两个比较都包含等号。采样值恰为 0 时，即使暴击概率为 0，也进入第一个分支；工具保留此边界。**没有证据把这个辅助函数直接替代 calcDamage 的卡牌暴击路径**。另外 `getCritical`（`7554:5.7`）在无卡分支以 0 乘基础暴击值；不擅自修成倍率 1。

动态 `factor.getValue`、卡牌方法、实体基础额外攻击和 `battle.getExtraBattleFormula` 仍未找到具体提供方。机器可读契约要求调用方显式提供这些结果，缺失即拒绝，不能自动当成 0 或 1。

## 数值类型是移植契约的一部分

- Python 2 的整数除法向负无穷取整；`int(float)` 向零截断。两者对负值不同。
- 整数需要保留超过 2^53 的精度。向量中真实攻击分支的纯整数 `9007199254740993` 必须原样返回。Node 不能无条件将所有值读成 Number。
- 浮点使用二进制双精度，必须保留原加乘顺序。玩家 buff 下限是 `1-0.9`，不是预先写死的 `0.1`。本轮向量中 `int(100*(1-0.9))` 得到 **9**；这不是拟定的新规则，而是被观察表达式的浮点结果。
- 浮点 modifier 的累加顺序也会影响最后截断。Python 2 字典顺序/实际实体类型尚未验证；移植接口应接收有顺序且有数值类型的快照，不能假装恢复了原运行顺序。
- 输出向量用整数十进制字符串与 binary64 十进制/hex 标记区分类型；`100` 和 `100.0` 不能在 JSON 解析后丢失差别。

本轮新增 `0x51 UNARY_NOT` 映射，依据包内 `lib/calendar.py` index 6561、`main` `[62]` 的偏移 `0x170`，与 [CPython 2.7.18 calendar 的 locale/encoding 判断](https://github.com/python/cpython/blob/v2.7.18/Lib/calendar.py#L616) 交叉核对。等级压制函数中的同一指令因此可解释；其余未知/融合指令仍不伪装成完整反编译。

下一步可以在无网络、无实体副作用的 Node 包中实现上述纯标量函数，直接复用带类型的合成向量。它应明确接受“已解析的依赖快照”，先验证表达式、截断和顺序，再逐步替换已找到提供方的系数；在构造链、扣血、护盾、随机状态和回合规则恢复前，不宣称已实现整场原版战斗。
