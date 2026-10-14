# ASTC 贴图实际转换

2026-10-14 已将抽样保存的 7 个 KTX1 资源转换为 12 张最高分辨率 PNG。包含 6 张普通纹理以及一个 6 面 cubemap。输出全部位于 `analysis/assets/converted-ktx/`，源 APK 与提取样本未修改。

## 实际验证结果

| 来源 NPK / entry index | 最高级尺寸 | 输出数 | 检查结果 |
| --- | --- | --- | --- |
| `uires.npk` / 3481 | 990 × 820 | 1 | 原角色立绘，含透明通道；已人工视觉查看 |
| `textures.npk` / 9 | 256 × 256 | 1 | 球形高光纹理；已人工视觉查看 |
| `ui_model.npk` / 19 | 256 × 256 | 1 | 黑白条状渐变纹理；已人工视觉查看 |
| `character.npk` / 6569 | 512 × 256 | 1 | 像素解码成功；用途与材质绑定仍未知 |
| `effects.npk` / 6289 | 256 × 256 | 1 | 像素解码成功；效果绑定仍未知 |
| `model.npk` / 3442 | 4 × 4 | 1 | 像素解码成功 |
| `scene.npk` / 306 | 128 × 128 / 面 | 6 | 六个面分别导出；尚未验证引擎坐标/环境映射 |

立绘的 PNG 路径：`analysis/assets/converted-ktx/uires.03481.KTX1.c6557b5b2a4e.m0.f0.png`。其原始 KTX SHA-256 为 `c6557b5b2a4e64ad4d01f93006d92f74bb5dbad794d5f9c03b7347614f2d38e1`，解码后连续 RGBA 像素 SHA-256 为 `5f5362f6e6c241116e1233f551859b48038a7b936b06e8bec1f7da049837e04d`。尚未将此立绘可靠映射到角色 ID，不按外观猜测绑定。

## 转换方式与边界

工具 [decode_ktx.py](../tools/decode_ktx.py) 校验 KTX1 头、大小端、ASTC 枚举、尺寸、元数据、所有 mip/face 长度和文件完全消费。随后通过基于 ARM 官方 `astcenc 5.7.0` API 的小型检查器逐块确认 LDR profile 与有效性，在任何 PNG 写出前拒绝 HDR/非法块；线性格式枚举本身不足以证明载荷是 LDR。最后将所选 mip 的原始载荷提取为标准 `.astc`，交给 ARM 官方解码器生成 PNG，用 Pillow 实际加载验证尺寸并记录像素摘要。此步骤是自编解析器与第三方解码器结果，不是 REA Evidence。

本批样本共 89 个 mip/face、30,207 个块，全部检查为合法 LDR，HDR 和错误块均为 0；包括 cubemap 全部 8 级的 2,064 个块。已用有效的 HDR 常色块、官方编码器生成的非恒定 HDR 块及非法全零块验证拒绝路径。仅靠解码器退出码或“出现紫色像素”来判断会产生误判，因此未采用这些方法。

原包部分纹理的 `glBaseInternalFormat` 错写为 ASTC 压缩枚举。转换器将此差异写入 manifest 警告，直接导出已验证的载荷，不修改原 KTX，也不依赖解码器容忍不规范头。cubemap 的 `imageSize` 按 KTX1 规范解释为每面的大小。

使用原始 `glInternalFormat` 区分 linear/sRGB 解码模式，不自动翻转 UV 或图片。保留 KTXorientation 元数据，不宣称 PNG 已匹配原游戏的材质、光照或坐标。透明区 RGB 可能含纹理边缘延展，导入目标引擎时仍应检查透明混合、预乘和色彩空间。此管线目前仅支持 ASTC LDR 的非数组 2D/cubemap，不覆盖分块虚拟图集、3D 纹理、HDR ASTC 或其它 codec。

`manifest.json` 保存原 NPK member、entry index/offset、样本 SHA-256、每层尺寸/偏移、解码器与检查器 SHA-256、逐块检查统计、导出 ASTC/PNG/RGBA 摘要。失败时不写入新的成功 manifest；同一输出目录可重建相同样本批次。

## 复现

```powershell
# 下载官方固定版本（约 1.7 MB），校验发布 SHA-256，仅解压到项目内
.\tools\setup_astcenc.ps1

$analysisPython = 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
# 利用已安装的 VS 2022 C++/CMake，本地构建官方 API 的块检查器
& $analysisPython tools/setup_astc_inspector.py
& $analysisPython tools/extract_texture_samples.py
$textureSamples = @(Get-ChildItem -LiteralPath analysis/assets/texture-samples -Filter '*.KTX1.bin' | ForEach-Object FullName)
& $analysisPython tools/decode_ktx.py @textureSamples --provenance analysis/assets/texture-samples/resource_samples.json
& $analysisPython -m unittest discover -s tests -p test_ktx.py -v
```

提取器只读原 APK，校验其固定 SHA-256 后从七个 NPK 各提取一个指定索引，并核对每个样本的固定 SHA-256，无需预先全量解包。9 项 KTX 测试包括截断/越界拒绝、大小端、多面/多级、非整块尺寸、元数据、实际 HDR/非法块拒绝，以及用官方 astcenc 解码原包立绘并对照像素摘要。新环境需要 Python 3.11+ 与 Pillow；解码器与检查器路径可通过 `--astcenc`、`--inspector` 指定。当前安装/构建脚本面向 Windows x64，其余宿主可使用相同版本官方源码构建对应平台工具，尚未做实际验证。

## 官方格式与工具依据

- [Khronos KTX1 规范](https://registry.khronos.org/KTX/specs/1.0/ktxspec.v1.html)
- [ARM astcenc 5.7.0 发布与校验值](https://github.com/ARM-software/astc-encoder/releases/tag/5.7.0)
- [ARM ASTC 容器读写实现](https://github.com/ARM-software/astc-encoder/blob/5.7.0/Source/astcenccli_image_load_store.cpp)

下一步是恢复文件名/hash 映射与材质绑定，再在候选引擎中验证实际显示效果；当前仅证明这批纹理已经能够作为通用图片进入新资源管线。
