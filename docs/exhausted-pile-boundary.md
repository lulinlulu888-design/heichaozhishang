# 湮灭牌堆的接收链与未恢复边界

2026-10-14。工具 `tools/trace_exhausted_pile_boundary.py` 扫描 9,698 条解码脚本索引，以六个确切名称/字面量筛出 14 个模块、48 个代码对象。候选 marshal 文件经索引 SHA-256 核验，报告保存方法常量路径、字节码哈希、指令偏移与上下文。这是普通本地静态提取，不是 REA 运行证据；扫描不覆盖动态拼接、原生实现及服务器代码。

## 已确认的客户端行为

- `CardPileActions.py`（1686）`ExhaustedCardPileChangeAction.onReceive` 读取 `Args.uuids`，解析现有卡牌信息，再调用 `dataSyncPile(CONSUMED_PILE, cards, Args.get('_isEnemy', False))`；`play` 对同一数据调用 `viewSyncPile`。这是收到的完整牌堆同步，不是决定哪些牌应该湮灭的逻辑。
- `DrawDiscardCardActions.py`（5026）`ExhaustCardAction.onReceive`（常量路径 23.1）读取 `Args.cardIDs`，调用 `dataMoveCards(HAND_CARD_PILE, CONSUMED_PILE, cards)`；`play`（23.2）更新表现牌堆后调用 `exhaustSomeCard`。
- 同模块 `RemoveCardsAction`（25.1、25.2）与以上两个方法的解析指令、参数和常量一致，仅源行号不同。不能依据名字给它赋予新核心 `removed` 的语义。
- `DrawFromExhaustAction`（15.1、15.2）使用 `Args.uuids` 对应卡牌，从 `CONSUMED_PILE` 移入 `HAND_CARD_PILE`，说明客户端支持显式取回；此动作没有恢复选牌条件或自动冷却时点。
- `SpecialDiscardCardAction`（19.2、19.3）从 `Args.get('pileType', USED_PILE)` 读取目的区。`doInit` 依特殊牌或该目的区是否为 `CONSUMED_PILE` 选择溶解表现。这个视觉分支不能用于推导服务端的出牌目的区。

## 实现决策

继续保留首战禁止非空终止牌堆的校验，以及客户端湮灭规则未恢复提示。现有纯牌堆核心能执行显式区域迁移，但不能替代缺失的权威路由条件。新增玩法可定义独立规则版本；不能将其称为原版恢复。

后续应追踪动作生成方、卡牌动态属性与关键词冲突顺序，并区分 `uuids` / `cardIDs` 两种动作入参。原服兼容适配时应分别建模接收数据与表现时序，而不是根据动作名称猜目的区。

## 复核

运行 `python tools/trace_exhausted_pile_boundary.py` 可重建：

- `analysis/battle-ui/piles/exhaustion/references.json`：有界引用清单。
- `draw-discard-actions.json`：模块 5026 完整静态指令。
- `remove-exhaust-equivalence.json`：两个动作的对应方法哈希与解析指令一致性检查。

本轮提取与一致性检查通过，未执行 APK、未改服务端行为、未声称已恢复湮灭玩法。
