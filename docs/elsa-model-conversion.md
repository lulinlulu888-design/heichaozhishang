# 艾尔莎养成模型：蒙皮与基础颜色导出

2026-10-14。已产出 `analysis/elsa-model/elsa-yangcheng.colour-reference.glb`，3,350,180 字节，SHA-256 `84956d9eeec1285c4de49faa6f0def6453663f288fb40352cf23deec6479a35f`。它包含真实源网格、完整绑定骨架和经着色器证据确认的颜色纹理，定位是 **无光照颜色参考**。未声称还原原游戏的 toon、光照、描边、动画或物理。

本轮只读 APK，本地静态解析，没有执行 APK 脚本/原生代码，没有启动客户端、编辑 Cocos TS 或操作 UI。已有原生分析后端限制保持不变；本轮材质语义由同一 APK 内的 `.surf`、`.nfx`、`.hlsl` 直接支持。

## 可复现入口与交付物

```powershell
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools/export_elsa_model.py
& 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -p test_elsa_model.py -v
```

入口先流式校验整个 APK SHA-256，再用已验证的路径哈希按需读取单条 NPK 资源。模型源 SHA 也固定校验；没有按相似外观或递增编号配对资源。已有 `export_neox_gltf.py` 不作修改，新包装器附加材质和嵌入 PNG。

- `analysis/elsa-model/export-report.json`：APK、资源路径、member/index、NPK offset、原始/解压长度、SHA、22 张纹理用途、着色器证据、每子网格 UV 范围、绑定验证、未支持效果。
- `analysis/elsa-model/source/`：本次重新定址提取的 GIM/MESH/MTG；扩展名保留的 `.provenance.json` 避免相同 stem 覆盖来源记录。
- `analysis/elsa-model/textures/`：20 张角色本地 KTX + 2 张共享 KTX。只将 7 张有直接颜色证据的纹理解码嵌入 GLB。
- `analysis/elsa-model/colour-png/manifest.json`：ASTC 检查器/解码器 hash、各 mip/face 逐块检查结果、PNG 与 RGBA hash。
- `analysis/elsa-model/shader-evidence/`：原始着色器、独立 provenance；机器可读完整清单见报告 `shader_sources`。
- `analysis/elsa-model/gltf.json`：GLB 内的 JSON，便于检阅材质、属性和限制。
- `analysis/elsa-model/bone-map.json`：mesh joint index、GLB node index、源骨名、父级、global/local bind 矩阵对照。没有将 ACL track 序号视为 joint 序号。

APK：`heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk`，SHA-256 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。

## 角色身份与几何来源

身份链沿用 `docs/resource-path-mapping.md` 的已验证静态表：角色 1 艾尔莎 → ENTITY_ID 0 → LOD_ID 201 → LOD_MODEL_LIST 的第一项 16 → level 0 `character/player/ailisha/ailisha_yangcheng.gim`。这是一条明确的养成模型链，不是先前未命名的 character index 6424 模型。

| 源资源 | character.npk index | name_hash | NPK offset | 解压字节 | SHA-256 |
|---|---:|---|---:|---:|---|
| ailisha_yangcheng.gim | 3494 | 78515e52 | 54108740 | 30780 | e04de6992fbd43a73f221b5a3ccc5d9744db5a46585e0f3beb43cc5b33460a51 |
| ailisha_yangcheng.mesh | 6008 | ce7a9e54 | 70551460 | 1614202 | 22677b92724bdc12c0e7aae0e8450a70602949f5f242dc1e965150cab316b618 |
| ailisha_yangcheng.mtg | 2608 | 59c2807d | 53013528 | 9844 | 672f08c5a8280f407db221142764c93b7f414e3c24865f90366480ec72323a74 |

NeoX 5.0.3 网格共 19,063 顶点、29,240 三角形、9 子网格、180 骨骼，解析覆盖 1,614,202 / 1,614,202 字节。原位置/法线/索引/两组二维通道均保留；完整覆盖不代表每个辅助字段都已解释。源单位、三角绕序和 XYZ 轴不变。没有通过旋转镜像或重排顶点“修正”外观。

