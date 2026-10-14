# Cocos Creator 工具链核验

核验日期：2026-10-14。范围：为 Windows、macOS、Android、iOS 共用 TypeScript 客户端准备真实构建环境。此文记录本机事实、官方资料和待验证项，不代表四平台已构建成功。

## 当前结论

建议先以 **Cocos Creator 3.8.8** 做最小工程验证。官方当前下载页将该版本列为最新稳定发行，发布日期为 2025-12-16。[官方版本页](https://www.cocos.com/creator-download)

本机原先没有在已检查的常见安装目录、Cocos Dashboard 默认目录或卸载注册表中发现 Creator。现已下载官方 ZIP 到工作区，完成 **Creator CLI 真实 Web 构建、浏览器中文场景显示、点击计数和原包立绘显示**。本次没有账号或协议交互，也没有修改编辑器认证逻辑。官方文档仍要求 Dashboard 登录 Cocos 开发者账号；本次直接 CLI 成功不表示所有编辑器功能均免登录。[官方安装文档](https://docs.cocos.com/creator/3.8/manual/en/getting-started/install/)

PoC 在 `clients/cocos-poc/`，是独立工具链与资源展示验证工程。Windows x64 原生 EXE 已实际完成编译、启动、立绘显示和点击验证；Android arm64 调试 APK 也已真实编译并通过签名、CRC及16KB静态对齐检查，尚无设备运行验证，详见 [Android 构建记录](android-build.md)。没有实现原游戏完整玩法，macOS、iOS 原生构建尚未完成。

## 本机可复用组件

| 组件 | 已核实版本与位置 | 结论 |
| --- | --- | --- |
| Node.js | 24.18.0，`C:\Program Files\nodejs\node.exe` | 可运行工作区工具；不推定替代编辑器内置 Node |
| npm | 11.16.0，同一 Node 目录 | 可复用 |
| JDK | Microsoft OpenJDK 17.0.19+10，`C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot` | 与 AGP 8.10 的 JDK 17 要求相符 |
| VS Build Tools | 2022 17.14.36，`C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` | `vswhere -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64` 确认 C++ 组件存在 |
| MSVC | 14.44.35207，以上目录的 `VC\Tools\MSVC` | Windows 原生编译器已安装 |
| Windows SDK | 10.0.22621.0、10.0.26100.0，`C:\Program Files (x86)\Windows Kits\10` | 原生构建基础组件存在 |
| CMake | 3.31.6-msvc6，VS 的 `Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` | 不在 PATH，可按绝对路径使用 |
| Ninja | 1.12.1，VS 的 `Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe` | 不在 PATH，可按绝对路径使用 |
| Android SDK | `D:\Android\Sdk`，platforms `android-34`、`android-36` | 已有 API 36 |
| Android build-tools | 34.0.0、35.0.0 | 后续实际构建复用35.0.0，符合AGP8.10要求，无需安装模板默认36.0.0 |
| Android NDK | r27 / 27.0.12077973，`D:\Android\Sdk\ndk\27.0.12077973` | 已实际编译；补齐页大小链接参数后16KB静态检查通过，设备运行待验证 |
| SDK CMake | `D:\Android\Sdk\cmake` 未发现 | 后续使用显式 `cmake.dir` 成功复用Creator随包3.24.3，无需SDK另装 |
| adb、sdkmanager | `platform-tools\adb.exe`、`cmdline-tools\latest` | 已存在；不自动接受新许可 |
| macOS/Xcode | 本机为 Windows，没有 Mac 构建机证据 | macOS/iOS 原生构建暂无法在本机验证 |

本轮检查安装目录、相关卸载注册表和明确工具路径；“未发现”不表示扫描了整个磁盘。D 盘检查时可用 400,700,657,664 字节（约 373.2 GiB）。

## 官方编辑器包与磁盘用量

来源：[Cocos 官方 Windows ZIP](https://download.cocos.com/CocosCreator/v3.8.8/CocosCreator-v3.8.8-win-121518.zip)。2026-10-14 通过 HTTPS HEAD 返回 200，无认证 Cookie；Range 请求返回 206。

| 字段 | 实测值 |
| --- | --- |
| Content-Type | `application/zip` |
| Content-Length | 1,027,270,586 字节，约 979.7 MiB |
| Last-Modified | Tue, 16 Dec 2025 01:31:18 GMT |
| ETag | `"6940b666-3d3ae7ba"`；不是已验证的加密校验值 |
| ZIP 条目数 | 51,661 |
| 中央目录大小 | 8,565,391 字节 |
| 声明解压总大小 | 3,915,570,914 字节，约 3.65 GiB |
| ZIP 加解压内容 | 4,942,841,500 字节，约 4.60 GiB；不含文件系统开销和工程缓存 |
| 顶层可执行文件 | `CocosCreator.exe`，声明大小 180,338,408 字节 |

建议编辑器及首个工程预留至少 10 GiB；原生中间文件、Gradle 缓存、后续资源导入还会增加占用。这是空间预算，不是已经测量的构建产物大小。

实际路径：下载文件 `.tools/downloads/CocosCreator-v3.8.8-win-121518.zip`；编辑器 `.tools/cocos/3.8.8/CocosCreator.exe`。完整归档 SHA-256 为 `e365030aa4f24b515f499cf093cd86fdf38a0f763b5fbcacb20e96253e0fcc0b`，全部 51,661 个成员解压时 CRC 校验通过。此哈希为本地实测，不冒充官方发布的校验值。

`Get-AuthenticodeSignature` 返回 `Valid / Signature verified`，签名主体 `Xiamen Yaji Software Co., Ltd.`，证书指纹 `D4270DC1892034C805F97AFFDEA29AFECDE8EEBE`。PE FileVersion 与 ProductVersion 均为 `3.8.8`。证据见 `analysis/cocos-toolchain/signature.json` 和编辑器目录内 `codex-download.json`。没有全局安装或修改系统 PATH。

Creator 运行会生成标准用户配置 `C:\Users\5090B\.CocosCreator`；传入的 `--home` 在实际日志中被默认路径替代，因此复现脚本不将它当作可用的隔离选项。后续调用使用 `--user-data-dir` 将 Electron 用户数据放入 `.tools/cocos/3.8.8/electron-user-data`。最初 `--help` 未返回参数帮助而驻留，已停止该次自己启动的进程；没有用修改内部文件的方式绕过此行为。

## Android 模板的直接证据

以下内容通过该官方 ZIP 中央目录定位，再以 HTTP Range 读取单个压缩成员、用 Deflate 解压；没有运行包内代码。相比泛用 3.8 文档，这些更准确描述所选 3.8.8 包：

| ZIP 内路径（前缀为 `resources/resources/3d/engine/templates/android/build/`） | 关键设置 | 解压成员 SHA-256 |
| --- | --- | --- |
| `build.gradle` | Android Gradle Plugin 8.10.1 | `30ca015c1974e4d6ba186b2a41d4380341af615b76dcfdbfc88d28f5fbdd6591` |
| `gradle.properties` | compile/target SDK 36、min SDK 21、build-tools 36.0.0、arm64-v8a、`PROP_NDK_VERSION` 留空、`PROP_ENABLE_COMPRESS_SO=false` | `38fec8fcbd70fa58a869b1f859792b6039e6f3d519157eac7739c09412a0eb3d` |
| `gradle/wrapper/gradle-wrapper.properties` | `https://services.gradle.org/distributions/gradle-8.11.1-bin.zip` | `eae602e954d3d5df6c2e5d506e2117da51d1100d485a1fe4b9d6842ee7dd3ef7` |

AGP 官方兼容表要求 Gradle 8.11.1、JDK 17，支持最高 API 36，默认 NDK 恰为本机 27.0.12077973，最低 build-tools 为 35.0.0。但 Creator 模板明确指定 36.0.0，不能未经构建直接假设可由 35 替代。[Android 官方 AGP 8.10 文档](https://developer.android.com/build/releases/agp-8-10-0-release-notes)

Creator 通用原生环境文档仍列出旧 NDK 推荐版本，因此暂不据此盲目降级。对于 16 KB 页面，Android 官方说明 NDK r28+ 默认支持，r27 及以下需要相应编译/链接选项；最终应检查构建 `.so` 的 LOAD/RELRO、APK zip 对齐并运行验证，不能只凭 Creator 版本号宣称通过。[Cocos 原生环境](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/setup-native-development.html)、[Android 16 KB 指南](https://developer.android.com/guide/practices/page-sizes)

首轮不提前安装另一套 NDK。先检查编辑器具体 Android CMake 要求及生成工程，确认后再列出缺失组件、官方下载体积与许可状态。Gradle 依赖下载会额外占用网络和磁盘，尚未计入上述编辑器包体积。

## 已执行与后续验证顺序

1. **已完成**：从官方 HTTPS 下载，安全检查 ZIP 路径，解压和记录哈希、版本、签名。
2. **已完成**：复制包内 `resources/templates/empty-2d`，以官方 `scene-2d.scene` 创建固定 UUID 场景，挂载真实 TypeScript 组件。
3. **已完成**：两次 `web-desktop` 构建均退出 36。首次引擎编译约 37.758 秒，加入立绘及 GLB 后约 5.680 秒。Chrome 中读取到 `scene-ready`、`portrait-ready`、`interaction=1`，截图可见中文场景、立绘和点击后的数字 1。
4. **已完成**：同一源码已导出 Windows x64 工程并生成实际 EXE，复用 VS 2022 Build Tools；原生窗口的中文、立绘、点击交互均已验证。
5. **已完成构建与静态校验**：复用现有 SDK/NDK/JDK 和 Creator 随包 CMake，生成 arm64 调试 APK；签名、CRC、ZIP/ELF 16 KB 对齐通过。用户目前没有手机/模拟器，设备运行仍待验证，详见 [Android 构建记录](android-build.md)。
6. **待执行**：macOS/iOS 实际工程导出、Xcode 编译、签名和运行，需要可用 Mac。官方文档要求 Xcode 14+，此处不宣称已验证最新 Xcode 的兼容性。[Cocos 原生环境](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/setup-native-development.html)

实际构建入口如下：

```powershell
Set-Location D:\hczs
& .\tools\cocos.ps1 build-web
# Windows：导出资源和 CMake 工程，再编译实际 EXE。
& .\tools\cocos.ps1 build-windows
# 单独导出或对已导出的工程增量编译：
& .\tools\cocos.ps1 generate-windows
& .\tools\cocos.ps1 compile-windows
# 运行生成的原生客户端，PID 与标准输出写入 analysis/cocos-native/。
& .\tools\cocos.ps1 run-windows
# 在前台运行本地预览服务器；Ctrl+C 停止。
node .\tools\serve_cocos.mjs
# 浏览器访问 http://127.0.0.1:7456/
# 手工打开编辑器：
& .\tools\cocos.ps1 open
```

官方说明 CLI 仍依赖图形窗口环境；它不是无 GUI 的纯命令行编译器。文档中的退出码为 32（参数无效）、34（构建失败）、36（构建成功），必须结合日志与实际产物判断。构建配置可从编辑器导出 JSON 后通过 `configPath` 指定，避免依赖某次本机界面状态。[官方 CLI 文档](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/publish-in-command-line.html)、[构建面板](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/build-panel.html)

从尚未准备工具链的工作区复现时，依次用 Python 执行 `tools/setup_cocos.py`（下载和安全解压）、`tools/create_cocos_poc.py`（工程不存在时创建，不覆盖已有工程）、`tools/prepare_cocos_assets.py`（验证恢复 PNG 哈希、复制素材并记录来源），再运行上述构建命令。已存在的工程无需重建。资源准备需要先有本项目的恢复产物；缺少时应先按资源转换文档生成，不能从无证据的网络素材代替。

如果之后启动其他编辑器功能要求账号或新的许可确认，保留界面/日志并由用户完成该步骤；本次没有此类阻塞，也未接受协议。

## Windows 原生构建记录

`build-windows.json` 使用 `windows` 平台、x64、Debug、GLES3，以及与 Web 相同的场景 UUID。关闭 Vulkan/GLES2、服务端模式和自动运行。Windows 选项名已对照安装包内的类型定义与[官方 Windows 构建参数](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/windows/build-options-windows.html)。

构建分为两个真实阶段：Creator `stage=build` 导出资源及 CMake 工程；`stage=make` 调用 CMake/MSBuild 编译、链接。`tools/cocos.ps1` 分别检查退出码 36，并要求实际找到唯一的 `hczs-cocos-poc.exe`，不会将工程导出当作编译完成。具体阶段语义见[官方 CLI 文档](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/publish-in-command-line.html)。

2026-10-14 首轮 `make` 耗时 139.081 秒，生成 `clients/cocos-poc/build/windows/proj/Debug/hczs-cocos-poc.exe`（40,830,464 字节）。使用 Creator 随包 CMake 3.24.3，自动选择已有 VS 2022 Build Tools、MSVC 14.44 和 Windows SDK 10.0.26100.0。Debug 目录还包含资源和运行所需 DLL；不能单独复制 EXE 就视为可分发版本。

官方 Debug 模板的 `Game.cpp` 默认启用 `0.0.0.0:6086` V8 调试监听。因此首轮 EXE 没有运行；工程通过受支持的 `native/engine/common/localCfg.cmake` 关闭 `USE_V8_DEBUGGER` 与 `USE_V8_DEBUGGER_FORCE`，复现脚本在编译前显式重新配置 CMake。此调整不修改 TypeScript 或场景。

实际遇到并已修复的两处工具链问题：PowerShell `Start-Process -Wait` 会等待 Creator 启动后遗留的控制台进程，现改为等待 Creator 自身退出；传给 CMake 的 `RES_DIR` 使用正斜杠，避免官方资源模板将 Windows 反斜杠解析为转义。首轮失败配置日志保留在 `analysis/cocos-native/configure-windows-first-attempt.stderr.log`。

证据目录 `analysis/cocos-native/` 包含导出、配置、编译的标准输出、错误输出和退出码，首轮编译日志另存为 `compile-windows-initial.*`。`cmake-cache-options.txt` 记录实际生成器和调试开关，`executable-sha256.json` 记录最后编译产物哈希。

关闭调试器后的重编译耗时 128.936 秒，EXE 为 40,297,472 字节，SHA-256 `2199ff35cbb9720215204670b5563cee7f81813d193cbb8531139c10c90401fc`。运行日志确认 GLES3、V8 11.6.189.22 与 Creator 3.8.8 已初始化；`scene-ready` 和 `portrait-ready` 都来自实际 Windows 进程。首启有缓存 JSON 不存在/空内容及渲染管线初始化警告，之后正常进入场景，未见脚本运行错误。

使用已安装的 Computer Use 技能（`@oai/sky`）选择唯一的 `hczs-cocos-poc` 窗口，实见中文标题、立绘与计数 0；一次工具点击后截图显示计数 1。`native-proof.png`、`native-ui-evidence.json` 和 `run-windows-proof.stdout.log` 保存截图、窗口信息和日志。稍后日志继续出现额外触摸事件，来源未确定，不将这些事件计为额外自动化测试。窗口验证后已停止本次启动的进程。`runtime-process.json` 记录检查时响应正常、该 PID 无 TCP 连接或监听。

`run-windows` 是交互式游戏启动入口，打开正常窗口；编辑器构建和 CMake 辅助进程仍保持隐藏。原生截图 SHA-256 为 `f1cae0cd5f5be9ee3c980e04704322f7fce22902543213fe8ba0c97e601e0543`。

![Windows 原生立绘与点击计数验证](../analysis/cocos-native/native-proof.png)

## 本地角色图鉴与档案联调

后续将同一 TypeScript 场景升级为 1280×720 的角色图鉴：左侧真实立绘，右侧三角色切换、四张恢复卡牌，以及“创建并保存”“保存角色选择”“重新读取”。角色、卡牌名称、消耗、等级和故事均来自 Node 的 `GET /api/rebuild/v1/catalog`；没有解释伤害公式，也没有将展示图鉴宣称为玩家拥有的角色或牌组。

客户端通过标准 XHR 访问 `http://127.0.0.1:7457/api/rebuild/v1`。启动只读取目录和档案列表；创建及修改仅响应按钮操作，保存携带 `expectedRevision`，冲突时提示重新读取。无档案时点击创建“本地旅人”并保存当前选择；已有档案时使用列表首项。重复保存同一选择不会产生额外写入。重新读取会即时移除并销毁旧图鉴节点，避免残留事件对象。

`tools/prepare_cocos_assets.py` 现在以来源 `member=assets/res/uires.npk`、`index=3481` 匹配旧独立样本，修复了来源目录更名后的路径匹配问题。新增立绘同时校验角色表 `CharImage` 与 `analysis/resource-mapping/characters/portraits.json`，核对 PNG SHA-256 后复制到 `resources/recovered/characters/{id}.png`。映射为艾尔莎1→NPK4995、琳2→NPK5664、未来3→NPK3395；完整来源和哈希写入 `asset-provenance.json`。它们与之前匿名立绘/GLB 的来源关系没有被混同。

本轮实际证据：

- Web 新界面已真实显示三角色按钮、艾尔莎与琳的对应立绘、四张卡牌。点击琳后出现“尚未保存”，再点击“创建并保存”成功写入本地旅人，`selectedCharacterId=2`、`revision=2`。界面显示“已保存：琳 · 下次打开将恢复”，截图和只读 API 复核分别为 `analysis/cocos-toolchain/catalog-browser-saved.jpg`、`catalog-browser-save.json`。
- 最终修订后的 Web 构建返回36。Windows 最终导出及编译也返回36，增量 `make` 耗时4.754秒。实际原生进程日志包含 `catalog-ready; characters=3; cards=4`、`profile-loaded; revision=2; selected=2`、`portrait-ready; character=2`，证明新客户端通过本地 API 读取了浏览器保存的档案并加载琳的资源。日志保存在 `analysis/cocos-native/catalog-native-launch.stdout.log`。
- 用户按实体 Escape 停止 Computer Use 后，所有界面操作已停止。最终 Web 刷新已经发起，但未继续视觉确认；新原生界面的截图、角色切换和保存按钮尚未验证。此前独立原生 proof 的中文/立绘/点击0→1验证仍成立，不能代替新档案界面的交互验证。
- 本次运行中的 API 服务没有重启；负责服务的主任务所发重启操作被自动审批拒绝，未执行，也未尝试绕过。不能据此宣称已完成本次 UI 链路中的服务重启恢复。

![浏览器中保存琳到本地档案](../analysis/cocos-toolchain/catalog-browser-saved.jpg)

## 资源导入与浏览器证据

- `clients/cocos-poc/asset-provenance.json` 记录两个独立样本的复制来源和 SHA-256；恢复素材目录已在工程 `.gitignore` 忽略。
- 立绘源为 `assets/res/uires.npk` 第 3481 项，经 KTX/ASTC 转换为 990×820 PNG。PoC 实际加载并显示，PNG SHA-256 为 `c603f26e3394fabd8cae655535783dcce3f016bb5f5cb681a047bb7fe76a309e`。这验证导入与透明度显示，不证明所有原材质效果完全一致。
- GLB 源为 `analysis/model-conversion/character.06424.skinned.glb`，SHA-256 `5067d493fa21bb7f9218fd1e0131c2dae35353192635e91211d3b894129e2560`。Creator 导入器生成 imported=true 的 mesh、skeleton、prefab：28,864 个三角形、159 个骨架关节，实际 mesh 二进制为 1,794,624 字节。证据为 `analysis/cocos-toolchain/imported-model.meta.json`、`asset-import.log` 及工程 `library/81/`。
- GLB 没有放进当前 2D 场景，尚未验证模型渲染、动画和贴图。立绘与网格来自不同条目，不推断它们属于同一角色。
- 浏览器证据：`analysis/cocos-toolchain/browser-console.json`、`browser-proof.jpg`。页面只由本地 `127.0.0.1:7456` 服务提供；没有向外网发布。
- 构建日志：`analysis/cocos-toolchain/build-web.stdout.log`、`build-web.stderr.log`、`build-web.exit-code.txt`。默认压缩选项有回退提示，调试日志也记录了工作进程结束时的 SIGTERM；最终退出码 36、实际产物及浏览器运行均已交叉验证。没有把这些日志静默抹去。

![原包立绘与点击后的计数验证](../analysis/cocos-toolchain/browser-proof.jpg)

## 验收记录

后续已加入首战图形界面和浏览器本地端口选择，最新Web、Windows `model`与Android再次构建成功，控制器15组真实HTTP/SQLite测试通过。实际图形首战仍待验收，当前预览服务状态及构建对应性见[首战客户端接入与构建](tutorial-client-build.md)。

后续已加入艾尔莎模型预览代码与两段原采样动画，最新 Web、Windows `model` 变体和 Android APK 均构建成功。资源逐帧静态审计和 APK 检查通过；本次未进行界面与动画实播验收。具体来源、数值结果、构建哈希及边界见 [角色动画接入](cocos-character-view.md)。下表的既有运行验证指 2D 工具链/图鉴，不代替新增 3D 功能验收。

| 项目 | 当前状态 |
| --- | --- |
| 官方版本及 ZIP 可访问性 | 已核实 |
| 下载与解压准确体积 | 已从 HTTP/ZIP 目录核实 |
| 本机 C++/Java/Android 基础组件 | 已核实，缺项如上 |
| 完整编辑器下载和签名 | 已完成；SHA-256、CRC、有效签名、版本已记录 |
| 编辑器真实启动/账号门槛 | CLI 构建已启动并完成；本次无需账号，无协议交互；GUI 功能未全面验证 |
| Web 构建与运行 | 已完成；中文、立绘、点击交互通过 |
| GLB 导入 | 已通过；mesh/skeleton/prefab 已实际生成，未验证渲染动画 |
| Windows 原生构建与运行 | 已通过真实 x64 EXE 编译、启动、中文与立绘显示、点击0→1验证 |
| 本地角色图鉴与档案 | Web真实切换/创建/保存通过；原生通过日志证实读取相同档案与立绘；新增原生保存交互待验证 |
| Android 原生构建与运行 | 已编译实际 arm64 APK；签名/CRC/16KB静态对齐通过，尚无设备可验证运行；见 [Android 构建记录](android-build.md) |
| macOS/iOS 构建与运行 | 未执行；缺 Mac 构建机 |

## 2026-10-14 Windows 战斗画面同步构建

重新执行 `tools/cocos.ps1 -Action build-windows -WindowsVariant model`，Creator导出、CMake配置和编译均成功。实际程序 `clients/cocos-poc/build/windows-model/proj/Debug/hczs-cocos-poc.exe` 的 SHA256 为 `b1b01998cdc14357c1a3105e1db77fd643c85a696d40690c08e7465c3c890afa`。本轮同步共享客户端的战斗受击/死亡动画、原版血条、能量组件、卡框及费用位图字体。

新增 `tools/verify_windows_content.py`，核对导出源码指纹、三个构建退出码、x64 PE头和运行目录Resources。全部249个导出数据文件与运行目录逐字节一致；证据为 `analysis/cocos-native-model/content-verification.json`。这是静态一致性验证，不是本版Windows画面或输入验收。

新增 `tools/package_windows_preview.py`，在先运行上述校验后，打包exe、相邻DLL和Resources，排除调试符号及链接中间产物。压缩包为 `runtime/dist/hczs-windows-x64-preview-2f88aaf2bc07.zip`，65,632,858字节，SHA256 `79713132260cd76782cc833b05555f96e229fcb4aed1993a410cd2de445fa8de`。ZIP CRC及每个打包文件的哈希复核通过，记录于 `analysis/cocos-native-model/package-verification.json`。

使用时完整解压并保持相邻DLL和Resources结构。此包为本地调试客户端，Node.js服务仍单独启动；不是包含服务端的一键安装包，也未验证干净Windows设备上的依赖完整性。本轮未启动新程序，macOS/iOS构建和Android实际运行闭环仍未验收。

### 2026-10-14：Windows 圆弧手牌与拖牌箭头同步包

上轮Android同步及Web起点验证为有效进展。本轮重新执行 `tools/cocos.ps1 -Action build-windows -WindowsVariant model`，导出36、CMake配置0、编译36，全部成功。包含圆弧手牌、画布拖动、原素材目标箭头和卡牌中心起点。

扩展verify_windows_content.py，核对箭头加载路径、视图/几何模板及effect一致性。10项静态检查通过，260个导出数据文件与Resources一致。原生exe仍为40,370,688字节，SHA256 `b1b01998cdc14357c1a3105e1db77fd643c85a696d40690c08e7465c3c890afa`；本轮TypeScript与资源变化体现在Resources，不能仅用exe哈希识别客户端版本。

新包 `runtime/dist/hczs-windows-x64-preview-8e815b17392c.zip`，65,769,687字节，SHA256 `b8e7928846c07d30d4e5fd382a194e430edab60f3f9c4baeef0a3d5487d1f41e`。302个客户端文件及附加README入包，ZIP CRC和全部文件哈希复核通过；旧版本压缩包保留。证据为analysis/cocos-native-model/{content-verification,package-verification}.json。

本轮没有启动Windows程序，runtime_verified仍为false。未把资源一致性扩展为画面、输入、驱动或干净系统兼容性结论。Node服务需单独运行，Android实际运行和Apple平台构建仍待验收。


## 2026-10-14 Windows 选牌光效包

完成当前共享源码的 Windows model 导出、配置与编译，包含 CardSelectionView、选中框48帧和源布局/配色。tools/verify_windows_content.py 扩大检查到选中组件模板、编译后的资源加载路径、48张源PNG哈希、SpriteFrame导出入口，以及Resources中的对应PNG字节。共 14 项检查通过，405个导出数据文件与程序Resources逐字节一致。

发布包：runtime/dist/hczs-windows-x64-preview-4f5485e36159.zip，65,987,216字节，SHA-256 1c21210d54cc8fd2680ba662e861ff3e88697b2ffd8632620013a59b8c2c4ab4。包含447个客户端文件及README，ZIP CRC和每个文件哈希通过。旧包保留。证据：analysis/cocos-native-model/content-verification.json 与 package-verification.json。

这是调试客户端，Node服务需另行启动；当前源码默认连接127.0.0.1:7458。本轮未运行Windows窗口，不能把Web拖牌测试或静态包检查当作Windows实际游玩。macOS/iOS仍未构建运行，四端验收未完成。
