# Android 本地测试构建

核验日期：2026-10-14。目标是将已经验证的角色图鉴与本地档案场景编译为 Android arm64 调试 APK。构建成功、安装成功、设备实际运行是三个独立验收项。

## 当前输入与环境

首轮使用 `clients/cocos-poc/assets/ToolchainProof.ts` 和同名图鉴场景，导出前 TypeScript SHA-256 为 `0bd09127ef03f5319810340e93d8139b4be357d780a3744755f0fd03168eace2`；场景为 `dfefcd312d0762cc3a7a58330bd7c6983842b081bf4e9591369c4aa4700bb18e`。后续加入 `RecoveredCharacterView.ts` 和艾尔莎动画 GLB，同一场景增加模型预览入口；见下文最新构建。每次导出前完整指纹写入 `export-source-fingerprints.json`，旧首轮数据不代表新 TS。原始 APK 保持只读。

| 组件 | 本次实际使用/检查 |
| --- | --- |
| Creator | 项目内官方 3.8.8；下载来源、签名和归档哈希见 [工具链记录](cocos-toolchain.md) |
| PowerShell | 本次实际使用 7.6.5；构建脚本以 `Start-Process -Environment` 配置子进程环境 |
| Java | `C:/Program Files/Microsoft/jdk-17.0.19.10-hotspot`，OpenJDK 17.0.19+10 |
| Android SDK | `D:/Android/Sdk`；已安装 platforms android-34、android-36 |
| Build-tools | 已有 34.0.0、35.0.0；本次明确选择 35.0.0 |
| NDK | 已有 `27.0.12077973`（r27），未另装 NDK |
| CMake | Creator 随包 3.24.3，路径 `.tools/cocos/3.8.8/resources/tools/cmake` |
| Ninja | VS 2022 Build Tools 已有 Ninja 1.12.1 |
| Gradle | 官方模板 wrapper 8.11.1，缓存位于项目 `.tools/gradle` |
| Android Gradle Plugin | 官方 3.8.8 模板固定 8.10.1 |
| adb | 只读 `adb devices -l` 结果为空；没有可见手机/模拟器 |

