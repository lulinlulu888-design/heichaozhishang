# 教程首战初始化与回合补牌的静态边界

2026-10-14。**本轮补全了初始能量进入客户端的具体路径，以及普通抽牌动作接收的字段；仍不能把当前教程的初始能量 5、回合能量 5、首次抽牌 6、每回合抽牌 6 升级为原版已验证规则。** 未修改服务端、战斗核心或教程政策。

调查沿 `analysis/first-encounter/` 的教程入口和 `docs/battle-foundation.md` / `docs/card-action-recovery.md` 的具体函数继续，不重复 `getRpgValue` 搜索。按 REA 静态证据流程复用原 APK 身份与解密 marshal；没有执行游戏字节码、APK、UI 或服务进程。

## 复现与范围

```powershell
python tools/trace_tutorial_turn_setup.py
```

工具固定 **20 个 marshal 文件的 SHA-256**，完整解析并验证文件名，导出 **62 个选定 code object、9 项结论、31 个机器校验的字节范围锚点**。导出物均位于 `analysis/tutorial-turn-setup/`：

- `turn-setup.json`：字段流、偏移锚点、声明常量、精确外部方法查询及政策状态。
- `function-sources.json`：每个函数的模块 index、源文件名、marshal SHA、NPK payload 偏移、constant path、bytecode SHA 与完整部分反汇编。
- `functions.partial-dis.txt`：同一证据的紧凑可读版。
- `module-sources.json`、`input-fingerprints.json`：源载荷和本地输入身份。
- `action-map-slice.json`：真实动作名 `BattleBegin/RoundBegin/DrawCard/EnergyChange` 到表现类的字面量映射。

下文的 `126:3.0` 表示 NPK 模块 index 126、code object 的 constant path `[3,0]`；字节范围左闭右开、相对于该 code object，不能当作 APK 文件偏移。工具保留未知 opcode，不给它们猜测语义，也不构造或调用游戏 code object。

