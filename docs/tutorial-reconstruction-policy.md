# 序章首战装配：明确的重建规则

`server/src/tutorial.js` 导出 `loadTutorialScenario(directory?)`，默认读取 `analysis/first-encounter`，返回可直接 JSON 序列化的 `{ definition, provenance, policies, title, notice }`。场景交给共享 `battle-session` 执行。**这不是恢复出来的原服务器或 `cardAction.getRpgValue` provider。** 原始最终战斗属性、原技能调度器、缺字段时的 RPG 处理仍未恢复。

`server/data/tutorial-policy.json` 是本模式唯一的政策与证据白名单。`notice`、完整政策、来源和计算轨迹随返回对象提供给客户端。集成方应展示 `notice`，并保存完整 `definition.id`，不得将本模式包装为“原版完全复原”。

## 本模式的选择

| 项目 | 采用值与边界 |
| --- | --- |
| 玩家 | 艾尔莎，课程表指定等级 100；品质 4 是明确重建选择，原教程账号品质未证明 |
| 玩家 HP / AP | 修正后 `player-baseline.json.baseStatsTagged`：HP `1768.8000000000002`，AP `482.4`；均保留 binary64 decimal/hex，不取整、不用 `exactDecimal` 替代 |
| 玩家伤害基础值 | 按卡表 `RPG_FORMULA=[["AP"]]`、`RPG_DEFAULT_FORMULA` 的系数计算 `AP * integer(factor) / binary64(100.0)`；这是临时 provider 规则 |
| 状态执行顺序 | 按 `OwnerIndex` 升序；此调度规则是新设计，并非已证实的原服务器实现 |
| 怪物基础值 | 状态 2/3/4 均无 RPG 字段，本模式明确采用整数 0；不是推断原缺省行为为 0 |
| 怪物伤害与盾 | 状态 2/3 的 `VALUE=302/402` 进入 `extraDamage`；状态 4 的 `VALUE=300` 加显式基础 0 进入 `calcBlock` |
| 中性配置 | 未恢复的增益、防御、克制、压制、暴击、额外伤害、PVP 等输入逐项写入政策；比例为 1、加值为 0，关闭 PVP/预览；不代表原战斗的这些值 |
| 目标 | 伤害作用于对手，护盾作用于自身；这是单玩家/单怪物场景明确的目标策略 |
| 护盾 card | `null`；来源和目标护盾属性均显式中性。保留原 `calcBlock` 三参数调用错绑 helper 的已恢复语义，不悄悄修复原包疑似 bug |
| 抽牌与限制 | 初始抽 6、每轮抽 6、每轮能量 5、手牌上限 10、最多 30 回合，全部是重建政策；常量与战斗表仅作参考 |
| 敌人意图 | 第 1/2/3 回合技能 990/991/992，之后 990；参考已提取 `newbie_cube.xml`，实际回合执行由新引擎定义 |

怪物 HP 采用表内强制基础值 4600，未宣称原最终战斗 HP 已恢复。玩家基础属性的被排除修饰项随 `provenance.baseline` 一并公开。

课程表 `CardPile` 每项为 `[cardId, ownerCharacterId]`，第二项是所属角色 ID，**不是卡牌等级**；原 5947 `getAvatarCharInitCardPile` 按该角色值筛选。装配器要求七项都属于当前角色 1，将归属保留在 `provenance.deckOwnership`。卡表当前等级也恰好都是 1，不能拿这个巧合当元组含义。

## 保留的源冲突

| 卡/状态 | 卡表值 | 状态表值 | 本模式 |
| --- | --- | --- | --- |
| 猛力斩击 110009 / 296 | 系数 150 | 系数字符串 `80` | 150 |
| 疾驰斩击 410102 / 368 | 系数 300 | 系数字符串 `200` | 300 |
| 疾驰斩击 410102 / 367 | DIY `VALUE=0` | `STORYLINE_PARAM.VALUE=1` | 显式覆盖为抽 0 |

冲突以原值和所选值保留在 `provenance.conflicts`，包括仍未恢复 provider 的说明。不会改写或抹去状态表原值。二连斩击按状态 365、366 产生两个伤害事件。

中性政策下，调用现有 `battle-core.calcDamage` 后：斩击 385、猛力斩击 723、强力斩击 482、二连斩击 361×2、疾驰斩击 1447；敌轻击 302、重击 402。`calcBlock` 得护盾 300。共 9 次核心调用，每次保留完整显式输入、源状态、基础值解析政策、阶段轨迹和最终整数结果。只在核心原公式规定的最终伤害/护盾转换处截断；HP/AP 保持浮点。

## 证据与存档锁定

装配器对 11 份指定提取文件逐个验证完整文件 SHA-256，再核查关键表的原始模块索引、路径、decoded SHA-256、行集合、字段值及字节码行/字段位置。基础属性的关联证据 SHA、原 APK 标识、BT 文件/归属也必须相符。必需来源缺失、字段被改、行被换、未带 binary64 标签或旧版 baseline 都拒绝加载；没有备用虚构场景。

这验证的是已提取证据字节与已核实原模块身份的绑定。装配器不会再次解密/执行原 APK，也不声称运行时重新检查了整个 APK；复现提取使用既有 `tools/trace_first_encounter.py`、`tools/trace_player_baseline.py`。修改证据后必须重新审查并更新政策白名单，不能无条件接纳新的导出文件。政策白名单本身是受版本管理的可信输入，不是下载内容。

`definition.id` 为 `tutorial-5000-<SHA-256>`，摘要覆盖政策文件、全部消费证据的摘要、装配器源码、`battle-core` 数值/公式源码、`battle-session` 源码及装配出的定义。代码、证据或政策改变会获得新 ID，避免继续旧规则存档。此保守策略也会让仅改变源码排版的版本产生新 ID；加载器的 ID 稳定性以同一代码/证据快照为边界。

返回对象通过 `battle-session.validateDefinition` 严格验证，再深度冻结。`provenance` 中原表字段及字节码位置可供客户端展示/开发核查；不要把其中的 `reconstruction-resolved-input` 标签删掉后称为原 provider 输出。

## 验证

在项目根执行：

```powershell
node --test server/test/tutorial.test.js
```

测试使用真实的本地导出证据，校验 5 种卡/7 个有序实例、binary64 位模式、固定中性结果与完整核心轨迹、三处冲突、复制证据的身份稳定性、来源缺失和篡改拒绝。没有执行游戏字节码、启动服务或进行 UI 操作。装配器测试证明当前重建合同与证据约束，不证明原游戏数值或最终可玩验收。
