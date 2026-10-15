# 黑潮之上重建服务端

Node.js ESM + MongoDB/Mongoose。默认存储已按用户要求与 so-im 技术路线对齐；SQLite 只保留旧存档迁移和历史回归。UE5、现有预览与 CLI 共用 `/api/rebuild/v1`，这是重建项目接口，不是原 APK 登录协议。`gameplayReady:false` 表示原版完整游玩尚未验收。

新增独立 `/api/admin/v1`，提供玩家管理、内容目录、运营配置草稿/发布/回滚和真实审计；配置发布直接影响创建开关及默认关卡。Admin与游戏共用Mongo连接和事务，84项服务端检查通过，现有1份档案/4场战斗/大厅状态保持。界面为[7470本地后台](http://127.0.0.1:7470/)，见[接口与验收](../docs/admin-server-api.md)、[领域规划](../docs/game-admin-roadmap.md)。

## 本地启动

```powershell
Set-Location D:\hczs
pnpm install --frozen-lockfile
node tools/start_mongo.mjs
node server/src/index.js --port 7460 --city-preview
```

MongoDB 为独立 Docker Compose 项目 `hczs-local`，只映射 `127.0.0.1:27027`，使用持久卷与单成员副本集；初始化脚本只操作此项目。默认 URI：`mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true`。不连接 so-im 的 27017 或其它项目的 27018。

`MONGODB_URI`、`MONGODB_DB_NAME` 可配置，也支持 `--mongo-uri`、`--mongo-database`。含凭证 URI 使用环境变量，不写命令行或日志。数据库名必须以 `hczs_` 开头。普通模式默认 `hczs_local`，`--city-preview` 为 `hczs_city_preview`，`--custom-scenario` 为 `hczs_custom`。缺少 Mongo 或事务能力时拒绝启动，不自动回退 SQLite。单成员副本集提供本地事务，不代表高可用。

`pnpm server` 默认 HTTP 7457；`--no-tutorial` 只提供目录、档案和可用大厅接口。服务只监听回环地址；浏览器允许来源 `http://127.0.0.1:7456` 和 `http://localhost:7456`。原生客户端直接调用。当前没有多人账户认证，手机的 127.0.0.1 指向手机自身，设备联调需另行配置网络路径。

需要 `analysis/game-data/characters.json`、`cards.json`，见[数据恢复](../docs/game-data-recovery.md)。`tools/prepare_server_heroes.py` 生成 `heroes.json`；缺该文件不声明 heroes/hall 能力，文件损坏则拒绝启动。完整目录35位英雄来自8995表 `UseRole=1` 投影，不表示拥有、解锁或全部可战斗。当前只有不知火（33）的大厅资源标为已验证参考，UE5运行尚未验证。

## API

路径统一加 `/api/rebuild/v1`；写入为 UTF-8 `application/json`，上限16KiB，不接受多余字段和查询参数。

| 方法及路径 | 用途 |
| --- | --- |
| `GET /status` | 能力、schema、storage、当前战斗模式 |
| `GET /bootstrap` | 启动信息、档案列表、内容摘要、可用接口 |
| `GET /heroes` | 35位英雄显示目录及来源（有该目录时） |
| `GET /catalog` | 旧三角色与四卡牌样本，保持已有客户端兼容 |
| `GET /encounters` | 当前可选战斗及默认入口；只列已启用的恢复/重建内容 |
| `GET /encounters/:id` | 指定入口的场景定义与证据说明 |
| `GET /profiles` | 独立本地档案列表 |
| `POST /profiles` | `{ "displayName": "本地旅人" }` 创建档案 |
| `GET /profiles/:id` | 档案及修订号 |
| `PATCH /profiles/:id` | expectedRevision + 名称或旧 selectedCharacterId |
| `GET /profiles/:id/hall` | 大厅偏好；未保存时revision 0，不因读取写入 |
| `PATCH /profiles/:id/hall` | requestId、expectedRevision、selectedHeroId |
| `GET /tutorial` | 场景定义、来源与重建规则差异 |
| `GET /profiles/:id/battles` | 战斗列表 |
| `POST /profiles/:id/battles` | requestId、可选uint32 seed和encounterId创建战斗 |
| `GET /profiles/:id/battles/:battleId` | 完整固定规则、状态和修订号 |
| `POST /profiles/:id/battles/:battleId/actions` | requestId、expectedRevision、动作 |

大厅示例：`{"requestId":"hall-select-1","expectedRevision":0,"selectedHeroId":33}`，返回 `{hall,replayed:false}`。`selectedHeroId:null` 取消偏好。大厅有独立revision，不改变旧selectedCharacterId，也不赋予原服角色所有权。

战斗示例：`{"requestId":"play-1","expectedRevision":1,"type":"play-card","instanceId":"tutorial-card-1"}`。结束回合使用 `type:"end-turn"` 并省略instanceId。服务端检查手牌、费用、终态并结算；胜负保存，不发放尚未恢复的原服奖励。旧战斗保留创建时的场景，不受后续配置修改影响。

选关创建示例：`{"requestId":"new-tutorial-1","encounterId":"tutorial-5000","seed":5000}`。城市服务同时提供tutorial-5000和city-preview-10405；自定义服务提供tutorial-5000和custom。省略encounterId保持旧客户端默认行为。新请求不能选择已停用入口，但历史同载荷重试及旧战斗恢复仍有效；同一requestId改选另一入口返回409。目录表示本地可执行内容，不代表原服关卡解锁。证据与限制见[选关接口](../docs/encounter-selection.md)。

超时重试复用原requestId和载荷；同请求返回首次回执replayed=true，同ID不同载荷或旧revision的新请求返回409。历史回执不回滚当前状态，客户端可GET最新状态。错误统一 `{error:{code,message}}`。原服/login等未实现路径为404。

## 持久化和迁移

`src/database/connection.js` 管理Mongoose连接、身份与版本；`storage.js` 装配档案、大厅、战斗模块。`packages/battle-session` 为独立纯规则层。状态与幂等回执同事务提交，唯一索引和revision防止并发重复写入。读取验证结构、归属和战斗摘要；损坏记录拒绝使用。API对象不直接暴露Mongo文档。

旧档迁移工具 `tools/migrate_server_sqlite.mjs` 默认只检查，显式应用才写入；同时保留档案、同名.hall/.battles和所有请求回执。源服务须先停写，目标必须为空；一次事务导入，拒绝覆盖不同业务数据。重复相同来源只报告已迁移，不覆盖后续进度。操作及实测见[迁移记录](../docs/mongodb-migration.md)。

显式旧档回归：`node server/src/index.js --storage sqlite --save-path runtime/server/old.sqlite --no-tutorial`。新主线无需SQLite路径；--save-path不会暗中选择旧存储。

## CLI、扩展和进程管理

`pnpm tutorial --auto --new --verify-reopen --seed 5000` 使用独立 `hczs_tutorial_cli` 数据库和临时HTTP端口验证保存恢复。`--custom-scenario server/data/custom/guard-and-draw.json` 加载[自定义玩法](../docs/custom-gameplay.md)，CLI使用 `hczs_custom_cli`。原始资料校验仍须通过。

`ecosystem.config.cjs` 定义PM2单实例hczs-battle（7460/hczs_city_preview）；先启动数据库再执行 `./tools/pm2_hczs.ps1 -Action start`。当前已实际托管成功。管理使用同脚本的list、logs、restart、stop；本机PM2硬编码全局Windows管道，因此脚本使用独立PM2_HOME与进程级专属管道适配，不改全局安装文件。不使用裸pm2命令管理此实例，不全局restart/save其它项目；没有设置Windows开机自启。

## 验证

```powershell
pnpm test:server
$env:HCZS_TEST_MONGODB_URI = 'mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true'
pnpm test:server
```

Mongo集成测试只有显式设置该环境变量才执行；未设置会标记跳过，不计作通过。测试创建随机hczs_test_数据库，只清理自己数据。覆盖真实跨进程并发、重启、幂等、事务回滚、存储身份和迁移。SQLite历史回归不能替代Mongo实测。UE接入见[客户端服务契约](../docs/unreal-server-contract.md)。