APK SHA-256：`aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。原归档身份复用 REA Evidence `ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220`（`analysis/rea/session-evidence.json`）；本轮函数分析是本地静态提取，未冒称新的 REA 工具结果或实际网络流量。

## 初始化确实消费 team1 字段，而非本地设置 5

新补全的调用链为：

| 来源 | 直接观察的操作 |
| --- | --- |
| 6597 `net/mbsentity/CAvatar.py` `25.2` `[0x37,0x50)` | `init_from_dict` 把 `bDict.get('battleInfo', {})` 传给 `_initBattle`；此前已对顶层字典逐项 `setattr` |
| 4153 `net/interfaces/iCAvatarBattle.py` `15.1` `[0x15,0x34)` | 创建 `Battle(battleID)`，调用 `onBattleInit(battleInfo)` |
| 2697 `net/battle/CBattle.py` `12.12` `[0x23,0x3e)` | 将 `battleData.get('team1', {})` 传给 `AvatarTeam` |
| 126 `net/battle/CAvatarTeam.py` `3.0` `[0,0x40)` | 遍历传入字典，先 `setattr(self,k,v)`，再 `setattr(Globals.BattlePlayer,k,v)` |
| 4153 `15.3` `[0,7)` | `energy` 属性直接返回 `self.fei` |

因此 `battleInfo.team1.fei/maxFei` 是可进入初始玩家状态的字段；不能因为没有字面量 `self.fei = ...` 就判断其未同步。这里证明的是字段接受路径，**不是已经抓到首战实际发送的值**。

之后 5455 `iCAvatarCombat.onInitedFromDict` `7.2` `[0x26,0xdd)` 还会顺序合并顶层 `clientCopyInfo`、`battleInfo.team1.clientCopyInfo`、`battleInfo.clientCopyInfo`，再把合并结果逐项写入对象；后面的同名字段覆盖前面的同名字段。该函数 `[0xdd,0x137)` 另读 `team2.fei/maxFei`，缺失时使用 `-1`，写入 `enemyFei/enemyMaxFei`。这是敌方资料缺失的占位值，不是正常战斗能量规则。

`4153:15.6` 的战斗更新也会遍历 `propertiesInfo.battleInfo.team1` 并逐项设置玩家字段。其触发仍沿 `ClientUpdateBattleProperties` 的接收/播放两阶段路径，不能把这个无条件字段复制器当作能量计算器。

## 能量动作给出当前值与上限，回合 UI 只重新显示

6198 `ActionFactory` 将原动作名 `EnergyChange` 映射到 `EnergyChangeAction`（类体 `4` `[0x183,0x18a)`）。实际消费链：

1. 2634 `logic/battle_action/OtherActions.py` `22.1` `[0x9,0x3c)` 读取 `Args['curEnergy']`、`Args['curMaxEnergy']`、`Args.get('_isEnemy',False)`，调用 `BattlePlayer.onUpdateEnergy`。
2. 4153 `15.13` `[0,0x2d)` 根据 `isEnemy` 直接赋值 `fei/maxFei` 或 `enemyFei/enemyMaxFei`，没有增减或恢复到默认值的公式。
3. 2634 `22.2` `[0x9,0x3f)` 在播放阶段把同一组参数交给 `refreshEnergyPlay`。

`RoundBeginAction.play`（6601 `22.4` `[0x23,0x33)`）调用的 `resetEnergyWhenRoundBegin` 是 UI 通知：5456 `UIOutput` `11.166` 只广播同名消息。4793 `ui/ui_fight/EnergynArea.py` 的处理器 `9.14` 从 `getEndBtnStateInfo` 读取 `CurFei/MaxFei`；数据源最终落到 9555 `FightDataTools.getEndBtnStateInfo` `9`：根据当前可出牌回合选择 `BattlePlayer.fei/maxFei` 或 `enemyFei/enemyMaxFei`。

这个处理器会把进度表现设成 `MaxFei`，但其调用的 `9.12` 只写 UI 对象的 `_realCurFei/_maxFei`，**没有把 `BattlePlayer.fei` 设置为最大值**。因此“UI 回合重置”的名字不能证明服务器每回合恢复 5 点。

表现还有分支：4793 `9.11` 在敌方动作或回放时直接使用传入能量参数；正常我方非回放则在 `0x87` 调用 `_onEnergyRealChanged`，再次读取当前数据源。这里没有把原表现时序简化成新的权威结算顺序。

## 补牌动作接收实例列表，不计算 6 张

原动作名为 **`DrawCard`（单数）**，6198 `4` `[0xe9,0xf0)` 映射到 5026 `logic/battle_action/DrawDiscardCardActions.py` 的 `DrawCardAction`。

| 字段或阶段 | 来源与观察 |
| --- | --- |
| `Args['uuids']` | 5026 `7.3` `[0x40,0x5c)`：交给 `dataGetCardInfosByUUIDS`，得到 `_cards` |
| `Args['isRoundStartDraw']` | 5026 `7.1` `[0,0xb)`：直接索引读取，不是默认抽牌数量 |
| `cacheRoundStartCardUUIDs` | 5026 `7.3` `[0x5c,0x82)`：若不存在，使用 `uuids`；随后解析为 `_showCardIDs`，用于显示和动作时长 |
| 实例解析 | 4942 `8.66` `[0,0x4d)`：按输入 `uuids` 顺序查 `syncCardInfos[str(uuid)]`，不存在的 ID 被跳过；没有生成新牌或随机选择 |
| 接收阶段 | 5026 `7.4` `[0,0x42)`：将已解析卡牌从 `UNUSED_PILE` 移到 `HAND_CARD_PILE` 的数据管理器；随后复制 `_cards` |
| 播放阶段 | 5026 `7.5` `[0,0x42)`：对表现管理器进行对应移动，再触发抽牌动画 |
| 最底层移动 | 4453 `5.20` `[0x3d,0x95)`：按传入实例 ID 遍历，从来源列表 remove，向目标列表 append；缺失/不在来源堆的实例跳过 |

这里能证明**已解析有效实例的客户端移动顺序跟随载荷顺序**。它不能证明服务器从牌堆头还是尾取牌、如何洗牌、首回合抽多少张，甚至不能从原始 `uuids.length` 无条件推定客户端最终入手数量（未知 ID 会被过滤）。

第一次抽牌另有表现标志：6601 `BattleBeginAction.doInit` `12.1` `[0,0x13)` 保存 UI 全局标志 `BattleBeginAction=True`；5026 `7.3` `[0,0x40)` 将其弹出并设置 `_isBattleStartDraw`。该标志影响首次抽牌延迟，不提供一个单独的首回合抽牌数。

初始牌堆仍由 4453 `5.10` 从 `battleInfo.team1/team2` 的 `handPile/drawPile/discardPile/exhaustedPile/powerUsedPile` 读取。已有首战表中的 7 张 `CardPile` 是起始牌组数据，不能直接当成收到的 `handPile` 或抽牌动作。

## 真正的数量修正器有精确调用边界

本轮还发现包内共享故事节点中以下明确操作（7693 `common/storyline_nodes/battle_common/action.py`）：

| code object | 已观察调用/赋值 |
| --- | --- |
| `516.2` `[0,0x13)` | `context.ownerTeam.setEveryRoundDrawNum(self.num)` |
| `516.3` `[0,0x13)` | `context.ownerTeam.addEveryRoundDrawNum(self.num)` |
| `516.4` `[0,0x13)` | `context.ownerTeam.subEveryRoundDrawNum(self.num)` |
| `512.2` `[0,0xf)` | `context.ownerTeam.extraDrawCardNum = self.num` |
| `55.2` `[0,0x13)` | `context.ownerTeam.changeEnergy(self.delta)` |
| `544.2` `[0,0x4f)` | 正 `num` 调 `addMaxEnergy(num)`，负 `num` 调 `decMaxEnergy(-num)`，0不调用 |

`63.7` 的 `DrawCardsNode.Start` 还引用 `ownerTeam.drawCardsFromDrawPile`，并传入 `num` 与过滤相关关键字；该函数涉及尚未在公共映射中命名的 closure opcode，所以工具保留原数值指令，不把它当作完整已恢复的解释器实现。

对这些新追到的七个 ownerTeam 成员（见 `turn-setup.json.new_provider_query`）查询现有 9698 项符号摘要，只有模块 7693 的引用，没有同名 code object。这是**新具体调用的提供方缺口**，不是重复旧名称负搜索；不排除动态注册、原生实现、未提供的热更或服务端代码，也没有证明这些节点在教程首战激活。`setEveryRoundDrawNum` 的名称本身不足以说明它与全局 6、存活角色数或 `extraDrawCardNum` 如何组合。

## 常量可以保留为线索，政策暂不减少

工具重新验证 6221 模块体的五个相邻字面量声明，并仅在上述 62 个具体 code object 中检查其读取位置：没有发现引用这些常量的指令。这一有界结果不能扩大为“整个游戏不会使用常量”。

| 声明 | 字面值 | 声明字节范围 |
| --- | ---: | --- |
| `DefaultBattleEnergy` | 5 | `[0xe46,0xe4c)` |
| `DRAW_CARD_NUM_PER_ROUND` | 6 | `[0x3ca,0x3d0)` |
| `MAX_DRAW_CARD_NUM_WHEN_ROUND_START` | 10 | `[0x3a0,0x3a6)` |
| `MAX_HAND_PILE_NUM` | 10 | `[0x3a6,0x3ac)` |
| `DEC_DRAW_CARD_NUM_PER_ROUND_LOST_CHAR` | 1 | `[0x459d,0x45a3)` |

目前最小待补证据已明确：教程的实际初始 `battleInfo.team1` / `clientCopyInfo`，其首个和后续 `EnergyChange` / `DrawCard` 动作，或负责生成这些值的 ownerTeam 初始化与回合调度实现。当前没有这些载荷/提供方，因此教程的 5/6 配置继续保留为明确重建政策；本轮不改数值，不伪造历史回放。

教程进入条件本身仍有限制：5947 `isNewPlayerCourse` 为返回 False 的包内 stub；`startNewPlayerCourse` 可确认调用 `doEnterChallenge`，但没有观察原运行时何时触发。报告中的链路均是静态可见消费关系，不代表旧服首战已完整还原。
