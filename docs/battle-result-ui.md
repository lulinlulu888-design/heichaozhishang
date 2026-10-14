# 战斗胜利界面恢复

2026-10-14。本轮为自编解析工具的静态证据与重建客户端 Web 运行证据，不能当作原 APK 实机运行证明。

## 实际注册链

- `PhaseFight.py`（脚本 4686）定义 `PhaseWin.clsName = PhaseName.BattleWin`。
- `PhaseConst.py`（9661）模块偏移 `0x2a9–0x2c4` 将 `BattleWin` 注册为 `ResultDialog`，保留 Fight 所属阶段。
- `UIConst.py`（6870）偏移 `0x28a4–0x28b9` 将 `ResultDialog` 注册到 `ui.ui_result.NewResultPanel.ResultDialog`。
- `NewResultPanel.py`（999）从 `uires_EventSynopsisDialog_SingleEventDialog` 和 `uires_EventSynopsisDialog_SingelResultArea` 导入布局。`ResultArea.playInAnim`（常量路径 24,2）实际请求 `in` 动画；`ResultDialog.onFirstUpdate`（26,6）读取结果数据、播放结算音效、调用 ResultArea，并按 boss 条件选择胜利语音。

因此 EventSynopsisDialog 的命名不能作为排除战斗结算用途的依据。3689 BattleSuccessPanel 为空模块；4055/5918 旧 Settlement 布局未用于当前接入。

## 可复现产物

依次运行 `tools/trace_battle_result_ui.py`、`tools/recover_result_ui_sprites.py`、`tools/stage_result_ui.py`。

`analysis/battle-ui/result/` 保存八个模块导出、四份 CSB、布局、胜利时间轴及图集裁切报告。提取校验原 APK SHA-256，模块解析校验 decoded marshal SHA-256；暂存再次校验布局报告与 PNG 哈希。资源写入 `clients/cocos-poc/assets/resources/recovered/result-ui/`，附 provenance.json。

原 SingelResultArea 的 `in` 区间为 5–75，`out` 为 90–110。已提取时间轴，但本轮仅显示 Panel_1 三层标题的入场完成姿态：PERFECT、黑色底字、行动胜利。保留源尺寸、透明边距和相对坐标。未播放完整时间轴，不宣称恢复粒子、混合方式、父层运动或原版结算镜头。MISSION AWARD 标签未显示，因为当前服务不发放奖励。

后续更新：三层标题与祖先节点的 8 条时间轴现已接入 `VictoryTitleView`。保留源 `speed=0.5`、入场区间 5–75、透明度与缩放关键帧；在入场末帧停留。时钟采用已有原生离线分析得到的 float32 帧间隔，缓动采用标准 cocos2d-x 枚举解释；原 APK 分支及加载器的时间行为尚未运行对照。`out` 轨道已暂存但没有调用，线条、辉光与粒子图层仍未恢复。上述静态末帧方案保留为资源加载失败时的回退。

## 接入与验证

胜利字样由服务端战斗快照的 `won` 状态触发，并等待当前攻击表现完成。收起手牌、战斗日志与敌方意图；失败不使用胜利字样，读档和重开仍沿原控制器操作。客户端模板与实际源码同步。

Web 实际操作：从第二回合敌人 1806 生命、4 能量的存档开始，拖出疾驰斩击造成 1447 伤害，敌人剩 359；再拖出斩击，触发胜利。胜利字样、倒地模型和手牌收起均已观察。严格 TypeScript 检查与 Creator Web 构建通过；浏览器未报告警告或错误。

本轮没有构建新 Windows/Android 分发包，macOS/iOS 仍未构建验收。奖励、完整原结算动画与原 APK 运行对照仍未恢复。

后续原生分发更新：标题动画现已实际编入 Android arm64 `9a3a6276bd74`、Android x86_64 `a79df57e1354` 和 Windows x64 `63d86fe2147e` 预览包，位于 `runtime/dist/`。`verify_result_content.py` 复核原 CSB 哈希、选定层级、时间轴、时钟证据、标题 PNG、资源路径、实际编译代码，以及导出 JsonAsset 内嵌对象与当前 manifest 的完整相等性。Android 两包各 58 项内容检查通过；Windows 全部 643 个导出资源和 ZIP CRC/文件哈希通过。Windows ZIP SHA-256 为 `365c552fa899b750da18ec74c71b9bedfbefe22a414ac145b42dbac761cea75d`。这些新包未完成原生运行验收，Apple 平台仍未构建。

最终构建刷新页面后重新进入首战，仍显示第二回合胜利、玩家 1466.8 生命和敌人消灭状态。存档提示已移到下方，避免与倒地模型重叠；截图为 `analysis/battle-ui/result/victory-live.png`。这是 Web 页面重载后的恢复验证，不代表服务进程重启或原生客户端验收。

动画更新验证：严格 TypeScript 与 Creator Web 构建通过。`node tools/test_victory_title.mjs` 使用实际 Creator 输出模块和模拟 cc 环境，通过 8 项检查：初始隐藏/1.5 倍缩放、插值、重复状态不重播、末帧、退出重入重置、无效时间增量、资源/回调释放、异步加载不重新打开隐藏界面。报告 `analysis/battle-ui/result/title-animation-tests.json` 记录构建哈希；该测试不验证实际渲染。浏览器重新进入胜利存档，起始与最终画面分别保存在 `animation-entry-live.png`、`animation-final-live.png`；控制台无警告/错误。这两张截图不证明原版逐帧一致性。
