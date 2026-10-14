# RPG 值提供方与首战参数解析

本轮没有恢复出 `cardAction.getRpgValue` 的实现，也没有证明首战缺少 RPG 字段时该方法返回 0。已进一步分清三条容易混淆的路径：技能节点调用外部 cardAction；遗物/Buff 使用包内通用公式函数；卡牌文案另用列表形式的 AP 公式。它们存在相关字段，但不能互相替换为已恢复的原版结算。

已为首战五种卡牌、敌人技能 990/991/992 建立带字段来源的参数矩阵，并确认一个有限而具体的零值分支：`combatUtils.getCommonRpgFormulaValues` 遇到空公式会直接返回 0。**尚缺的是 cardAction 方法到该函数的调用边。** 这个通用函数在早期 battle-rules 整模块输出中已经存在，本轮新增的是消费者范围、缺字段分支、系数转换语义与首战参数差异核对，并非新发现了服务端 provider。

## 复现和边界

```powershell
python tools/trace_rpg_value.py
```

工具固定校验 13 个模块的解密 SHA256，读入时再次检查完整 marshal 和文件名。输出 `analysis/rpg-value/`：

- `function-sources.json`、各 `*_instructions.json` / `*_partial-dis.txt`：34 个精确函数，含 NPK offset、constant path、bytecode SHA256、逐指令偏移。
- `cards.json`、`skills.json`、`skill-states.json`、`state-index.json`：5 卡、8 技能、10 状态及原始逆索引顺序；不把索引顺序断言为运行顺序。
- `first-encounter-parameters.json`：同一张卡的文案、DIY、技能状态字段并列，未恢复的 RPG 返回值明确标为 `unresolved_provider`。
- `bounded-consumer-audit.json`：仅对已有非 cdata 符号索引查询 4 个公式字段名和 2 个通用辅助函数名；匹配的代码逐一哈希复核。
- `reference-vectors.json`：8 个有限小数值的独立人工翻译向量，验证空公式、系数先截断、结果不最终截断和错误分支；不是执行原始字节码，也不是原版动态差分。
- `provider-status.json`：准确调用边、尚缺的连接及复用负证据文件的 SHA256。

未执行 APK/原脚本、调用 UI、启动或停止任何进程。未修改共享核心、客户端、服务端。未重复 `getRpgValue` 全库名称扫描或 native 三编码扫描；REA native provider 既有环境限制没有改变，本轮没有新锚点可支持继续 native 定位。

## 实际 receiver 是 cardAction

`common/storyline_nodes/skill/data.py`，index **296**，`SkillGetRpgValue.Start [20,6]`：

| 字节区间 | 行为 |
| --- | --- |
| `[0,0x21)` | 读节点 target；只有它是 None 时才使用 context.owner |
| `[0x21,0x38)` | 调 `context.cardAction.getRpgValue(target)`，返回 `{'rpgValue':结果}` |

它没有调用 `owner.getRpgValue()`。owner 在默认路径中是传入 cardAction 方法的参数。

`common_storyline`（618）`BaseServiceCardActionSL.__init__ [24,0]` 从外部接收 cardAction，`setCardContext [24,2]` 将它放进上下文。本模块没有生成实际 cardAction 类；SService 上下文继续消费其 actionData/cardObj/skillID/skillUuid 等字段。

既有负证据显示，9698 模块的直接名称中只有上述调用，未找到同名定义/赋值；已读取的 libclient.so 三种字符串编码也没有具名注册锚点。**这不足以认定方法位于 native。** 仍不能区分缺失的服务端代码、动态注册/生成、另一个未识别载荷或线上更新缺口。本轮不把“没找到”包装成具体实现位置。

## 已证明的通用公式函数

`common/combatUtils.py`，index **3510**，`getCommonRpgFormulaValues [39]`，bytecode SHA256 为 `3990707827682727fe3d299c9f7a42e083dcacab4f3c5bd90918280d8a585ebd`。

| 字节区间 | 已确认语义 |
| --- | --- |
| `[0,0xa)` | strRpgFormula 为假时立即返回整数 0；不读取系数字段，也不调用 owner |
| `[0xa,0x32)` | 公式字符串按逗号拆分，每项 strip |
| `[0x32,0x66)` | 系数字符串按逗号拆分，每项执行 `int(float(strip值))` |
| `[0x66,0x84)` | 断言两组长度相等 |
| `[0x84,0xc6)` | 顺序累计 `owner.getRpgPropByKey(属性名) * 转换后系数 / 100.0` |
| `[0xc6,0xca)` | 返回累计结果，没有整体 `int()` |

例如显式属性结果 10、系数文本 `75.9` 得到 7.5，因为系数先变成 75；不是 7.59，也不是函数内部直接返回 7。重复的属性项分别读取并累加，不能先合并成一项再按不同位置截断。

空公式与空系数不是同一分支。空公式会忽略无效系数直接返回 0；公式非空而系数 None 会在 `.split` 处失败，系数为空字符串会在数值转换处失败，长度不同会触发断言。本轮没有把这些失败“修好”为 0。

限定静态索引中，直接消费者只有：

