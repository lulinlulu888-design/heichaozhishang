# 艾尔莎两段原动画 GLB

2026-10-14。已生成 `analysis/elsa-animation/elsa-yangcheng.animated.glb`，6,751,680 字节，SHA-256 `fcb17d9b88dc7ba726dbb7cb1a37fa4879065896cc969874424a5390c679b63b`。固定动画名称为 `stand_idle`、`skin`；供 Cocos 导入的机器清单为同目录 `manifest.json`，包含 `file`、`glbSha`、`clipNames`。

这是恢复的原动画采样与前一阶段基础颜色模型的组合。此次没有打开 UI、运行游戏代码、修改 Cocos TS、改变原 mesh inverse bind matrices 或校正源骨骼姿态。数值检查通过不等于已完成 Cocos 实播验收。

## 输入与身份校验

基础 GLB 为 `analysis/elsa-model/elsa-yangcheng.colour-reference.glb`，SHA-256 `84956d9eeec1285c4de49faa6f0def6453663f288fb40352cf23deec6479a35f`。它含 19,063 顶点、29,240 三角、180 骨骼、9 材质和7张颜色 PNG；颜色范围及未迁移的原 shader 见 `docs/elsa-model-conversion.md`。

输入动画来自 `analysis/animation/recovered/` 的原 wrapper、库、metadata 和 `.poses`。导出前重新解析 RGIS/clip，验证 wrapper SHA、ACL payload 的 FNV-1a、已记录的官方 ACL 1.2.0 sampler 输入 hash 和成功标志；重算 clip ID→library bone name→mesh joint 映射，要求与既有 `bone_mapping` 完全一致；同时校验每个 `.poses` 文件 SHA、帧/骨数、采样率、有限值与单位四元数范围。不是用180条轨道恰好与180根骨骼同序来猜关联。

| 动画 | APK character.npk index | poses SHA-256 | 帧 × 骨 | 原始频率 | 最后一帧 |
|---|---:|---|---|---|---|
| stand_idle | 4504 | 7a53c76d58ac5951a2bd43b9e5f7d83f0c778dd2938d2e4c2ef17377cacbb579 | 121×180 | 30 Hz | 4 秒 |
| skin | 4964 | 8bb87f97ec5a39fe16ed7a69ca08c125b556e37d9571eb1f4cdccf5e28473d0b | 318×180 | 45 Hz | 317/45 秒 |

