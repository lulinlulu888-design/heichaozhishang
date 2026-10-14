# 首轮战斗规则静态追踪

本轮已把 410101、410102 从卡牌配置追到技能效果图、节点输入和公共伤害函数，并建立两个可独立验证的标量计算片段。尚未恢复完整战斗：字段覆盖、实体扣血、护盾处理、随机状态和回合调度仍需要继续定位。

所有结果来自当前 APK 的解密 marshal 对象与原生库静态字节；没有执行 APK 字节码、导入游戏模块、构造 Python 可执行 CodeType，也没有使用 `eval`/`exec`。这是本地静态证据，不是原客户端运行回放或 REA 动态证据。

## 复现

```powershell
python tools/inspect_battle_rules.py --report
```

该命令重新验证每个读取模块的解密 SHA256、文件名及 marshal 完整消费，生成 `analysis/battle-rules/` 中的部分反汇编、结构化指令、选定表行、技能反向索引、JSON 效果图、有限符号搜索及 10 个标量验证向量。运行时不联网；CPython 上游源代码仅用于本次人工交叉核对混淆 opcode。

也可以指定 NPK index 和函数名导出更窄的证据：

```powershell
python tools/inspect_battle_rules.py 7042 --function rpgGetDstEntityDefenseValue
```

每条指令保存原始字节码偏移和行号，每个函数保存 `constant_path` 与 bytecode SHA256。函数偏移是相对该 code object 的偏移，不是 NPK 文件偏移。模块的 APK member、NPK offset、payload SHA256、decoded SHA256 保存在各文件 `source` 和 `report-sources.json` 中。

## 卡牌展示公式 AP 已有明确依据

| 环节 | 证据 |
| --- | --- |
| 卡牌参数 | `common/cdata/card_table.py`，index 3391，410101 行起点 127044；410102 行起点 127367 |
| AP 定义 | `common/cdata/card_description_table.py`，index 1280，行 1 构造 `[118,169)`；`NAME_ID="AP"`、`class_RpgBasicProp=1`，描述为“攻击x$s%” |
| 属性枚举 | `common/const.py`，index 6221，`RpgBasicProp.PropAtk=1`；顶层 `[0x555,0x55f)` 把该枚举作为 key、`"PropAtk"` 作为 value 加入 `RpgPropMap` |
| 公式名称转换 | `common/combatUtils.py`，index 3510，`InitRpgFormulaMap` `[0x0,0x35]` 从 `card_description_table` 建立 `NAME_ID→row ID`；`getRpgFormulaDatas` 再解析 AP |
| 数值计算 | 同模块 `getRpgNumberValue`，`constant_path=[36]`，非零公式分支 `[0x3c,0x62]`，最终 `[0x69,0x72]` 调用 `int` |

针对这两个卡牌配置的一项 AP 展示值，可独立翻译为：

```text
display_value = int(PropAtk * configured_percent / 100.0)
```

`int` 向零截断；不能改成四舍五入。一般函数会先累加同组多项公式，再统一转为整数；`formulaType==0` 是直接加基础常量的分支。这些是展示公式的计算语义，不意味着最终伤害或实际攻击次数已经确定。

卡表 410101 为 `RPG_DEFAULT_FORMULA=[[75]]`、`RPG_FORMULA=[["AP"]]`；410102 为 `[[300]]`、`[["AP"]]`。`SKILL_DIY_PARAMETER/ VALUE` 分别为 `FACTOR/[75]` 和 `FACTOR,VALUE/[300,0]`。本轮未发现正常战斗流程直接读取这两个 DIY 字段的静态代码；它们与展示默认值相同不证明服务端使用相同字段。

另一个函数 `combatUtils.getCommonRpgFormulaValues`，`constant_path=[39]`，把逗号分隔的属性名与默认值配对，默认值先 `int(float(text))`，逐项相乘后除以 `100.0` 并求和，返回浮点和，不在此处统一 `int`。它与 AP 展示函数不是同一个接口。

## 技能效果表给出了不同信息

