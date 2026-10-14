# 技能图运行语义与首战节点边界

已恢复包内 SunshineClient 图运行器的参数注入、端口传值、同步触发、子过程与条件分支，并把 5 个实际技能图规范化为可审查的数据。最适合先翻译到纯 Node 的范围是这些图的调度和节点包装：抽牌、受伤、护盾状态修改继续通过显式外部接口接入。原版 `cardAction.getRpgValue`、牌堆和 HP 状态机仍未恢复，不能把图能走通称为原版战斗结算已恢复。

本轮只静态读取解密 marshal，未导入或执行 APK 脚本，未启动游戏、UI 或外部运营服务。REA native provider 的既有环境限制未变，本轮未反复尝试。下面证据来自本地逐模块哈希校验，不冒充 native REA 反编译或运行记录。

## 复现与来源

```powershell
python tools/trace_skill_graph.py
```

输出在 `analysis/skill-graph/`：

- `sources.json` 和 `*_instructions.json`：30 个脚本的 APK member、NPK entry offset、解密 SHA256，以及各函数 constant path、bytecode SHA256、指令偏移、cell/free variables。`*_partial-dis.txt` 供人工读。
- `02657/03109/04168/07455/08593_graph.json`：5 个原始 JSON 字面量及其哈希、赋值偏移。
- `normalized-graphs.json`：节点、数据/触发连线、会因数据输入而启动的端口；保留字面量序号，但明确它不是运行顺序。
- `execution-contract.json`：17 条恢复规则及精确函数/区间证据；另含 `calcBlock` 完整顺序和外部边界。
- `enemy-skill-states.json`、`enemy-value-boundaries.json`：另校验技能状态表 index 8903，提取首战敌人状态 2/3/4 的字段与来源。
- `opcode-corroboration.json`：仅供本工具使用的新增 opcode 对照；共用反汇编工具未修改。

所有已写入人工语义的模块都有固定 SHA256 guard；版本改变即拒绝沿用结论。以下 `876:1.6` 表示模块 index 876、constant path `[1,6]`。偏移相对该 code object，区间末端不包含在内。