源 APK SHA-256 为 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`；动画库 SHA-256 为 `2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41`。每个 clip 的逻辑路径、NPK offset、wrapper/ACL hash、sampler executable hash 和180条映射完整保存在 `export-report.json`。

## 导出规则

每段动画为180骨 × translation/rotation/scale 三个通道，共540通道。保留全部原始采样帧，`skin` 没有因为是常量便删减时间轴。关键帧时间是 `frame / sourceRate` 转 float32；最大时间量化误差分别为1.1127e-7秒、2.3313e-7秒。

动画控制的180个节点从 `matrix` 转为 `translation`、`rotation`、`scale`。先检查仿射、非奇异、正行列式和无明显 shear；分离轴长，用正交投影去除源浮点矩阵的微小非正交误差，再转单位四元数。重新构造后最大矩阵分量误差为 **1.8847791928e-7**。这些默认 TRS 对应原 mesh bind，不拿动画第一帧覆盖静态默认姿态。

原始 skin 对象、joint顺序、inverseBindMatrices accessor、网格/材质/纹理/图片结构保持相等，整个基础 GLB 的 BIN 内容逐字节保留，只在末尾增加动画数组。因此原 IBM 和源几何没有被重新生成或悄悄更换。父子层级、坐标轴、单位和三角绕序不变。

非骨骼 mesh node0 从含 `/` 的 `Elsa / ailisha_yangcheng / source bind pose` 改名 `ElsaMesh`，原名保留于该节点 `extras.sourceNodeName`，变更列表保存在 GLB extras 与报告中。180根骨骼名字不变。依据是实际 Cocos 3.8.8 导入后的两段 CCON 均生成182条节点动画，并给该 mesh 生成相同的含 `/` `_path`；原 CCON 名称位置分别为179949和181111，文件 hash/原始 MessagePack 字节见 `node-path-issue.json`。引擎 `cocos/animation/exotic-animation/exotic-animation.ts:963` 将它交给 `TrackPath.toHierarchy`，`target-path.ts:87` 调用 `getChildByPath`，`cocos/scene-graph/node.ts:602` 用 `/` 分隔后逐级查找。因此该原名无法指向实际单个节点。新测试按同样规则验证全部182个导出节点均唯一可寻址；这仅修复引擎寻址兼容性，没有改资源绑定或姿态。

采样姿态的 translation/scale 保留原 float32；rotation 只允许 `q` 与 `−q` 的等价符号选择，让相邻四元数点积非负。当前两段原始轨道已经连续，实际符号翻转数均为0；没有归一化重写采样数据。原四元数范数平方误差≤2.7774e-7，在原采样记录范围内。验证时将其按单位旋转解释，使用双精度累计世界矩阵，避免把单精度噪声误认为位移。

`bip001 r toe0`（mesh joint50）的约3.81174° bind/reference差异仍保留，未做全局或单骨补偿。它影响 cloth 的39个顶点，详见 `analysis/elsa-model/bind-difference.json`。测试明确检查 `skin` 的该骨动画旋转未被换成 mesh bind 旋转。

## 插值与循环边界

所有 glTF sampler 使用 `LINEAR`。平移/缩放为分量线性插值；[glTF 2.0 规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#animation-sampler-interpolation)规定旋转应使用球面线性插值，允许实现进行精度/性能近似。

实际采用的 [ACL v1.2.0 decoder](https://github.com/nfrechette/acl/blob/v1.2.0/includes/acl/algorithm/uniformly_sampled/decoder.h) 的 `SamplingContext::interpolate_rotation` 调用 `quat_lerp`；本地官方源码 `includes/acl/math/quat_32.h:319` 起的实现先修正邻帧符号、线性混合，再归一化。也就是说，**在恢复出的原采样点逐值一致，并不证明所有中间时刻与原 ACL nlerp 位姿完全一致**。本轮未用原 helper 做非采样时刻比较，也没有修改目标引擎插值实现。

`stand_idle` 末帧与首帧并非位姿完全相同：CPU重算的最大顶点差0.00271658源单位，7477个顶点差异>1e-4。未把末帧替换成首帧，未增加循环平滑。新客户端若循环播放，需要在实播中评估该原数据边界；导出本身不设置引擎循环策略。

## 完整回读与 CPU 蒙皮验证

导出后重新读取 GLB，逐条检查全部1080通道：时间严格递增且来自原 rate，translation/scale 与 poses 每个 float32 相同，rotation 与原值相同或整体取反且符号连续，没有重复/缺失目标，没有受动画节点残留 matrix。总计检查21,780 + 57,240 = **79,020个骨骼帧姿态**。

对两段所有439帧，用回读通道构造 local→parent world，再乘原 IBM，对全19,063顶点做四权重 CPU 蒙皮；全部位置有限。报告列出每段完整AABB和首/中/末帧AABB，用于与后续客户端实例缩放前的局部模型坐标比较。

| 动画/帧 | 秒 | AABB min | AABB max | 相对首帧最大位移 | 移动顶点数（>1e-4） |
|---|---:|---|---|---:|---:|
| stand_idle / 0 | 0 | (-2.998073,-0.012675,-2.635749) | (3.460716,15.991621,2.462132) | 0 | 0 |
| stand_idle / 60 | 2 | (-2.994396,-0.012690,-2.639540) | (3.474020,15.991883,2.454137) | .236998 | 18853 |
| stand_idle / 120 | 4 | (-2.997820,-0.013040,-2.635842) | (3.460632,15.991617,2.461705) | .002717 | 7477 |
| skin / 0,158,317 | 0,3.511111,7.044444 | (-5.177701,.013254,-1.895447) | (5.172196,16.177210,2.961140) | 0 | 0 |

`stand_idle` 有136根随时间变化的轨道；所有帧取并集，19063顶点曾移动>1e-4，最大相对首帧位移0.6178334837。所有帧总AABB为 min=(-3.121976,-.013241,-2.686658)、max=(3.476331,15.992100,2.623932)。这证明骨骼驱动了真实网格的数值位移，尚不证明目标引擎中的可见动画效果。`skin` 所有318帧完全相同，保留为常量片段，不能当作另一段动态动作展示。

独立 `tests/test_elsa_animation.py` **9项通过**：标识/BIN不变、所有节点TRS重构、每轨原始姿态/时间一致、输入pose或映射篡改拒绝、符号连续性、非TRS矩阵拒绝、直接使用源pose的另一种四元数矩阵实现重算选定帧AABB/移动数量、动态idle与常量skin及toe差异保留、全部节点的路径可唯一寻址。没有运行 Khronos 全量 validator，也没有做 UI/引擎实播测试。

## 复现与后续核验

```powershell
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools/export_elsa_animation.py
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -p test_elsa_animation.py -v
```

导出脚本生成并验证全部数据后替换最终 GLB，重复运行得到相同 hash。父任务负责按manifest复制到 Cocos，再做导入/构建静态验证。本轮 UI 自动化保持停止；实际播放尚待后续授权范围内核验：确认 `stand_idle` 4秒、180骨，实例坐标/缩放后的首中末帧范围与上表对应，暂停/切换不混用角色身份，再检查右脚趾局部、透明覆盖层和循环边界。材质仍是无光照颜色参考，原动画事件、动作切换、物理和玩法连接均未纳入本GLB。
