# 序章第一场战斗的数据恢复

2026-10-14。已从 APK 恢复一条可用于重建的真实教学战斗数据链：**新号课程入口 → 活动2／关卡3997 → 地图3997 → 战斗5000 → 单只怪物991“幻眼魔方”**。同时恢复艾尔莎100级的教学配置、七张指定卡牌、八项双方技能的状态／时间线索引、敌方行为树与模型资源。没有运行 APK 代码、原服务端或 UI；这些数据尚不是完整可玩的战斗实现。

机器入口为 `analysis/first-encounter/encounter.json`，全部字段及逐字段来源见同目录 JSON。工具 `tools/trace_first_encounter.py` 默认可重建该集合，重新校验整个 APK 的 SHA-256：`aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。本调查沿用 reverse-engineer-anything 的静态证据边界，复用已确认的本地 marshal／opcode／NPK 解析器，不创建新的 REA Evidence 编号。

## 为什么选择这场战斗

选择来自明确的新号入口和教学引用，不是比较 ID 大小：

1. `common/new_player_course.py`，script index **5947**，常量路径 `[4]` 的 `startNewPlayerCourse`，字节码 `0x00..0x2d` 将 `const.PRE_FIRST_ENTER_GAME_CHALLENGE` 的 `activityID`、`challengeID`、`UseChars` 传入 `athlete.doEnterChallenge`。
2. `common/const.py`，index **6221**，模块字节码 `0x3fd..0x426` 构造并保存 `PRE_FIRST_ENTER_GAME_CHALLENGE`：活动2、关卡3997、`UseChars={1:CharPos.MID}`、`BefroeRegisNameAvg=9991`。字典保存栈为 value 后 key，因此该键1是角色 ID，不把它误读成站位。
3. `guide_group_table.py`，index **9623**，行1001直接命名“序章-第一场战斗”，条件 `MazeId=3997`，过期条件引用 `BattleId=5000`；行构造偏移 `[273,362)`。行1002命名“序章-BOSS战”，指向3998／1703。
4. `guide_table.py`，index **8791**，行1850“序章-战斗0-摸牌”引用 `BattleId=5000,Count=1`；行1858引用同一战斗、Count2。组1001及其 `NEXT_GUIDE` 闭包已导出，包含属于共享组1000的1855，未因不同 GROUP 错当成缺失。`GuideCondition.py` index6525 `[12] dungeonCurMazeId` 的 `0x2d..0x48` 实际比较当前地图；`[11] battleRoundCount` 的 `0x3f..0x5d` 调用 `getCurBattleRoundCount(BattleId)` 并与 Count 比较。
5. `challenge_table_39.py`，index **5921**，3997的 `MazeIDList=[3997]`；3998另有 `Unlock=[3997]`，提供先后关系。`maze_table.py` index **1303** 行3997的 `LoadingBattleID=5000`。

重要限定：5947的 `[3] isNewPlayerCourse` 当前只是 `LOAD_GLOBAL False; RETURN_VALUE`。这不能验证原客户端的新号自动触发仍完整；也不否定同模块入口函数与静态课程内容。重建客户端可把此历史教程做成显式入口，那属于新客户端的设计，不能称为已经复原原服务器的触发条件。

## 关卡与单个敌人

| 环节 | 原脚本 index／行 | 已恢复字段 | 行字节码范围 |
|---|---|---|---|
| 关卡 | 5921／3997 | 序章·终局；MazeIDList3997；AllowLess3Char=True；HasLoot=False；challengeLevel100 | `[32,290)` |
| 地图 | 1303／3997 | LoadingBattleID5000；BanAuto1；BanBarrage=True；LoadingBattleScene中5000→2133 | `[59136,59227)` |
| 战斗 | 4664／5000 | MonsterInfo仅含MonsterID991、SpawnPointIdx0；MonsterSpawnIndex5；MaxRoundFail30 | `[32,143)` |
| 怪物 | 2363／991 | 幻眼魔方；BT_PATH=newbie_cube.xml；ENTITY_ID6605；level1.0；enforce_maxHp4600；enforce_PropAtk2.0 | `[2640,2851)` |

战斗行的 `BattleName` 仍写“蜘蛛蝎”，而 MonsterInfo 明确指向幻眼魔方。按实际 ID 关系恢复怪物，不能按显示名称挑资源。战斗行 `BattleScene=2081` 与地图 `LoadingBattleScene={5000:2133}` 均原样保留；本轮未把后者的场景选择优先级冒充为已验证的完整运行结果。

生命／攻击覆盖有控制流证据，不只靠字段命名：`combatUtils.py` index **3510** `[69] getForceProp`，`0x18..0x2b` 读取 `monsterData.get('enforce_'+propName,None)`；`const.CharBasicProps` `[190]` 将 `PropHP` 定义为 `maxHp`。`[70] getMonsterHP` 和 `[74] getMonsterATK` 在 `0x15..0x24` 判断结果不是 None 即直接返回，绕过后面的成长与关卡倍率。因此这两个函数针对991返回 **4600／2.0**，不能把挑战等级100直接套进怪物成长表覆盖它们。这仍是基础属性入口的结果，不是已观察的最终战斗实体、增益或伤害。

`monster_info` index6708行1也已保存为参考，但不拿它的普通HP250／攻击25替代强制值。其余防御、成长、战斗修正必须沿实际初始化路径确认，未虚构最终属性。

## 敌方行为树与技能

原 `assets/assets.list` 确实包含 `bt/newbie_cube.xml`。按已验证的 NeoX name hash 定位到 `assets/assets.npk` **entry225**，NPK offset110056，解压2435字节，SHA-256 `b7286ce138ec548dc4f6cf50ae95d7857bb3c146f22bc7f69fb5bc51b5b8a809`。XML真实结构为：

- 玩家回合开始分支：RoundComparison为1／2／3时分别调用 ShowSkillIntentions990／991／992；之后的回退节点为990。
- 自身回合开始分支：UseIntentionSkill，再 RoundEnd。

这是行为树中声明的规则。`PlayerRoundStart`、`RoundComparison`、`UseIntentionSkill` 的原服务器调度与节点实现未执行验证；不能仅凭XML承诺目标选择、回合增量和失败分支完全等同原服务端。

| 技能 | 显示名 | skill_state行／源图 | STORYLINE_PARAM | timeline行／动画逻辑名 |
|---|---|---|---|---|
| 990 | 轻击 | 2／SkillState_MonsterCauseDamage | VALUE302 | 558／ATK_1 |
| 991 | 重击 | 3／SkillState_MonsterCauseDamage | VALUE402 | 559／SPL_1 |
| 992 | 防护 | 4／SkillState_AddShield | VALUE300 | 560／SHD_UP_2 |

技能表index9333、状态表index8903、时间线表index6655已保存完整字段和逆索引赋值偏移。每个逆索引指向的行均与 `OwnerSkill` 交叉验证。图 **2657** 的 `IntParameter` 节点 `3qx53m3vPsDDRPqMAE9e4Y` 声明参数VALUE，并将输出接到 `CardFormulaAndDealDamage` 的 `finalExtraDamage`；图 **7455** 将 `SkillGetRpgValue` 与 VALUE 经 `IntAddNode` 接到 `AddShieldCard.shieldValue`。保留原JSON图、节点ID和连线，不执行图。

技能内部名称含“攻15／攻20／盾15”，却与实际参数302／402／300不一致，不能用名称数字替代字段，也不能未经目标／参数注入／公式证据就把VALUE认定为最终伤害或护盾。

## 真实教学玩家与七张牌

`new_player_course_table.py` index **4105** 行1 `[22,94)` 明确：`FirstBattleID=5000`、`BattleChar=[1]`、`CharLevel=[100]`、`DisableSpecialSkill=True`、`SkipChooseChar=True`。课程逆索引5000→1也已恢复。七张牌按源数组顺序为：

`410101, 110001, 210003, 110009, 210003, 110001, 410102`，每项角色ID均为1（艾尔莎）。

5947 `[7] getAvatarCharInitCardPile` 的 `0x28..0x76` 匹配 FirstBattleID、枚举 CardPile、按角色过滤并返回 `(cardID,index)`；`[11] getBattleCharInitLevel` 的 `0x38..0x83` 按 BattleChar 对应索引返回 CharLevel。源数组位置是已知数据，抽牌从哪端开始、首次如何发牌仍需调用端确认。

| 卡牌／技能ID | 名称／费用 | 卡牌参数 | skill_state逆索引 | timeline逆索引 |
|---|---|---|---|---|
| 110001 | 斩击／1 | FACTOR80 | `[294]` | `[2923]` |
| 110009 | 猛力斩击／2 | FACTOR150 | `[296]` | `[2925]` |
| 210003 | 强力斩击／1 | FACTOR100 | `[311]` | `[2938]` |
| 410101 | 二连斩击／1 | FACTOR75 | `[365,366]` | `[2983]` |
| 410102 | 疾驰斩击／2 | FACTOR300、VALUE0 | `[368,367]` | `[2984]` |

状态365／366同属 `SkillState_CauseDamage`；368为伤害、367为 `SkillState_getCard` 且参数VALUE1。逆索引顺序原样保留，未将 OwnerIndex 当成已证明的执行时序。时间线均为TIME0的动画条目；例如410101有 `ANIMATION_LIST=[ATK_3,ATK_5,ATK_2]`，不能单凭该列表推导攻击命中次数。

数值冲突也保留：110009卡牌FACTOR150，而状态296的 `RPG_DEFAULT_FORMULA='80'`；410102卡牌FACTOR300，而状态368默认公式为200。结合既有参数恢复结论，最终注入选择仍是待解决边界。数据不做修正或自选。

课程行没有能量字段。本报告不把全局DefaultBattleEnergy等常量当作这场教程实际初始化的已证事实。

100级玩家属性的具体下一锚点是 index **2165** `CommonAthleteCharBasicProp.py` `[6,7] getCharLevelBasicPropByLvAndRarity`：`0x15..0x57` 查角色CHARTYPE及职业倍率，`0x5a..0x7b` 查等级成长，`0x7e..0xc3` 查rarityRatio／rarityBaseValue，`0xc6..0xf9` 取 `char_basic_prop` 字符串公式并调用原eval。这里只解析并保存公式字符串，**没有执行eval**。已恢复艾尔莎CHARTYPE1、等级100的totalCultivateValue704、职业HP倍率2.2／攻击倍率0.6及原始公式；教程实际稀有度、装备／收藏品／天赋修正尚未确定，不能据此给出最终HP／攻击数值。完整组合还在 `[6,3] getSingleCharBasicProp`、`[6,22] getCharMaxHP`。

## 模型与资源可用性

怪物991 → `entity_table[6605]` → `model_lod_table[6605].LOD_MODEL_LIST=[66051,66052]` → `lod_index_table[66051]` LEVEL0，指向紫色异界魔方GIM；没有通过图像相似或固定ID减法猜映射。

| 资源 | character.npk entry／offset | 解码大小 | SHA-256 |
|---|---|---:|---|
| yuanjieguai_yijiemofang_purple.gim | 6648／19843824 | 11893 | 99c37714e0912f7cd6bef546e7e7774860155bebf5853bd3953ce7137b58dcb6 |
| yuanjieguai_yijiemofang.mesh | 1902／20526264 | 314503 | 21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa |
| yuanjieguai_yijiemofang.gisacl | 6081／19194576 | 13278 | cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0 |

目录均为 `character/monster/yuanjieguai_yijiemofang/`。GIM直接引用上面的mesh与gisacl，根资源逻辑路径、hash、NPK记录和解码摘要见 `resources.json`。小量网格解析成功：**4208顶点、6246三角、61骨、1子网格**，完整消费314503字节，权重和最大偏差2.98e-8，索引／骨骼边界校验通过。GISACL动画库列出8片段：fire、hit_1、death、idle、skill_1、skill_2、skill_3、skill_2_1。实体动画映射把ATK_1→fire、SPL_1→skill_2、SHD_UP_2→skill_3，与三项技能时间线形成可用表现链；本轮未解码这些动画帧、导出GLB或恢复材质效果。

## 可复现范围与未完成部分

```powershell
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 tools/trace_first_encounter.py
```

工具验证整APK、输入marshal摘要与完整消费、精确表行引用、metadata枚举来源、skill逆索引与OwnerSkill一致、实际NPK名称hash、网格范围和动画库结构。本轮已实际执行通过。所有表行和字段保留字节码区间、常量索引及NPK来源；分片表只静态跳过已识别的metadata import，读取其直接标量声明作为枚举，重新映射偏移，不运行import或包装器。未知指令／函数值拒绝；原始`taggeddict`包装行为和热更结果不在恢复结论中。

当前内容足以支撑一个**以原教学数据为依据的新客户端显式战斗入口**，但仍需实现并验证：100级玩家实际属性、七张牌的发牌方向和回合初始化、技能参数覆盖与目标选择、伤害／护盾及AI节点调度。奖励尤其不能直接照搬：challenge3997明示HasLoot=False，而battle5000含DropPersistentItems；没有恢复奖励发放路径前，不将其宣称为实际奖励。模型材质和实播表现另作后续工作。

## 补充：显式稀有度4的100级基础配置

可供重建模式直接引用的配置已保存为 `analysis/first-encounter/player-baseline.json`；完整表行、字段来源及局部指令证据在同目录 `player-baseline.evidence.json`。这份配置**显式选择稀有度4（高阶），只计算等级／稀有度基础公式**，并不宣称恢复了原首战最终属性。它关闭装备、专属装备、收藏品、天赋、生命树、好感、等级／稀有度故事线附加、活动、羁绊、GM及战斗临时修正；这些排除项是重建模式定义，不是原账号状态的已知事实。

稀有度证据现在比前一轮明确：

- `character_basic_info.py` index8995，角色1行 `[136,501)` 有 `CHARRARITY=4`（字段 `[184,187)`，常量5）、`CHAR_SUB_RARITY=0`（`[205,208)`，常量2）、`InitChar=True`（`[375,378)`）。这里没有额外假设“最小稀有度”。
- `iCAthleteChar.py` index9420 `[9,24] getCharRarity` 在 `0x00..0x29` 检查角色是否存在于 `characterDbData`，存在时读取同步数据中的 `rarity`；不存在时 `0x2a..0x49` 明确返回 `character_basic_info[int(charID)]['CHARRARITY']`。`[9,26] getCharSubRarity` 同样回退 `CHAR_SUB_RARITY`。
- 同模块 `[9,73] getCalculationRarity` 在没有该角色数据时，`0x36..0x4e` 返回 `(rarity,0)`；有角色数据时还可能经过临时稀有度覆盖。2165 `[6,6] getCharLevelBasicProp` 的 `0x1b..0x37` 接受显式 `charRarity`，未传入有效值时才调用 `getCalculationRarity`。
- 9420 `[9,0] __init__`、`[9,1] init_from_dict`、`[9,2] onCreate` 没有本地指定角色稀有度；`[9,28] unLockChar` 把外部 `data` 交给 `addANewCharacter`。`CAthlete.py` index1703 `[101,3] addANewCharacter` 的 `0x0f..0x21` 直接将传入 `data` 写到 `characterDbData[str(uid)]`，不补入稀有度。因而客户端缺省读取路径已证实，服务端创建初始记录的实际值仍未证实。
- 5947 `[4] startNewPlayerCourse` 只传活动、关卡、布尔值、角色位置和空字典；4105课程行1给出 `CharLevel=[100]`，没有稀有度字段。不能由课程强制100级推出其稀有度必为4。

手工受限算式只支持并逐字核对源公式 `occupation*((100+increase)*rarityratio*1+raritybase)`。修正后的生成器保留原字段的Python `float` 类型及常量100、1的 `int` 类型，按原括号和运算顺序执行我们手写的表达式，**不 eval／exec 游戏字符串，也不运行或编译游戏字节码**。原先先算Decimal再转float的方式会丢失这个表达式的binary64舍入差异，已替换；`exactDecimal` 仅保留为十进制数学参考，不参与输出属性计算。

| 输入／结果 | maxHp | PropAtk | 原始来源 |
|---|---:|---:|---|
| occupation | 2.2 | 0.6 | 1617职业1，字段 `[90,93)`／`[69,72)` |
| increase | 704.0 | 704.0 | 8577等级100，字段 `[5270,5273)` |
| rarityratio | 1.0 | 1.0 | 6181稀有度4，字段 `[304,307)` |
| raritybase | 0.0 | 0.0 | 6181稀有度4，字段 `[297,300)` |
| 十进制数学参考（非运行值） | 1768.8 | 482.4 | `exactDecimal` |
| 保留原类型运算的binary64结果 | **1768.8000000000002** | **482.4** | `baseStats`／`baseStatsTagged.decimal` |
| binary64精确十六进制表示 | `0x1.ba33333333334p+10` | `0x1.e266666666666p+8` | `baseStatsTagged.hex` |

每项 `baseStatsTagged` 明示 `numeric_type="binary64"`，`decimal` 是能往返恢复相同浮点位值的十进制字符串，`hex` 精确保存binary64值。`baseStats` 普通JSON数值也来自同一次float运算。1768.8000000000002与将十进制1768.8直接转float的结果相差一个ULP，不能互相替换。上述是静态重建计算的值，不是原APK运行时观测。

这条窄检查没有发现最终整型截断：2165 `[6,7] getCharLevelBasicPropByLvAndRarity` 在 `0xf9` 直接返回公式结果；`[6,22] getCharMaxHP` 从 `0xd6` 组合加乘，在 `0x1a8` 直接返回，无 `int`／`round`；`[6,3] getSingleCharBasicProp` 在 `0x2e9` 直接写 `data[k]`，`0x363` 返回数据。该函数 `0x100..0x109` 的 `int` 调用转换的是 **charID**，不是属性。因此JSON保留1768.8000000000002和482.4，不擅自取整。后续战斗实体、序列化、显示或伤害层是否另有类型转换，不在本次结论内。

复现补充配置：

```powershell
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 tools/trace_player_baseline.py
```

补充工具重新校验所用marshal模块的SHA及完整消费，验证关键表值、原始float类型及公式原文，校验本地Python使用binary64；计算后回读JSON，分别从普通数值、十进制标签和十六进制标签还原并比较 `.hex()`。同时断言HP结果不同于将数学参考1768.8直接转float，防止重引入精度替换。修正后生成器已运行通过。整APK身份沿用前文主工具已完成的校验。生成器位于受版本控制的 `tools` 目录，原analysis目录生成器已迁移。
