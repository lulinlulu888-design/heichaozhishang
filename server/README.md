# 本地重建服务端

这是跨平台新客户端使用的 Node.js 服务，当前提供恢复数据图鉴、本地档案、角色选择存档和序章首战的重建规则流程。首战支持出牌、回合、胜负、逐步保存与重新打开继续；部分规则是明确配置的重建选择，已接入 Cocos 战斗界面代码但尚未完成实际图形首战或四端游玩验证，`status.gameplayReady` 仍为 `false`。它不实现原 APK 网关或原账号登录。

## 启动

已在 Windows / Node.js 24.18.0 验证。使用 Node 内置 HTTP 与 SQLite，不需要另装数据库服务。

```powershell
Set-Location D:\hczs
pnpm server
# 可选：单独指定端口、恢复数据和本地存档路径。
node server/src/index.js --port 7457 --data-directory analysis/game-data --save-path runtime/server/hczs.sqlite
# 只运行图鉴和档案服务，不读取教程证据。
node server/src/index.js --no-tutorial
```

先按 [数据恢复说明](../docs/game-data-recovery.md) 生成 `analysis/game-data/characters.json` 与 `cards.json`。输入缺失或结构无效时启动失败，不自动生成假角色或卡牌。目录样本当前包含艾尔莎、琳、未来，以及四张卡牌；卡牌费用和短文案来自原包字面量，不能由此推断持有关系、初始卡组或实际伤害。

默认地址 `http://127.0.0.1:7457`，仅监听回环地址。浏览器允许来源为 `http://127.0.0.1:7456` 与 `http://localhost:7456`；原生客户端可直接调用。本版本供个人本地运行，没有多人账户与网络认证。手机、模拟器接入须另做明确的网络配置与验证。

## PM2 战斗预览

用户要求以PM2管理本地战斗服务。仓库根目录的 `ecosystem.config.cjs` 定义单实例 `hczs-battle`，固定监听 `127.0.0.1:7458`，对应预览页面 `http://127.0.0.1:7456/?apiPort=7458`。

```powershell
Set-Location D:\hczs
pm2 start ecosystem.config.cjs --only hczs-battle
pm2 status hczs-battle
curl.exe -i -H "Origin: http://127.0.0.1:7456" http://127.0.0.1:7458/api/rebuild/v1/status
# 查看日志或主动重启本项目服务
pm2 logs hczs-battle --lines 40 --nostream
pm2 restart hczs-battle
```

成功的健康响应应为HTTP 200，`capabilities` 包含 `tutorial-battles`。存档为 `runtime/server/tutorial-preview.sqlite` 和同名 `.battles`；日志为 `runtime/server/pm2-battle.{out,err}.log`。配置使用独立预览存档，未复制或覆盖7457旧服务存档，默认未创建任何新档案。未设置Windows开机启动，也未对其他PM2应用运行save/restart/stop操作。

2026-10-14本次执行环境实测：PM2 7.0.3已安装，配置语法检查通过；`pm2 ls` 与上述start均在访问默认Windows管理管道 `\\.\pipe\rpc.sock` 时返回 `EPERM`，因此没有确认服务启动。后续HTTP与TCP核验显示7458仍未监听；7457原服务正常但只提供图鉴/档案。请在有权访问现有PM2实例的同一Windows账户与权限级别的终端执行上述启动命令；无需删除管道、杀死所有PM2进程或改动其他项目。

## 教程命令行入口

先生成 `analysis/first-encounter` 的首战与基础属性证据，见 [首战报告](../docs/first-encounter-recovery.md)。默认启动会严格核对这些证据；缺失或被修改时拒绝启动教程，不自动填充数据。重建政策和已知冲突见 [规则配置](../docs/tutorial-reconstruction-policy.md)。

```powershell
pnpm tutorial
# 使用固定种子自动完成一次新战斗，并验证中途保存后重新打开。
pnpm tutorial --auto --new --verify-reopen --seed 5000
```

命令行入口独立创建由它自己管理的临时端口服务，使用 `runtime/server/tutorial-cli.sqlite` 档案及对应 `.battles` 战斗库，不停止已有预览服务。输入牌序号出牌、`e` 结束回合、`q` 退出；每次成功操作自动保存，再次运行优先恢复未完成战斗。`--new` 显式新建；`--save-path` 可指定独立存档。它是当前可运行的重建流程入口，不代表图形客户端已接通。

## API

自定义玩法可通过 `--custom-scenario server/data/custom/guard-and-draw.json` 启用，默认使用独立 `runtime/server/custom.sqlite`；它仍要求原教程证据先通过校验。新增卡牌使用 `custom:` 命名空间，旧战斗保存的规则不随配置修改。完整用法及验证见[守势试炼](../docs/custom-gameplay.md)。未传此参数时保持原教程模式。

