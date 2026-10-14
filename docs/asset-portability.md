# APK 资源可移植性：跨平台重建前的有限抽样

调查日期：2026-10-14。目标为本地《黑潮之上》APK。结论基于**解压后的实际字节、结构字段和内容**，不是仅按扩展名判断。

后续进展：本文保留初次抽样时的状态；其中 KTX 像素转换已继续完成，7 个保存样本生成 12 张 PNG，见 [实际贴图转换结果](texture-conversion.md)。一个角色网格也已转换为带蒙皮 GLB，见 [模型转换](model-conversion.md)。下文“尚未解码/恢复”仅描述初次抽样，不代表当前转换进度。

**关键结论：包容器与 Python 数据提取已经解决，但角色模型、骨骼动画、材质效果和大型 UI 图集仍需专门转换。选 Cocos Creator、Unity 或 Godot 都不会自动消除这些 NeoX 格式的转换工作。旧 UI 存在 Cocos 二进制特征，不等于 Cocos Creator 3.x 能直接导入旧项目。**

本次从 12 个资源 NPK 中抽取 283 条目录项：各包取一小段按物理偏移排列的开头记录，加分散位置样本；小包去重。累计检查约 21.1 MB 解压数据，并保存 56 个代表样本。另检查 4 个 WEM、1 个 BNK、3 个 MP4 的真实结构及少量 PNG/字体。未安装转换器、未批量解包全部模型、未运行游戏或播放样本。抽样比例与分布不足以推断每类资源的全量占比。

## 已确认格式及迁移含义

下表的 NPK `index` 是该资源包内部零起始记录序号，`offset` 是未压缩 NPK 内的十进制数据偏移。完整 SHA-256、大小、压缩标志与样本路径保存在 [resource_samples.json](../analysis/assets/portability/resource_samples.json)。

