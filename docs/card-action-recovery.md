# 卡牌构造缺口与客户端战斗消息边界

本轮仍未找到“卡表 DIY 列表 → `cardAction.diyActionData`”的实际构造器。新增证据明确了另一条可用于重建的边界：**原客户端接收卡牌快照和动作列表，按服务端给出的最终血量/护盾值更新表现；预计算数据和可见数据在不同阶段刷新。** 这可以指导消息回放和新客户端状态同步，但不能代替出牌结算、抽牌或回合规则。

本轮只读原包和已有提取物，不执行游戏字节码，不运行 APK，不调用 UI，不触碰现有客户端/API进程。没有重复上一轮 `diyActionData/getRpgValue` 的全库名称搜索或 native 搜索；改为检查类引用、条件导入和具体客户端构造/同步入口。

## 证据和复现

```powershell
python tools/trace_card_action.py
```

工具对18个涉及人工语义判断的模块固定 SHA-256，对实际读取的29个模块逐一核验完整 marshal、文件名和解密哈希。自动导出2422个 code object，其中48个入口被单独选入 `function-sources.json`；并非声称2422个函数均已完成语义恢复。未知指令仍标为 `UNKNOWN`，没有构造可执行 code object 或运行通用字节码解释器。

输出在 `analysis/card-action/`：