| 子网格序号/名 | 材质槽/名 | 顶点 | 三角 |
|---|---|---:|---:|
| 0 eye | 5 eye | 218 | 376 |
| 1 head | 7 head | 2175 | 3624 |
| 2 head_1 | 8 eye_nei | 147 | 234 |
| 3 eye_boliti | 6 eye_yinying | 102 | 160 |
| 4 body | 4 body | 2690 | 4113 |
| 5 hair | 3 hair | 5039 | 7417 |
| 6 cloth | 1 yifu | 7983 | 12149 |
| 7 cloth_1 | 2 siwa | 584 | 1035 |
| 8 hair_yinying | 0 hair_yinying | 125 | 132 |

关联来自 GIM 每个 `SubN.MtlIdx`，并用该子网格顶点 min/max 与独立 GIM BoundingCenter±BoundingHalf 比较：9/9 通过，最大端点误差 7.0085048676e-6。严禁把第 N 个几何 primitive 直接连到第 N 个材质。

蒙皮将源骨骼 global bind 矩阵取逆作为 IBM，按父级求 local bind；采用独立的源骨骼局部包围盒验证，最大 AABB 误差 2.7020591681e-6，半径误差 1.6698011818e-7。源权重最大总和误差 1.0803341866e-7，导出时归一化；零权重占位 joint 255 改成有效 joint 0。GLB 回读后重建父子 world、与 IBM 相乘，对所有 19,063 个顶点重算绑定姿态，误差 <3e-6。这是数值绑定验证，**不是动画播放验证**。

## Tex 与 UV 的证据

所有下列 index 都属于 `assets/res/shader.npk`，完整 hash 和 offset 留在报告。

| 证据文件 | index | 关键行/意义 |
|---|---:|---|
| compositor-config-index-1241.xml | 1241 | 4：DefaultVF 对应 model_default.hlsl；原逻辑文件名尚未确定 |
| model_default.hlsl | 3343 | 3 引入 default_vertex_struct，42 引入 default_functions |
| default_vertex_struct.hlsl | 2554 | 13：texcoord0 : TEXCOORD0 |
| default_functions.hlsl | 2889 | 79：vert.uv.xy=input.texcoord0；216：frag.uv=vert.uv |
| basic.surf / material.hlsl | 450 / 2186 | surf 7 为 Albedo；hlsl 68 采样 UV0，79/81 指向 albedo，97 指向 opacity |
| skin.surf / material_skin.hlsl | 3226 / 1675 | hlsl 31 采样 UV0，40/42 指向 albedo，48 指向 opacity |
| hair_cartoon.surf / material_hair_cartoon.hlsl | 163 / 2369 | hlsl 31 采样 UV0，42/44 指向 albedo，50 指向 opacity |
| eye_cartoon.surf / material_eye_cartoon.hlsl | 1020 / 21 | hlsl 24 采样 UV0，32/34 指向 albedo，40 强制 opacity=1 |
| stocking.surf / material_stocking.hlsl | 1769 / 3377 | hlsl 33 采样 UV0，48/50 为 Tex0.rgb×StockingColor.rgb，58 为 Tex0.a |
| eye_ao.nfx / eye_ao.hlsl | 772 / 3464 | nfx 53–61 定义 TShader 并链接 eye_ao.hlsl；hlsl 52 为 texcoord0.xy，58 采样 Tex0，69–70 原 RGBA 输出 |

MTG 的 `.fx::TShader` 标识对应同 stem 的 `.nfx` 技术和 `.hlsl` 实现，二者是通过路径哈希实际匹配的原包内容。该配套实现为覆盖层使用 Tex0 RGBA 提供证据；本轮没有完整恢复原生 `.fx` 扩展名调度或 RenderStates 数值枚举。

颜色统一使用导出的 TEXCOORD_0。第二组二维数据完整留作 TEXCOORD_1，其特殊数值和更广泛用途本轮不解释。UV0 中衣服、身体等 U 会大于 1（最大约 1.995），不能 clamp；`material_common.hlsl` index 1035，20–27 行确定正常材质为 Wrap 采样。输出使用 REPEAT 双线性/三线性采样；两张 effect 的采样器寻址未单独证实，采用同一 REPEAT 兼容策略。原 UV 浮点和 PNG 行序均不翻转；跨原 OpenGL 后端到新引擎的最终视觉方向仍需在模型场景比对，未用猜测强行翻转。

## 9 材质槽与 20 张角色贴图

