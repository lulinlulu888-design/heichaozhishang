# NeoX 模型解析与首个带蒙皮 GLB

2026-10-14。本次只检查本地 APK、已提取原生库和 6 个模型样本，没有运行游戏代码、安装转换器或批量解包角色资源。

**交付：`analysis/model-conversion/character.06424.skinned.glb` 已包含一个真实角色的 20,268 顶点、28,864 三角形、9 个子网格、159 个骨骼、每顶点 4 个影响槽和原始两套 UV。** 原始 mesh 全部 1,707,673 字节已按结构消费。导出的几何与原数组逐项相等，GLB 重新读取后的 CPU bind pose 蒙皮误差小于 `3e-6`。没有恢复贴图、材质、角色身份或原游戏动画播放。

`character.06424.preview.png` 是从 **导出后的 GLB** 重新读取顶点、法线、三角形生成的诊断图。图中 VIEW A / VIEW B 不宣称原游戏正面方向；绘制使用平均深度排序，局部遮挡可能存在误差，它不等同于 Cocos/Unity/Godot 实机渲染验收。

后续集成证据：Cocos Creator 3.8.8 已实际导入此 GLB，生成 mesh/skeleton/prefab，并报告 28,864 三角形与 159 joints，与导出数据一致。记录见 `analysis/cocos-toolchain/imported-model.meta.json`、`asset-import.log`。这证明导入可用；当前展示场景尚未播放该模型的原动画或恢复其原材质。

## 来源与范围

| 项目 | 证据 |
|---|---|
| APK | `heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk` |
| NPK member | `assets/res/character.npk` |
| NPK index / name_hash | `6424` / `dbe808ec`，hash 尚未反解为路径 |
| NPK payload offset | `608739212` |
| Stored / decoded bytes | `1028931` / `1707673`；zlib，encryption=0 |
| Decoded mesh SHA256 | `89131cc4ee67c2fe88da28f7c3e5708b5986e29e67129365f18debcbf7cdcc5b` |
| GLB SHA256 | `5067d493fa21bb7f9218fd1e0131c2dae35353192635e91211d3b894129e2560` |
| GLB bytes | `1460744` |
| Native source | `analysis/bootstrap/extracted/lib/armeabi-v7a/libclient.so` |
| Native SHA256 | `54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef` |

完整表记录保存在 `character.06424.source.json`。检查起点是此前小样本 `ui_model.npk` index 10，194 B；随后比较 `effects` index 23441、`model` index 801、`character` index 4713，再新增限量提取 `character` index 5922、6424。仅 5922 和 6424 是本阶段新解压的 NPK 资源。

| 样本 | 顶点 | 三角形 | 子网格 | 骨骼 / 实际使用 |
|---|---:|---:|---:|---:|
| ui_model 10 | 4 | 2 | 1 | 0 |
| effects 23441 | 4 | 2 | 1 | 0 |
| model 801 | 4 | 2 | 1 | 0 |
| character 4713 | 1,787 | 1,499 | 3 | 166 / 32 |
| character 5922 | 1,531 | 1,493 | 2 | 178 / 22 |
| character 6424 | 20,268 | 28,864 | 9 | 159 / 158 |

4713 只使用 `shoutao_bone*` 段，不能称为完整角色。6424 的网格范围为 X `[-5.563984, 5.565435]`，Y `[0.009803, 17.049141]`，Z `[-2.165229, 5.377290]`。保留原坐标和尺度；真实世界单位、前向方向仍未绑定到新引擎约定。

## 原生实现证据

使用现有 NDK `D:/Android/Sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-objdump.exe --triple=thumbv7a-linux-android -d`。下列地址在 `.text`，VA 与 ELF 文件偏移相同。完整反汇编窗口保存在 `analysis/model-conversion/mesh-reader-c21300.thumb.txt` 与 `mesh-reader-c22400.thumb.txt`，不是通过扩展名推测格式。