- `function-sources.json`：选定函数/类/模块体的来源、NPK偏移、constant path、bytecode SHA-256、指令偏移和参数名。
- `*.partial-dis.txt`：便于审查的部分反汇编；同名JSON保留完整指令记录。
- `action-map.json`：139个原始表现动作名和类符号。仅识别固定的字典字面量三指令结构；不解析或实例化类。
- `client-presentation-contract.json`：已确认的应用层请求、动作列表、HP/护盾赋值和两阶段同步边界。
- `provider-boundary.json`：新的六个类/上下文名称索引查询、非客户端导入的精确模块匹配、复用的包内脚本/清单证据。
- `import-edges.json` / `module-sources.json` / `input-fingerprints.json`：导入和输入范围。
- `opcode-corroboration.json`：本工具局部补充的 `0x8d CALL_FUNCTION_KW`。包内 `lib/json/__init__.py` index0、`loads` `[26]`、偏移`0x106`的栈形状与 [CPython 2.7.18 json.loads](https://github.com/python/cpython/blob/v2.7.18/Lib/json/__init__.py#L317) 的 `cls(encoding=encoding, **kw)` 一致；未修改共用opcode工具，也不冒充原生分派表恢复。

下文用 `模块index:constant.path` 定位 code object；字节范围末端不包含在内。APK SHA-256 为 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。归档身份复用既有 REA Evidence `ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220`，见 `analysis/rea/session-evidence.json`。本轮脚本结论来自普通本地静态工具，不标记成新的 REA Evidence。REA native provider 的已知缺环境状态未改变，本轮未重试或切换会话。

## DIY 构造缺口缩小到了什么范围

`common/const.py`（6221，模块体）在 `[0xc,0x12)` 将 `True` 写到 `IsClient`。这是包内初始值，不能保证之后没有动态修改。

`common/storyline_nodes/common_obj.py`（1259，模块体）在`0x22`读取该标志，`0x28`为条件跳转：

- 客户端分支导入 `plugin.sunshine.external.SunshineClient.*`，在`0xad`跳过服务端分支。
- 非客户端分支从`0xb0`开始，导入 `storyline.Storyline.*`，并在`0x13e`导入 `ServerUtils`、随后导入 `DamageInfo/BuffSourceInfo`。

`skill/action_formula.py`（6224，模块体）有相同分支：`0x3a`判断，`0xa7`跳过服务端路径；`ServerUtils.DamageInfo`位于非客户端分支的`0x11a`。`common_storyline.py`（618）在客户端/非客户端分支中分别导入插件版和`storyline.StorylineBattleContext`版的上下文。

9698条已恢复模块的精确路径索引中，没有上述六个服务端模块名；新的六个类/上下文名称查询也只在618自身发现 `BaseServiceCardActionSL`、`SServiceCardActionSL`、`CServiceCardActionSL`等引用，没有找到外部的直接构造调用。这个结论限于现有符号索引和静态名称；不排除动态生成名称、原生模块注册或其它载荷。

618的`BaseServiceCardActionSL.__init__` `[24,0]`接收外部传入的`cardAction`，`setCardContext` `[24,2]`继续消费其`cardObj`。`SServiceCardActionSL.setContext` `[26,0]`又读取 `skillID/skillUuid/times/selectCardObjs/skillObj/sharedData/target`。这些字段共同描述了所需对象，但该模块仍是消费者。**`[26]`的实际类名是 SServiceCardActionSL，上一轮说明中把`[26,4]`写成CService的文字标签应更正；原始函数证据未变。**

名字看似可疑的 `U1CardActionEditorPluginServer.py`（5631）也已排查：其类体`[4]`只设置`SUNSHINE_UUID`，继承插件的`EditorPluginServer`，没有卡牌构造方法。不能因文件名含Server就把它当作游戏服务端实现。

现有资源勘察还证明：原APK共有17个NPK；`script.npk`以外可直接辨识的Python文件只有四个`assets/device_config/*.pyc`。`filelist.txt`列出的3295项全部MD5匹配。清单一致只证明包内内容完整，不证明停服前线上热更内容齐全；没有找到可直接采用的战斗回放样本，也不能据此证明所有其它资源都不含序列化战斗对象。

**推断：**当前证据更支持“APK保留共享战斗消费者和客户端表现层，所需服务端对象尚未恢复”，而不是把缺口直接定性为某个 NeoX 引擎API。没有足够证据认定它必然来自 native 注册、缺失热更或某个特定资源包。原卡410102的`VALUE=0`是否进入实际运行对象，仍须保持未定。

## 实际客户端卡牌来自同步快照

`CardPileMgr.BaseCardPileMgr.init_from_dict`（4453:`5.10`）从 `battleInfo.team1` 和 `battleInfo.team2`读取五种牌堆：`handPile/drawPile/discardPile/exhaustedPile/powerUsedPile`。

`_syncCardObj`（4453:`5.16`）按`cardInfo['cardID']`查找实例，缺少时调用`_createCardObj`。后者`[0x2e,0x47)`实际构造：

```text
ClientCard(cardInfo['cardID'], cardInfo['cardTypeID'], cardInfo['charID'])
```

`logic/card/ClientCard.py`（9137，模块体`[0x56,0x6c)`）直接以`object`为基类。构造函数`[9,0]`保存uuid和角色关联，`initData` `[9,1]`取`card_table`并初始化牌型、暴击、额外攻击次数等展示属性。此函数没有读取`SKILL_DIY_PARAMETER/VALUE`。

`syncCardInfo`（9137:`9.13`）先把同步字典合并进`self.cardInfo`，再逐项调用`setattr(self,k,v)`。因此单纯搜索所有显式`STORE_ATTR`不足以列出客户端可能接收的全部字段；但这不证明服务端曾发送`diyActionData`，也不意味着这个`ClientCard`就是618所需的`cardAction`。

`calcTargets`（9137:`9.9`）和`calcRunResult`（`9.10`）继续读取`Globals.BattlePlayer.cardPredictRun[str(uuid)]`；按`needTarget`选择目标子项，处理预测目标和结果。没有在这些函数中调用完整伤害结算。它们的命名不能作为“客户端已有战斗模拟器”的证据。

## 出牌与动作推送的应用层形状

| 入口 | 已确认行为 | 来源 |
| --- | --- | --- |
| `useCard(cardID,targetID)` | 调用`requestPlayACard`，参数字典为`cID/tID` | 5455:`7.5` `[0x22,0x43)` |
| `endRound()` | 调用`avtRequestEndRound`，参数为空字典 | 5455:`7.13` `[0,0x13)` |
| `onPushActions(rawActions)` | 声明为`rpc_method(CLIENT_STUB, (List('a'),))`，转交`playPushActions` | 4153:`15` `[0xb4,0xd5)`；`15.16` |
| `playPushActions` | 对象未销毁且Battle存在时，调用`Battle.addRawActionGroup` | 4153:`15.17` `[0,0x27)` |

`useCard`只对`usingCardUUIDs`中的重复记录避免再次append；RPC调用仍在判断块之后。不能把这个客户端列表解释成完整的防重复出牌校验。

`ActionParser.getRestructuredRawData`（6786:`3.5`）逐项解包`(actionName,actionData)`。`SkillUseBegin/SkillEachStateBegin/TargetBegin`新建并压入嵌套列表，对应三个End名称弹出栈且不作为普通动作追加；结尾要求栈深为1。该函数并没有比对结束标记种类与开始标记种类，不能凭名字自行补成已恢复的严格配对规则。

`ActionFactory`（6198:`4`）有139个字面量映射，包括`HpChange→HpAction`、`ShieldChange→ShieldAction`、`RoundBegin→RoundBeginAction`。`createAction`（`4.139`）查类、构造实例、将传入字典设为`Args`并调用`doInit`。这是表现动作名映射，不是RPC数字编号。动作列表后续还经过custom修改、merge和postprocess；本轮没有完整移植这些阶段。

## 血量、护盾和回合展示的边界

`HpAction.play`（2350:`5.2`）以`Args['target']`查Battle实体，再在`0x34`以`**Args`调用`onChangeHp`。`CBattleEntityBase.onChangeHp`（5485:`13.22`）的关键步骤是：

1. 读取`lastActionShield/deltaValue/finalValue/skillInfo/srcEntityID`。
2. `[0x4e,0x57)`执行`self.hp = finalValue`。
3. 根据deltaValue正负选择受击/恢复表现，再把deltaValue与finalValue交给UI。

这里不是`hp += deltaValue`，也不负责防御公式、护盾吸收或HP上下限裁剪。deltaValue与finalValue的关系必须由提供消息的一方保证；真实服务器如何生成它们尚未恢复。

`ShieldAction.play`（2350:`15.2`）读取`deltaValue/finalValue/skillInfo`等字段；`skillInfo`为空时调用`onChangeShieldAuto`，否则调用`onChangeShield`。5485:`13.19/13.20`均在`[0,9)`把传入的`curValue`直接写入`self.shield`。这仍是最终值消费，不能据此推导护盾抵扣优先级或溢出扣血规则。

`RoundBeginAction.play`（6601:`22.4`）激活当前玩家、显示回合开始提示，并调用UI的`resetEnergyWhenRoundBegin`；`RoundEndAction._realPlay`（`24.3`）显示结束提示并发出`RoundEnd`通知。这些函数没有实现服务端抽牌、能量结算、回合归属转移或怪物AI。不能把UI方法名当作已恢复的战斗规则。

## 数据状态与表现状态分两阶段同步

4153:`15.5`的`onUpdateAllProperties`在Battle存在时，创建一个本地动作：

```text
('ClientUpdateBattleProperties', {'propertiesInfo': propertiesInfo})
```

随后走同一动作队列。`CBattle.addRawActionGroup`（2697:`12.51`）对每个动作先调用`onReceive`，再将其放入普通轨或UI轨。

`ClientUpdateBattlePropertiesAction`（1317）在`onReceive` `[6,2]`调用`updateAllPreCalcPropertiesAfterAction`；该函数4153:`15.6`刷新预计算可用性、死亡状态和`_dataCardPileMgr`，并把`battleInfo.team1`字段写入当前对象。等到`play` `[6,3]`才调用4153:`15.7`的`updateAllPropertiesAfterAction`，更新`_viewCardPileMgr`、清空`usingCardUUIDs`并刷新可见实体等。

因此新客户端可以把“接收结算快照”和“按队列更新表现”设计成两个明确阶段。这是从原实现得到的结构依据；消息数值、先后顺序、插队/并行轨及完整动画时序还需要真实样本和更多恢复，不能宣称已兼容整场原版战斗。

## 可推进与仍缺失的部分

本轮可以支持后续实现受控的动作输入检查、最终值回放和数据/表现双状态；测试输入须标记为合成，不能冒充旧服战斗记录。本轮没有改客户端、服务器或构建配置。

真正从卡牌ID推进到结算，仍缺少`cardAction/getRpgValue`提供方、DIY构造、实体`beHurt`、盾/HP结算、能量与牌堆规则、随机状态和服务端回合调度。下一步应以这些未决对象的具体导入/序列化调用点或新的实际载荷为线索；在没有新证据时，不应再次重复相同的全库直接名称扫描，也不能用0/1默认值补成看似可玩的原版规则。