从 `common/cdata/skill_state_table.py`（index 8903）恢复了 `data` 和尾部 `extra_data` 的字面量参数。新 recognizer 仅接受 `taggeddict({integer: tuple(integer...)})` 的已观察形状，拒绝其他表达式，不调用 `taggeddict`。

`extra_data` 构造起点 179179、赋值点 195352：

| 技能 | 索引列表 / map assignment offset | 表行与行为字段 |
| --- | --- | --- |
| 410101 | `[365,366]` / 189058 | 两行 `OwnerIndex=0,1`，均为 `RPG_FORMULA="PropAtk"`、`RPG_DEFAULT_FORMULA="75"`、`DAMAGE_TYPE=1`、`STORYLINE_NAME="SkillState_CauseDamage"` |
| 410102 | `[368,367]` / 189071 | 行 368：PropAtk、默认 `"200"`、CauseDamage；行 367：`SkillState_getCard`、`STORYLINE_PARAM={"VALUE":1}` |

`skillTableAdapter.getSkillStateData`（index 8010，`constant_path=[357]`，`[0x0,0x44]`）使用 `skill_state_table.getExtraData(skillID,[])` 取这些行，再转换为 adapter。该调用说明反向索引与技能 ID 的关联；尚未证明整个服务端调度的执行次数和次序，因此不能仅凭两行就断言最终触发次数。

`skill_timeline_table`（index 6655）的反向索引另把 410101 映射到行 2983、410102 到 2984，分别包含动画列表 `ATK_3/ATK_5/ATK_2`、`ATK_1`。这属于表现数据，不能拿动画数量替代命中次数。

**410102 的 300 与 200 必须保留为冲突证据。** 卡牌展示默认值为 300，技能效果表默认值为 200，且效果表还有抽牌。未恢复运行时参数覆盖之前，不能选一个数当作原版最终伤害，也不能把 `[300,0]` 的第二项解释成已经取消抽牌。

## 从效果图到伤害入口

`common/storyline_implement/card_action/server/SkillState_CauseDamage.py`（index 4168，NPK offset 22090060，decoded SHA256 `cd433af95790fb7d03d603d5b0d2fca3d8757f13ce7f3eb4500c69e809e381b8`）只把 JSON 字符串常量 0 赋给 `data`。该 JSON 图的明确连线是：

```text
StartEvent → SkillGetRpgValue → CardFormulaAndDealDamage
                 rpgValue ──→ damageValue
IntParameter("#EXTRA_DAMAGE") → finalExtraDamage
```

节点实现进一步证明：

- `common/storyline_nodes/skill/data.py`，index 296，`SkillGetRpgValue.Start`，`constant_path=[20,6]`，`[0x21,0x37]`：调用 `context.cardAction.getRpgValue(target)` 返回 `rpgValue`；target 未指定时取 context.owner。
- `common/storyline_nodes/skill/action.py`，index 4762，`CardFormulaAndDealDamage.Start`，`constant_path=[21,8]`：`[0x0,0xf]` 先把 damageValue 转为 int；`[0xb7,0xd8]` 从 actionData.DAMAGE_TYPE 取覆盖值；`[0xde,0xf6]` 构造 DamageInfo；`[0x11d,0x12f]` 保存 cardActionObj 并标记 isDamageSkill；`[0x132,0x13e]` 调用 dstEntity.beHurt(damageInfo)。
- `common/storyline_nodes/skill/action_formula.py`，index 6224，`CalculateDamageNode.Start`，`constant_path=[11,9]`，`[0x12f,0x13b)` 直接调用 `formula.calcDamageWithDamgeInfo`，随后至 `0x13f` 返回含 damage 字段的字典；这是预览路径。
- `common/formula.py`，index 7042，`calcDamageWithDamgeInfo`，`constant_path=[5]`，`[0x0,0xab]`：读取 DamageInfo 字段，再调用 calcDamage。

`SkillState_getCard.py`（index 3109，NPK offset 21567448）也是纯 JSON 常量：`IntParameter("VALUE")` 连到 `DrawCardsNode.num`，StartEvent 连到执行输入。这证明了抽牌图节点与 VALUE 的连接，但尚不能替代真实回合/牌堆规则。

