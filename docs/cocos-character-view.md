# 艾尔莎角色动画接入 Cocos

目标是验证恢复出的网格、骨骼、颜色纹理和原动画可以进入同一套跨平台客户端工程。本轮增加了资源转换、模型预览代码及构建验证；未进行新的界面操作，不能将编译或静态数据一致性视为画面与动画播放验收。

## 资源与转换

`tools/export_elsa_animation.py` 将两份原 ACL 采样结果写入 glTF 动画：`stand_idle` 为 121 帧、30 Hz、4 秒；`skin` 为 318 帧、45 Hz、317/45 秒，后者源采样本身没有变化。180 根骨骼每根都有平移、旋转、缩放轨道，每片段 540 通道。

产物 `analysis/elsa-animation/elsa-yangcheng.animated.glb` 为 6,751,680 字节，SHA-256 `fcb17d9b88dc7ba726dbb7cb1a37fa4879065896cc969874424a5390c679b63b`。基础网格仍为 19,063 顶点、29,240 三角形、9 材质和 7 张嵌入颜色 PNG。原始网格、逆绑定矩阵和纹理二进制保持不变，原矩阵转 TRS 的最大重建误差约 `1.885e-7`。

导入过程中发现 mesh 节点原名 `Elsa / ailisha_yangcheng / source bind pose` 含路径分隔符。Cocos 的动画绑定经过 `TrackPath.toHierarchy` → `getChildByPath`，后者按 `/` 拆分；实际导入的两片段 CCON 同样包含这个无法定位的路径。导出器将此节点改为 `ElsaMesh`，原名写入 `extras.sourceNodeName`。骨骼名字、层级和采样不变，182 个节点路径唯一可解析。证据在 `analysis/elsa-animation/node-path-issue.json`，不是通过忽略失败轨道规避问题。

四元数仅做等价符号连续化。glTF 使用 LINEAR 插值，在源采样时刻逐项比对，不声称任意帧间插值与原 ACL 运行时完全相同。右脚趾参考姿态与网格绑定姿态的局部差异仍保留；待机首尾并不完全一致，也没有人为补平。

## 客户端代码

`assets/RecoveredCharacterView.ts` 在场景中建立独立 3D 节点与正交相机，将 RenderTexture 显示到图鉴左侧。仅在选择艾尔莎并按“模型”时加载。切换“立绘”、角色或场景时隐藏/暂停，提供“暂停动作”“继续动作”和每次 45° 的“转向”。选择和保存档案仍由原图鉴流程控制。

预览只播放已恢复的 `stand_idle`；循环是预览设置，不是已恢复的原游戏状态机。使用实时 SkeletalAnimation、原轨道和 unlit 颜色参考材质，尚未恢复原游戏 toon、阴影、特效或完整动作切换。相机可见层与主 UI 相机分离。实例根节点不在 182 个动画路径内，因此预览旋转不会被动作轨道覆盖。

模型放在 `resources/recovered/models/elsa/elsa.glb`。Cocos 会生成 prefab 子资源，不能直接把 glTF 主资源作为 Prefab 加载；代码按目录与类型查找唯一 prefab，再加载该路径。异步完成时检查视图是否销毁或被隐藏，场景销毁时释放预览引用及渲染目标。

已启用 `3d` 和 `skeletal-animation` 模块。可复现源码模板位于 `tools/templates/cocos-recovered-character-view.ts` 与 `cocos-toolchain-proof.ts`，现有工程和模板同步维护。

## 验证与构建

转换器 9 项测试覆盖采样、骨骼映射、源数据保留与全部节点路径；另有 CPU 蒙皮逐帧位移检查。Creator 的 TypeScript 检查通过。Cocos 实际导入会生成 180 joints、2 个 animation 子资源、9 个材质以及 prefab；生成并不自动证明播放正确。

`tools/verify_cocos_character.mjs` 使用安装包内可信 MessagePack 解码器读取实际 CCON 数据，不启动引擎或执行原游戏代码。已将导入结果与原 poses 的 **79,020 个骨骼帧**逐项比较：时间、平移、缩放最大误差为 0，四元数在等价符号比较下的最大分量误差为 `1.1920928955078125e-7`。每片段 182 个路径全部可定位，180 个骨骼完整映射；材质均引用 builtin-unlit，7 条纹理→图像引用链完整。`skin` 的 Cocos sample 属性虽然为导入默认 30，实际仍保留全部 318 个 45 Hz 时间键，并未重采样为 30 Hz。

Web、Android 与 Windows `model` 构建的两段动画二进制和已审计 library 逐字节哈希相同；各 resources config 中模型 Prefab 路径唯一，为 `recovered/models/elsa/elsa/elsa`。三份报告各有 17 项检查通过，分别为 `analysis/cocos-character/import-verification.json`、`import-verification-android.json` 和 `import-verification-windows.json`。审计没有独立反序列化构建中合包后的 Prefab/材质 JSON，仅记录这些 pack 哈希，不把动画一致性扩大为所有构建资产均已独立验证。

模型接入当轮 Web 导出退出 36；Windows `model` 变体导出与编译均退出 36，EXE SHA-256 为 `b1b01998cdc14357c1a3105e1db77fd643c85a696d40690c08e7465c3c890afa`，没有启动新窗口。当轮Android APK 78,043,121 字节，SHA-256 为 `5fb7652cff5c5b0832493884ee5575a4f454070864204b26d3a23c286323b4a6`。后续首战界面构建已重新验证这些动画数据和APK结构，最新产物见[首战客户端接入](tutorial-client-build.md)。构建成功不代表动画实际播放正确。

复现顺序：

```powershell
# 先按 animation-recovery.md 恢复原始采样。
python tools/export_elsa_animation.py
python tools/prepare_cocos_assets.py
node .tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/tsc.js --project clients/cocos-poc/tsconfig.json --noEmit --skipLibCheck
# 以下构建操作依次执行，避免同一工程被多个 Creator 实例同时修改。
pwsh -NoProfile -File tools/cocos.ps1 build-web
pwsh -NoProfile -File tools/cocos.ps1 build-windows -WindowsVariant model
pwsh -NoProfile -File tools/cocos.ps1 build-android
# 导入和选定构建的静态数据审计：
node tools/verify_cocos_character.mjs
node tools/verify_cocos_character.mjs --config clients/cocos-poc/build/android/data/assets/resources/cc.config.json --output analysis/cocos-character/import-verification-android.json
node tools/verify_cocos_character.mjs --config clients/cocos-poc/build/windows-model/data/assets/resources/cc.config.json --output analysis/cocos-character/import-verification-windows.json
```

Windows `model` 变体输出到 `build/windows-model`，证据在 `analysis/cocos-native-model/`；它可以在不覆盖已运行旧 EXE 的情况下构建。每个平台导出前记录 TS、场景、GLB、引擎模块配置、来源清单和构建配置的 SHA-256。Windows 分发需要整个产物目录，不能只复制 EXE。

待验收：模型朝向与取景、RenderTexture 在各后端的显示、待机动作、暂停/继续/切换、纹理与透明度，以及四个平台上的实际运行。Android 尚无设备；macOS/iOS 尚无 Mac/Xcode 环境。现有 Windows 2D 图鉴的运行记录不能替代本次 3D 预览验收。

依据：[Cocos 动态加载与子资源](https://docs.cocos.com/creator/3.8/manual/zh/asset/dynamic-load-resources.html)、[RenderTexture](https://docs.cocos.com/creator/3.8/manual/zh/asset/render-texture.html)、[glTF 导入](https://docs.cocos.com/creator/3.8/manual/en/asset/model/glTF.html)。