所有路径使用 `/api/rebuild/v1` 前缀。写入为 UTF-8 `application/json`，请求体最大 16 KiB；接口不接受额外字段或查询参数。

| 方法及路径 | 用途 |
| --- | --- |
| `GET /status` | 能力、存档版本和未完成的可玩状态 |
| `GET /catalog` | 角色、卡牌展示字段、来源和内容摘要 |
| `GET /profiles` | 本地档案列表 |
| `POST /profiles` | `{ "displayName": "本地旅人" }` 创建独立本地档案 |
| `GET /profiles/:id` | 读取档案及修订号 |
| `PATCH /profiles/:id` | 带 `expectedRevision` 更新名称或 `selectedCharacterId` |
| `GET /tutorial` | 当前首战定义、来源、重建配置及差异说明（启用教程时） |
| `GET /profiles/:id/battles` | 当前档案的战斗列表 |
| `POST /profiles/:id/battles` | `{ "requestId": "new-1", "seed": 5000 }` 创建并保存首战；seed 可省略 |
| `GET /profiles/:id/battles/:battleId` | 读取完整战斗、固定规则定义及修订号 |
| `POST /profiles/:id/battles/:battleId/actions` | 带 requestId/expectedRevision 的 play-card 或 end-turn |

创建响应为 `{ "profile": { ... } }`，修订号从 1 开始，角色初始为 `null`。例如，使用返回的 ID，提交 `{ "expectedRevision": 1, "selectedCharacterId": 2 }` 保存选择；成功后修订号为 2。过期修订号返回 HTTP 409，客户端应重新读取再保存。未知角色返回 400，不会修改档案。角色选择仅为重建客户端的本地偏好，不表示原服角色已经解锁或获得。

错误响应为 `{ "error": { "code": "...", "message": "..." } }`。旧服样式的 `/login` 等路径返回 404，不伪造兼容结果。

战斗指令示例：`{"requestId":"play-1","expectedRevision":1,"type":"play-card","instanceId":"tutorial-card-1"}`；结束回合使用 `type:"end-turn"` 并省略 instanceId。客户端只提交意图，服务端检查手牌、费用与终态并结算。胜负单独保存，没有发放尚未恢复的原服奖励。

创建和动作请求都要求稳定 requestId；网络超时应重发同一请求，而不是生成新 ID。同一 ID、同一载荷返回首次提交的结果并标记 `replayed:true`，不同载荷返回409。旧修订号的新动作返回409。重放的收据可能早于当前状态，客户端须按 revision 防止画面倒退，必要时 GET 最新战斗；不可把旧收据当成回滚。

## 存档与代码边界

`src/index.js` 负责 CLI 和生命周期；`src/app.js` 负责 HTTP 适配；`src/catalog.js` 投影恢复出的展示数据；`src/store.js` 管理 SQLite 事务与本地档案。此划分借鉴 so-im 的入口、领域逻辑和生命周期分离，未搬入其 Redis/MongoDB 或微服务部署依赖。

SQLite 默认位于 `runtime/server/hczs.sqlite`，用项目 application ID、schema version 1、STRICT 表、WAL 和完整同步写入。更新在事务中检查修订号并提交。未知存档身份或版本明确拒绝，未实现跨版本迁移，不会清空旧数据库。存档与 WAL/SHM 均位于被 Git 忽略的运行目录；手工备份应先停止服务，再复制存档文件，避免遗漏尚在 WAL 中的数据。

来源字段和模块索引会做结构检查，内容摘要标识实际加载的文件；它们不等于针对人为修改数据的真实性认证。恢复来源的严格校验由上游提取工具及其证据完成。

`src/battles.js` 使用独立的 `${savePath}.battles` SQLite 文件，拥有自己的 application ID/schema version。战斗状态、固定场景定义和请求结果在事务中保存；不会改动已有档案表结构。状态使用带类型的 JSON，保留小数生命值和PRNG状态。`packages/battle-session` 实现纯回合状态机，`src/tutorial.js` 把有来源的数据与显式重建政策装配成场景。校验和用于识别意外不一致，结构校验不证明存档历史未经人为编辑。

## 验证

```powershell
pnpm test:server
pnpm test
```

当前33项服务端测试通过，覆盖实际HTTP首战通关、基础图鉴/档案、新Node进程恢复战斗及请求收据、创建/动作幂等、并发修订冲突、跨档案拒绝、存储失败回滚及未知数据库保留；其中新增5项自定义玩法校验及配置变更后的存档隔离测试。9项原教程装配器检查包含原始资料摘要、字段来源和明确规则差异。半截请求另有真实连接测试：关服给予1秒宽限后关闭活动连接，释放SQLite；重复关闭返回同一Promise。全工作区178项测试通过。原教程CLI运行见[验证记录](../docs/tutorial-session-verification.md)，自定义运行见[守势试炼](../docs/custom-gameplay.md)；四端实际游玩继续单独验收。