## common/formula.py 的可复用片段与边界

模块 index 7042，NPK offset 12168648，decoded SHA256 `ea9b0bb6c277d605e039bbbc6e18d4eabad98fb8316659948129efa4709586fc`。

`rpgGetDstEntityDefenseValue`（`constant_path=[9]`，原行 212）可抽出一个确定的标量表达式：先按物理/魔法类型取对应防御，减去攻击者 `PropBreakDefend`；若攻击者 `PropAtk==0` 返回 0，否则返回：

```text
PropAtk / (PropAtk + max(selected_defense - PropBreakDefend, 0) * 5)
```

证据偏移：选择防御 `[0x6,0x57]`，减穿透 `[0x5a,0x70]`，读取攻击/零分支 `[0x73,0x97]`，返回表达式 `[0x98,0xb0]`。这是乘在伤害上的系数，不是“直接减掉防御值”。

这里存在重要 Python 2 类型语义：opcode 是经典 `BINARY_DIVIDE`，表达式没有强制 `float`。若输入均为整数，经典除法返回整数；若包含浮点，保留小数。`CommonCombatBasicProp.getBasicProp/getRpgPropByKey`（index 7554）没有统一 float 转换，本轮也未证明运行时实体属性的实际数值类型。独立验证向量刻意同时记录 `100.0/(100.0+20.0*5)=0.5` 和整数情况下的 0，不能悄悄把原式“修正”为浮点。

`calcDamage`（`constant_path=[7]`）已经可以观察到下列运算顺序，尚未把依赖对象替换成新游戏规则：

1. `[0x6b,0x99]`：基础动作值、卡牌强化与额外攻击值。
2. 非真实攻击分支 `[0xa5,0x1bd)`：阵营克制系数、防御系数、攻击方/受击方 buff 系数、玩家减伤下限、暴击/格挡或卡牌暴击系数。
3. `[0x1bd,0x296]`：通用增伤减伤与物理/魔法专项增伤减伤。
4. `[0x299,0x2f1]`：等级压制系数、额外攻击值、额外受击值、extraDamage。
5. `[0x2f4,0x33b]`：PVP 系数与预览路径的延迟伤害调整。
6. `[0x341,0x353]`：值不大于 1 时改为 1；`[0x3cf,0x3d8]` 最终转 int。

因此仅用“攻击×百分比−防御”不能还原这一版本。`calcDamageOnCard`（同模块 `constant_path=[12]`）是另一条缺少目标防御的卡牌预览计算，不能当作实际扣血。

`formula-probes.json` 保存 6 个 AP 预览向量和 4 个防御系数向量；执行前检查三个原函数的 bytecode SHA256，源字节改变立即拒绝。验证的是人工移植的纯标量语义，不是对原客户端进行动态差分，也没有实现实体、buff 或伤害派发。

## 6002 / 6003：来源和同号误区

已证明的源头是 `character_init_attack.py`（index 1338）中的 `InitAttackSkillID=6002`、`InitDeffendSkillID=6003`。角色 1 行中 LOAD_CONST 6002 在字节码 35，字段名在 38；6003 对应值在 49、字段名在 52。原始配置确实存在，不能删掉或随便改号。

但本次没有找到它们的完整可用技能定义：

- `skill_table.data` 中无 6002/6003；`skill_state_table.extra_data` 与 `skill_timeline_table.extra_data` 中也无这两个 key。
- `card_table` 同号 6002/6003 是不可使用的任务/诅咒类卡牌，`CAN_NOT_PLAY=true`、`SKILL_ID=0`，不是基础攻击/防御技能。`skill_state_table` 行 4214831/4214841 中的 6002/6003 明确位于 `STORYLINE_PARAM.CARD_ID`，不能跨 ID 空间混用。
- `logic/battle_action/SkillUseAction.py`（index 4497）`_prepareBeforeReactAction`，`constant_path=[9,7]`，`[0xc2,0x117]` 对 `_skillID==6002` 添加一个 ActionID 3 的前置表现动作。`action_performance_table.py`（index 7372）行 3，构造 `[132,183)`，明确 `ActionKey="ClientPlaySfxAction"`、资源 `effects/player/fight/fight_player.sfx`，不是伤害公式。
- 对 InitAttackSkillID/InitDeffendSkillID 的全部直接名称/字面量引用，只观察到 character_init_attack 与 monster_table 的配置声明，没有定位到客户端消费者。

