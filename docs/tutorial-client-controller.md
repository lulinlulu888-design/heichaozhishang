# Cocos 教程控制器的独立验证

`clients/cocos-poc/assets/TutorialBattleController.ts` 是不依赖 `cc` 的状态协调器。它只调用新本地 API，不在客户端重新计算伤害，也不把原包未恢复部分冒充完整原版。Cocos View 负责显示、输入和网络 transport；本文件记录控制器与真实服务之间的独立测试边界。

## 复现

项目根目录运行：

```powershell
node tools/test_tutorial_client.mjs
```

可指定项目 `analysis/test` 下的报告路径：

```powershell
node tools/test_tutorial_client.mjs --report analysis/test/tutorial-client/verification.json
```

需要 Node 24、本机已准备的 Creator 3.8.8，以及已生成的 `analysis/game-data` / `analysis/first-encounter` 证据。编译器固定使用 Creator 自带的 `resources/app.asar.unpacked/node_modules/typescript/lib/typescript.js`，验证版本是 **5.8.2**。脚本通过 `transpileModule` 将单个控制器 TS 编译至隔离临时 `.mjs`，再从该模块运行测试。它同时检查真实客户端文件与 `tools/templates/cocos-tutorial-battle-controller.ts` 镜像一致，并记录原 TS 和编译 JS 的 SHA-256。

这是单模块转译和运行验证，`transpileModule` 不是完整项目类型检查，也不是 Cocos 导入或原生构建。完整 Cocos TypeScript 检查和平台构建另行记录，不能由本脚本结果推定。

## 如何取得独立证据

每组测试创建自己的临时目录、真实 `createApp` 服务和 `127.0.0.1:0` 随机端口。角色/卡牌/教程政策均来自项目实际提取数据。transport 通过 `fetch` 发送真实 JSON 请求；HTTP 错误转为控制器定义的 `BattleRequestError`。

测试从**独立只读 SQLite 连接**读取 `battles.state_json`、revision、`battle_commands` 和 `battle_creations`，与控制器发布的状态比对。不会以控制器自身计算结果或另抄一份伤害公式作为期望答案。注入的“响应丢失”发生在真实服务器已经返回提交结果之后，因此数据库确实已经提交，控制器却无法得知结果。

默认 JSON 证据保存到 `analysis/test/tutorial-client/evidence.json`，包含每组通过/失败结果、写请求和原 `requestId`、状态摘要、SQLite 记录数、源码摘要、临时服务关闭记录。临时转译文件与数据库均在本次 `mkdtemp` 目录内，清理前再次检查目录归属。只关闭本脚本创建的服务，不触碰已有预览/API/原生客户端进程。

## 覆盖的行为

- 真实创建战斗、出牌、结束回合、丢弃旧控制器并关闭/重开本测试服务，恢复存档后继续通关。
- 创建响应丢失后，使用原请求重试，SQLite 中只有一场战斗及一条创建收据。
- 出牌提交后超时，刷新只能读取当前状态；在取得原写请求收据前保持未确认状态。重试相同 `requestId`，命令记录、扣血和能量只改变一次。
- 另一客户端更新后产生 409，重新读取最新 revision，不偷偷提交新的替代操作。
- 未确认写请求跨档案切换后仍保留；返回原档案可以重试原请求。
- 已获得写入收据、随后确认 GET 失败时，可仅通过 GET 刷新解锁，不必新增 POST。
- 旧幂等收据和延迟 GET 都不能让界面回退到已见过的较低 revision，包括 `onChange` 中间回调。
- 传输忙时的重复出牌/结束回合只发送一次写入。
- 切换档案或 `dispose()` 后，旧回包不能污染当前状态；销毁后的方法不再发送请求或发布回调。
- 畸形 battle、浮点标签、技能效果、敌意图和播放事件得到可控错误；已提交但响应畸形的写请求仍可安全重试。

这些测试只在 **Node 控制器 + HTTP + SQLite** 层运行。未操作浏览器或原生 UI，不代表本轮按钮布局、触摸、动画、Cocos XHR、Android 真机或者 macOS/iOS 运行已验收。服务重开在同一测试进程内，数据库使用重新创建的连接；本脚本不将其宣称为跨操作系统进程恢复测试。

## 本次结果

2026-10-14 本地执行 **15/15 组通过**，`cleanupComplete=true`。15 个用例与一次服务重开共创建 16 个临时监听服务，全部关闭。通关用例在实际存档中达到 `won`、revision 9、8 条命令记录，创建记录与战斗记录各 1。随机种子由真实服务生成；重跑的具体牌序、回合和 revision 可以变化，验收要求是状态与 SQLite 一致且最终胜利。

固定运行证据为 `analysis/test/tutorial-client/evidence.json`，结束时间 `2026-10-13T20:58:15.426Z`（UTC）。当次控制器和模板 SHA-256 均为 `af1e0562c97ebbad5a7adeae494bce03670a653b020321bcf7fd03473713805c`；转译模块为 `28be115e072f1d8ed68cefc244e7870edba6a1b6e14baec337ca8b9452c7265c`。脚本会在后续运行中覆盖默认证据文件，留存独立结果可使用 `--report`。

独立测试曾实际发现空 binary64 decimal 被接受并发布的问题；修正后，空串/空白/负值/decimal 与 hex 不一致均被拒绝，保留已验证的旧快照。此次通过不只是正常路径验证，也包括提交已生效但回包丢失、回包畸形和旧回包乱序等故障注入。
