# 黑潮之上 · Unreal Engine 5 客户端

最新实际工程为本目录 `clients/unreal5 5.8`，UE5.8.3。默认FX大厅已有原光照图、艾尔莎独立受光参考、原阳光粒子输入和五个可切换AI图标，见[实际运行验收](../../docs/unreal-hall-fx-runtime.md)。原NeoX完整材质/发射器、UI交互和四平台包仍未完成。

用户已选择 UE5 为新的共享客户端主引擎。本机 UE5.8.3 下已通过 UHT、C++ 编译和链接，原APK大厅与艾尔莎真实大厅待机已导入并在Windows编辑器游戏模式实际运行；尚未完成发布包及四平台可玩验收。详见 [艾尔莎大厅](../../docs/elsa-hall-unreal.md)。Cocos预览效果已退出主线；不知火/扇子历史资源保留。

## 工程边界

- `Hczs.uproject`：单 Runtime 模块；Python/编辑器脚本插件仅 Editor 目标启用。`EngineAssociation` 已关联5.8，本机 Build.version为5.8.3。
- `Source/Hczs.Target.cs` / `HczsEditor.Target.cs`：Game 和 Editor 构建目标。已锁定 `BuildSettingsVersion.V7` 与 `IncludeOrderVersion.Unreal5_8`，真实编译通过。
- `UHczsGameInstance`：只 GET `http://127.0.0.1:7460/api/rebuild/v1/status`，5 秒超时，检查 `service=hczs-rebuild`、`apiVersion=1` 和布尔 `gameplayReady`。请求回调明确在游戏线程执行；Shutdown 解绑并取消请求。
- `AHczsBootstrapMode`：默认引擎 Entry 地图使用引擎方块作为方向标记和地板，非游戏还原资源；其他地图不生成这些标记。使用 SpectatorPawn 检查基本桌面移动，HUD 显示真实请求状态，H 可重试。
- `Config`：启动地图为实际导入并保存的 `/Game/Recovered/Hall/Maps/L_ElsaHallAlignedPreview`；地图覆盖模式为 `AHczsRecoveredHallMode`，显示原大厅资源和静态UI。`/Engine/Maps/Entry`仍可手动用于基础调试。
- `UHczsHallWidget`：从原CSB转换的DataAsset加载84项静态UI，使用37张原PNG及2份原TTF；包含源变换、中文、颜色、阴影及标准Panel裁剪。UI目录纳入AlwaysCook，但发布包验证尚未执行。原按钮交互、加色混合、粒子和时间轴仍待接入，见[运行记录](../../docs/unreal-hall-ui-runtime.md)。

接口连接成功仅说明服务在线。工程不发送登录、创建档案或保存请求，也不根据服务返回将 `bOriginalGameplayReady` 置为 true。原版协议兼容与重建 API 分离。

## 安装后的验证顺序

1. 选择并记录实际安装的 UE5 版本，关联 `.uproject`，生成 IDE 工程文件。
2. 先构建 `HczsEditor`（Windows Development Editor / macOS 对应 Editor 工具链），处理真实 UHT/C++ 编译结果。
3. Editor 中打开实际艾尔莎大厅并 Play，确认原场景、角色待机和UI；状态请求结果见日志。Entry仍用于基础移动和HTTP调试。Node服务需另行启动；客户端不自动启动或终止进程。
4. 用真实编辑器导入脚本创建资源和地图，验证骨骼、坐标、贴图、动画与原 APK 证据一致，再接入玩法。不能把空场景移动当作游戏可玩闭环。
5. 分平台构建安装并验证 Windows、macOS、Android、iOS。TargetPlatforms 是目标清单，**不是支持完成声明**。

目前配置不默认启用 Lumen、硬件光追或全平台 Nanite。移动渲染、触屏输入、尺寸与抗锯齿策略需要独立验证。手机上的 `127.0.0.1` 指手机本机；USB 转发、设备内服务或其他实际联网方案尚未确认，不能直接把电脑端服务视为手机已连接。macOS/iOS 仍需 Mac/Xcode 与实际签名、安装条件。

## 官方 API 核对

源码使用已核对的官方文档接口，文档显示 UE 5.8；这不代替本机编译：

- [UGameInstance](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/UGameInstance)：客户端生命周期边界。
- [FHttpModule](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/HTTP/FHttpModule) / [IHttpRequest](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/HTTP/IHttpRequest?lang=en-US)：创建与管理平台 HTTP 请求。
- [请求回调线程策略](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/HTTP/EHttpRequestDelegateThreadPolicy)：选择 CompleteOnGameThread。
- [UnrealBuildTool Target Reference](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-build-tool-target-reference?lang=en-US)：Game/Editor Target 结构与构建设置。
- [项目打包](https://dev.epicgames.com/documentation/unreal-engine/packaging-your-project?lang=en-US)：平台构建与地图准备要求。

生成资源、缓存、运行日志和包均不提交。`Content/Python` 由独立编辑器导入任务维护，本骨架不覆盖其文件。

## 当前预览（2026-10-14）

默认已按用户要求切换到初始角色艾尔莎，暂停不知火画面调整。运行 `../../tools/unreal_project.ps1 -Action preview` 或 `-Action open`；使用原APK养成几何和正确home_stand_idle_1，整体俯仰错误已修正。静态原大厅UI在Play/独立游戏检视窗口显示，编辑器普通视口仅显示场景模型。原材质、完整UI功能和玩法未完成。
