# @hczs/battle-presentation

纯 ESM 战斗状态投影，供新客户端和 Node 使用。它保留“已经接收的结算快照”和“播放到的可见状态”两个位置，并直接消费消息提供的 HP / 护盾最终值。没有引擎、网络、时间、随机数、渲染或伤害计算依赖。

**输入是新客户端定义的归一化 DTO，不是原服消息格式。测试全部为显式合成场景，没有原服流量或完整战斗兼容验证。** 本包不能从 cardId 推导伤害、执行出牌或推进真实回合。

## 接口与接入

入口为 `src/index.js`，类型为 `src/index.d.ts`。根工作区注册由集成方处理；包本身零依赖。

```js
import {
  createProjection, receiveBatch, playNext, inspectProjection,
  integerValue as int,
} from './src/index.js';

// 合成数据，仅展示调用约定。
let projection = createProjection({
  snapshotId: 'initial',
  entities: [{ id: 'elsa', hp: int('100'), shield: int('20') }],
  teams: [],
});
const received = receiveBatch(projection, {
  batchId: 'synthetic-1',
  actions: [{
    type: 'Group', kind: 'SkillUse', id: 'skill-1',
    actions: [
      { type: 'HpChange', targetId: 'elsa', deltaValue: int('-20'), finalValue: int('80') },
      { type: 'SyncSnapshot', snapshot: {
        snapshotId: 'settled-1',
        entities: [{ id: 'elsa', hp: int('80'), shield: int('20') }],
        teams: [],
      } },
    ],
  }],
});
projection = received.projection; // 整批校验成功后，调用方提交这个新句柄。
// 此时 receivedSnapshot.hp = 80，visibleState.hp = 100。
const step = playNext(projection, 2); // GroupBegin，再播放 HpChange。
projection = step.projection;
// step.events 供显示层消费；此时 visibleState.hp = 80，组仍未结束。
const state = inspectProjection(projection);
```

| 接口 | 语义 |
| --- | --- |
| `createProjection(initialSnapshot)` | 校验、复制初始完整快照；两个位置从同一个初始值开始。 |
| `receiveBatch(projection, batch)` | 校验整个批次及已有队列末端的目标状态，再返回新句柄和快照接收通知。任何错误都抛出 `TypeError`，旧句柄不改变。 |
| `playNext(projection, count = 1)` | 按顺序播放指定数量的事件，返回新句柄和事件列表。count 包含组开始、组结束、快照与数值动作；不是时间或帧数。没有待播事件时拒绝调用。 |
| `inspectProjection(projection)` | 只读查看 `receivedSnapshot`、`visibleState`、待播数、已播数、已接收批次数及当前嵌套组。 |
| `integerValue(decimal)` / `binary64Value(number)` | 构造明确带类型的数值。整数只接受十进制字符串，不接受可能已失真的 Number。 |

句柄是本模块实例内的不可变内存对象，不能 JSON 序列化/跨 worker 传输；快照和事件可以序列化。调用方可以保留旧句柄产生分支，因此批次去重只保证各条已提交分支。接口没有自动保存、撤销 UI 副作用或网络重放恢复机制。

## DTO 与状态语义

`Snapshot` 严格包含 `snapshotId / entities / teams`。实体只含 `id / hp / shield`。队伍只含 `id / cards / piles`；卡牌只含 `id / cardTypeId / charId`；五种牌堆字段必须齐全：`handPile / drawPile / discardPile / exhaustedPile / powerUsedPile`。空列表允许。详细可判别联合类型见 `src/index.d.ts`。

动作只支持以下四种：

- `HpChange` / `ShieldChange`：`targetId / deltaValue / finalValue`。在播放位置查找已知实体，直接赋值 finalValue；事件保留 previousValue、deltaValue 和 finalValue。不会把 delta 相加，也不检验两者算术一致、裁剪负数、推断死亡或联动扣除护盾。
- `SyncSnapshot`：一个完整 Snapshot，替换本包选定字段的全部状态，不做隐式局部合并。接收时更新 receivedSnapshot 并产生 SnapshotReceived；播放到这里才更新 visibleState，产生 SnapshotApplied。
- `Group`：`id / kind / actions`；kind 仅为 SkillUse、SkillEachState、Target。递归结构产生显式 GroupBegin / GroupEnd，保留空组、嵌套边界及原输入次序。

