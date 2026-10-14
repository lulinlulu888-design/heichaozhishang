# 黑潮之上：Node.js 服务端方案与 so-im 架构参考

调查日期：2026-10-14。参考仓库：`D:\project\so-im`。本次只读源码、包清单、架构文档及脚本，未读取真实 `.env` 或凭证，未修改或启动 so-im。

## 结论与约束

服务端优先采用 **Node.js + ESM JavaScript**，沿用 so-im 的模块分层、独立协议包、消息处理器、统一生命周期与契约检查习惯。类型边界可采用 JSDoc 与 `.d.ts`，需要时再增加 TypeScript 检查；现阶段不必为了使用 TS 先引入完整编译链。

最新目标是从一开始重建可维护、可重新打包、可新增玩法的跨平台客户端，覆盖 **Windows、macOS、Android、iOS**；服务端仍优先 Node.js。原 APK 作为资源、行为和协议的参考依据，不再以先让原 Android 客户端登录作为主线。按“新客户端启动与登录 → 角色与基础主界面 → 基础战斗 → 重启后存档恢复”逐步验收。Node.js 是服务端实现语言的选择，不能替代对资源与游戏规则的恢复。

新客户端的领域 API 与原游戏协议兼容层分开：领域模块管理角色、卡牌、战斗和存档；新 API 按可维护性与新玩法需求设计，兼容层仅负责已恢复原协议的适配。新 API 必须明确标为重建项目协议，不能冒充原 APK 兼容接口。先实现真实用例，需要扩展玩法时再建立对应抽象，不预建无调用方的插件系统或空服务。

**已恢复部分原生 Protobuf schema 和包内 Python RPC 参考帧格式，当前仍没有已验证的游戏兼容服务端。** 不把 so-im 的 REST、WebSocket、JWT、Redis RPC、消息 JSON 格式或应用层加密协议当作黑潮之上的协议；在客户端证据明确前，不预建假登录接口、不虚构 opcode、字段、错误码或响应。能启动通用 HTTP 服务器不等于 APK 能登录。

## so-im 中实际观察到的结构

下列事实以本次读取的文件为依据；它们描述仓库代码，不代表线上运行状态。