新增闭包映射由包内 `lib/contextlib.py`（3337:10/10.1）与 [CPython 2.7.18 官方源码](https://github.com/python/cpython/blob/v2.7.18/Lib/contextlib.py)逐段对应，确认 `0x81/0x78/0x64/0x8e` 的读取闭包、载入闭包、构造闭包与可变参数调用语义。融合指令 `0xad` 的 `fast[0] + const[arg]` 栈形由 `lib/functools.py`（7930:8，0x9）与[官方 wraps 实现](https://github.com/python/cpython/blob/v2.7.18/Lib/functools.py#L45-L46)对应，并在 Procedure/FunctionStart 的 self/常量成对写入中交叉核对；只标注这些精确位置。其余未知指令仍为 UNKNOWN，不声称恢复了 native opcode 分发表。

## 运行器范围：客户端共享代码与服务端分支不同

`common_storyline`（618）的模块入口按 `const.IsClient` 选择导入：客户端使用 `plugin.sunshine.plugins.U1Galaxy.StorylineBattleContext`；另一分支指向 `storyline.StorylineBattleContext`。本轮证据来自前者及包内共用节点。它足以作为新 Node 图实现的明确参考，**不能证明未提供的原服务端运行器在排序、异常处理或生命周期上逐项相同**。

`BaseServiceStoryline.onCreate`（618:8.1，[0x92,0xd1)）加载图，先注入 owner/entity，再依次注入 `getParamList()`。`Storyline.LoadFromFile`（353:13.2，[0x2b,0x8c)）构造 `storyline_implement.<filename>` 模块名，读取其 `data` 字符串，再 JSON 解析；本工具直接提取字面量，完全不执行这条动态 import。

## 参数、连线与执行次序

原编辑格式是 `Storyline.nodeData[NodeID]` 和 `lineData`。节点包含 `Type`、`Data`，连线包含 `startNode/startPort/endNode/endPort`。位置、分组字段不能当成运行先后。`StorylineDataReader`（8951:29.0）建立双向连线；`NodeGraphBuilder`（9072:13.0）通过注册的类型创建节点，再用元数据更新 `Data` 字段。另有已编译 `NodeBuffer` 格式分支，本轮 5 图均使用编辑格式。

参数节点的名字取 `Data.parameterName`，初值取 `Data.value`，Input/Output 由 `parameterStyle` 区分。战斗版 `NodeGraphBattle`（1113:9.10/9.11）按名字保存**所有**匹配节点；`setParams`（1113:7.5）按三元组列表顺序调用 `setParam(name,type,value)`，只有名字与类型标签都匹配才 `SetValue`。赋值不做 `int()` 转换；未匹配的名字/类型不改值。同名同类型多次注入时后写覆盖，并覆盖该名字的所有同类型节点。普通 `Storyline.SetParameter` 的单节点 map 不是这里使用的战斗参数实现。

启动时按 `(priority, runtimeNodeID)` 倒序：参数节点、ProcedureStart、FunctionStart 的优先级为 1000，StartEvent 为 1。`NodeGraphBattle.Run`（1113:9.12）还按 `startNodes` 的类名列表筛选 StartEvent 及其子类，其余自动节点照常启动。SService 的普通技能入口只选择 `StartEvent`，怪物意图入口只选择 `MonsterIntentionStartNode`。

`StartNode`（876:1.5）同步调用 `node.Start(context)`；返回 dict 才自动调用 `FinishNode`。返回 None 不等于空成功结果，不自动继续后继。`FinishNode`（876:1.6）有明确阶段：

1. `[0xed,0x19c)` 记录要走的触发端口。输出字典中的 `__out__` 可指定一个字符串或列表；若为空且节点存在默认 `__out__` 端口，会回退到默认端口。因此返回 `{}` 可以继续默认连线。
2. `[0x19c,0x306)` 先传播数据。普通输入经 `InputData(oldData,srcPort,newData,indegree)` 后设置节点字段；基类 `InputData` 直接返回新值，不等待所有入边。若该数据输入自身 `isTrigger=True`，把该节点加入待启动列表。
3. `[0x306,0x375)` 把普通触发后继追加到数据触发后继之后，并同步逐项启动。子节点可以递归进入另一次 FinishNode。

这不是统一的拓扑排序，也不是每节点只执行一次。`IntAddNode.x/y` 就是带触发的数据端口，每次输入更新都会计算一次；需要保留这种行为。

连接保存在 Python set（9072:11.0.1/11.0.2、13.3），编辑格式节点 ID 来自 Python 2 字典遍历。因此可以保证上述数据阶段优先，不能保证同一集合内的多后继顺序、多个写入者的最后值、JSON lineData 顺序或字符串 NodeID 顺序。**OwnerIndex 属于技能状态表，本轮图调度器没有用它决定顺序；图内调度不解决图外多个 skill_state 的顺序。**

## 五条实际图路径

| 图 / script index | 已恢复的实际路径 | 仍需外部结果 |
| --- | --- | --- |
| `SkillState_getCard` / 3109 | IntParameter VALUE→DrawCardsNode.num；StartEvent→DrawCardsNode | 队伍的抽牌方法 |
| `SkillState_CauseDamage` / 4168 | `#EXTRA_DAMAGE`→finalExtraDamage；StartEvent→SkillGetRpgValue→CardFormulaAndDealDamage，rpgValue先写入damageValue | RPG值、受伤接口及状态机 |
| `SkillState_MonsterCauseDamage` / 2657 | 实际与意图两个开始事件共用 Function 子图计算RPG值；实际走受伤，意图走CalculateDamageNode→SetMonsterIntention | RPG值、预览公式依赖、受伤/意图接口 |
| `SkillState_AddShield` / 7455 | VALUE→IntAdd.y；SkillGetRpgValue→IntAdd.x；IntAdd.result→AddShieldCard.shieldValue，然后显式触发AddShieldCard | RPG值、护盾公式依赖、护盾状态接口 |
| `640018` / 8593 | 抽2张，过滤子过程读取卡牌费用并Compare(target=0)，equal分支才结束过滤过程 | 当前费用值、抽牌方法的候选集/顺序 |

### RPG值、目标与伤害

`SkillGetRpgValue.Start`（296:20.6）只在自身 target 为 None 时改用 `context.owner`，然后调用 `context.cardAction.getRpgValue(target)`。它不计算 `RPG_FORMULA`。本轮沿运行器和 `skillTableAdapter` 相关函数追踪，没有出现此前缺失的公式消费端；8010:353.1 仍只是字段访问/类型包装。没有重复全库同名搜索，也不把这个有限结果写成“所有可能的提供方均不存在”。

`CardFormulaAndDealDamage.Start`（4762:21.8）先 `int(damageValue)`，精确 int 类型的 src/dst 选择器 0→owner、1→context.target；已有实体对象保持原值。布尔不是这里的 int 类型选择器。`actionData.DAMAGE_TYPE` 非 None 时覆盖节点 rpgDamgeType，然后创建 DamageInfo、写 extraDamage/cardActionObj/isDamageSkill，最后 `dstEntity.beHurt(info)`。它没有赋最终 HP。

### 抽牌与条件

`DrawCardsNode.Start`（7693:63.7）没有 filter 时构造恒真筛选函数并传 `isNowDrawPile=False`；有 filter 时传 True。最终调用：`context.ownerTeam.drawCardsFromDrawPile(num, cardFilterFun=..., isNowDrawPile=...)`，返回 `cards`。图中 `VALUE=0` 会照样传 0，不能当成缺失；底层是否洗牌、上限和候选迭代顺序没有出现在该节点内。

过滤子过程使用 `StorylineBattle.pushNest/popNest` 保存调用方，先把 `_result` 置 False，再同步触发 ProcedureStart；ProcedureEnd 回调调用方 `onProcedureEnd` 后变 True。图 640018 的 GetCardEnergyNode（2905:51.7）对客户端读取 `card['energyAll']/['energy']`，另一分支读取 `card.cardEnergyAll/CardEnergy`。全费用卡输出 `isX` 且没有 result；该图未连接 isX，所以它不进入费用等于 0 的分支。这里使用当前运行时费用，不能替换成卡表印刷费用。

`CompareNode.Start`（5250:12.7）依次 `<`、`==`、else 选择 less/equal/greater。`YesNoNode`（5250:20.2）对计算值使用 Python bool。名字相近的 `EqualNode`（5250:16.6，0x19）却使用 `COMPARE_OP 8`，即 Python `is` 身份比较。不能为了方便直接翻成 JavaScript 数值相等；初版图子集应拒绝未实现的身份语义。

### 怪物意图与 Function 子图

FunctionStart 在自动初始化时把自己作为 procedure 输出，随后由 FunctionNode 同步调用 awakeFunction。FunctionNode（5250:44.16）压栈自己、清空 `_result`、传入 paramIn1..5，子图中的 FunctionEnd（5250:52.8）调用栈顶 `onFunctionEnd(paramOut1..5)`，调用方出栈后返回 `_result`。这条路径可以人工翻译成普通同步函数，不需要执行原 Python VM。

怪物图的 VALUE 同时接实际与意图节点的 finalExtraDamage。实际 `StartEvent` 走 beHurt；`MonsterIntentionStartNode` 走 CalculateDamageNode（6224:11.9），它设置 `isDamageSkillPreview=True` 并调用 `formula.calcDamageWithDamgeInfo`，把输出交给 `cardAction.setMonsterIntention(damageValue,damageTime)`（7186:11.3）。图内 damageTime=1。预览支路本身没有扣血，不能把它替代实际受伤结算。

### 护盾与首战 VALUE

护盾图中的 `IntAddNode`（7975:22.0）只是 `x+y`，没有额外 int 转换。其两个输入都是触发数据端口（7975:13）：即使先收到 VALUE 时计算过初始值，收到 RPG 值后也会再算一次；调度器先跑数据触发节点，再跑 AddShieldCard 的显式触发，所以最终传入的是更新后的和。

`AddShieldCard.Start`（4762:25.6）在该图的 oprtType=0 下调用 `calcBlock(sum,1.0,target,cardObj,srcEntity=context.owner)`，随后 `target.addShieldHp(block,owner,getSkillInfo())`。oprtType=1 另走 forceSetShieldHp，其他值走 decShieldHp；本图不会走这些分支。

`formula.calcBlock`（7042:11）已完整拆出：

1. 有 src 时调用 `_calcRpgBasicActionValue(basicBlock,srcEntity,cardObj)`，但**只有三个位置参数**（7042:11，0x12 `CALL_FUNCTION 3`）。helper 的签名是 `(basicValue,srcEntity,strengthFactor=None,cardObj=None)`（7042:10；模块体0x6a/0x6d载入两个None默认值）。因此这里把卡对象传给未使用的 strengthFactor，helper.cardObj仍是None，跳过强化分支，返回basicBlock原值；无src时也是直接用basicBlock。不能在移植时自行把此处改成四参数调用或补上卡牌强化。
2. 乘 `1 + src.PropAddTargetShield/1000.0`，再乘 `1 + dst.PropBeAddShield/1000.0`（分别以实体真值为条件）。
3. 乘 `1 + src.getSrcAddTargetShieldFactor(dst) + dst.getShieldFactorValue() + card.extraBaseBlockPercent/100.0`；不存在实体/卡时该项按原分支为 0。
4. 加卡牌 `getAdditionalBlockValue()`；PVP 时再乘 `dst.battleInst.pvpShieldRatio`。
5. 最后 `int(max(0,value))`。agilityFactor 与 cardActionObj 参数在此函数体内未被使用，不能自行补乘。

上述参数错位只影响开头的helper调用，后续仍读取calcBlock自己的cardObj以计算额外护盾百分比和附加值。calcDamage在0x7a使用四参数调用，与此不同。原代码明确的“无实体/无卡”分支与“有实体但方法尚未恢复”是两件事。后者需要显式提供该方法的结果，不能用0/1自动替代。完整偏移、字节码哈希与运算顺序在 `execution-contract.json.calcBlock`。

首战敌人技能状态表（8903，解密 SHA256 `be8c1ea4abc43f7dab5e38187e6ac286f2f338aef1581313eb99d099dbea090c`）证明：

| 技能 / 状态 | VALUE | 图中意义 |
| --- | --- | --- |
| 990 / 2 | 302 | MonsterCauseDamage 的 `DamageInfo.extraDamage`，不是基础伤害百分比 |
| 991 / 3 | 402 | 同上 |
| 992 / 4 | 300 | AddShield 的 `RPG值 + 300`，之后仍经过 calcBlock |

这三行没有 `RPG_FORMULA/RPG_DEFAULT_FORMULA`，但对应图仍会调用 getRpgValue(owner)。**“缺字段就返回 0”目前没有 provider 证据**。若新首战模式选择这个规则，必须单独写成可替换的重建策略；不能声称已经从 APK 恢复。302/402 也不能直接写成最终 HP 减少值，300 不能直接当最终护盾。

## 下一步可构造的对象与必须标明的设计

| 部分 | 可以按现有证据构造 | 尚需显式输入或重建设计 |
| --- | --- | --- |
| 图节点/参数 | 这5图、固定类型注册、初值、同名同类型参数覆盖、数据先于触发、同步Function/Procedure栈 | 任意图的多写者/fanout顺序、未支持节点、异步生命周期 |
| 技能上下文 | 传入owner/target/cardAction/cardObj/ownerTeam；执行已恢复的0/1选择器；按所选入口隔离实际和意图 | 这些实体的权威属性初始化、skill_state执行顺序和随机目标 |
| RPG/DIY | 保留原字段原类型；将调用接口做成必须明确提供的依赖 | RPG公式解析与缺字段策略、卡表DIY列表→diyActionData构造 |
| 伤害/护盾标量 | 使用已有calcDamage与本轮calcBlock的顺序、Python数值类型/截断语义 | 所有动态modifier方法的结果，HP/盾扣减、事件触发与死亡顺序 |
| 抽牌 | 参数值与过滤规则、当前费用检查、明确抽牌调用签名 | 候选顺序、洗牌、手牌上限、卡实例归属和权威牌堆更新 |

建议首版只实现明确白名单节点与这5图，遇未支持节点或必需依赖缺失时停止并报告。新服务端可以自己拥有权威状态，但凡 APK 尚未证明的策略，要放在单独可替换配置中并标注重建设计；图调度与显示预测不能替代这些规则。