| 地址 | 可观察行为 |
|---|---|
| `0xc218aa–0xc218be` | 写出 `0x00050003` 版本及 `0xbbc88034` magic |
| `0xc218c2–0xc218dc` | 写 2-byte mesh type，再写两个可选动画块的标志 byte |
| `0xc21998–0xc21a16` | type=1 才写骨骼；2-byte 数量、1-byte/骨父索引、32-byte/骨名字、可选 28-byte/骨块、64-byte/骨矩阵 |
| `0xc21d9c–0xc21f2c` | 对应骨骼 reader；数量限定 1..254，按相同长度复制数组 |
| `0xc218e8–0xc218f2` | type=1 写额外 skeletal data 的标志 byte；样本均为 0 |
| `0xc21a42–0xc21b0e` | 预留目录绝对 offset，写几何，写末尾目录后回填 offset |
| `0xc2289a–0xc228da` | 每个子网格写 `uint32 vertexCount, uint32 triangleCount, uint8 uvCount, uint8 colorPresent` |
| `0xc228ea–0xc22936` | 写 `uint16=1`、全局顶点/三角数，再写 position float3 与 normal float3 |
| `0xc2293a–0xc22976` | 可选 float3 顶点辅助流的 `uint16` 标志，随后每三角 6-byte 的 uint16 索引 |
| `0xc2297a–0xc22a08` | 按子网格写 UV float2 流及可选 4-byte 顶点颜色数据 |
| `0xc22a18–0xc22a3e` | skin type=1 写每顶点 4-byte 骨索引、16-byte 权重 |
| `0xc22a7e–0xc22b7a` | 忽略 index=255 或 weight=0 的影响，生成并写出 32-byte 使用骨骼 bitset |
| `0xc22cec–0xc22da0` | 目录写 offset 数组与 8-byte `(type, index, padding)` 记录 |

早期 `0x94d0ec`、`0x95c69c` 一带是另一套 reader，版本/动画尾部与当前文件不能直接套用。本实现采用实际写出上述 magic 的 `0xc21890` 路径及其配对 reader。相邻函数/符号缺失，因此报告给地址，不伪造 C++ 函数名。

## 6424 的关键范围

以下均为 **解压后的 mesh 文件 offset**，端序 little-endian。完整无重叠范围账本见 `character.06424.json` 的 `ranges`。

| Offset | Length | 内容 |
|---:|---:|---|
| 0 | 10 | magic / version / type |
| 10 | 2 | 可选动画标志，均 0 |
| 12 | 2 | bone count = 159 |
| 14 | 159 | parent index，255 表示无父节点 |
| 173 | 5088 | 159 × 32 字节骨名 |
| 5261 | 1 | 28B 骨附加块存在标志 = 1 |
| 5262 | 4452 | 骨局部 AABB center float3 / halfExtent float3 / radius float |
| 9714 | 10176 | 模型空间 bind transform，159 × 16 floats |
| 19890 | 1 | 额外 skeletal data 标志 = 0 |
| 19891 | 4 | directory offset = 1707657 |
| 19895 | 90 | 9 个子网格 descriptor |
| 19985 | 10 | `1, 20268, 28864` |
| 19995 | 243216 | positions |
| 263211 | 243216 | normals |
| 506427 | 2 | vertex auxiliary 标志 = 1 |
| 506429 | 243216 | float3 vertex auxiliary，保留原数据但未映射 glTF TANGENT |
| 749645 | 173184 | 28,864 × 3 个 uint16 index |
| 922829 | 324288 | 各子网格 2 套 UV |
| 1247117 | 55148 | 子网格 1、6、7、8 的 4B 顶点颜色流 |
| 1302265 | 81072 | 4 个 uint8 骨索引 / 顶点 |
| 1383337 | 324288 | 4 个 float 权重 / 顶点 |
| 1707625 | 32 | 使用骨骼 bitset |
| 1707657 | 16 | 单几何记录目录；精确结束于 EOF |

Native 几何 reader 的子网格数来自外部模型/材质元数据；当前没有恢复该文件的逻辑路径。解析器只接受一个候选：各 descriptor 计数之和必须等于总数，所有流长度必须精确到目录边界，索引必须处在对应子网格顶点区间。6 个样本都存在唯一解。它是受约束的结构恢复，不是任意扫描顶点 float；不宣称通用 NeoX 解码器。

## 骨骼语义与导出验证

