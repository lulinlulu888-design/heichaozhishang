# Android 模拟器验证准备

2026-10-14：准备完成，尚未启动模拟器、安装 APK 或执行界面测试。

## 已完成

- 官方 Android Emulator 37.2.12（build 16428233）已安装到 `D:\Android\Sdk\emulator`。
- `emulator -accel-check` 返回 0，报告 WHPX(10.0.26200) installed and usable；未更改 Windows 功能或重启系统。
- 已安装 `system-images;android-35;default;x86_64` revision 2。
- 独立 AVD `hczs-api35` 位于 `runtime/android/avd/hczs-api35.avd`，使用项目自己的 `ANDROID_AVD_HOME`。`-list-avds` 已确认可发现它。720×1280、240 dpi、2 GB RAM、GPU auto；实际图形兼容性未验证。
- `tools/cocos.ps1 -Action build-android -AndroidVariant emulator` 已完成真实 Creator 导出与 Gradle 编译，退出码 0；独立输出到 `clients/cocos-poc/build/android-emulator`，保留原 arm64 包。
- 最新模拟器 APK（含立绘等比缩放修正）：81,890,375 字节，SHA-256 `a9d2bdb7cf4cc4d24698729373dfa55e4a8dda3e70144f15105ebb5c0513f85c`。签名、ZIP CRC、ZIP/ELF/RELRO 16 KB 对齐通过。它是重建客户端调试包，不是原 APK 重签名。
- 艾尔莎和幻眼魔方的 Cocos 导入及导出动画采样检查均通过；并未证明实际播放画面。
- 原 arm64 包重新验证通过，现有首战构建检查 28 项通过。

证据分别位于 `analysis/android-runtime`、`analysis/cocos-android-emulator` 和 `analysis/tutorial-client/build-verification.json`。

## 后续运行步骤（尚未执行）

此前用户曾用 Escape 停止界面自动化，须确认恢复界面测试后再启动、安装和操作。不要以无窗口模拟器或 ADB 输入绕过该停止。

启动终端需设置项目 AVD 目录：

```powershell
$env:ANDROID_AVD_HOME = 'D:\hczs\runtime\android\avd'
& D:\Android\Sdk\emulator\emulator.exe -avd hczs-api35
```

等待系统启动后，先用 `adb devices -l` 确认具体设备序列号，再以 `adb -s <序列号>` 安装 `clients/cocos-poc/build/android-emulator/proj/build/hczs-cocos-poc/outputs/apk/debug/hczs-cocos-poc-debug.apk`，避免操作其他设备。

原生客户端当前使用设备自身 `127.0.0.1:7457`。战斗预览服务需先在主机 7458 健康运行，然后为这个设备设置 `reverse tcp:7457 tcp:7458`。目前 PM2 连接 Windows 管道 `rpc.sock` 报 EPERM，7458 尚未启动；这里未绕过该故障另开服务。

验收必须包含实际画面、触摸出牌、胜负结算、关闭重开及存档恢复；构建检查不能替代这些结果。