| 资源 | 实际字节/结构证据 | 判断与迁移含义 |
|---|---|---|
| 包容器 | 所有资源包为 `NXPK`；24 字节头，28 字节索引项；样本可用 zlib 或原样读取 | 包装不是主要障碍。已有边界检查提取器，能保留源包/记录/哈希追溯。 |
| 独立压缩纹理 | 39 个样本有完整 `AB 4B 54 58 20 31 31 BB 0D 0A 1A 0A` KTX1 标识；解析尺寸、面数、mip 长度均成功 | 属于可转换的标准压缩纹理载荷。先转为引擎中立的 RGBA/PNG 作为母版，再按四个平台重新压缩，比直接依赖旧 Android 压缩资源更稳妥。尚未真正解码成像素或验证视觉一致性。 |
| UI 图集描述与块 | `packed_png.npk` index 5426 / offset 24 是可由 `plistlib` 解析的 XML plist；index 4625 / offset 4128 是 16,384 字节无 PNG/KTX 头的数据块；index 69 / offset 123818460 是带 `alluires_*` 名字的二进制表 | 属于需要进一步复原的图集/虚拟纹理组织，不能当普通整图 PNG 直接导入。详见下文。 |
| 旧 UI 布局 | `uires.npk` index 410 / offset 24，起始 `14 00 00 00 10 00 1c 00...`，含 `2.1.0.0`、`Node`、`Panel`、`SingleNode`、`Button` 及图片路径 | 是 FlatBuffers 风格表结构、符合旧 Cocos Studio 二进制布局的候选。完整 schema 尚未验证；应重建新引擎 UI 或编写只读转换器，不能视作 Creator prefab/scene。 |
| 角色/模型二进制 | `character.npk` index 4713 / offset 29794092，magic `34 80 c8 bb`，144,222 字节，含 `bip001`、head、calf、finger 等骨骼名；`ui_model.npk` 与 `model.npk` 也有同 magic | 是需逆向的 NeoX 模型相关二进制。当前未恢复顶点、索引、权重、绑定矩阵等字段，不能直接声明已支持 mesh/skinning 转换。抽样没有出现 GLB 或 FBX 标识。 |
| 另一骨骼相关二进制 | `character.npk` index 774 / offset 1080，magic `RGIS`，36,826 字节，含大量 `002_hiar_bone_*` 名字；其它角色样本出现数值头 `82 00 00 00`、`7b 00 00 00`、`3e 00 00 00` | 说明角色资源不是单一标准模型文件；这些格式的骨架/动画语义、字段边界仍未知。不能把找到骨名等同于恢复动画。 |
| 轨迹 | `track.npk` index 116 / offset 24，magic `NTRK`，3,332 字节，含 `Camera001` 与可见浮点时间序列；effects index 15723 同 magic | 可望转换为新引擎关键帧/曲线，但尚未验证通道类型、插值、坐标系、时间单位。 |
| 动画状态配置 | `animator.npk` index 53 / offset 24，XML `<AnimatorTree version="1.0">`，有 `StateMachine`、`clipName="ui_upgrade"`、Trigger/Float 参数；index 5 / offset 4408 是 JSON，含 `airFriction`、`damping`、`bip001` 碰撞配置 | 状态机与物理附属配置可读，适合转换为独立 JSON 规范；实际骨骼动画片段仍需解析。 |
| 材质 | `model.npk` index 1573 / offset 24，XML `<NeoX><MaterialGroup...>`，引用 `shader/surface/basic.surf`、`Tex0/Tex1/Tex2`、`.dds/.tga` 名称、描边参数；角色材料也有 emissive/macro 配置 | 能恢复材质意图与贴图引用；仍需按目标引擎重写 shader、混合、透明、描边与光照语义。XML 中的 `.dds` 名称不能证明对应载荷仍为 DDS。 |
| Shader / 特效 / 场景 | shader 样本有实际 `float4`、`sampler2D`、`register(s0)` 文本及 XML/JSON；effects 有 `<FxGroup...>` XML、NTRK、KTX；scene 有 XML、KTX 及 `c1 83 2a 9e` 二进制头 | 文本、配置可保留用于行为对照；效果和场景绑定是引擎专属，需重建或转换。不能仅复制源文本就假设能在另一引擎渲染。 |
| 音频 | 4 个 WEM 都是 `RIFF ... WAVE`，具有 `fmt ` 与 `data` chunk；`format_tag=65535`、单声道、32 kHz，bits/sample=0；music.bnk 有 `BKHD/DIDX/DATA/HIRC` | 是 Wwise 资源，WEM 样本不是普通 PCM WAV。编解码器尚未独立确认/解码。应单样本验证转为 WAV/Ogg，再恢复事件→音频映射；不能只改后缀。 |
| 视频 | login/op/story 三个 MP4 均按 ISO box 边界解析到 `ftyp/moov/.../stsd`，sample entry 为 `avc1` 与 `mp4a` | 有通用视频容器与编码轨道，可以优先用于重建的登录/剧情原型。各平台播放/必要转码仍需实际构建验证。本次没有解码试听，`mp4a` 内的具体音频 object type 尚未解析。 |
| 常规图片/字体 | `assets/res/icon_share.png` 真实 PNG 签名、IHDR 48×48；`DroidSansFallback.ttf` 具有 TrueType sfnt 与 `cmap/glyf/head/...` 表 | 存在能直接复用的通用资源，但小图标不代表主 UI 纹理已经可用。 |

## KTX：载荷结构完整，但仍需清洗与平台重压缩