- **3598:10.6 `RelicGetRpgDamage.Start`**：读取 `context.excelData` 的两个 RPG 字段，调用通用函数，随后再 `int()`；excelData 本身为空时直接保留初始 0。
- **3207:6 `BuffDataTools.getBuffDescriptList`**：在 RPGValue 文案分支使用该函数；可按 buff 次数乘值，随后转 int。

3510 自身另有函数定义；没有观察到 cardAction 对此函数的直接调用。`RPG_FORMULA/RPG_DEFAULT_FORMULA` 的其余直接消费者是 CardDataTools、ClientCard 和 BuffDataTools 的字段读取/文案辅助函数。这个结果限于确切名称及已有短字符串索引，不能证明动态别名、隐藏字节码或外部代码不可能调用它。

相关属性方法 **7554:5.13 `getRpgPropByKey`** 先取初始属性，再按现有 modifier 迭代顺序逐项相加，仅 PropAtk 限制不小于 0。其基类初值方法 **7554:5.14** 对 maxHp 读对象字段，对其他键用 `rpgProp.get(key,0)`。这证明该基类的缺属性分支，但不能证明所有实际实体都不重写它，更不等于技能缺公式字段的处理。

## 技能适配器的缺字段结果是 None

`skillTableAdapter.Adapter.__getattr__`（8010:353.1）的优先级仍是行顶层→DATA 子表→None；只有 TYPE 另做类型名转换。找不到 RPG_FORMULA 或 RPG_DEFAULT_FORMULA 时，[0x7d,0x81) 返回 None，**不是 0**。

如果一个尚未恢复的 cardAction 方法随后把这个 None 原样传入通用公式函数，后者会返回 0；这是一个有明确前提的推论。缺失的 cardAction 完全可能有别的覆盖、默认值、属性来源或错误处理，当前证据没有证明这个前提成立。

## 五种初始卡牌的三层参数

卡表 index **3391**；技能表 **9333**；状态表 **8903**。原表及每个字段的构造偏移均在产物中。下列百分数只表示公式配置系数，不是实战最终伤害。

| 卡牌 / skill | 卡表 AP 文案系数 | 卡表 DIY 原字段 | 技能状态配置 |
| --- | --- | --- | --- |
| 110001 | 80 | FACTOR=80 | 294：PropAtk，系数字符串 `80`，额外伤害0 |
| 110009 | 150 | FACTOR=150 | 296：PropAtk，系数字符串 `80`，额外伤害0 |
| 210003 | 100 | FACTOR=100 | 311：PropAtk，系数字符串 `100`，额外伤害0 |
| 410101 | 75 | FACTOR=75 | 365、366：均为PropAtk、字符串 `75`、额外伤害0 |
| 410102 | 300 | FACTOR=300、VALUE=0 | 368：PropAtk、字符串 `200`；367：抽牌图、VALUE=1、无RPG字段 |

卡表的 AP 配置是嵌套列表，状态表是 PropAtk/系数的逗号字符串，两者不是同一种输入格式。`getCardDefaultValue`（9137:9.8）只返回卡表字段；CardDataTools 的角色/地牢/战斗文案函数（9176:42/43/44）调用 `getRpgNumberValues`，不能证明技能对象使用相同系数。

110009 的 150/80 和 410102 的 300/200、VALUE 0/1 冲突仍不能消除。原 `getCardParamList` 已证明“若运行时 diyActionData 含某键，就覆盖图参数，包括 0”，但卡表 DIY 数组的运行时构造和 FACTOR 如何进入 getRpgValue 仍未恢复。不能用字段名字相同或文案相符替代这条缺失的连接。

状态367的抽牌图没有SkillGetRpgValue节点，因此它自身不需要RPG提供方；矩阵明确标为 `not_requested_by_this_graph`。它尚未解决的是VALUE覆盖来源与实际抽牌接口，不能因缺RPG字段就给抽牌补一个RPG数值。

## 敌人 990/991/992 的参数已经定位，基础 RPG 仍未定

| skill / 状态 | 确定存在的图参数 | 确定的图内使用位置 | 尚未证明 |
| --- | --- | --- | --- |
| 990 / 2 | VALUE=302 | MonsterCauseDamage → DamageInfo.extraDamage | getRpgValue(owner) 的基础结果 |
| 991 / 3 | VALUE=402 | 同上 | 同上 |
| 992 / 4 | VALUE=300 | AddShield → RPG值+300 → calcBlock | 同上 |

三行顶层与 DATA 均没有 RPG_FORMULA/RPG_DEFAULT_FORMULA；图仍会调用 cardAction.getRpgValue。302/402 不是已经确定的最终 HP 减少值，300 不是已经确定的最终护盾。原图的后续标量、modifier、护盾/HP状态接口仍会影响结果。

当前可以把图参数、原始表值和接口形状接入新服务端，并要求 RPG 提供方显式返回结果；缺失时报告未解析依赖。若需要先完成可玩的重建首战，可单独制定并版本化“无公式返回0”“卡表DIY优先”等策略，但必须标为重建设计，并保留原始冲突值供后续替换。当前静态证据不足以称这些策略为原版行为；继续重复同一名称扫描也不能完成这种验证。