原生读写代码确认了数组长度，但单凭复制矩阵不能确认其方向。本次用独立存储的骨局部 bounds 交叉验证：将每个有非零权重的原始顶点乘 `inverse(rawBoneMatrix)`，所得顶点包围盒与该骨 28B 数据 `center ± halfExtent` 比较。6424 的 158 个使用骨骼全部通过，37,522 个骨-顶点关联全部匹配；最大边界误差 `2.69516e-6`。`radius = length(halfExtent)` 的最大误差 `2.45901e-7`。因此这批原始矩阵可确定为骨到模型空间的 bind transform，28B 数据可确定为对应局部 bounds。保留机器字段 `auxiliary_unknown` 是为了兼容初始调查产物，已验证语义以此报告和 `bind_validation` 为准。

GLB 的节点局部变换按 `inverse(parentGlobal) * childGlobal` 生成，inverseBindMatrices 为 `inverse(globalBind)`。159 个节点均为可分解 TRS 的无剪切矩阵，归一化列向量正交误差最大 `2.64550e-7`。无父节点的骨骼挂到公共 identity skeleton root。原 NeoX `255` 无效影响只在其 weight=0 时转为 glTF 的有效索引 0；权重仅做浮点归一化。

原始法线长度 `[0.9999999271, 1.0000001078]`；权重和最大误差 `9.12697e-8`。使用骨集合与保存的 32B bitset 逐位一致。原始三角形 winding 保留：28,752 面的 cross product 与平均顶点法线同向，112 面反向；未擅自翻面，可能来自原模型薄片/平滑法线，需材质与渲染验证。

`tests/test_neox_model.py` **14 项通过**：逐字节截断、异常 count/目录/索引、NaN、未知格式标志、循环父节点、越界 joint、零权重、错误骨矩阵不能通过独立 bounds 检查，以及真实平面/角色 GLB 二次解码、所有位置和索引一致、所有顶点 CPU bind pose 重建误差 `<3e-6`。

**这验证的是资源结构和 bind pose，未验证原动画 clip、动作切换、游戏表现或跨平台打包。** 尚未运行官方 glTF Validator；当前没有安装新工具。另一个客户端工作单元负责 Cocos 导入验证，结果不预先计入本文。

## 复现

Python 使用现有运行时：`C:/Users/5090B/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。工具主体仅标准库；预览脚本用已有 numpy/Pillow。

```powershell
$py = 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py tools/inspect_neox_model.py heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk --extract-index 6424 --output analysis/model-conversion/character.06424.mesh
& $py tools/inspect_neox_model.py analysis/model-conversion/character.06424.mesh --output analysis/model-conversion/character.06424.json
& $py tools/export_neox_gltf.py analysis/model-conversion/character.06424.mesh --skin --output analysis/model-conversion/character.06424.skinned.glb
& $py -m unittest discover -s tests -p test_neox_model.py -v
& $py analysis/model-conversion/render_preview.py
```

无 `--skin` 时可输出静态 GLB；`--skin` 会强制独立 bounds 检查和无剪切检查，未通过就拒绝输出骨架。解析器有 32 MiB 单资源预算，拒绝未知版本/精度、动画附加块、多几何目录、非唯一 descriptor 数和所有越界；NPK 解压复用现有带输出预算与尾数据拒绝的 decoder。

glTF 布局按 [Khronos glTF 2.0 官方规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) 的 GLB 对齐、accessor、skin 和节点变换要求编写。没有使用外部 NeoX 转换器或无来源的格式代码。

## 当前缺口与最小下一步

1. 找到 `dbe808ec` 对应的模型路径、伴随 MaterialGroup 与贴图映射；9 个 primitive 目前只保持顺序，不猜材质名。颜色流与 float3 辅助流尚未导出，UV 原值保留且没有擅自翻 V。
2. 在新引擎导入这个 GLB，确认骨架层级、bind pose、剔除与前向/单位；可用一个人工测试旋转检验新引擎蒙皮，但这仍不是原动画恢复。
3. 后续单独匹配对应 RGIS/skeleton/animation 资源，确认骨名和 bind pose 一致后再转换一段真实 idle clip。此报告没有扩大到动画格式解析。