39 个 KTX 样本的 `glInternalFormat` 分布为：`0x93B7` 29 个、`0x93B5` 6 个、`0x93B6` 2 个、`0x93B4` 2 个。它们分别对应 RGBA ASTC 8×8、8×5、8×6、6×6；枚举由 [Khronos 官方 ASTC 扩展规范](https://registry.khronos.org/webgl/extensions/WEBGL_compressed_texture_astc/)核对。

例如 `textures.npk` index 9 / offset 24，21,988 字节，是 256×256、9 mip、1 face 的 ASTC 8×8 纹理。按各级宽高、块尺寸、每块 16 字节计算，**39/39 样本的全部 mip 大小一致，且包括 cubemap 面数在内恰好消费完整文件**。逐项结果见 [ktx_validation.json](../analysis/assets/portability/ktx_validation.json)。

一个具体兼容性问题：样本的 `glBaseInternalFormat` 同样写成了压缩格式枚举（如 `0x93B7`），而 [KTX1 官方规范](https://registry.khronos.org/KTX/specs/1.0/ktxspec.v1.html)规定该字段表示基础颜色格式（如 RGB/RGBA）。因此即使载荷长度正确，也不能直接保证严格 KTX 导入器接受这些文件；转换工具应校验/规范化头字段，不覆盖源件。

## UI 图集不是普通“plist + PNG”即可还原

对 `packed_png.npk` index 5426 的 plist 已做实际结构解析：

- `metadata.format=2`，`textureFileName=alluires_14.png`，声明大小 `{2048,2048}`。
- 含 154 个 frame。比如 `activity/lottery_img_hei.png` 的 frame 为 `{{37250,1013},{100,108}}`。
- **154/154 frame 的 X 范围超出 2048，最大 X 范围到 37732**；这不是可直接照普通 2048 图集裁切的坐标。
- 分散抽样出现多个同为 16,384 字节、无容器头的数据块；另有 818,688 字节索引载荷含 `alluires_16` 等名字。

这些是自定义虚拟纹理/分块映射的强线索，但本次没有恢复映射公式或证明块内 codec。需结合已经恢复的 `helper/cocosvt.py` 与原生纹理加载实现，先完整还原一个头像或按钮，再扩大转换。

## 对新客户端框架决策的影响

本次资源证据**不支持**“选择与旧 UI 同名的 Cocos 就可免转换”的假设。它也没有证明 Unity/Godot 能原样导入 NeoX 模型。框架决策应建立在同一组中立资源样本上：模型转为 glTF/GLB 或其它明确的中间格式，图片还原成像素母版，声音转为通用音频，规则/状态配置导出为版本化数据。

- 若主工程选 Cocos Creator + TypeScript，合理的复用对象是新写的规则、契约、工具链以及经转换的资源；旧 Cocos Studio 树和 NeoX Python 字节码都不应被当作现成 Creator 项目。
- Unity 作为 3D 表现候选，也应接受同一个“角色 + 骨架 + 一段动作 + 材质”导出样本做验证，不能因其 3D 工具较成熟就跳过资源格式验证。
- Godot 同理：是否适合需要用已转换的角色/UI/视频及四平台构建样本验证。本报告不重复评估各引擎当前平台支持或商业条款。

## 最小下一步与验收标准

1. **一个角色闭环**：选角色包中一组材质、mesh、骨架、idle 动画与贴图，先建立文件名/hash 映射和字段 schema；导出中立格式，验证姿态、权重、UV、坐标系、动画时长。只成功读出骨名不算完成。
2. **一张 UI 图的闭环**：依据 `cocosvt`/原生加载逻辑恢复上述图集的一个 frame，输出 PNG，并核对透明、裁切、旋转和边缘。
3. **一段音频闭环**：确认 WEM codec，解码一个短样本并匹配 Wwise 事件名；检查播放长度、采样率与是否缺初始化数据。
4. **一个框架原型**：在候选主引擎中展示该角色动作、还原 UI、播放剧情视频，随后做 Windows/macOS/Android/iOS 构建验证。这个原型应先于批量资源转换和引擎专属的大量玩法开发。

以上可作为跨平台客户端的真实技术验收点。包装层可提取、ASTC 载荷可解析、描述数据丰富是积极证据；角色格式和图集映射仍是当前最需要解决的两项未知。

补充证据：[音频 chunk 明细](../analysis/assets/portability/audio_samples.json)、[视频 box/轨道明细](../analysis/assets/portability/video_samples.json)、[资源包全量目录统计](../analysis/assets/npk_catalogue.json)。