`receivedSnapshot` 只代表最近接收的显式快照，**不会**根据 HpChange 推算最新结算，也没有恢复原客户端的可用性预测或死亡预计算。连续接收 A、B 后，播放到 A 时可见状态为 A，而 receivedSnapshot 仍为 B。内部仅为验证目标存在性而暂存队列末端状态，不作为权威结算结果暴露。

`visibleState.snapshotId` 是最近已播放快照的标签；后续数值动作可继续改变 visibleState，所以它不是状态内容哈希。snapshotId 不承担服务端版本号、先后判断或防重放功能。

每个事件附带批次 ID、输入树中的零基 `actionPath` 和从 1 开始的播放 `sequence`；组事件附 depth（结束时使用弹栈前深度）。一个批次可能横跨多次 playNext，但不会重排。当前采用单一串行队列，不实现原普通轨 / UI 轨并行或动画调度；count 也不能作为原版动画时长。

## 新客户端完整性约束

这些规则是重建设计，不冒充原同步器或原服务器的校验：

- 实体 ID、队伍 ID 不重复；卡牌实例 ID 在快照中全局唯一。**同队实例不能同时属于多个牌堆**，同牌型的不同实例可以重复；牌堆必须引用本队 registry 中的实例。
- registry 可以包含当前未分派牌堆的卡；已移除的历史实例可以不保留。不要求五种牌堆覆盖 registry，也不推断 charId 一定对应当前 entities。
- 所有 ID 使用 1–128 位规范化 ASCII 字符串：首位字母/数字，其余允许字母/数字/点/下划线/冒号/横线。源数据 ID 转换由上游显式负责，本包不隐式 Number 转换或去空格。
- 同一已提交分支拒绝重复 batchId；空批次作为可去重的无动作批次接受。组 ID 在同一批次内唯一，不要求跨批次唯一。
- 仅接受普通 DTO 对象和普通密集数组；缺失/额外字段、accessor、稀疏数组、未知动作/组、未知目标都拒绝。对象经过复制，输出递归冻结。应从受控代码或 JSON 解析取得 DTO；它不是对任意 JavaScript Proxy 的安全沙箱。
- `LIMITS` 给出本包选择的数量上限：每快照 1024 实体、16 队、8192 卡；每批 4096 动作（含 Group），32 层组；每句柄最多待播 16384 事件、累计接收 4096 批；整数文本最多 4096 字符（含符号）。这些不是原游戏已恢复的上限，也不代替上游请求体字节限制。

receiveBatch 先复制验证所有 DTO，再按**此前全部已接受动作之后**的状态验证目标。若一个已排队快照移除了实体，即使该实体仍在屏幕上，随后针对它的动作也会拒绝。后面才创建实体的快照不能让前面的无效目标动作合法。没有调用用户回调；失败不会发布部分通知或污染旧状态。应用应在函数返回后替换句柄，再自行决定如何消费事件。

## 数值与运行范围

数值 DTO 与 `battle-core.toTagged` 的序列化形状相同：

```json
{"numeric_type":"integer","decimal":"9007199254740993"}
{"numeric_type":"binary64","decimal":"-0.0","hex":"-0x0.0p+0"}
```

整数保持规范十进制字符串，既不转 Number 也不要求 BigInt。浮点保留 decimal 和 Python 风格 binary64 hex，并校验二者对应同一有限数值，保留负零；不接受 NaN/Infinity。数值可以经 JSON 往返。这里仅赋值和转交，没有 Python2 除法或伤害公式计算；需要计算时由独立 battle-core 或将来的权威结算负责。

运行码不依赖 Node API、BigInt、文件系统或 Cocos。使用现代 ECMAScript（含对象展开、Object.getOwnPropertyDescriptors、String.padStart），由客户端现有编译链处理。已用安装中的 Creator TypeScript 5.8.2 按项目 target/module ES2015、strict、isolatedModules 检查消费者类型；此检查不是 JS 运行时降级或四端原生执行认证。Node 的隔离上下文测试将 BigInt 设为 undefined，仍可保真回放大整数。

## 原字节码依据与转换边界

