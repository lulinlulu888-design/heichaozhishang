# ASTC 块级验证

当前纹理转换只输出 LDR PNG。KTX 的线性 `GL_COMPRESSED_RGBA_ASTC_*_KHR` 枚举不足以证明压缩块是 LDR：HDR 与 LDR 使用同一组线性枚举。ARM CLI 对 LDR 模式下的 HDR/错误块可能返回成功并输出错误颜色，退出码和 PNG 尺寸不能完成块级验证。

`tools/astc_block_info.cpp` 使用未修改的 ARM astcenc 5.7.0 官方库解析每一个 16 字节块；不通过洋红色像素判定错误，也不实现完整的 ASTC 位流解析器。

## 构建与调用

需要本机已有 Visual Studio 2022 C++ Build Tools 和 CMake。在仓库根目录使用可用的 Python 3：

```powershell
python tools/setup_astc_inspector.py
tools/runtime/astc-inspector-5.7.0/build/Release/astc-block-info.exe image.astc
python -m unittest discover -s tests -p test_astc_inspector.py -v
```

构建仅写入 `tools/runtime/astc-inspector-5.7.0/`，不安装全局工具。脚本使用官方 5.7.0 标签源码 ZIP，并固定本次下载的 SHA256：

`a28919f28547f9d9bc480f3147dcfc8383d7d845c635da90a7edd0a99576b496`

该校验值是从官方标签归档计算并固定的本地校验值，不声称是上游发布的校验声明。每次构建先验证归档并恢复其中源码，使用 SSE2、Release、完整静态库、关闭 CLI。`source.json` 记录下载地址、源码和 checker 哈希、CMake 版本、编译配置哈希、命令及结果 EXE 哈希。它使源码和配置可复现，不承诺不同编译器生成逐字节相同的 EXE。

工具输入为一个非空、非数组的二维 `.astc` 文件，检查魔数、足迹、维度及精确载荷长度，限制文件 256 MiB、单边 16384、像素 64 Mi。KTX 包装层应负责 mip/face、原始来源与哈希，再逐个提取 raw ASTC 调用此工具。

退出码：

| 退出码 | 含义 | 标准输出 |
| --- | --- | --- |
| 0 | 每块均为合法 LDR | JSON，`ldr_compatible=true` |
| 2 | 至少一个 HDR 或错误块 | JSON，完整计数及前 16 个问题块的位置/原始十六进制 |
| 1 | 输入损坏、不支持或 API 调用失败 | 无 JSON，标准错误说明原因 |

合法 HDR 块计入 `hdr_blocks`；非法块仅计入 `error_blocks`；三类与 `ldr_blocks` 之和等于 `block_count`。`raw_astc_offset` 包含 16 字节 raw ASTC 头，不是 KTX 内偏移。若需要原始 KTX 位置，应由 `ktx_payload_offset + 16 * block_index` 计算。端点模式直方图按 partition 计数，不是按块计数。

## 官方 API 的必要边界

1. 使用 `astcenc_get_block_info` 的 `is_error_block` 检查非法编码。该 API 对非法块仍可能返回 `ASTCENC_SUCCESS`，因此必须检查字段。
2. 必须编译完整库。`ASTCENC_DECOMPRESSOR=ON` 的精简库对 `get_block_info` 返回 `ASTCENC_ERR_BAD_CONTEXT`。运行时仍可用 `ASTCENC_FLG_DECOMPRESS_ONLY` 建立轻量上下文。
3. 检查上下文使用 `ASTCENC_PRF_HDR`，保留非恒定块真实 HDR 端点信息；之后用 `is_hdr_block` 分类。该 profile 是检查手段，不是声称素材为 HDR，也不改变后续 LDR/sRGB 像素解码选择。
4. 5.7.0 的实现对恒定颜色块提前返回，未设置 `is_hdr_block`。仅在官方库已经确认非错误且 `is_constant_block=true` 后，读取规范定义的 bit 9（`block[1] & 2`）区分 U16 LDR 与 F16 HDR。损坏的 void extent 先被官方库拒绝，不因该位被误分类为合法 HDR。

依据：[ARM 5.7.0 API 头文件](https://github.com/ARM-software/astc-encoder/blob/5.7.0/Source/astcenc.h)、[官方 get_block_info 实现](https://github.com/ARM-software/astc-encoder/blob/5.7.0/Source/astcenc_entry.cpp)、[ASTC HDR 扩展规范 C.2.23](https://registry.khronos.org/OpenGL/extensions/KHR/KHR_texture_compression_astc_hdr.txt)。

## 回归样本

`tests/test_astc_inspector.py` 覆盖合法 LDR 恒定块、HDR 恒定块、非恒定 HDR 块、非法块、损坏 void extent、混合块的偏移和计数、问题记录数量上限、原始头/载荷边界，以及已有原始纹理样本。

HDR 非恒定块来自官方 Windows SSE2 astcenc 5.7.0（EXE SHA256 `ded446f477755af96875c7f4f8e85216a73c06367fdba3fda2744f6bb15b87aa`）真实编码，非手写位流。生成一个 4×4 的 Radiance RGBE 文件：

```python
header = b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 4 +X 4\n'
pixels = bytes(v for y in range(4) for x in range(4)
               for v in (32 + 48*x, 32 + 48*y, 64 + 16*(x+y), 131))
source = header + pixels
```

宽度 4 小于 Radiance 扫描行 RLE 的最小宽度，数据使用直接 RGBE 像素。源文件 SHA256 为 `b64394c4d1fe5cd98939f43d2c864cf770ce49bd39bde19ae9b4a396e7911318`。

```powershell
astcenc-sse2.exe -ch gradient.hdr gradient.astc 4x4 -fastest -silent
```

所得块为 `510802b6c882e0ce8a2c116c4d7fbd01`；官方 API 报告两个 partition 均为端点模式 11、HDR、非恒定。检查器返回 2，`hdr_blocks=1`、`constant_hdr_blocks=0`。常色 HDR 样本 `fcffffffffffffff003c003c003c003c` 同样返回 2；全零块返回 2 且 `error_blocks=1`。

## 实际 APK 样本结果

本次完整检查七个 KTX 的全部 mip 与全部立方体面，共 89 个 mip/面、30,207 块，全部合法 LDR，HDR 与错误块均为 0。已输出的 12 张 mip0 图因此没有发现 HDR 误用 LDR 解码问题。完整来源 SHA、raw ASTC SHA、原 KTX 载荷偏移、检查器 SHA、逐层计数保存在 `analysis/assets/converted-ktx/block-profiles.json`。

| 样本 | mip/面数 | 块数 | HDR/错误 |
| --- | ---: | ---: | ---: |
| character.06569 | 10 | 3700 | 0/0 |
| effects.06289 | 9 | 1368 | 0/0 |
| model.03442 | 3 | 3 | 0/0 |
| scene.00306 | 48 | 2064 | 0/0 |
| textures.00009 | 9 | 1368 | 0/0 |
| ui_model.00019 | 9 | 1368 | 0/0 |
| uires.03481 | 1 | 20336 | 0/0 |

scene 立方体 mip0 六面每面 256 块，均为合法 LDR。因此该样本高 R/B、低 G 的色彩范围不能归因于 HDR 被 LDR 解码。该检查不证明原游戏材质颜色、采样方向、曝光、shader 参数或场景光照已经还原，也不推及未检查的其他 NPK 资源。
