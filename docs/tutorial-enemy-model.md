# 首战敌人 991「幻眼魔方」：带蒙皮颜色参考 GLB

2026-10-14。已导出 `analysis/tutorial-enemy/tutorial-enemy-991.colour-reference.glb`，659,652 字节，SHA-256 `c39eaba279687e3dd1f3c786d627a6738d6aa6138990ffba20bc4990a79095f5`。包含原始 4,208 顶点、6,246 三角形、1 子网格、61 根骨骼及 Tex0 颜色。这里的“颜色参考”是无光照 albedo：**没有渲染原材质的紫色发光、光照或描边，也没有包含动画**。

本轮只读 APK 和已恢复数据，在本地进行有限静态提取、ASTC 解码和数值验证；没有执行游戏代码、启动服务/UI 或改动客户端、共享解析器、艾尔莎转换脚本。原生/JADX provider 的既有不可用情况没有变化，本轮没有重复初始化。

## 复现与产物

```powershell
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 tools/export_tutorial_enemy.py
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -X utf8 -m unittest discover -s tests -p test_tutorial_enemy.py -v
```

导出先流式校验 APK SHA-256 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`，再按已验证路径哈希唯一匹配 NPK 条目，校验四个模型输入 SHA。逐条提取使用既有有界 NPK 解压器，不批量解包。

- `export-report.json`：身份表、资源 provenance、着色器代码行、四张贴图用途、材质绑定、61 骨逐项交叉校验、GLB 回读/CPU 蒙皮结果与限制；`glbSha` 和 `glb_sha256` 均为上述输出 hash。
- `bone-map.json`：mesh joint、glTF node、骨名、父级、原 global bind、导出 local bind、原 28 字节 auxiliary 未解释值。
- `source/`：GIM/MESH/MTG/GISACL 原始载荷；完整扩展名 `.provenance.json` 保留独立来源。
- `shader-evidence/`：有限提取的原 shader，以及 member/index/offset/hash。
- `textures/`：四张原 KTX，完整结构检查；仅 Tex0 解码嵌入 GLB。
- `colour-png/manifest.json`：ASTC inspector/decoder hash，10 个 mip 的逐块验证和解码图片/RGBA hash。
- `gltf.json`：GLB JSON 镜像。

REA 的已有 Evidence `ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3`（`analysis/rea/initial-artifact-evidence.json`）证明该 APK 根 manifest/ZIP inventory；链接根清单 Evidence `ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220`。**本轮 GLB、像素、矩阵与报告是普通本地转换证据，不冒充新留存的 REA Evidence，也不将 ZIP inventory 当成材质/绑定语义证据。**

## 身份与资源绑定

使用 [首战恢复记录](first-encounter-recovery.md) 的静态表显式外键：

| 模块 index / 表 | 行与字段 | 对应值 |
|---|---|---|
| 2363 monster_table | 991：NAME / ENTITY_ID | 幻眼魔方 / 6605 |
| 1955 entity_table | 6605：LOD_ID / SCALE | 6605 / `[0.7,0.7,0.7]` |
| 1268 model_lod_table | 6605：LOD_MODEL_LIST | `[66051,66052]` |
| 6328 lod_index_table | 66051：LEVEL / MODEL_PATH | 0 / `character/monster/yuanjieguai_yijiemofang/yuanjieguai_yijiemofang_purple.gim` |

工具检查上述字段，并将表导出 SHA、原 script.npk 的 index/offset/payload hash、解密 marshal hash、逐字段字节码位置放入报告；原 marshal 文件再次核对 SHA。身份来自表引用，不靠外观、ID 大小或减固定编号。

以下均在 `assets/res/character.npk`：

| 资源 | index | NPK offset | 解压字节 | SHA-256 |
|---|---:|---:|---:|---|
| purple.gim | 6648 | 19843824 | 11893 | `99c37714e0912f7cd6bef546e7e7774860155bebf5853bd3953ce7137b58dcb6` |
| yuanjieguai_yijiemofang.mesh | 1902 | 20526264 | 314503 | `21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa` |
| purple.mtg | 6425 | 19055276 | 1531 | `281066fafcf1df444f2b22650e0cc68b1c5a244730e0430fdceb4495aa4b7136` |
| yuanjieguai_yijiemofang.gisacl | 6081 | 19194576 | 13278 | `cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0` |

表内 `purple.gim/.mtg` 均简写完整文件名 `yuanjieguai_yijiemofang_purple`；完整路径在报告。GIM 的 `Mesh` 属性和 `GisFiles` 明确引用 mesh/GISACL。GIM→MTG 使用已恢复的原生 loader 扩展名替换规则：Thumb `0xc212f4–0xc212fe`，`.mtg` 字符串 `0x249e5b1`，调用 `0x10daec6`；见 `analysis/resource-mapping/mesh-loader.thumb.txt` 和 `replace-extension.thumb.txt`。因此不是仅凭同名猜测 companion 文件。

GIM `Sub0 Name=yuanjieguai_yijiemofang, MtlIdx=0` 指向 MTG `Material_0 / initialShadingGroup`。源几何 AABB 与独立 GIM `BoundingCenter±BoundingHalf` 最大端点误差 `4.4068908691e-5`，在六位小数边界容差 `1e-4` 内。只保留源单位与坐标，entity 的 0.7 缩放留在 metadata，未烘焙进顶点或骨架。

## 实际 Tex 语义与颜色范围

MTG 明确指定 `Surface=shader/surface/emission.surf, VertexFragmentModel=DefaultVF, LightingModel=Isotropy`，不是根据 `_d/_n/_m` 文件名判断用途。

| shader.npk index / 文件 | 实际代码证据 |
|---|---|
| 2440 emission.surf | 4：Code 指向 material_emission.hlsl；13：BaseColor 默认 1,1,1,1 |
| 988 material_emission.hlsl | 27：Tex0 在 `frag.uv.xy` 采样；36/38：RGB→albedo×BaseColor（publish/editor 两分支）；44：A→opacity；49/54/64：Tex2 G/B/R→roughness/metalness/occlusion |
| 3498 material_setup_func.hlsl | 9：包含 exttechnique；79–98：default normal 由 Tex1.xyz 解码；171/173：调用 normal/emission |
| 3903 exttechnique.hlsl | 119–129：EXT_EMISSIVE+EMISSIVE_TEXTURE 时 UV0 采样 Tex6，`srgb2linearf3(tex6.rgb) * EmissiveColor.rgb * EmissiveParams.g` |
| 1241 compositor 配置（原逻辑名未确定） | 4：DefaultVF→model_default.hlsl；Sampler 表定义 Wrap |
| 3343 model_default.hlsl / 2554 default_vertex_struct.hlsl | 引入默认顶点与传递函数；texcoord0:TEXCOORD0 |
| 2889 default_functions.hlsl | 79：`vert.uv.xy=input.texcoord0`；216：`frag.uv=vert.uv` |
| 1035 material_common.hlsl | 20–27：普通采样使用 Wrap 变体 |

每条精确匹配代码片段和实际行号由 `shader_semantics.checked_source_lines` 生成，文件原始 hash/index/offset 同时保留。预处理宏的完整运行配置没有被执行或复现；GLB 按源 sRGB 格式提供颜色参考，不声称重建发布版所有 shading 分支。

四项 MTG `.dds` 引用的同路径 `.ktx` 均唯一命中；实际 magic/header 确认为 KTX1 ASTC 8×8、512×512、10 mip。这里的后缀只是路径定址，格式和颜色空间取自真实载荷：

| 槽 / 纹理 | character.npk index | KTX profile | 本次用途 |
|---|---:|---|---|
| Tex0 mofang_d | 3987 | sRGB | 原 albedo，解码并嵌入 baseColorTexture / TEXCOORD_0 |
| Tex1 mofang_n | 1656 | linear | 原法线数据；只保留证据，不接 baseColor |
| Tex2 mofang_m | 1304 | linear | 混合遮蔽/粗糙/金属通道；不接 baseColor |
| Tex6 mofang_e | 6639 | linear | 原发光数据；本轮不渲染，不接 baseColor |

Tex0 SHA `f951902943a9c1684ffc7578bf091a739bea2e81f0fe96e7809f709fb6a20a8e`。10 mip 共 5,464 个 ASTC 块逐块通过既有 ARM inspector：0 HDR、0 error，之后 `astcenc -ds` 仅解码 mip0；输出 PNG 保留行序。Tex0 每个像素 alpha=255，BaseColor 的 surface 默认 alpha=1，故颜色参考用 OPAQUE。使用 `KHR_materials_unlit` 和白色 factor；REPEAT 采样，原 UV0 不翻转，不凭外观调亮或染紫。双面为参考导出策略，原 `CullMode=2`、`TransparentMode=1` 原值保留但未完整映射枚举。

紫色来源有明确证据：MTG 开启 `EXT_EMISSIVE=TRUE`、`EMISSIVE_TEXTURE=TRUE`，`EmissiveColor=(1,0.109804,0.929412,1)`，`EmissiveParams=(0,3,1,0)`。由于普通 unlit baseColor 并不包含这段发光公式，**当前 GLB 外观没有该紫色发光效果**。后续可以据已保留 Tex6 与 shader 做独立发光端口，而不能把 Tex0 染紫称作还原。

## 绑定验证与辅助包围盒差异

共享 `inspect_neox_model.parse_model` 完整覆盖 314,503 / 314,503 字节，验证索引范围、61 骨父级无环、矩阵 finite/非奇异、权重范围和 used-bone bitset。只有一组二维 UV0；没有伪造 UV1。源权重和误差最大 `2.9802322388e-8`，导出归一化后写 float32，零权重占位 joint 255 仅替换为有效 joint 0。

直接调用原 `validate_bind_pose` 会失败，bone0 辅助 AABB 误差 `2.38940334337224`，其第 7 float 与半尺寸对角线的差 `0.15090181704884786`。bone0 原 7 float 为 `(1.5630896091461182,0,0,1.5630896091461182,0.5,0.5,1.5646882057189941)`。这不能当作艾尔莎那种“受影响顶点精确局部 AABB”；目前不解释它的其他用途，也不修改这些值或放宽原门禁。

采用另一项独立数据验证：GISACL 原库 61 个骨名与 mesh 集合完全一一对应，原库每骨 local TRS 按名字匹配、通过 mesh 父级递归累积，与 mesh 原 global bind 逐骨比较。global 最大误差 `2.2485287489715233e-6`；直接与 `inverse(parent raw global) * child raw global` 比较 local 的最大误差 `8.908938533558342e-7`。所有 61 行明细保存在 `bind_validation.rows`；名称查找而非假设 ordinal，测试也验证同步打乱库名/姿态顺序仍得到相同映射。

该任务专属 exporter 先复用共享 `encode_glb(skin=False)` 的几何写入，再以独立 reference-pose 门禁附加骨架、原 raw global 矩阵的逆 IBM 和原权重；没有修改或 monkey-patch 共享 skin 检查。源矩阵原值保留，不用 GISACL 姿态替换它。

GLB 回读后的验证：

| 检查 | 结果 |
|---|---|
| 原位置/法线/全部 UV0/三角索引 | 逐项完全一致 |
| 导出 IBM 对源 global inverse 的 float32 值 | 逐项完全一致 |
| glTF 层级重建 global 对源 global | 最大误差 `2.6645352591e-15` |
| global×IBM 与 IBM×global 对单位矩阵 | 最大误差 `5.3961283442e-7` |
| 全 4,208 顶点 CPU 绑定蒙皮对源位置 | 最大误差 `7.6194303134e-7`，全部 finite |
| AABB | 原及 CPU 结果均在报告逐轴保留 |

这是数值静态绑定验证，不是动画播放或视觉验收。另一个代理独立从 GISACL 比较同一 local/global 关系，结果在 `analysis/tutorial-enemy-animation/reference-bind-comparison.json`，local 最大误差同为 `8.908938533558342e-7`。

## 稳定节点契约、测试和下一步

节点 0 为 `TutorialEnemy991Mesh`；mesh joint 0..60 对应 glTF node 1..61，按原骨名和父级；节点 62 为 identity `TutorialEnemy991Skeleton`，挂载原骨架根。所有名字不含 `/` 或 `\`，避免 Cocos 动画路径寻址歧义。`bone-map.json` 提供完整索引对照；当前骨节点以 matrix 保存静态 local bind。若追加动画，受控骨节点应改为 TRS，并保持原 IBM；clip bone ID 必须经库名映射到 mesh bone，不能把 clip ordinal 当节点号。

本轮 10/10 测试通过，覆盖真实数据回读、逐骨 reference 验证、原 aux 不篡改、库顺序变化、错误姿态/材质/子网格/着色器拒绝、嵌入 PNG hash 与全部 mip 块、父级/IBM/顶点破坏拒绝。没有增加“看起来正确”作为通过标准。

下一步可把已采样的 idle/fire 经显式骨 ID→库名→mesh joint 映射追加到单独动画产物，并对实际 Cocos 导入做静态审计。现有范围仍不包括 shader 移植、音效/触发器/粒子、实体运行时材质改写、完整战斗动作事件关联和最终 UI/实机视觉验收。