| 观察项 | 文件依据 | 对黑潮之上的借鉴 |
| --- | --- | --- |
| pnpm workspace 管理网关、业务服务、共享层和独立 packages | [根 package.json](D:/project/so-im/package.json)、[pnpm-workspace.yaml](D:/project/so-im/pnpm-workspace.yaml) | 一个项目统一管理分析工具、协议库与服务端；用工作区包表达依赖 |
| 已查看的后端入口是 Node ESM JavaScript，直接运行 `.js`；不是全后端 TypeScript 工程 | [Gateway package.json](D:/project/so-im/server/gateway/package.json)、[Shared package.json](D:/project/so-im/server/shared/package.json) | 先选 ESM JavaScript，降低初期构建成本；不误把 TS 当作 so-im 现有后端事实 |
| Gateway 使用 Koa、路由、中间件与内部转发 | [Gateway app.js](D:/project/so-im/server/gateway/src/app.js)、[routeManager.js](D:/project/so-im/server/gateway/src/services/routeManager.js) | 外部协议入口只处理连接、编解码与调用适配；游戏业务放在领域模块 |
| Auth 使用 `index.js → app.start() → RedisServiceApp → AuthMessageHandler` 的启动与注册方式 | [Auth index.js](D:/project/so-im/server/services/auth/src/index.js)、[app.js](D:/project/so-im/server/services/auth/src/app.js)、[AuthMessageHandler.js](D:/project/so-im/server/services/auth/src/services/AuthMessageHandler.js) | 显式启动、显式 handler 注册与资源关闭；路由名有单一登记处 |
| 内部请求通过 requestId 关联响应，维护待响应请求及超时；领域 handler 与传输适配分离 | [InternalCommService.js](D:/project/so-im/server/shared/src/services/InternalCommService.js)、[RedisMessageHandler.js](D:/project/so-im/server/shared/src/services/RedisMessageHandler.js)、[EventService.js](D:/project/so-im/server/shared/src/services/EventService.js) | 借鉴关联、超时和分发机制；初期在同进程调用，暂不增加 Redis 依赖 |
| 长连接服务将连接状态管理与处理器拆分 | [ConnectionManager.js](D:/project/so-im/server/services/websocket/src/managers/ConnectionManager.js)、[WebSocketMessageHandler.js](D:/project/so-im/server/services/websocket/src/services/WebSocketMessageHandler.js) | 按会话集中管理连接、心跳、顺序与断线；原协议兼容层以 APK 为准，新客户端 API 单独设计与标识 |
| 协议包独立导出 JS 与类型声明，并测试运行时枚举和声明的一致性 | [message-protocol package.json](D:/project/so-im/packages/message-protocol/package.json)、[src/index.js](D:/project/so-im/packages/message-protocol/src/index.js)、[contract.test.mjs](D:/project/so-im/packages/message-protocol/test/contract.test.mjs) | 黑潮协议单独成包，解析工具、服务端与测试共用；来源证据和兼容版本必须可追溯 |
| 共享数据层采用 Mongoose/MongoDB | [database/connection.js](D:/project/so-im/server/shared/src/database/connection.js)、[Shared package.json](D:/project/so-im/server/shared/package.json) | 借鉴统一数据入口和生命周期；不因参考项目使用 Mongo 就直接要求本地单机复现安装 Mongo |
| 有 Node 内置测试、Jest、契约检查和架构边界检查 | [Gateway package.json](D:/project/so-im/server/gateway/package.json)、[Shared package.json](D:/project/so-im/server/shared/package.json)、[check-service-boundaries.mjs](D:/project/so-im/scripts/checks/check-service-boundaries.mjs)、[后端开发规范](D:/project/so-im/docs/engineering/后端开发规范.md) | 优先采用 `node --test`，重点测二进制协议、状态迁移、重放与存档；保持边界检查规模适合本项目 |
| PM2 配置管理 fork/cluster、实例数、内存和关闭超时 | [ecosystem.config.cjs](D:/project/so-im/ecosystem.config.cjs)、[processLifecycle.js](D:/project/so-im/server/gateway/src/utils/processLifecycle.js) | 先用一个本地前台进程可控启动与关闭；能完整游玩后再考虑 PM2，部署参数重新制定 |

## 拟采用的项目布局

当前已实现 `packages/game-protocol`，以及单进程 `server/src/{index,app,catalog,store,errors}.js`：提供新客户端的图鉴读取、本地档案及角色选择持久化。运行说明和准确接口见 [服务端 README](../server/README.md)。以下服务划分是后续职责扩展方向，不是已经创建的全部目录；只在有真实用例时拆分。

```text
D:\hczs\
├─ analysis/                 # APK 清单、解包结果、脚本/协议证据
├─ tools/                    # 提取、解码、反汇编、证据检查工具
├─ docs/                     # 需求、恢复状态与兼容性说明
├─ packages/
│  └─ game-protocol/         # 经证据验证的帧、编码、消息定义与测试夹具
└─ server/
   ├─ gateway/              # 原客户端实际需要的传输入口和连接适配
   ├─ services/
   │  ├─ session/           # 本地账号映射、登录状态、角色选择
   │  ├─ player/            # 角色、编队、卡牌与进度
   │  └─ battle/            # 战斗状态和结算；职责以恢复结果为准
   └─ shared/               # 配置、日志、时钟、存档适配与生命周期
```

`services` 初期表示领域模块，放在一个进程中运行，不等于先部署多个微服务。新客户端连接的领域 API 与原协议适配器共享领域模块，但各有独立的传输与契约定义。原客户端资源补丁入口只有在确有需要且协议已确认时加入；管理入口、新客户端入口与游戏兼容入口必须明确区分。

依赖方向为：入口适配 → 消息注册/分发 → 领域模块 → 存档接口。协议包不得依赖业务服务，存档结构不得直接代替线上报文结构。共享层只收纳确有多个模块需要的稳定能力。

## 消息分发与协议恢复

