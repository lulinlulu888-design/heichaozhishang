# 首战客户端接入与构建

2026-10-14，Cocos图鉴加入“进入序章首战”。界面包含艾尔莎真实立绘、幻眼魔方模型待机、双方生命/护盾、能量、敌方意图、最多十张手牌、出牌、结束回合、继续存档和重试。首屏明确标注重建规则；缺失的原服务端逻辑沿用[显式重建配置](tutorial-reconstruction-policy.md)。模型接入与验收边界见[敌人Cocos接入](cocos-tutorial-enemy.md)；原版战斗动作衔接和奖励尚未实现。

## 实现与验证

`ToolchainProof.ts`负责入口、档案和XHR；`TutorialBattleController.ts`负责请求与状态；`TutorialBattleView.ts`负责显示和触摸。三份源码都有`tools/templates/`镜像，工程生成器已接入新文件。异步响应检查组件生命周期，防止退出后更新已销毁的界面。

控制器保留未确认写入的原请求编号，收到收据后再读取最新状态，旧回包不能倒退已见版本。已提交但响应丢失时，重试不会再次执行同一命令。未确认请求保存在当前控制器内存中，服务端状态和收据持久化在SQLite；不声称实现了跨客户端进程的离线请求队列。

- 完整Cocos工程TypeScript严格检查通过。
- `pnpm test:client`的15组真实HTTP/SQLite测试通过，包括通关、恢复、丢失响应、409冲突、重复点击和畸形数据；详见[独立验证](tutorial-client-controller.md)。这些测试不混入上一轮173项工作区测试。
- Web、Windows `model`变体和Android arm64已实际导出/编译。Windows新增脚本在EXE旁`Resources`中，必须连同DLL和资源分发；原生EXE哈希可保持不变。
- APK签名、ZIP CRC及16KB ZIP/ELF/GNU_RELRO对齐检查通过。三份角色动画构建各自通过既有17项静态检查，不代表实播验收。
- `tools/verify_tutorial_build.py`检查测试源码哈希、四份模板一致性、三平台各10份导出前来源指纹、六份模型审计的当前输入、实际Windows资源、APK内脚本及整个resources目录。最新28项结果和完整产物哈希在`analysis/tutorial-client/build-verification.json`。接入当前关卡标题/来源说明后APK为78,771,737字节，SHA-256 `5505c5c9de20a06e73d0deb862cff2a964a6fc1694d9e6c686690cd20126228b`。

界面标题与说明从当前战斗保存的 `scenario.title/notice` 读取，因此自定义关卡会明确显示“自定义”及其来源说明；没有把它显示成已恢复的原版关卡。[自定义示例](custom-gameplay.md)的实际验证为API/CLI，图形画面仍未验收。

## 当前预览

现有页面为`http://127.0.0.1:7456/`，默认连接`127.0.0.1:7457`。只读HTTP检查确认7457当前仅提供图鉴和档案能力，没有`tutorial-battles`，所以点击首战会明确提示服务版本不足。

浏览器入口现支持`?apiPort=7458`指定另一个本地服务端口；仅接受1至65535的数字，地址始终是`127.0.0.1`，不能指定远程主机。参数缺省或无效时使用7457。原生构建仍默认7457。端口解析经独立审查，16个边界样例通过；CORS和Host配置与新端口兼容。

用户已明确授权启动独立7458战斗服务，但自动审批仍拒绝启动命令，只返回“blocked by policy”，未提供更具体原因。服务未由工具启动，也未停止或重启旧服务。可由用户在本机终端启动后使用`http://127.0.0.1:7456/?apiPort=7458`：

```powershell
node "D:\hczs\server\src\index.js" --port 7458 --save-path "D:\hczs\runtime\server\tutorial-preview.sqlite"
```

用户截图验证了新入口和图鉴实际显示，以及旧服务能力检查提示。尚未实际运行图形首战，不将HTTP层通关当作Cocos XHR、布局、触摸或动画验收。Android无设备，macOS/iOS仍缺Mac/Xcode构建与运行环境。Android上的回环地址指设备自身，后续实测还需设备转发或平台端点配置。

用户随后明确要求PM2启动；已添加根目录 `ecosystem.config.cjs`，应用名 `hczs-battle`，相同7458端口和独立预览存档。本次 `pm2 start ecosystem.config.cjs --only hczs-battle` 返回默认管理管道 `EPERM`；最后只读核验7458仍未监听。此失败是PM2运行时权限错误，与此前自动审批拒绝分开记录，详见[PM2说明](../server/README.md)。

## 复现构建

在已准备工具链与恢复资源的项目根目录，串行运行：

```powershell
pnpm test:client
node .tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/bin/tsc --project clients/cocos-poc/tsconfig.json --noEmit --skipLibCheck --strict *> analysis/tutorial-client/typescript.log
$LASTEXITCODE | Set-Content analysis/tutorial-client/typescript.exit-code.txt
if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed' }
pwsh -NoProfile -File tools/cocos.ps1 -Action build-web
pwsh -NoProfile -File tools/cocos.ps1 -Action build-windows -WindowsVariant model
pwsh -NoProfile -File tools/cocos.ps1 -Action build-android
python tools/verify_android_apk.py clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk
node tools/verify_cocos_character.mjs
node tools/verify_cocos_character.mjs --config clients/cocos-poc/build/windows-model/proj/Debug/Resources/assets/resources/cc.config.json --output analysis/cocos-character/import-verification-windows.json
node tools/verify_cocos_character.mjs --config clients/cocos-poc/build/android/data/assets/resources/cc.config.json --output analysis/cocos-character/import-verification-android.json
node tools/verify_cocos_character.mjs --model enemy991
node tools/verify_cocos_character.mjs --model enemy991 --config clients/cocos-poc/build/windows-model/proj/Debug/Resources/assets/resources/cc.config.json --output analysis/cocos-enemy/import-verification-windows.json
node tools/verify_cocos_character.mjs --model enemy991 --config clients/cocos-poc/build/android/data/assets/resources/cc.config.json --output analysis/cocos-enemy/import-verification-android.json
python tools/verify_tutorial_build.py
```

此机器使用已安装Python/PowerShell 7的完整路径调用；系统`python`别名不可用。整体验证还读取本次TypeScript退出码记录`analysis/tutorial-client/typescript.exit-code.txt`，重跑时应同时更新该记录。Android结构检查须先于整体验证，后者会核对签名检查证据是否对应当前APK。

日志分别保存在`analysis/cocos-toolchain/`、`analysis/cocos-native-model/`、`analysis/cocos-android/`。Creator的构建配置版本、压缩选项默认值及Android WebGL模块回退提示均保留在日志中；最终成功退出码和实际包内容已交叉检查。
