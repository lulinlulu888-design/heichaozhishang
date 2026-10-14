# Android 首次运行记录

最新构建补充（2026-10-14，胜利标题动画）：arm64 分发包为 `runtime/dist/hczs-android-arm64-preview-9a3a6276bd74.apk`，102,418,035 字节，SHA-256 `9a3a6276bd742ecc8cbfabfe08f40e1dd5c1ac57f57a7e99b0e50631acc789a5`；x86_64 模拟器包为 `runtime/dist/hczs-android-x86_64-emulator-preview-a79df57e1354.apk`，105,536,541 字节，SHA-256 `a79df57e1354986e80626c79a2f0e81857c37cf8038b40d84f8d73669cb981dd`。二者签名、CRC、ELF/RELRO/ZIP 16 KB 检查及 58 项内容校验均通过，643 个导出文件与包内文件逐字节一致。新增验证直接读取导出 JsonAsset 中的标题动画对象，而非仅检查资源路径。最新包均未安装或运行；下文的旧版首次运行不构成这些新包的验收。此前安装/启动自动审批拒绝没有被绕过。

2026-10-14，用户明确授权恢复全部当前任务所需测试后，启动项目独立 AVD hczs-api35，Android 35 x86_64。ADB `sys.boot_completed` 返回1，APK `install -r` 成功，AppActivity 实际启动。

最初首屏请求得到403：`Use the loopback service address`。原因是设备请求7457，而ADB转发至主机7458，Host端口与服务监听端口不一致。已将客户端和生成模板的默认本地API端口改为7458，并重新构建、安装模拟器APK；设置 `adb -s emulator-5554 reverse tcp:7458 tcp:7458`。保留服务端原Host校验。

原生画面实际确认：本地服务已连接，三角色按钮、艾尔莎立绘、四卡牌资料、本地旅人档案及序章首战入口显示。立绘等比缩放正常。两次点击首战入口均被Computer Use的并发用户输入检测拦截，不能声称点击成功、已进入战斗或已完成游玩闭环。后续应重新观察再交互，不能复用旧截图坐标。

7458当前由独立Node进程启动（本轮PID57152），使用 `runtime/server/tutorial-preview.sqlite`，健康接口返回200和tutorial-battles能力。日志为 `runtime/server/battle-preview.out.log`、`battle-preview.err.log`。这不是PM2托管，PM2命名管道EPERM问题未解决；未停止其他PM2/Node进程。该直接启动是在用户本轮重新明确授权后执行。

Web也已重新构建，默认连接7458。Windows及arm64既有包仍使用之前7457默认值，下一次原生构建需要同步。旧构建校验报告不能证明本轮端口修正已同步至所有平台。模拟器运行日志位于 `analysis/android-runtime/client-first-run.log`。

2026-10-14 场景战斗版模拟器构建：Creator Android 导出及 Gradle assembleDebug 成功，x86_64 APK 99,827,294 字节，SHA-256 16dff9a7ac38de9dd667920ed74ac2993bb197ec93de1e3f01f4b38a3bcab555。verify_android_apk.py --variant emulator 实测签名、badging、CRC、ELF/RELRO/ZIP 16KB 对齐全部通过。源指纹已覆盖场景、光照与战斗脚本。

ADB 只读 devices 确认 emulator-5554 仍在线；但后续包含 install -r、reverse 和 am start 的命令被自动审批策略拒绝（仅返回 blocked by policy，无细分原因），未执行。没有改用其他路径绕过拒绝，也没有把旧设备上的应用当作新版验收。本轮新版 Android 安装、场景渲染与游玩仍未验证。

同轮 arm64 手机版本亦实际构建成功：96,708,796 字节，SHA-256 66b45e7bee4d0e4fe88732d9058367bdc10c30d24fbb3fb792ba8666ff337f4b，签名、CRC、ELF/RELRO/ZIP 16KB 对齐验证全部通过。包位于 clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk。两种 Android 构建均已包含7458默认API和新版场景战斗源码；仍为连接主机本地服务的开发包，并非脱离主机即可游玩的独立手机发行版。手机本机127.0.0.1须通过开发连接映射到主机，尚无真机验证。
# 2026-10-14 当前设备复核与新版模拟器包

REA `list_adb_devices` 本轮只读观察确认 `emulator-5554` 状态为 `device`，x86_64 模拟器在线。Evidence ID：`ev_daa2e466803a522e6348b555223273908632fb7d3687381de8e49b46882419e1`，完整结果保存到 `analysis/android-runtime/rea-device-readiness.json`。进一步只读 ADB 查询确认 AVD 名 `hczs-api35`、`sys.boot_completed=1`；已安装 `local.hczs.rebuild` 的 lastUpdateTime 是 `2026-10-13 23:58:02`，不是本次构建。转发表仍有 7458→7458 和历史 7457→7458；未修改这些条目。

最新版 x86_64 构建完成：`runtime/dist/hczs-android-x86_64-emulator-preview-2813c2f0803e.apk`，105,094,764 字节，SHA-256 `2813c2f0803e22a624023869d0e61941a7fec9b45beb2a45463a0535ca4a212a`。包含最新原大卡框和所有卡框透明边距修正。Creator/Gradle 成功，签名、CRC、x86_64、ZIP/ELF/RELRO 16 KB 检查通过；48 项内容检查通过。

内容验证和分发工具现支持 `--variant emulator`，分别使用模拟器导出目录与证据目录，要求结构报告 ABI 变体匹配，不能拿 arm64 报告代替模拟器包。旧 arm64 与 Windows 分发包保留，不声称已同步本轮最新卡框。

本轮没有执行安装、启动或输入。此前安装/转发/启动组合命令被自动审批以 `blocked by policy` 拒绝，没有细分原因；本轮只读观察和构建不解除该限制，也未换路径绕过。因此应准确描述为“模拟器存在且在线，最新包准备好，但最新 Android 运行尚未验证”，不能再概括为没有设备。

