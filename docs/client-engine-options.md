# 跨平台客户端引擎候选

用户已确认从一开始重建 Windows、macOS、Android、iOS 客户端，并支持重新打包与增加玩法。以下为 2026-10-14 的选型建议；Cocos Creator 3.8.8 已安装到工作区用于真实原型验证，尚未完成最终选型验收。

## 初步建议

优先验证 **Cocos Creator 3.x + TypeScript 客户端 / Node.js 服务端**。这是基于项目需要统一玩法、配置和协议契约的工程判断；并不表示现有 NeoX APK 能直接导入 Creator。

已取得的工程证据：官方 Creator 3.8.8 完成实际 Web 构建，浏览器中的中文场景和点击计数运行通过；Windows x64 EXE 已用 VS 2022 编译并实际启动，中文、透明立绘及点击 0→1 通过。Android arm64 调试 APK 已真实编译，签名、ZIP CRC、ZIP/ELF 16 KB 对齐通过；没有设备，尚未验证运行。艾尔莎 180 骨骼颜色参考 GLB 已加入两段原始采样动画，模型预览代码与资源已进入最新 Android 构建（约 78 MB）。动画实播和原游戏材质效果仍待验证。原始 APK 的 NeoX 文件需先经过自编转换器，不能直接导入。macOS/iOS 构建尚未验证。环境与复现记录见 [Cocos 工具链](cocos-toolchain.md)、[Android 构建](android-build.md)和[角色动画接入](cocos-character-view.md)。

在无引擎依赖的共享包中定义卡牌、Buff、关卡配置、战斗规则和数据契约；客户端负责画面、动画与输入，Node.js 负责会话、进度和结算。仅共享不使用 Node/Cocos 专属 API 的模块。现有 `@hczs/game-protocol` 使用 Node Buffer 和文件加载，不能原样视为移动端通用库；跨端需要独立构建/适配。

`@hczs/battle-core` 已将一部分有证据的数值公式做成无运行依赖 ESM，数值与牌堆合计81项 Node 测试通过。完整标量公式要求 BigInt，实际 Cocos 四端数值对照仍待执行；当前首战由 Node.js 结算，客户端接收状态并负责交互与表现，没有因为同用 JavaScript 就宣称四端计算已经一致。

| 候选 | 主语言 | 四平台发布 | 本项目取舍（工程判断） |
| --- | --- | --- | --- |
| Cocos Creator | TypeScript | 官方支持 Windows/macOS/Android/iOS | 便于与 Node.js 统一纯逻辑、数据和契约；需验证角色渲染、骨骼动画及材质效果 |
| Unity | C# | 官方支持四平台 | 适合侧重复杂 3D 动画、材质与编辑工具的路线；与 Node 分别实现表现/逻辑边界，原 NeoX 资源同样需要转换 |
| Godot | GDScript / C# | 官方列出四平台导出 | 可作为自主维护的替代引擎；若采用 C#，应另查移动端该版本支持边界，不把所有脚本语言的导出能力混为一谈 |

## 先验证的最小样本

1. 从原包转换一名角色：网格、骨架、贴图和一段动画。
2. 重建一屏卡牌 UI，验证字体、图集、触控和窗口缩放。
3. 加载同一份卡牌/Buff 数据，完成一次固定输入的战斗规则与表现对照。
4. 产出桌面与移动端构建样本，再根据原画面接近程度、开发成本和四平台构建情况锁定引擎。

初步资源抽样显示：贴图有 KTX1，UI 有旧二进制布局结构，模型/骨架/轨迹为 NeoX 自定义格式。没有证据表明这些模型能被任一候选引擎直接完整导入。资源转换是独立管线，应保留原始数据和转换证据，避免绑定单一引擎。

## 构建环境

Cocos 官方文档规定 Windows、macOS、iOS 原生发布依赖对应宿主环境。Windows 使用 C++ 构建工具，Android 使用 Android SDK/NDK，macOS/iOS 使用 Mac 和 Xcode。四平台共用源码不等于当前 Windows 电脑能够独自完成四个平台的正式构建与运行验证。

| 目标平台 | 构建工具与交付 | 当前工程验证 |
| --- | --- | --- |
| Windows | Windows + Visual Studio C++；EXE 连同引擎 DLL 和资源 | 已实际编译、运行和点击验证 |
| Android | SDK/NDK + Gradle；签名 APK/AAB | arm64 调试 APK 已构建及静态校验；未安装/运行，AAB 未验证 |
| macOS | Mac + Xcode；`.app` 及分发签名 | 尚缺 Mac 构建机 |
| iOS | Mac + Xcode；工程编译及对应签名的设备包 | 尚缺 Mac 构建机与运行验证环境 |

现已补齐macOS/iOS配置、模板和仅在Mac允许导出的脚本，详见[Apple构建准备](apple-build-preparation.md)。Windows上的配置与宿主保护检查通过，尚未执行Apple实际构建。

后续新增卡牌、关卡和玩法时，维护共享数据、规则模块与客户端表现代码，再使用各平台构建配置重新打包。Node.js 服务端独立运行和发布，不把引擎的四端客户端支持等同于移动端可直接运行完整 Node.js 进程。

Node.js 服务端与客户端打包分开管理。移动端客户端可连接用户运行的 Node.js 服务；“将 Node.js 直接内嵌 iOS 客户端”不是当前默认方案。若后续明确要求手机完全脱离服务端单机运行，需要增加本地规则执行和存档适配的验收。

## 官方依据

- [Cocos 原生平台发布](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/native-options)
- [Cocos 多平台与构建扩展](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/index.html)
- [Cocos FBX/glTF 模型资源](https://docs.cocos.com/creator/3.8/manual/en/asset/model/mesh.html)
- [Unity 6 平台要求](https://docs.unity.com/en-us/engine/6000.0/manual/get-started/install-and-upgrade/getting-started-installing-unity/system-requirements)
- [Godot 四平台导出入口](https://docs.godotengine.org/en/stable/tutorials/export/index.html)
- [Godot iOS 与 Xcode 要求](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_ios.html)