这些事实支持“可能是遗留/服务端初始化路径”的分析假设，但不足以证明无用字段或服务端实现肯定缺失。当前保留未解决状态，不制造 6002/6003 占位技能。

## 缺口核查范围

`boundary-references.json` 搜索全部 9698 条脚本符号记录，并对匹配模块进行哈希验证及逐指令检查，包含 LOAD、STORE、导入和字符串字面量，未只依赖同名 def 搜索：

- getRpgValue：一个 LOAD_ATTR 调用，未见直接定义/赋值。
- beHurt：一个 LOAD_ATTR 调用，未见直接定义/赋值。
- DamageInfo：6 组 IMPORT_FROM/STORE_NAME，全部来自 `ServerUtils`，以及其构造调用；未找到该提供方的同名模块文件。
- 未找到以这些完整字面名称调用 setattr 的生成 wrapper。动态拼接名称、通用注册器、加密/压缩的其他载荷、热更新及外部服务实现仍未排除。

对原始 `libclient.so`（SHA256 `54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`）进一步做了 ASCII、UTF-16LE、UTF-16BE 的完整字节搜索，getRpgValue/beHurt/DamageInfo/ServerUtils 均为 0 命中。未找到可据此跟进的具名 PyMethodDef/字符串注册锚点；这不是穷尽 native 控制流或间接注册的证明。当前 REA native provider 未配置 Ghidra，记录该限制后使用有限的原始字节检查，没有声称得到 REA 反编译结论。

## Opcode 交叉验证与后续最小范围

原 APK `lib/opcode.py`（index 8976）保存的是标准编号，而其自身字节码已混淆，不能直接拿该表解释游戏指令。补充映射通过相同 APK 中的库函数与 CPython 2.7 官方源码交叉核对：

- `0x2c BINARY_DIVIDE`：index 2597 `bsddb/dbutils.py` 顶层 `0x52` 的浮点最小退避时间除法；`0x52 INPLACE_MULTIPLY`、`0x37 INPLACE_SUBTRACT` 对应其 DeadlockWrap 的倍增退避与重试数递减。[CPython 源码](https://github.com/python/cpython/blob/v2.7.18/Lib/bsddb/dbutils.py)
- `0x15 INPLACE_ADD`：index 414 selective_len 的计数器加一，及 index 6561 calendar 的字符串累加。`0x52` 另由 calendar.formatstring 的 spacing 乘空格交叉核对。[CPython calendar](https://github.com/python/cpython/blob/v2.7.18/Lib/calendar.py)
- `0x0d BINARY_TRUE_DIVIDE`：index 1644 random.normalvariate/expovariate，模块启用 future division；`0x34 BINARY_FLOOR_DIVIDE` 则由 index 3976 bisect 的中点计算交叉区分。[random](https://github.com/python/cpython/blob/v2.7.18/Lib/random.py)、[bisect](https://github.com/python/cpython/blob/v2.7.18/Lib/bisect.py)

映射是基于结构、操作数和上游源语义的静态推导，未读取原生解释器完整 dispatch 表。工具将未确认 opcode 继续标成 UNKNOWN，不运行它们。

可立即复用的最小成果是 AP 展示公式、来源明确的技能图数据和带类型边界的防御系数验证片段。下一步应先补 cardAction.getRpgValue 的字段覆盖策略与实体 beHurt 路径，再选一张没有配置冲突的卡牌，固定属性/随机种子/牌堆，对命中次数、护盾和扣血做可记录的差分验证。原始数据与新客户端领域规则仍应分开保存，避免把未经证实的规则包装成原版事实。
