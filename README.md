# 黑潮之上 · 跨平台重建

项目仓库：[lulinlulu888-design/heichaozhishang](https://github.com/lulinlulu888-design/heichaozhishang)。本地origin已关联；源码、工具与文档纳入版本管理，原APK、提取资源、构建缓存和运行存档保留在本地。

目标：基于目录内现有 APK 的资源、脚本、协议和行为证据，从一开始重建可维护的跨平台客户端与 Node.js 服务端，重温《黑潮之上》，并支持自行新增玩法和重新打包发布本地构建。

用户最新确认：客户端主引擎切换为 **Unreal Engine 5**，覆盖 **Windows、macOS、Android、iOS**，继续直接跨平台重建。Cocos/Three 预览保留作资源与画面对照，不再是后续客户端主线。UE5 5.8.3 已安装，当前推进真实 UE 工程与原 APK 资源接入，继续完善 Node.js 服务端。此处是持续目标的最新范围，补充并修正最初的 Android 兼容方向及后续 Cocos 选型。

完整范围、当前状态、开发顺序和验收标准见 **[完整重建开发计划](docs/development-plan.md)**。后续直接维护这一份长期计划，覆盖全部角色与服装、模型动画、光影特效、玩法、Node.js/MongoDB 服务端、Admin 和四平台打包；必要证据保留在 `analysis/`，不再新增一次性开发记录。

本地视频参考：运行 `powershell -ExecutionPolicy Bypass -File tools/convert_bilibili_cache.ps1`，会扫描用户 `Videos/bilibili` 内已完成的桌面端缓存，无损合并 MP4、完整解码校验并提取带时间点的截图，生成 `analysis/video-references/index.html`。重复运行会跳过已转换且校验一致的视频；未下载完成的文件不处理。工具只读取原缓存。可用 `-Only <BV号或CID>` 限定视频、`-List` 查看状态、`-FFmpegDirectory <目录>` 指定含 ffmpeg/ffprobe 的工具目录；本机路径可放在不入库的 `runtime/reference-tools.json`。
