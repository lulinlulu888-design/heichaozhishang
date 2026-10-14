# 牌堆与回合基础规则

2026-10-14。本轮将包内说明、常量定义与客户端可用性提示分开恢复，并实现了新战斗核心所需的确定性牌堆操作。尚未实现整场战斗调度、能量扣除、技能结算、随机数状态或奖励。

## 已确认的包内说明

`tools/trace_battle_foundation.py` 对五个原 marshal 模块锁定 SHA-256，完整解析后导出 `analysis/battle-foundation/`。它只识别字面量与记录函数指令，不执行原字节码。

| 规则 | 原字段依据 |
| --- | --- |
| 回合开始从抽牌堆随机抽手牌 | 3935 `code_content_table.CHOUPAI/CARD_TIPS` |
| 回合结束将剩余手牌放进弃牌堆 | 3935 `QIPAI`；存在下列关键词例外 |
| 抽牌堆空时，将弃牌洗回抽牌堆 | 3935 `SHUFFLE_CARD_INSTRUCTION` |
| 普通洗牌不使用湮灭牌 | 3935 `CONSUMED_PILE_INSTRUCTION`；6593:57 的“冷却”另有返回机制 |
| 护盾抵消伤害，默认在下次己方回合开始清空 | 6593 `key_words_table` 行5 |
| 保留牌在回合末留手；不稳定/临时牌在手时湮灭 | 6593 行12、8、61 |
| 终结技和虚幻牌离开手牌时移除 | 6593 行53、71；不等同于进入湮灭牌堆 |
| 回溯牌打出后进入抽牌堆随机位置 | 6593 行22 |
| 连续三个角色连击点产生终结技，每角色每回合最多三次 | 3935 `BATTLE_ULT_TIPS` |

完整原文和字段偏移保存在 `code-text.json`、`keywords.json`。这是产品规则说明证据，无法单独证明触发顺序、关键词叠加优先级、伤害穿盾细节或冷却返回时点。它足以指导新实现的职责划分，但不能冒充原服务器代码或实战录制。

后续静态核对修正：上表“移除”与“湮灭”的说明差别不能直接映射为原客户端两个不同的动作目的区。模块 5026 `DrawDiscardCardActions.py` 中 `RemoveCardsAction` 和 `ExhaustCardAction` 的 `onReceive`、`play` 去除源行号后解析指令完全一致，均从 `Args.cardIDs` 读取实例，并将 `HAND_CARD_PILE` 移到 `CONSUMED_PILE`。新核心的 `removed` 是重建设计，不是通过该原客户端动作证实的单独区域；原服务器的永久移除、冷却及关键词优先级依然未知。证据见 `analysis/battle-ui/piles/exhaustion/remove-exhaust-equivalence.json`。

## 常量与实际运行值的区别

`common/const.py` index6221 模块体中有以下相邻 `LOAD_CONST → STORE_NAME` 定义：

| 名称 | 字面值 | 指令范围，末端不含 |
| --- | ---: | --- |
| `MAX_DRAW_CARD_NUM_WHEN_ROUND_START` | 10 | 0x3a0–0x3a6 |
| `MAX_HAND_PILE_NUM` | 10 | 0x3a6–0x3ac |
| `DRAW_CARD_NUM_PER_ROUND` | 6 | 0x3ca–0x3d0 |
| `MAX_SPECIAL_SKILL_ONE_CHAR_ONE_ROUND` | 3 | 0x3d0–0x3d6 |
| `DefaultBattleEnergy` | 5 | 0xe46–0xe4c |
| `DEC_DRAW_CARD_NUM_PER_ROUND_LOST_CHAR` | 1 | 0x459d–0x45a3 |

对9698项脚本符号记录的精确名称查询，仅在该常量模块自身命中。这不排除服务端、动态引用或其它加载路径；也不能把这些值直接称为“已验证首战每回合初始化”。新牌堆接口要求显式传入有效手牌上限和抽牌数量，不隐式应用这些声明。

客户端 `iCCardPile.isCanPlayCard`（4942:`8.38`）甚至在非玩家回合直接返回 True；玩家回合中 `energyAll` 分支先于 `canNotPlay`，随后才比较 `energy <= fei`。这个方法用于视图提示，不能照搬为服务端出牌校验。自动战斗 `ClientGameProxy.isCardCardUse`（5445:`6.11`）消费同步的 `canUse` 并排除 `usingCardUUIDs`，也没有生成权威可用性。

## 新实现的边界

`@hczs/battle-core/piles` 提供 `createPiles`、`drawCards`、`movePlayedCard` 和 `finishHandRound`，只有不可变的实例ID与状态转换，没有 Node/Cocos 专用API。其事件是新项目内部事件，不是原服的动作报文名称。

- 五种现存牌堆另加本地 `removed` 终止区，保留实例去向；同一实例必须且只能出现一次。相同牌型的不同实例可以同时存在。
- `drawCards` 按显式队列顺序取牌；发生弃牌回填时必须提供弃牌实例的完整排列，不内置一个假称原版的 RNG。湮灭、能力已用和移除区不参与普通回填。
- `movePlayedCard` 只消费已经解析好的目标牌堆；回溯到抽牌堆时必须明确插入位置。它不判断出牌是否合法，也不扣能量。
- `finishHandRound` 要求手牌每个实例都有且仅有一个去向。调用方先解析保留、临时、虚幻等关键词与 Buff 的优先级；此模块不会替尚未恢复的冲突规则默认作决定。
- 所有输入先校验，返回新状态；无论中途发现非法排列还是去向，输入都不发生部分修改。事件按当前手牌顺序输出是新实现的确定性选择，不声称恢复了原触发时序。
- 输入记录只能含数据属性，列表使用普通密集数组；稀疏数组、访问器、数组子类及自定义迭代器/额外数组字段都拒绝。洗牌排列按自身索引复制一次，在同一份私有副本上校验并使用，避免检验通过后又从另一个迭代结果取牌。这是新接口的完整性约束，不是任意 JavaScript Proxy 的安全沙箱。

12项测试覆盖跨抽牌/洗牌/出牌/回合末的实例守恒、关键词去向、牌堆排除、达到手牌上限、错误原子性、显式随机排列、稀疏排列拒绝、访问器/自定义迭代器不执行与不可变边界。现有 Creator TypeScript 编译器同时检查牌堆和数值消费者；非抽牌堆去向只接受省略或空 options，错误参数由类型断言覆盖。测试全为合成实例，没有冒充原战斗记录。

```powershell
python tools/trace_battle_foundation.py
node --test packages/battle-core/test/piles.test.mjs
```

下一步将首战的真实初始牌组与技能图连接到这些操作，再实现明确版本的重建调度规则。需要分别记录已恢复原行为、由说明推导的行为和重建设计；当前模块通过不能视为首战已经可玩。
