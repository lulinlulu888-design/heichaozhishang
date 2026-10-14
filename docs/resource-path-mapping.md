# 逻辑资源路径到 NPK 的确定性映射

调查日期：2026-10-14。已恢复此 APK 的 NeoX `StringIDLegacy` 算法，以 **9,698 / 9,698 个脚本条目**交叉验证；已找到艾尔莎、琳、未来的 `CharImage` / `CharImage2` 六项，并转换前三张 `CharImage` 为 PNG。另完成艾尔莎养成模型到网格、材质槽、贴图的可追溯链。没有按角色外观、记录序号相邻关系或 ID 差值绑定资源。

## 来源与证据边界

- APK：`heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk`，SHA-256 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。
- 原生证据：`lib/armeabi-v7a/libclient.so`，SHA-256 `54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`；下列 Thumb 地址位于 `.text`，VA 与文件 offset 相等。使用既有 NDK `llvm-objdump` / `llvm-readelf` 静态查看，未执行目标代码。
- 脚本数据来自先前数据型 Python 2 marshal 解析结果，未导入游戏模块。表字段是 `taggeddict` 的静态实参，不声称已恢复其运行时包装行为。
- 索引读取只访问 17 个 NPK 的头和目录，共 68,768 项；保存到 [npk-indices.json](../analysis/resource-mapping/npk-indices.json)。没有全量解包资源。

## 哈希算法与路径规则

[neox_resource_paths.py](../tools/neox_resource_paths.py) 的 `string_id_legacy(bytes)` 按原生 `StringIDLegacy(const char*)` 移植。它区分大小写、逐个小端 32 位字处理、保留 uint32 溢出与乘法高低位折叠，末尾不足 4 字节用零补齐，遇 NUL 截止。初始状态为 `37a8470e / 7758b42b / f4fa8928`，最后额外处理 `9be74448 / 66f42c48` 两字。

这不是 CRC32、FNV 或 Murmur3。库中确实存在后两种实现，但当前包头选择 Legacy：

| 原生位置 | 观察 |
| --- | --- |
| `0x138d534–0x138d540` | `NpkReader::DoOpen` 根据头部类型取得函数指针，存入 `this+0x28`。 |
| `0x138daec–0x138db02` | `GetStringIDTypeByHeader` 比较头部 offset 8 的 12 字节与 `0x289938c` 的 `00 00 00 00 00 00 00 00 01 00 00 00`；相同返回 0，不同返回 2。17 个本包均相同。 |
| `0x18eb59c–0x18eb5b8` | `GetStringIDFunc` 的类型 0 / 1 / 2 分别经 GOT 解析到 Legacy / VS2012 / Murmur3。 |
| GOT `0x2a8a970 / 0x2a8ebb4 / 0x2a8a96c` | ELF 重定位明确给出三个函数符号及地址。 |
| `0x18eaf6e–0x18eb180` | 本次实际移植的 C-string Legacy 实现。 |
| `0x138d736–0x138d73a` | `NpkReader::GetIndex(const char*)` 将名称传给选定函数，再在 28 字节记录数组按结果查找。 |

原始反汇编：[哈希及其实现](../analysis/resource-mapping/string-id.thumb.txt)、[类型选择](../analysis/resource-mapping/npk-select-hash.thumb.txt)、[GOT 重定位](../analysis/resource-mapping/string-id-got-relocations.txt)。剥离符号区域的 objdump 可能沿用远处最近符号名，因此其它函数只按地址描述。

### 脚本的完整验证

Python code filename 是源码名；包内资源实际后缀是 `.nxs`。规则及命中数：