路径前缀均为 `character/player/ailisha/texture/ailisha_new_`，下表简写后缀。MTG 逻辑名是 `.dds`，实际唯一命中的是同路径 `.ktx`，magic 为 KTX1，ASTC 8×6。`.dds` 扩展名本身未用于判断像素或材质用途。

| 槽/名字 | 源 shader | Tex0（颜色证据） | 其他纹理及用途 |
|---|---|---|---|
| 0 hair_yinying | eye_ao TShader | hair_d_yinzi | 原 RGBA 覆盖层颜色；并非把 AO 标量塞入 baseColor |
| 1 yifu | basic / Isotropy | cloth_d | Tex1 cloth_n 法线；Tex2 cloth_m R遮蔽/G粗糙/B金属 |
| 2 siwa | stocking | cloth_d × StockingColor | Tex1 cloth_n；Tex2 cloth_m A参与厚度；Tex3 siwa_d 图案在 UV0×220 采样，参与自定义织物/皮肤混合 |
| 3 hair | hair_cartoon | hair_d | hair_n 法线；hair_m 混合；hair_an 流向/各向异性；hair_h 高光颜色 |
| 4 body | skin | body_d | body_n 法线；body_m R遮蔽/G粗糙/B为1-SSS曲率；共享 Tex3 皮肤 LUT |
| 5 eye | eye_cartoon | eye_d（不透明） | eye_n 法线；eye_hl 静态反射；共享 Tex4 matcap，使用视空间法线生成 UV |
| 6 eye_yinying | eye_ao TShader | eye_ao | 原 RGBA 覆盖层颜色 |
| 7 head | skin | head_d | head_n 法线；head_m 混合；共享皮肤 LUT |
| 8 eye_nei | skin | head_d | 与 head 共用纹理，独立材质/描边参数 |

关键差别：skin.surf 把 Tex2 的 UI 描述写成通用 Metalness(B)，但 material_skin.hlsl 明确 metalness=0、sss_curvature=1−Tex2.b。必须以代码覆盖 UI 标签，不能将全部 `_m` 纹理无条件接成 glTF ORM。眼睛 surface 的 UI 把 Tex0.A 说明为“视差强度”，实际 opacity 函数强制 1；本轮没有证明该 alpha 在运行时被用于视差，只能确定它不驱动透明度。

| 角色纹理后缀 | character.npk index | 像素尺寸 | KTX RGB profile |
|---|---:|---|---|
| body_d / body_n / body_m | 509 / 470 / 4827 | 512×512 | sRGB / linear / linear |
| cloth_d / cloth_n / cloth_m | 5886 / 707 / 6278 | 1024×1024 | sRGB / linear / linear |
| eye_d / eye_n / eye_hl / eye_ao | 3449 / 4099 / 615 / 5333 | 512×256 | sRGB / linear / linear / linear |
| hair_d / hair_n / hair_m | 1328 / 6154 / 5197 | 512×512 | sRGB / linear / linear |
| hair_an / hair_h / hair_d_yinzi | 5795 / 4779 / 5293 | 512×512 | linear / linear / linear |
| head_d / head_n / head_m | 2162 / 4189 / 3710 | 512×512 | sRGB / linear / linear |
| siwa_d | 4093 | 512×512 | sRGB |

另外两张共享资源单独计算：`shader/core/texture/lut_newfix.png` → `.ktx`，shader.npk index 385，128×128、linear ASTC8×8；`common/matcap/matcap_04.dds` → `.ktx`，common.npk index 151，512×512、linear ASTC8×8。所以本次是 20 张角色本地 + 2 张共享 = 22 个唯一纹理资源。

## 可移植的颜色范围与明确限制

只解码并嵌入 body_d、cloth_d、eye_d、hair_d、head_d、hair_d_yinzi、eye_ao 七张。其全部 mip/face 的 66,063 个 ASTC 块均先通过检查，HDR/error 均为 0，之后只输出 mip0 PNG。其他 15 张仅保留原 KTX 及结构检查/用途证据，没有冒充完成解码。原 mip 链不嵌入 PNG glTF，最终引擎需生成 mipmap。