本机 SDK 没有独立 CMake 安装，也没有 build-tools 36.0.0。没有直接扩大安装：AGP 8.10 官方兼容表支持 API 36，要求 JDK17、Gradle8.11.1，build-tools 的最低与默认版本均为35.0.0，默认 NDK 正好为本机r27。[Android 官方兼容表](https://developer.android.com/build/releases/agp-8-10-0-release-notes)

Creator 模板模块原先固定 CMake3.22.1，本项目明确改为已有3.24.3，并通过生成工程的 `local.properties` 中 `cmake.dir` 指向编辑器随包版本；Ninja 仅加入子进程环境。该配置方式由[Android 官方 NDK/CMake 文档](https://developer.android.com/studio/projects/install-ndk)支持。没有修改全局 PATH、安装系统软件或接受新的 SDK 许可。

## 复现入口

在本机 PowerShell 7（`pwsh`）中执行；旧 Windows PowerShell 5.1 不支持脚本使用的 `-Environment` 参数。

```powershell
Set-Location D:\hczs
# 完整：Creator 导出资源/Gradle 工程，再真实编译 APK。
& .\tools\cocos.ps1 build-android
# 或拆为两个阶段：
& .\tools\cocos.ps1 generate-android
& .\tools\cocos.ps1 compile-android
# 编译完成后检查签名、ZIP 与 ELF；不安装或运行 APK。
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
    .\tools\verify_android_apk.py `
    .\clients\cocos-poc\build\android\proj\build\hczs-cocos-poc\outputs\apk\debug\hczs-cocos-poc-debug.apk
```

`clients/cocos-poc/build-android.json` 使用包名 `local.hczs.rebuild`、arm64-v8a、GLES3、横屏、API36、调试签名，关闭 App Bundle、Instant App、Input SDK 和自动运行。Android SDK/NDK/Java 路径在该配置中明确给出，对应选项已核对安装包类型定义和[Creator 官方 Android 参数](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/android/build-options-android.html)。包名属于新建本地客户端，不覆盖原游戏应用身份。

导出阶段检查 Creator 退出码36；编译阶段直接调用生成工程官方 Gradle wrapper 的 `assembleDebug`，检查退出码0和唯一实际 `*-debug.apk`。脚本不会把 Gradle 工程导出视为 APK 完成。Gradle使用 `--no-daemon`（Gradle仍可能创建本次构建专用、结束即退出的 JVM），依赖仅下载到项目 `.tools/gradle`；以 `-Pandroid.builder.sdkDownload=false` 禁用 SDK 自动安装。

Gradle 8.11.1 归档为136,920,070字节，SHA-256 `f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6`，与[Gradle 官方校验值](https://services.gradle.org/distributions/gradle-8.11.1-bin.zip.sha256)相同。脚本向生成的 wrapper 配置写入 `distributionSha256Sum`，后续首次下载仍会校验。归档与依赖都保留在 `.tools/gradle`，无需全局 Gradle。

为 NDKr27 添加 `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON`，并在 Android 项目 CMake 中给 `libcocos.so` 显式设置 `max-page-size=16384` 和 `common-page-size=16384`；保留模板的未压缩 `.so` 打包方式。首轮仅有前一项时，LOAD 段已对齐，但 GNU_RELRO 末端没有对齐；实际 ELF 检查发现后补齐后一项并重新链接。处理依据为[Android 官方 16 KB 页大小文档](https://developer.android.com/guide/practices/page-sizes)。最终仍逐项检查产物，不能仅凭参数判断兼容性。`native/engine/common/localCfg.cmake` 的关闭远程 V8 调试设置沿用 Windows 构建。

一次增量链接后，AGP 的 APK ZIP 中保留了旧未压缩库的无效空间，导致大小暂时翻倍。复现脚本在打包前只删除固定路径的上次生成 APK，让 Gradle 重新打包；不删除源代码、缓存或原始游戏 APK。最终包大小恢复正常。

## 2026-10-14 场景、武器与战斗动作版

重新执行 `tools/cocos.ps1 -Action build-android`，Creator 导出通过，Gradle `BUILD SUCCESSFUL in 11s`。arm64 调试 APK 为 99,177,076 字节，SHA-256 `a88d1fadaccafa4fab2c6fbd4e6201ad4e3aa00b97871b7cd87aebdd49d7c71a`。签名、ZIP CRC、ZIP/ELF 16KB 对齐检查均通过，最新证据为 `analysis/cocos-android/apk-verification.json`。

本次同步共享客户端中的序章场景、艾尔莎武器绑定、敌方四片段动画及玩家命中标记驱动的血量显示；导出指纹增加武器 GLB、绑定 JSON 和新敌方 GLB。武器流动效果目前仍仅在独立 Web 诊断页，未接入此包。以下早期图鉴版、模型版和端点说明是历史记录，不代表当前版本。

本次没有安装或启动 APK。此前安装操作遭自动审批拒绝，未改用其他方式绕过；构建及静态校验不能证明 Android 画面和输入已通过实机验收。

## 实际构建与验证证据

首战界面接入后的最新APK已重新构建和校验，最新体积、SHA-256及包内脚本一致性以`analysis/cocos-android/apk-verification.json`和`analysis/tutorial-client/build-verification.json`为准；详见[首战客户端接入](tutorial-client-build.md)。下文图鉴版与模型版哈希保留为历史构建记录。

证据统一放在 `analysis/cocos-android/`：

- `source-fingerprints.json` / `export-source-fingerprints.json`：导出源码指纹。
- `adb-devices.txt`：设备枚举为空。
- `generate-android.stdout.log` / `stderr.log` / `exit-code.txt`：Creator真实导出结果。首次导出30.437秒，退出36。
- `compile-android.stdout.log` / `stderr.log` / `exit-code.txt`：Gradle真实编译结果。
- `apk-sha256.json`：实际 APK 路径与 SHA-256。
- `apk-verification.json`：签名工具退出码、ZIP CRC、每个 ELF 的架构/LOAD/GNU_RELRO/ZIP 数据偏移；对应工具原始输出为 `aapt2-badging.log`、`apksigner-verify.log`、`zipalign-16k.log`。
- `apk-verification-first-build.json`：保留首轮发现 GNU_RELRO 对齐问题的失败证据。`compile-android-first-build.*` 保留首次完整 C++ 编译日志；`compile-android-relro-fix.stdout.log` 保留修复后的增量链接日志。
- `gradle-distribution-sha256.json` / `gradle-official-checksum.json`：Gradle 归档本地哈希和官方校验值。

实际 APK 路径为 `clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`。首轮图鉴版 74,630,445 字节（约74.6MB），SHA-256 `9f7f98556f623f3a945b014fae64670c9bc9f1efd045d47267bfbde9d598fa95`，首次完整编译168秒；后续重新打包14秒。修复后完整重跑过 `build-android`，确认 Creator 再次导出保留 Android CMake 修正。

**最新模型版**为 78,043,121 字节（约78.0MB），SHA-256 `5fb7652cff5c5b0832493884ee5575a4f454070864204b26d3a23c286323b4a6`。包含艾尔莎 180 骨骼、两段原采样动画及图鉴内模型预览代码；Creator 导出27.857秒、退出36，Gradle编译16秒、退出0，90项任务中5项执行、85项复用。完成后重新执行签名、ZIP CRC、16KB ZIP/ELF 检查并通过。原生 `.so` 与上一版相同，本次新增资源与脚本没有冒充设备实播验收。

| 检查 | 实际结果 |
| --- | --- |
| 构建 | Creator 导出退出36；Gradle `BUILD SUCCESSFUL`、退出0；实际 APK 存在 |
| 元数据 | `local.hczs.rebuild`，versionCode1/versionName1.0，minSdk21、targetSdk36，arm64-v8a，debuggable |
| APK 签名 | apksigner验证通过，v1与v2签名；Android Debug证书SHA-256 `34214739e0df9bf3937b73298552ae0fe6ef37f8892657a5065d27630e70faf4` |
| 内容完整性 | 全 ZIP 成员CRC通过 |
| ZIP 对齐 | `zipalign -c -P 16 -v 4` 通过；未压缩 `libcocos.so` 数据偏移327,680，为16KB倍数 |
| ELF 对齐 | AArch64；3个LOAD段均为16KB对齐；GNU_RELRO末端为16KB倍数 |
| 原生库 | `lib/arm64-v8a/libcocos.so`，71,663,496字节，SHA-256 `157ddb032d0eed25062fc2690e441408baec794058773f314cc8c94edd0cc7d9` |
| 安装与实际运行 | 未执行；adb设备列表为空 |

apksigner 对标准 `META-INF/com/android/build/gradle/app-metadata.properties` 给出其不受 JAR/v1 条目签名保护的提示，完整输出已保留；本包 APK v2 验证通过。manifest 沿用 Creator 模板，包括 INTERNET/网络状态和 BILLING 权限；没有实现付费功能。这是本地调试产物，发布配置尚未整理。

## 设备运行边界

本轮没有调用 Computer Use 或其他界面工具，没有安装 APK、启动模拟器，也未停止或重启现有 Windows 客户端/API服务。没有设备，不能声称安卓画面、触摸、驱动兼容性或16KB运行已经验证。

当前 TypeScript 仍连接 `127.0.0.1:7457`。在 Android 上它表示设备自身；连接本机 Node 服务需要后续针对实际设备设置 `adb reverse tcp:7457 tcp:7457`，或者另行实现平台端点配置。本轮未执行 reverse。模板允许明文HTTP，适用于当前本地测试；不能把此调试包直接视为正式发布配置。

## 2026-10-14 原版卡框、费用字体及受击动作版

本次重新完成 Creator Android 导出和 Gradle 编译，产物为 `clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`，99,551,753 字节，SHA-256 `66b8901551139e0f1dc188ad1f3db100cba458bcc3dea207e1c853110c6aa6c8`。该哈希覆盖当前共享客户端的玩家/敌方受击与死亡动作、原版血条、左下能量组件、攻击卡框以及费用底图和位图字体；原版特效和完整界面仍未恢复。

`tools/verify_android_apk.py` 的签名、CRC、arm64及16KB ZIP/ELF/GNU_RELRO检查通过。新增 `tools/verify_android_content.py` 核对当前导出源码指纹、视图/场景模板、导出/编译退出码及APK结构证据哈希，逐字节比较全部249个导出数据文件与APK内对应文件，7项检查通过。证据为 `analysis/cocos-android/content-verification.json`；只证明导出与打包一致，不能证明引擎在设备上正确渲染。

运行复核命令：

```powershell
& 'C:/Users/5090B/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -X utf8 tools/verify_android_content.py
```

本轮没有尝试安装或运行APK；此前安装动作的审批拒绝保持不绕过。Android实际运行闭环尚未验收，Windows/macOS/iOS也不能由本次Android构建推定通过。旧 `analysis/tutorial-client/build-verification.json` 属于早期多平台检查，包含旧指纹数量约束与旧Windows产物，不作为本次构建依据。

## 2026-10-14 圆弧手牌、拖牌及原素材箭头版

重新完成Android导出（Creator退出36）及Gradle编译（退出0）。同一调试APK路径现为99,694,360字节，SHA256 `71db37ece26e386cea4b6de126b09ad9b8a1a8cc56952ad2a3d815c609acac78`。包含圆弧手牌、画布级拖动、原素材曲线箭头和从卡牌中心发出的起点修正。

签名、CRC、arm64、16KB ZIP/ELF/GNU_RELRO检查通过；内容验证扩大到箭头模板、effect一致性和编译后加载路径，共9项检查通过，260个导出数据文件与APK逐字节一致。证据仍保存在analysis/cocos-android/{apk-verification,content-verification}.json。此结果证明构建与资源打包，不证明Android设备图形、触摸或连接可用；未尝试安装、运行或绕过此前审批限制。Windows包仍是旧版，macOS/iOS未构建。

## 2026-10-14 选牌序列帧版

当前 APK 为 99,922,841 字节，SHA-256 `385750c40796d5b970ae14ca32180d10130645cae1f6f80e3ced9c590aec4f5c`，路径仍为 `clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`。包含 CardSelectionView、48 张选中框序列帧及源布局/配色 manifest。Creator 导出和 Gradle 编译均成功。

签名、CRC、arm64、16KB ZIP/ELF/GNU_RELRO 检查通过。内容验证新增组件模板一致性、编译后加载路径、源图 SHA、48 个 SpriteFrame 资源入口及实际打包 PNG 哈希，合计 13 项检查通过；405 个导出数据文件与 APK 内容逐字节一致。Android 资源入口文件为 `cc.config.json`，与 Web 的 `config.json` 不同；检查器首次使用 Web 文件名失败，修正平台路径后重新执行通过。

这是打包验证，未安装或运行设备，不证明 Android 图形/触摸/网络闭环。Web 已验证选中、取消与出牌清理；Windows 包仍不含本次光效，macOS/iOS 未构建运行。证据位于 `analysis/cocos-android/apk-verification.json` 和 `content-verification.json`。


## 2026-10-14 连续技能与回合控件动画版

当前调试APK为100,834,010字节，SHA256 `e920e7c96254bf4fb4f6f8b36a741ec576e3bfbbcd4cdd344da8701231b4268e`，路径保持 `clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`。包含连续敌方动作分段、回合显示投影、原EndArea五段动画和两套粒子、选牌光效game.deltaTime计时修复。Creator导出36、Gradle编译0。

签名、CRC、arm64及16KB ZIP/ELF/GNU_RELRO检查通过。内容检查增至23项，545个导出数据文件与APK逐字节一致。新增共享verify_end_turn_content.py核验原时间轴、41张源图、粒子源身份、解压PNG与参数适配、资源入口和实际包内PNG。源模板包括EndTurnView和EnemyTurnPresentation。

未安装或启动设备；设备图形、触摸、网络闭环仍未验收。本次不改变既有运行授权限制。

## 2026-10-14 终局姿势与输入控制同步

重新导出并编译当前共享源码，APK为100,834,380字节，SHA256 `cb3e134d744e30ec0ba7dd5604d415dc0a83ff3a7e5d36a23e79df02a2163e5a`，路径仍为 `clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`。包含原回合入退场期间输入禁用、终局存档恢复death末帧及动作队列完成前推迟终局姿势。

签名、ZIP CRC、arm64及16KB ZIP/ELF/GNU_RELRO静态检查通过，24项内容检查通过，545个导出数据文件与APK逐字节一致。新增检查确认已编译终局恢复和输入就绪标记；这只证明代码已随包导出，不替代设备行为测试。没有安装或运行Android，设备闭环仍未验收。

## 2026-10-14 终局存活角色待机初始化版

调试APK已更新为100,834,436字节，SHA256 `2eadb2d507f495bc0895785f35659b69a0a0c873410b3aa56b50049359d136e5`。包含终局存档重载时存活角色待机姿势采样修复。签名、CRC、arm64、16KB静态检查及内容检查通过，545个资源文件与导出内容一致。未安装或运行设备，Web胜利存档姿势验证不能替代Android运行验收。

## 2026-10-14 首批原声音效版

当前APK为101,367,421字节，SHA256 04f9bdba64870c52fbb6a2435d292ff443489f776fda15b5c49d833f8f216371。包含暴击、二连斩两段及死亡的原音频和生命周期清理。结构/签名/16KB检查及29项内容检查通过，554个导出资源逐字节与APK一致，四段PCM按哈希验证。未安装运行，原生声音效果与设备闭环仍未验收。

## 2026-10-14 原头像血条与死亡状态版

最新APK为101,483,803字节，SHA256 eb899f71d20bf21b70e05c878deba126b4dfb0c33429d2347a3938ed34809343，路径仍为clients/cocos-poc/build/android/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk。包含原VT头像、154×18血条、原背景及重创/消灭状态。新增verify_health_content.py，验证两头像提取文件、九项活跃HUD图像源哈希、资源入口、实际包内PNG字节及当前状态逻辑编译标记。

签名、CRC、arm64及16KB ZIP/ELF/RELRO静态检查通过，36项内容检查通过，575个导出数据文件与APK一致。没有安装或运行设备，不作设备兼容性/触摸/音频/网络闭环声明。

## 2026-10-14 三类语音与退出修复版

最新稳定分发 APK：`runtime/dist/hczs-android-arm64-preview-94d81a98a570.apk`，101,714,821字节，SHA256 `94d81a98a57042286f5e54600a1d78756707069510c1f430a186d6f0da4e480a`。包含三个原战斗语音事件及退出时Set清理修复，保留原四个SFX和原头像血条。41项内容检查、589个导出数据文件一致性、签名/CRC/arm64/ZIP+ELF+RELRO16KB检查通过。未安装或运行；声音、触摸及服务器连接仍需实际设备验收。
# 2026-10-14 牌堆浏览与卡牌详情版

当前分发文件：`runtime/dist/hczs-android-arm64-preview-8a25e28da7a6.apk`，101,933,377 字节，SHA-256 `8a25e28da7a6cd6fc8d27a9773b312014834a116861cdbbe70b0837195d9ec03`。包含原牌堆图集、五列卡牌、角色查看和只读卡牌详情。

真实 Creator 导出与 Gradle 编译成功。签名、ZIP CRC、arm64、ZIP/ELF/RELRO 16 KB 静态检查通过；47 项内容检查通过。新增 `verify_pile_content.py` 对照提取报告核验源 PNG、导出 SpriteFrame 路径、包内字节及当前浏览逻辑编译标记。`package_android_preview.py` 在当前内容验证后生成带哈希前缀的分发副本，旧包保留。

未安装或启动此包，设备触摸、音频与网络闭环未验收。客户端仍需要本地 Node.js 服务，不是内置完整离线服务端。Web 中的点击与画面验证不能替代 Android 验收。

