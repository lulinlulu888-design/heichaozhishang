# 自定义玩法：守势试炼

2026-10-14。新增数据配置入口和一个可保存、可继续的自定义关卡示例。它基于已验证的教程重建定义新增卡牌、替换起始牌组并调整回合参数，**不改原始APK、提取证据、原卡牌或教学政策**。这不是发现了原版隐藏关卡。

## 直接运行

在仓库根目录运行，使用已有Node.js 24及以上版本：

```powershell
node tools/play_tutorial_cli.mjs --custom-scenario server/data/custom/guard-and-draw.json
```

输入牌序号出牌，`e`结束回合，`q`保存退出。默认使用独立的 `runtime/server/custom-cli.sqlite` 和 `.battles`；下次运行继续未完成的存档。`--new`明确新开一局，`--save-path`可指定别的独立存档。

本轮自动通关与中途重开验证使用：

```powershell
node tools/play_tutorial_cli.mjs --custom-scenario server/data/custom/guard-and-draw.json --auto --new --verify-reopen --seed 5000 --report analysis/custom-scenario/cli-run.json
```

结果为第3回合胜利、版本8、7次已提交动作，中途重开后完整战斗对象一致；独立只读SQLite连接复核记录在 `analysis/custom-scenario/persistence-verification.json`。自动策略没有使用蓄势屏障，护盾加抽牌的复合效果由另一组真实HTTP测试明确验证。这里是命令行/API验收，不是Cocos画面验收。

## 示例内容

文件为 `server/data/custom/guard-and-draw.json`：

| 项目 | 自定义内容 |
| --- | --- |
| 蓄势屏障 | 1能量，获得600护盾，抽1张牌 |
| 突破斩击 | 2能量，造成1600伤害 |
| 回合参数 | 3能量，首次与每回合抽3张，手牌上限6，回合上限20 |
| 对战角色 | 沿用教程重建的艾尔莎与幻眼魔方，以及敌方重建行动 |

牌组内可以引用原卡牌或新增卡牌。新增ID必须使用 `custom:` 前缀，不能覆盖原ID；重复卡牌在牌组中生成不同实例编号。伤害与护盾值是明确自定的非负整数字符串，**不是原属性公式推导的结果**。

## 扩展接口与边界

配置格式 `hczs-custom-tutorial-v1` 包含 `id/title/description/addCards/deck/rules`，未知字段拒绝。当前支持已有状态机的伤害、护盾、抽牌效果及五个回合参数，不执行脚本、表达式或动态插件。增加全新效果类型、角色资源、剧情、奖励或复杂触发器仍需要继续扩展共享状态机和客户端。

`server/src/custom-scenario.js` 在原教程来源检查完成后装配新定义，文件限制64 KiB，卡牌数量、效果形状和数值范围由共享 `validateDefinition` 复核。手牌上限限制1至10，以适配当前图形界面的十个槽。新增定义ID包含基础定义、配置字节和装配器源码摘要；源恢复记录保留在 `provenance.base`，自定义部分明确标识 `mode: custom-content` 和 `originalScenarioRecovered: false`。

完整定义随每场战斗保存。编辑配置只影响之后创建的战斗；已存档的战斗继续按当时定义结算，不能用新参数悄悄改写旧存档。即使服务切回原教程，已有自定义战斗仍按保存的定义读取和执行。CLI恢复时选择该存档中最近一场未完成战斗并显示它实际保存的标题；要体验新配置需显式新建。

## 图形客户端入口

独立启动本地服务时可指定配置：

```powershell
node server/src/index.js --port 7459 --custom-scenario server/data/custom/guard-and-draw.json
# 或在有权访问现有PM2实例的终端中管理这个独立服务：
pm2 start server/src/index.js --name hczs-custom -- --port 7459 --custom-scenario server/data/custom/guard-and-draw.json
```

默认独立存档为 `runtime/server/custom.sqlite` 和 `.battles`。服务启动后，现有Web页面可使用 `http://127.0.0.1:7456/?apiPort=7459`。进入战斗后标题为“自定义 · 守势试炼”，说明明确指出不是原版关卡。API保持 `/api/rebuild/v1`，`GET /status` 的 `battleMode` 为 `custom-content`；未传配置时仍是原教程的 `explicit-reconstruction`。`--no-tutorial`与自定义模式不能同时启用。

本轮没有启动7459常驻服务，也未更改7458的PM2配置；当前执行环境的PM2管道权限问题仍未解决。图形客户端只完成代码接入、编译与静态包验证，未进行实际点击、触摸、画面或跨端游玩验收。

## 测试

新增5项服务端测试覆盖：原定义不变/内容版本变化、非法覆盖和不支持的效果、文件大小和UTF-8错误、不能绕过原教程来源校验，以及真实HTTP护盾与抽牌、幂等重试、服务重开、配置变更隔离和通关。

```powershell
node --test server/test/custom-scenario.test.js
pnpm test
pnpm test:client
```

工作区178项全部通过（原173项加5项），客户端15组HTTP/SQLite测试全部通过。命令行独立存档与真实HTTP临时存档均不接触已有预览服务。

标题/说明显示改动已重新构建Web、Windows model和Android，整体28项来源/资源/包检查通过，两模型的三平台审计均通过。最新Android APK为78,771,737字节、SHA-256 `5505c5c9de20a06e73d0deb862cff2a964a6fc1694d9e6c686690cd20126228b`，签名/完整性/16KB对齐通过。Apple两平台预检已刷新，仍未在Mac编译或运行。
