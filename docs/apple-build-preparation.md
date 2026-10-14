# macOS 与 iOS 构建准备

项目现有 `build-mac.json`、`build-ios.json` 与原工程共享同一场景、TypeScript源码和恢复资源；生成器对应模板在 `tools/templates/cocos-build-{mac,ios}.json`。这一步完成配置与构建入口准备，**尚未在Mac上导出、编译、签名、安装或运行**。

## 配置依据

字段名逐项对照本机官方Creator 3.8.8安装包中以下类型声明，未猜测 `bundleIdentifier` 等字段名：实际字段是 `packageName`。

| 平台 | app.asar内路径 | 声明文件SHA-256 |
| --- | --- | --- |
| mac | `modules/platform-extensions/extensions/mac/@types/index.d.ts` | `ca65edc3555f09c81a6b5df44490a93565a9585acebba959d707e660f5c7d7f2` |
| ios | `modules/platform-extensions/extensions/ios/@types/index.d.ts` | `ae0a5a19e66ff630eeb7b8f1b4aa3ca4d0339c177077029b5c55a3b95f0b9d21` |

声明副本位于 `analysis/apple-build/`。字段含义另与[Cocos macOS构建选项](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/mac/build-options-mac.html)和[iOS构建选项](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/ios/build-options-ios.html)核对。

- 两平台包名 `local.hczs.rebuild`，只启用Metal，构建不自动运行游戏；保留项目原生V8调试监听关闭配置。
- mac配置 `supportM1=true`，部署目标11.0。这个标志用于引擎模块兼容检查，**不证明导出为arm64或Universal包**；最终架构必须检查实际二进制。
- iOS选择真实设备目标、横屏、部署目标13.0。没有填入或虚构开发者团队、证书、描述文件。系统版本只是当前开发配置选择，实际最低可运行系统仍待设备测试。
- `skipUpdateXcodeProject=false`，保证重新生成工程。因此实际iOS签名应在本次导出后的Xcode中配置；后续重新导出可能覆盖手动设置。

## Windows上已验证的范围

```powershell
node --test tests/cocos-apple.test.mjs
node tools/cocos-apple.mjs --platform mac --action check
node tools/cocos-apple.mjs --platform ios --action check
```

6项测试通过：配置与实际场景/模板对应、含空格路径保持独立argv参数、非Mac宿主拒绝导出且不会启动Creator，以及临时项目中缺失metadata、场景UUID改变、模型导入设置改变的检查。预检实际读取并记录场景、四个TS、恢复资产及父目录的19个 `.meta` 文件（含新增首战敌人），场景UUID必须匹配配置；其它导入设置以SHA留存供迁移对照。两份预检报告在 `analysis/apple-build/{mac,ios}/preflight.json`，记录所需源码/资源/metadata SHA、配置SHA以及 `canExport/exported/compiled/signed/installed/runtimeVerified=false`。这里的JSON配置验证是项目约束检查，不是Apple宿主Creator实际接受参数的证明。

## Mac上的下一步

需要Mac、Xcode和Creator **3.8.8**。Cocos官方[iOS发布步骤](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/ios/build-example-ios.html)要求Mac/Xcode，设备签名还需要相应Apple开发账号设置。

迁移时保留 `clients/cocos-poc` 的源码、`.meta`、`settings`、`native`项目覆盖文件，以及被Git忽略的 `assets/resources/recovered/` 实际资源。不要迁移Windows生成的 `library/`、`temp/`、`build/` 缓存，也不需要把原APK打入新客户端；在Mac上由Creator重新导入资源。

在仓库根目录运行（将应用路径替换为Mac上的实际安装位置）：

```sh
node tools/cocos-apple.mjs --platform mac --action check --creator '/Applications/CocosCreator/Creator/3.8.8/CocosCreator.app'
node tools/cocos-apple.mjs --platform mac --action export --creator '/Applications/CocosCreator/Creator/3.8.8/CocosCreator.app'
node tools/cocos-apple.mjs --platform ios --action export --creator '/Applications/CocosCreator/Creator/3.8.8/CocosCreator.app'
```

脚本先检查宿主、Creator应用版本、Xcode和所需资源，再通过不使用shell的参数数组调用Creator `stage=build`。它只导出，不触发安装、游戏运行、证书管理或向外发布。退出36且资源输出存在才记录 `exported=true`；仍然保留 `compiled/signed/installed/runtimeVerified=false`。之后在Mac上检查生成工程并使用Xcode编译、配置设备签名和运行，记录实际架构、产物摘要及真实游玩结果。

当前仅能在Windows验证前置逻辑。Mac端命令、PlistBuddy版本读取及Creator导出链路自身仍需首次实机执行，不将准备脚本的测试通过视为Mac/iOS构建成功。