只读核查了现有静态指令记录，未运行 APK 字节码。以下 index 为 `assets/script.npk` 条目；constant path 与指令偏移可在根目录 `analysis/card-action/function-sources.json` 查到完整来源（含 NPK 偏移、解密 SHA-256、bytecode SHA-256）。

| 已观察事实 | 精确来源 | 本包采用的边界 |
| --- | --- | --- |
| HpAction 按 Args['target'] 查实体；onChangeHp 把 finalValue 写到 hp | 2350:`[5,2]`，target 查找 `[0x09,0x22)`、调用 `0x34`；5485:`[13,22]` 赋值 `[0x4e,0x57)` | target 显式转换为 targetId；赋 finalValue、转交 delta。 |
| 两种护盾消费者直接写入 curValue，play 从 Args 传 finalValue | 2350:`[15,2]`；5485:`[13,19]`、`[13,20]` 均 `[0,9)` | 统一 ShieldChange 数值投影；不模拟自动衰减/技能分支的特效。 |
| propertiesInfo 先生成 ClientUpdateBattleProperties 动作；onReceive / play 分别调用预计算 / 可见刷新 | 4153:`[15,5]` `[0x2f,0x46)`；1317:`[6,2]` / `[6,3]`；4153:`[15,6]` 数据牌堆 `[0x41,0x51)`、`[15,7]` 可见牌堆 `[0,0x10)` | 显式 SyncSnapshot、两个状态位置；不复制任意 propertiesInfo 或执行可用性/死亡逻辑。 |
| 入队前调用每个动作 onReceive，随后送入普通或 UI 轨 | 2697:`[12,51]` onReceive `[0x1c,0x26)` | 接收先于播放；新队列串行，不宣称轨道/嵌套 onReceive 传播已经全恢复。 |
| Begin 建立嵌套列表，End 弹栈且不追加；没有严格比对结束标记类型 | 6786:`[3,5]`；结束栈深校验 `[0x9d,0xb5)` | 新 DTO 直接提供 Group 树，显式 begin/end 事件是新接口，不是原 raw tuple 解析器。 |
| team1/team2 五种牌堆同步，按 cardID 查实例，使用 cardID/cardTypeID/charID 构造 ClientCard | 4453:`[5,10]`、`[5,16]`、`[5,18]` 构造 `[0x2e,0x47)`；9137:`[9,13]` 动态 setattr | cardID→id、cardTypeID→cardTypeId、charID→charId；上游建立显式 registry 与完整选定字段快照。 |

这里未提供旧 payload 自动转换器，因为原 propertiesInfo 全字段、真实数值类型与流量时序尚未完整恢复。`skillInfo / srcEntityID / HeavyAttack / damageShowTags / isAutoReduce / lastActionShield` 等原字段不在当前 DTO 内，传入会拒绝；不能悄悄把完整原消息当作本包格式。也没有移植 ActionParser 的 custom / merge / postprocess、完整139种动作、回合 UI、技能预测、盾/HP结算或完整战斗。

证据文件固定指纹（本次开发读取时）：

| 根目录文件 | SHA-256 |
| --- | --- |
| `analysis/card-action/function-sources.json` | `060c8ed2dec7e6a988cdfd082387361156ef92d13b44c178b3ac1d798fa3d12f` |
| `analysis/card-action/client-presentation-contract.json` | `27d7a6f6497045e1de84938d06a2dc43a79dc203845b59f4b09ed5dbaabe8ba1` |
| `docs/card-action-recovery.md` | `0fc7ed957c57fa252d26b0f6680bf2069c9d31bbbcb9fc5cf29380610398a900` |

## 验证

从项目根目录运行：

```powershell
node --test packages/battle-presentation/test/projection.test.js
node .tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/tsc.js --target ES2015 --module ES2015 --moduleResolution node --strict --isolatedModules --noEmit packages/battle-presentation/typecheck/consumer.ts
```

19 项测试通过，覆盖接收/播放分离、按 finalValue 赋值、异常原子性、队列末端验证、嵌套事件顺序、快照牌堆替换、实例重复拒绝、数值类型和大整数保真、非法 DTO、资源上限、分段播放一致性。所有测试是新模块契约测试，不是旧服回放或完整战斗验证。没有改动客户端、服务器或根工作区配置，没有启动 UI 或构建四端。