- 源码 `.py` 换成 `.nxs`，保留大小写及 `\`：8,944 项。
- 其余去掉源码 `lib\` 或 `engine\` 的来源目录：753 项。
- `engine\common\rpc.py` 的实际归档名为 `rpc.nxs`：1 项。这是该来源的显式映射，不能推广成“所有文件都只保留 basename”。

总计 9,698 项、9,697 个唯一源码名，全部相等。两个 `redirect.py` 记录都对应 `redirect.nxs`，值 `fb54f059`。例如 `lib\json\__init__.py` 对应 `json\__init__.nxs`，值 `0004cc2d`。逐项预期/计算值见 [script-verification.json](../analysis/resource-mapping/script-verification.json)。

### 资源路径的挂载与后缀

资源逻辑路径 `root/path` 对应 `assets/res/root.npk`，hash 输入为去掉挂载根后的 `path`，`/` 换为 `\`，保留大小写。`lookup_logical()` 按指定包查询，`lookup()` 返回所有同 hash 项，**不把哈希碰撞或重复项静默折叠成首条**。

后缀重定向要单独处理，不能把 `.png` 名称当成真实编码格式。本次 UI 六项使用 `.png → .pkm`，但解压载荷全部是 **KTX1 / ASTC**。原生 `0xbfccac–0xbfccbe` 查找最后的点，`0xbfcd66–0xbfcd72` 匹配 `.png`（字符串 `0x24a39c8`），`0xbfcdf6–0xbfce0e` 用 `.pkm`（`0x25264cc`）替换后缀后查询文件。见 [UI 纹理路径反汇编](../analysis/resource-mapping/ui-texture-path.thumb.txt)。这里还检查 `.tga/.dds/.jpg/.jpeg`，未将其扩展为全资源转换保证。

## 三个角色的六项立绘

源表为 script.npk index **8995**，`common\cdata\character_basic_info.py`。表的英文字段为 ELSA LOVEFIELD、LYNN FLY、MIRAI；角色 ID 分别为 1、2、3。文字编码问题仍按原表记录，不通过损坏的中文字符串做识别。

共同前缀为 `uires/CommonRes/BigSan/`；表中为 `.png`，下表按 `.pkm` 归档名查询。

| 角色 ID / 名称 | 字段与相对路径 | uires.npk index | 原始表 const / bytecode |
| --- | --- | --- | --- |
| 1 艾尔莎 | `Char_detail/img_char_photo_elsa.pkm` | 4995 | 34 / 233 |
| 1 艾尔莎 | `Char_detail2/img_char_photo_elsa2.pkm` | 1767 | 36 / 240 |
| 2 琳 | `Char_detail/img_char_photo_lynn.pkm` | 5664 | 105 / 602 |
| 2 琳 | `Char_detail2/img_char_photo_lynn2.pkm` | 3010 | 106 / 609 |
| 3 未来 | `Char_detail/img_char_photo_future.pkm` | 3395 | 144 / 971 |
| 3 未来 | `Char_detail2/img_char_photo_future2.pkm` | 4603 | 145 / 978 |

每项的逻辑路径、归档路径、hash、NPK offset、压缩大小、解压 SHA-256、源 const / 指令位置在 [characters-path-matches.json](../analysis/resource-mapping/characters-path-matches.json)。六项都仅命中一条。CharImage2 仅保存提取证据，没有转换 PNG。

三张 CharImage 已走既有 `decode_ktx.py` / ARM astcenc 管线：每张 990×820，ASTC 逐块检查 20,336 块，HDR/错误块均为零；Pillow 验证 RGBA/尺寸/摘要，透明通道范围 0–255。已视觉查看三张输出，未翻转、裁切、重绘或依据图像猜身份。透明区中保留原纹理 RGB 边缘延展，使用时应保留 alpha。

- [艾尔莎 PNG](../analysis/resource-mapping/characters/elsa.CharImage.295c1e4964e2.m0.f0.png)
- [琳 PNG](../analysis/resource-mapping/characters/lynn.CharImage.a7c8a8ad1412.m0.f0.png)
- [未来 PNG](../analysis/resource-mapping/characters/mirai.CharImage.632fd6793ef2.m0.f0.png)

新客户端可直接读取 [characters/portraits.json](../analysis/resource-mapping/characters/portraits.json) 的 `character_id → png`。该目录的 `manifest.json` 保存完整 ASTC 检查、解码工具 hash 与 PNG/RGBA 摘要；`provenance.json` 保存固定 APK SHA-256、条目和原表字段。可重复提取脚本为 [extract_character_portraits.py](../tools/extract_character_portraits.py)。

## 艾尔莎模型到材质、贴图

已按源数据关联，并非假设角色 ID 与实体 ID 有固定差值：

1. characters row 1 的 `ENTITY_ID=0`（script 8995，const 2，bytecode 312）。
2. entity_table row 0 的 `LOD_ID=201`（script **1955**，const 198，bytecode 917）。
3. model_lod_table row 201 的 `LOD_MODEL_LIST=[16,17,18,19]`（script **1268**，const 1651，bytecode 486）。
4. lod_index_table row 16 的 `LEVEL=0`，`MODEL_PATH=character/player/ailisha/ailisha_yangcheng.gim`（script **6328**，const 55，bytecode 698）。这表示一个明确 LOD 配置，不声称所有游戏界面总使用此 LOD。

三个中间表的所需记录保存为 [entity-table-selected.json](../analysis/resource-mapping/entity-table-selected.json)、[model-lod-selected.json](../analysis/resource-mapping/model-lod-selected.json)、[lod-index-selected.json](../analysis/resource-mapping/lod-index-selected.json)。`helper\LodModelHelper.py` index 1838 中 `makeLodModelFilename` / `registerLodData` / `loadLODModels` 可见先读 `LOD_MODEL_LIST`，再按 `lod_index_table` 查 `LEVEL` / `MODEL_PATH`；[静态指令记录](../analysis/resource-mapping/LodModelHelper.partial-dis.txt) 保留未知 opcode。三位角色共 12 项 LOD 路径也均单条匹配，见 [lod-path-matches.json](../analysis/resource-mapping/lod-path-matches.json)。

| 艾尔莎资源 | character.npk index / hash | 解压数据 |
| --- | --- | --- |
| `player/ailisha/ailisha_yangcheng.gim` | 3494 / `78515e52` | 30,780 B，XML 模型描述 |
| `player/ailisha/ailisha_yangcheng.mesh` | 6008 / `ce7a9e54` | 1,614,202 B，NeoX `34 80 c8 bb` 网格 |
| `player/ailisha/ailisha_yangcheng.mtg` | 2608 / `59c2807d` | 9,844 B，XML，9 个材料 |
| `player/ailisha/texture/ailisha_new_cloth_d.ktx` | 5886 / `c9a03055` | 467,996 B，1024×1024、11 mip、ASTC 8×6 sRGB |

同 basename 的 `.mesh` / `.mtg` 有原生支持：`0xc213e8–0xc213f0` 用 `.mesh` 构造网格路径，`0xc212f4–0xc212fe` 用 `.mtg` 构造材料路径；字符串分别在 `0x249e3ee / 0x249e5b1`，调用 `0x10daec6`。后者扫描最后一个点并在分隔符处停止，然后接入新后缀，见 [mesh-loader.thumb.txt](../analysis/resource-mapping/mesh-loader.thumb.txt) 和 [replace-extension.thumb.txt](../analysis/resource-mapping/replace-extension.thumb.txt)。

网格解析得到 **19,063 顶点 / 29,240 三角形 / 9 子网格 / 180 骨骼**，索引边界、有限数值和权重通过现有模型解析器检查。更进一步，逐子网格顶点的 AABB 与 `.gim` 对应 `BoundingCenter/BoundingHalf` 的最大绝对误差为 **6.64e-6 以内**，9/9 都一致，从而独立验证网格与 `.gim` 的次序关联。

例如 `.gim` 的 `Sub6 Name=cloth, MtlIdx=1` 对应 `.mtg Material_1/Material Name=yifu`，其 `Tex0` 明确为 `character/player/ailisha/texture/ailisha_new_cloth_d.dds`。在 Android 包以 `.ktx` 名单条命中 index 5886，实际 KTX 结构完整。9 个材料中 **26 项贴图引用 / 20 个唯一路径全部单条命中**，见 [elsa-material-textures.json](../analysis/resource-mapping/elsa-material-textures.json)；只提取了上述一张贴图验证格式，没有批量转换全部材料。

源 `.gim/.mtg/.mesh/.ktx` 和对应 `.source.json` 全部位于 `analysis/resource-mapping/`。几何对应检查见 [elsa-mesh-material-validation.json](../analysis/resource-mapping/elsa-mesh-material-validation.json)。尚未把艾尔莎模型的全部材料重建到 Cocos，也未导出此新角色 GLB 或播放其动画；先前已导出的 character index 6424 仍不能据本结果冒称为艾尔莎。

## 虚拟纹理的有限补充

`helper\cocosvt.py` index **5831** 常量明确给出 `packed_png/vt_data/vt_config.jsondata`，去挂载根哈希后单条命中 packed_png index **69** / `01ac43ee`。按其 `saveConfigJson2BinData` / `writeStringAligned4` 的结构恢复出 version 1、47 个 `plistToPageID`、5,894 个 `pngsToPageID`、5,894 个 `fullPathToPng`，**完全消费 818,688 字节**；所有字符串长度和边界均检查。

完整解析见 [vt_config.parsed.json](../analysis/resource-mapping/vt_config.parsed.json)，相应脚本指令见 [cocosvt.partial-dis.txt](../analysis/resource-mapping/cocosvt.partial-dis.txt)。这六张大立绘不在 VT 路径表中，它们通过独立 `.pkm` 条目定位。此次没有继续解析 `vt.table` 块数据或拼图算法。

## 复现与检查

```powershell
$analysisPython = 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $analysisPython tools/neox_resource_paths.py --verify-scripts analysis/assets/decoded/script/index.json --apk heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk
& $analysisPython tools/neox_resource_paths.py --catalogue analysis/resource-mapping/npk-indices.json 'CommonRes/BigSan/Char_detail/img_char_photo_elsa.pkm'
& $analysisPython tools/extract_character_portraits.py
& $analysisPython -m unittest discover -s tests -p test_resource_paths.py -v
```

新增 **8 项回归测试全部通过**：真实脚本全量哈希、固定归档向量、大小写/分隔符/NUL、来源目录例外、碰撞不丢失、六项立绘查找、VT 截断/越界拒绝、实际 PNG 像素追溯。没有调用原游戏运行时，也没有从旧服务器获取资源。
