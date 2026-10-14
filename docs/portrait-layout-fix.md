# 立绘比例修正

2026-10-14：用户截图中立绘明显横向拉伸。代码此前将所有已裁剪 SpriteFrame 强制显示为 558×462，未保持帧的宽高比。

`ToolchainProof.ts` 和生成模板现显式启用 `trim`，使用 `frame.rect` 的宽高，以 `min(558/width, 462/height)` 等比缩放，保留原居中位置。仅改变立绘布局，不改图片或 3D 模型表面。

Web 已重新导出成功（Creator 退出36），7456 HTTP 返回200。工程源码严格 TypeScript 检查通过（skipLibCheck 跳过 Creator 自带声明）；未跳过库检查的首次尝试因引擎声明缺少 WebGPU/编辑器类型等报错，不算通过。没有执行浏览器界面自动化，真实画面尚待确认。

随后已重建 Windows model、Android arm64 和 Android x86_64 模拟器包，全部编译成功。两种 APK 签名、CRC、ZIP/ELF/RELRO 16 KB 对齐通过；四份构建的角色与敌人资源静态审计通过，首战构建总检查28项通过。没有安装或启动这些原生客户端。

最新 arm64 APK 为 78,771,876 字节，SHA-256 `1e3d60c84a60cd334b5c322dea4466dc2b57f5e7929e214bdd1d0ae89b0cfa5e`；x86_64 APK 为 81,890,375 字节，SHA-256 `a9d2bdb7cf4cc4d24698729373dfa55e4a8dda3e70144f15105ebb5c0513f85c`。详细报告分别位于 `analysis/cocos-android/apk-verification.json` 和 `analysis/cocos-android-emulator/apk-verification.json`。

macOS/iOS 仅更新源码预检，仍未导出、编译或运行。真实画面、输入及战斗闭环继续保持未验收。