1. 对每个恢复出的命令记录客户端版本、调用点、帧结构、编码、请求与响应、前置会话状态及证据文件。静态推断、运行观测和仍未知字段分别标注。
2. 传输层按实际证据选择 HTTP、TCP、UDP、WebSocket 或其他方式。封包、压缩、序列化和加密分别实现、分别验证，不能根据业务函数名猜测整条网络链路。
3. 内部使用注册表将已确认命令映射到 handler；内部调试标识不能冒充客户端线上字段。没有恢复的命令明确记录为未支持，不能统一返回“成功”。
4. 会话保存已验证的登录状态和序列信息。请求顺序、重复包与重连行为按客户端实际逻辑实现；涉及战斗奖励等写操作时，确认幂等边界后再修改存档。
5. 解码后的领域参数经过校验后进入游戏逻辑，响应再经协议层编码。保留可脱敏重放的原始样本与预期输出，避免只测试自己编造的请求。

如果恢复出的 Python 脚本承载了大量战斗规则，先分析其职责。可把可验证的规则移植到 JavaScript；若依赖特殊字节码或原生扩展，允许先用独立本地工具/进程提供规则验证，不把“全部用 Node 重写”作为阻断恢复的前置条件。Node.js 服务端与 Python 逆向工具可以共存。

## 持久化选择

初期先定义存档适配接口，保存账号/角色映射、角色状态、卡牌编队、关卡进度和必要的已结算记录；字段以恢复结果为准，不预设商业化全量模型。

首个本地档案用例已直接采用 Node 内置 SQLite：事务更新、修订号冲突检查、存档身份与版本检查，避免后续由 JSON 快照迁移。当前只保存名称及所选角色，未实现战斗进度、导入导出工具或跨版本迁移；未知版本明确拒绝打开。这是本项目的实现选择，不是 so-im 的现有存储方式。若后续目标扩大为多人服务，再根据实际需求评估 MongoDB 与 Redis。

无论采用哪种存储，都需要验证：重启不丢进度、重复结算不重复发奖、异常退出不会留下半次战斗结算、存档版本不兼容时有明确报错。磁盘快照、备份与源代码分离；原始 APK 和提取证据不作为数据库写入目标。

## 测试与部署验收

- **协议测试**：以真实脚本或运行证据为依据验证字节序、长度、编码、压缩/加密、消息方向和异常输入；已知样本应逐字节对比。
- **业务测试**：登录状态迁移、重复请求、存档恢复、战斗规则和结算一致性。战斗相关随机数与时间如果影响结果，应作为可控制的依赖；具体算法以证据为准。
- **端到端验收**：主线通过跨平台新客户端验证完整游玩闭环，并在各目标平台实际构建、安装和运行。原 APK 的静态资源、恢复出的规则以及可取得的运行行为用于对照；若声称兼容原协议，另需真实 APK 验证。只有服务测试通过，不能宣称已可游玩或四平台已支持。
- **本地运行**：先使用可配置端口和显式启动/关闭；默认仅供本机调试，模拟器或局域网设备接入再按其网络路径配置。缺少必要资源或协议配置时明确失败。
- **Windows 兼容**：不复制 so-im 中依赖 `lsof`、`xargs` 或 shell 风格环境变量的脚本，不按端口盲目结束未知进程。启动脚本直接使用 Node，环境配置与路径处理适配当前 Windows 工作区。
- **发布**：首阶段无公网发布需求。待登录、基础战斗和重启存档完成后，再固化依赖锁文件、启动说明、备份恢复和可选 PM2 配置。

## 下一步实现门槛

当前已有 `packages/game-protocol`：Protobuf 编解码保持 snake_case、required 字段和 int64 精度，并提供无网络依赖的 Python 参考帧编码与增量解码。来源文件、偏移和 SHA-256 记录在其 `schemas/provenance.json`；26 项 Node 测试验证静态推导的固定样本及边界，尚未与真实客户端流量比对。

新客户端首个领域 API 已实现真实目录投影与 SQLite 档案操作；14 项测试验证 HTTP 边界、冲突、事务回滚、数据库重开、独立进程重启，以及半截请求存在时的有界退出。下一步继续完成客户端联调与有证据的战斗规则移植。`AsioGateClient` 原生路径的加密、压缩、握手和方法调度继续作为兼容性研究，不作为新客户端开发的前置阻塞。当前没有游戏兼容接口；源码中的 `.proto` service 声明不意味着使用 gRPC。仅凭当前 APK 能否恢复完整内容仍待验证。