五张普通颜色图都是 sRGB ASTC，RGBA 解码直接嵌入；其 alpha 全部为 255。两张覆盖图是 linear ASTC，额外创建 `.gltf-srgb.png`：对 RGB 使用标准 linear→sRGB 编码，alpha 字节不变；保留未经该转换的源解码 PNG。这样符合 glTF baseColorTexture 对 RGB 的 sRGB 采样定义，不把源线性值再次错误解码为更暗颜色。依据 [glTF 2.0 颜色纹理约定](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#pbrmetallicroughness-basecolortexture)。转换后的两张图经反向 sRGB 解码与源线性像素比较，量化误差 <0.0045。

所有材质使用 `KHR_materials_unlit`，金属度 0、粗糙度 1 仅作 fallback。丝袜保留代码证明的 StockingColor=(.392157,.368627,.392157,1) 乘色。这只对应 GetAlbedo 阶段；原 shader 的视角相关织物/皮肤合成、法线、粗糙/遮蔽、发丝流向与高光、眼睛 matcap/高光、皮肤 LUT、tone adjust、环境/阴影/补光、描边均未迁移。

透明/剔除是明确的兼容策略：眼睛按 HLSL 设 OPAQUE；其余普通颜色面采用 MASK，cutoff=源 AlphaRef/255（源贴图 alpha 都是255，当前不会因该选择挖洞）；覆盖层使用常规 straight-alpha BLEND。**尚未从原生枚举证明 TransparentMode 1/2 和 CullMode 2 的完整等价关系**；原 RenderStates 保留在 GLB extras。为便于检查源绕序，当前 doubleSided=true，不将它解释为原游戏双面材质。覆盖层混合顺序/深度与运行时可见性还需单独验证。

## 验证与最小下一步

`tests/test_elsa_model.py` 8 项通过：完整来源/计数、每顶点位置法线和两组 UV 逐值回读、全部索引、非顺序材质映射、错误包围盒/材质索引拒绝、180 骨骼的全顶点静止蒙皮重算、仅颜色贴图与正确眼睛 alpha、嵌入 PNG hash/色彩转换、GLB 截断/长度越界拒绝。导出重跑得到相同 GLB hash。尚未运行 Khronos 全量 validator，也未在此子任务做 Cocos 导入或真实动画播放；不能以数值通过替代它们。

最小下一步是在模型展示场景验证此明确身份模型的 UV 方向、覆盖层 alpha/排序和两侧绕序，保持 `colour-reference` 标识。父任务已报告用官方 ACL 解出 stand_idle/skin 的180轨道姿态；本轮没有验证那些轨道与本 mesh 的顺序/坐标关系。应先将 RGIS 的骨骼 ID/名字与 `bone-map.json` 对照，独立验证轨道映射、local/global 矩阵以及 idle 首帧形变，再生成动画 GLB；不能仅因180对180便顺序绑定。着色器重建另行使用已提取 HLSL，先基本皮肤/衣服，之后处理发丝、丝袜与眼睛。当前 GLB 可以作为跨引擎有蒙皮的真实资产基线，不需要再从外观猜角色。

父任务随后报告已用 MurmurHash3 和名字逐项确认180轨道/mesh顺序，并请求独立检查库参考姿态与 mesh bind 的 0.066478 差异。本轮只读结论写在 `analysis/elsa-model/bind-difference.json`：使用父任务识别的 RGIS byte5774 起180条 T,Qxyzw,S，唯一显著差异是 mesh joint50 `bip001 r toe0`（parent46，无子骨）。库记录 byte7774，其 R^T×mesh local R 约为局部 Z 的 −3.811740°。库四元数范数为 .9999999407–1.0000000758；归一化不能消除该差异，且该骨 scale=(1,1,1)，换 R*S/S*R 也无效。其余179骨的 rotation/scale 最大误差1.2690e-6，全体 translation最大误差6.7461e-5。

该脚趾骨只直接影响39个顶点，全部在 cloth 子网格6；skin 和 stand_idle 解码姿态中，该骨各自全帧常量但两 clip 的值不同。现有证据更支持单骨源 bind/reference pose 差异，而不是全局矩阵次序错误；这是推断，不足以证明原游戏是否另作校正。未修改任何骨架/动画。下一步应保留原动画姿态和 mesh IBM，观察这39个顶点的局部形变；如需生成 glTF 动画，目标节点必须使用 TRS 表示，不能同时保留当前静态节点的 `matrix` 字段。
