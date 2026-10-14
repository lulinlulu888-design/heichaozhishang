# 首组游戏数据恢复

已从当前 APK 解密后的脚本中提取一组小型数据样本，可供重建客户端展示和 Node 领域实现研究使用。输出位于 `analysis/game-data/`，生成工具为 [extract_game_data.py](D:/hczs/tools/extract_game_data.py)。这是**本地静态解析证据**，不是 REA Evidence，也不是运行中的游戏行为观察。

## 已恢复的样本

| 文件 | 样本 | 来源模块 / NPK index | 原表行数 |
| --- | --- | --- | --- |
| `characters.json` | ID 1 艾尔莎、ID 2 琳、ID 3 未来的完整字段 | `common/cdata/character_basic_info.py` / 8995 | 228 |
| `initial_attacks.json` | 以上三个 ID 的初始化攻击字段 | `common/cdata/character_init_attack.py` / 1338 | 93 |
| `cards.json` | 410101、410102、410104、410105 的完整字段 | `common/cdata/card_table.py` / 3391 | 1538 |
| `skills.json` | 0、410101、410102、410104、410105 的完整字段 | `common/cdata/skill_table.py` / 9333 | 1487 |
| `sample.json` | 本次选择范围、卡牌/初始化字段中的技能引用，以及未找到的引用 | 上述样本之间的显式数值匹配 | — |

“完整字段”指该行传给 `taggeddict` 的字面量参数，不代表游戏运行后叠加、热更新或包装器处理后的最终对象。未把 `taggeddict` 视为可执行或已知无副作用的普通字典构造函数。

已观察到的卡牌字段示例：

| 卡牌 ID | `NAME` | `COST` | `SKILL_ID` | `SKILL_DIY_VALUE` |
| --- | --- | --- | --- | --- |
| 410101 | 二连斩击 | 1 | 410101 | `[75]` |
| 410102 | 疾驰斩击 | 2 | 410102 | `[300, 0]` |
| 410104 | 赤色地平线 | 0 | 410104 | `[38]` |
| 410105 | 飓风斩击 | 1 | 410105 | `[120]` |

上述数值原样导出。尚未证明 `SKILL_DIY_VALUE` 的计算单位和最终伤害公式，不能把 `[75]` 直接宣称为“固定伤害 75”或“75% 攻击力”。例如 410101 还有 `SKILL_DIY_PARAMETER=["FACTOR"]`、`RPG_FORMULA=[["AP"]]`，恢复公式解释器与战斗流程后才能验证它们的组合含义。

三个初始化行中的 `InitAttackSkillID=6002`、`InitDeffendSkillID=6003` 均原样保留，但这两个 ID 不存在于已识别的 `skill_table.data` 字面量表；`sample.json` 明确列为未解决引用，不生成占位技能或套用编号换算。

## 解析边界

本工具沿用 `reverse-engineer-anything` 工作流对静态证据与运行结论作区分；混淆 opcode 映射与现有静态脚本分析交叉核对。实际提取由自编工具完成，未创建新的 REA Evidence 编号。

接受的语法仅包括：

- 固定的 `taggeddict` 声明前导字节，作为识别标记处理，不执行 import。
- `LOAD_CONST (0x99)`、`LOAD_NAME (0x65)`、`STORE_NAME (0x91)`：有限常量和已声明常量名。
- `BUILD_MAP (0x97)`、`STORE_MAP (0x08)`：按 Python 2 的“map, value, key”栈顺序重建字面量。
- `BUILD_TUPLE (0x87)`、`BUILD_LIST (0x5a)`：有限数组字面量。
- `CALL_FUNCTION (0x83)` 仅识别 `taggeddict(一个字面量映射)` 的语法，保存其参数，不调用函数。

解析在第一个 `data` 赋值处结束，记录停止位置与未解析尾部长度。尾部包括辅助函数、部分表的 `extra_data`；本工具没有解释它们，也不宣称已恢复模块运行后的最终状态。未知操作、导入其他模块、任意函数调用、分支/循环、未解析名称、重复字典键、代码常量、非 UTF-8 字节及非有限数值一律拒绝。

Python 2 字节字符串严格解码为 UTF-8，字段名保持原大小写；列表/元组在 JSON 中均表示为数组。不会修正文案、拼写或字段中的零值。运行控制台编码有时不能显示中文，不影响输出文件的 UTF-8 内容。

## 来源追溯

每份表保存源 APK member `assets/script.npk`、NPK entry index/offset/size、原始 payload SHA-256、解密后 marshal SHA-256。输入必须与解密索引中的摘要和模块文件名匹配，marshal 必须完整消费。

每个样本行保存构造表达式起止字节码偏移、外层字典赋值偏移，以及由 Python 2 `lnotab` 推导的原始行号。每个字段还保存表达式偏移、常量索引、引用的名称和赋值偏移；模块内部枚举常量另有声明来源。行号属于字节码行号元数据，不是反编译生成文件的行号，定位时以字节码偏移为主要依据。

例如，卡牌 410101 的行构造位于 `card_table.py` 字节码 `[127044,127363)`，行号元数据为 16579。其解密后 marshal 摘要为 `c506ea0dd24ab8b7f35b2c563521ea83657668905345573de22a6273827c1d09`。

## 复现与验证

先完成当前 APK 的 NPK/脚本提取，然后在仓库根目录执行：

```powershell
python tools/extract_game_data.py
python -m unittest discover -s tests -p test_game_data.py -v
```

默认生成上面的 15 行样本及引用报告。也可显式选择一张表及精确 ID：

```powershell
python tools/extract_game_data.py --table cards --ids 410101 410104
```

该命令会重写 `analysis/game-data/cards.json` 为所选子集；重新运行默认命令恢复整组默认样本。使用 `--table cards` 且不传 `--ids` 时提取该表所有字面量行。输出为中立 JSON，不依赖 Node、Godot 或任何游戏运行时，当前均在忽略提交的 `analysis/` 目录中。

11 项标准库测试通过，覆盖合法字面量、来源定位、尾部隔离、未知操作/调用/导入拒绝、截断、边界、重复键、真实角色/卡牌数值和未解决技能引用。没有导入 APK 模块，没有使用 `eval`、`exec` 或构造 Python 可执行代码对象。

## 仍未解决

当前四张卡牌是明确选定的数据示例，不是已证明完整的初始卡组。另观察到 `card_build_table` 的 `CardItemID` 与 `card_table` 的行号属于不同编号空间；相关 `item_table_14101.py` 导入 `item_table_meta`。当前语法拒绝此额外导入，因此没有靠减去固定数值等猜测建立道具到卡牌映射。

下一步应以同样方式恢复明确的道具映射、角色成长属性和技能实现，再将字段翻译为新客户端/Node 领域模型。原数据保持原样，新增玩法采用独立版本与明确的覆盖层，不直接篡改静态证据。
