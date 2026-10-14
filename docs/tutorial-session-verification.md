# 首战重建流程运行记录

2026-10-14，Windows / Node.js 24。本轮验证的是新客户端规则装配、Node API、回合状态机与SQLite存档。没有操作原APK、Cocos窗口或手机，不能据此宣布原服兼容、四端游玩或完整游戏恢复。

## 已实际执行

```powershell
pnpm install --ignore-scripts --offline
pnpm test
node tools/play_tutorial_cli.mjs --auto --new --verify-reopen --seed 5000 --save-path runtime/server/tutorial-proof-20261014.sqlite --report analysis/battle-session/cli-proof.json
```

全工作区173项测试通过：battle-core81、battle-presentation19、battle-session19、game-protocol26、server28。Creator随附TypeScript编译器按ES2015/strict/isolatedModules检查了五份共享包消费者，结果通过。日志保存在 `analysis/battle-session/whole-workspace-tests.log`。

命令行程序使用自己的临时端口服务和独立存档，未停止或替换现有预览。它通过HTTP接口创建本地档案和首战，逐次提交手牌实例/期望版本号；所有伤害由服务端按固定定义执行。程序在第一次动作后关闭自己创建的服务，再以新数据库连接打开，GET返回的完整战斗与关闭前一致，然后继续行动。

本次运行结果：

| 项目 | 结果 |
| --- | --- |
| 战斗ID | `88cceffa-3426-447d-a3fa-531de2bb5d57` |
| 场景定义ID | `tutorial-5000-f2429ac567fc160f596efb7b8cc84b7369a37c049d8036cb3d4d992a8c71ac2f` |
| 种子 | 5000 |
| 初始玩家HP | binary64 `1768.8000000000002`，hex `0x1.ba33333333334p+10` |
| 初始敌人HP | integer `4600` |
| 结束状态 | `won / enemy-defeated`，第2回合 |
| 存档修订号 | 9：创建后8次动作 |
| 请求收据 | 1条创建、8条动作 |
| 中途关闭/重新打开一致性 | 通过 |

完整轨迹和固定场景元数据见 `analysis/battle-session/cli-proof.json`，终端输出见同目录 `cli-proof.log`。运行结束后，另开 `node:sqlite` 只读连接核对数据库中的state_json、scenario.definition.id、revision及两类收据数量，与报告逐项一致。

CLI的重新打开验证发生在同一Node进程内；另外的 `server/test/process.test.js` 真实启动并停止自己创建的独立Node进程，随后由新进程读取已提交战斗及幂等收据，再成功执行下一回合。两种验证的范围分别记录，不互相冒充。

## 数据来源与重建差异

原教学入口、七张牌、卡名/费用、敌人和技能状态有静态来源。玩家稀有度4且无附加修正、卡表系数优先、状态顺序、怪物缺字段基础值0、中性修正、洗牌算法、回合初始化及盾/HP结算策略属于此模式的明确选择。原技能提供者、完整属性合成、终结技以外的扩展行为和原服务器调度并未因此恢复。具体差异由 `server/data/tutorial-policy.json` 和每份API场景的notice/provenance提供，见[规则说明](tutorial-reconstruction-policy.md)。

护盾公式保留了已恢复的原调用参数错位：原辅助函数第四参数cardObj默认None，而护盾函数只传三个位置参数，基础强化不生效。伤害函数四参调用正常。相关实现和合成对照位于 `packages/battle-core`；本轮并未擅自修正原包这一疑似缺陷。

## 下一项验收

把已验证API接入Cocos的手牌、能量、敌方意图、出牌和结束回合界面，并让界面按revision恢复最新状态；重放收据不能覆盖更新的状态。随后分别构建并实际验证Windows/Android，继续补齐macOS/iOS构建机与运行环境。当前原型的图鉴和模型构建不等于已经包含本轮战斗界面。
