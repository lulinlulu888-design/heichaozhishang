# 艾尔莎原动画恢复

2026-10-14：已解析艾尔莎原动画库，确定性定位其全部 75 个分离动画文件，并通过官方 ACL 1.2.0 数据解码器恢复 `stand_idle` 和 `skin` 两个片段的逐帧姿态。180 个轨道 ID 与模型骨名逐项匹配。当前完成的是原始动画数据恢复；尚未在新客户端播放、验证动画事件或证明完整动作表现一致。

## 证据来源

原 APK SHA-256：`aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。原 ARM `libclient.so` SHA-256：`54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`。

GIM 模型文件直接引用 `character/player/ailisha/ailisha.gisacl`。本轮通过已恢复的 NeoX 资源哈希定位 `character.npk` 的 index134，解码后 96,082 字节，SHA-256 `2eda877730287d1c0843150eb4050d5b46ab8e910e7d9f3828609b61a98c5b41`。

格式解释来自本机 NDK `llvm-objdump --triple=thumbv7-linux-androideabi` 静态反汇编、实际数据边界和跨文件身份比对，没有加载或执行游戏代码。它们是自编分析工具证据，不是新增的 REA Evidence。REA 原生 provider 的环境限制仍见 README。

## RGIS 动画库

本次仅支持观察到的 `RGIS`、版本 `0x03070000`、分离存储布局：

| 文件偏移 | 内容 | 交叉依据 |
| --- | --- | --- |
| 0 | `RGIS` 魔数 | 原生读取路径与文件头 |
| 4 | u32 版本 `0x03070000` | Thumb `0x993ee8` 版本拆分/检查 |
| 8 | u16 动画数 75 | `0x9942a4` |
| 10 | u32 骨骼数 180 | `0x9942ee` |
| 14 | 180 × 32 字节骨名 | 固定长 C 字符串，NUL 后填充可能非零 |
| 5774 | 180 × 40 字节参考姿态 | `0x9943c2..0x99444a` 按 3/4/3 浮点复制；t xyz、q xyzw、s xyz |
| 12974 | u32 分离文件标志 1 | `0x99445c` |
| 12978 | u32 每条记录 1108 字节 | `0x994472..0x994476` |
| 12982 | 75 × 1108 字节记录 | 正好覆盖文件末尾 |

每条记录前 32 字节是片段名，后 32 字节为根骨名；其余 1044 字节保留为不透明数据，未将疑似时长/偏移猜成已经恢复的字段。

原生 `0x994494..0x9944c0` 将库扩展名替换为 `_gis`，`0x9945a4` 选择格式 `%s_acl/%s.gisacl`。因此实际路径为 `character/player/ailisha/ailisha_gis_acl/<name>.gisacl`。全部 75 个名字均在指定 NPK 中唯一匹配；错误的省略 `_gis` 路径没有匹配，未用文件顺序猜测资源。

## 分离片段与 ACL

包装读取函数位于 `0x98fe00..0x99028c`，先读骨骼 ID 表，然后复制独立 ACL buffer。本次两个片段都使用 180 骨骼：

| 文件偏移 | 内容 |
| --- | --- |
| 0 | u32 骨骼数 180 |
| 4 | 180 × u32 骨骼 ID |
| 724、728 | 两个仍未确认语义的 u32；保留原值 |
| 732 | u32 ACL 字节数 |
| 736 | u32 校验值，与 ACL 内部字段一致 |
| 740 | ACL buffer，长度正好覆盖剩余文件 |

ACL 魔数为 `0xac10ac10`，算法版本为 4；与 [ACL v1.2.0 版本定义](https://github.com/nfrechette/acl/blob/v1.2.0/includes/acl/core/algorithm_versions.h)和[原始解码器](https://github.com/nfrechette/acl/blob/v1.2.0/includes/acl/algorithm/uniformly_sampled/decoder.h)匹配。没有使用版本不匹配的新版 ACL 解读旧数据。

| 片段 | NPK index | 包装字节数 | ACL 字节数 | 骨骼 × 采样帧 | 采样率 | 最后一帧时间 |
| --- | --- | --- | --- | --- | --- | --- |
| stand_idle | 4504 | 53,259 | 52,519 | 180 × 121 | 30 Hz | 4 秒 |
| skin | 4964 | 5,591 | 4,851 | 180 × 318 | 45 Hz | 317/45 秒 |

实际解码两段均通过官方 ACL 哈希验证；全部输出为有限值，C++ 单精度检查报告四元数范数平方误差低于 `2.4e-7`，Python 双精度回读复算低于 `3e-7`。`skin` 的采样姿态是常量，但仍保留原始帧数和时间轴，不因名字或数据特征擅自重定义片段用途。

`tools/setup_acl_sampler.py` 从官方 v1.2.0 tag 获取 MIT 源码，固定归档 SHA-256 `167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8`。源码不修改；本项目封装、构建命令及可执行文件哈希记录在 `tools/runtime/acl-1.2.0/provenance.json`。原 ACL 哈希不是恶意数据的完整边界验证，因此 helper 在任何 ACL 解析/解压前，用 Windows CNG SHA-256 严格限定为上述两份原始 ACL；输出明确带 `validationScope=sha256-pinned-original-clips-only`。不是通用 ACL 导入器。

输出使用独占临时文件，完整写入、flush/close 成功才替换最终文件；失败保留旧目标，输入输出同文件及硬链接均拒绝。Python 入口另外使用新临时路径，核对采样器报告的输入 SHA、版本、帧数、骨数、采样率和哈希验证标志，避免旧结果冒充本次成功。采样器 9 项回归测试覆盖两份真数据及重算 FNV 的畸形内部字段、截断、输出失败和硬链接等情况。

`*.poses` 是临时转换格式：8 字节 `HCZPOSE1`，随后 u32 骨数、u32 帧数、f32 采样率；每帧每骨 10 个 little-endian f32，顺序为 q xyzw、t xyz、s xyz。不是新的原游戏文件格式。

## 骨骼身份与参考姿态差异

原生 `StringIDMurmur3` 位于 `0x18eaf44`，seed 为 `0x9747b28c`；`MurmurHash3A` 位于 `0x18eb5f4`。按标准 x86_32 计算，180/180 片段 ID 与库骨名逐项匹配；库骨名又与 `ailisha_yangcheng.mesh` 的 180 骨一致。映射工具通过身份查找，并拒绝骨名、哈希重复或集合不一致，不依赖数组恰好同序。

独立对照发现：参考姿态按 `T*R*S` 构造后，179 骨与网格局部绑定矩阵的旋转/缩放最大误差 `1.2690e-6`；所有骨平移最大误差 `6.7461e-5`。唯一显著差异为 mesh joint50 `bip001 r toe0`，相对旋转约绕局部 Z 轴 −3.81174°，直接影响 cloth 子网格 39 个顶点，没有子骨。归一化四元数或改变缩放顺序无法消除它。

这支持整体局部坐标约定，但单骨差异成因仍未知，可能来自源绑定姿态与动画参考姿态的制作差异。没有修改源动画，也没有对全部骨骼强行增加修正。后续应保留网格 inverse bind matrices 和源动画姿态，并重点验证这 39 个顶点的实际变形。证据为 `analysis/elsa-model/bind-difference.json`。

## 复现

```powershell
# 首次构建数据解码器（已有 VS 2022 C++ 工具链）。
python tools/setup_acl_sampler.py
# 从原 APK 定址、提取、解析，再采样上述两段动画。
python tools/inspect_neox_animation.py --apk heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk --sampler tools/runtime/acl-1.2.0/build/Release/acl-sample.exe
python -m unittest discover -s tests -p test_neox_animation.py -v
```

本机 `python` 别名不可用时，改用 `C:/Users/5090B/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。不指定 `--sampler` 时只解析包装/头部并明确记录 `acl_hash_verified=false`，不声称重新验证或采样 ACL。

可重复生成的证据放在 `analysis/animation/recovered/`，包括库全表、75 条资源路径、两个片段包装元数据、骨骼映射、原始 ACL、逐帧姿态和摘要。源 sidecar 使用完整扩展名 `*.gisacl.source.json`，避免同名 `.ags` 与 `.gisacl` 的溯源相互覆盖。

未完成项：其余 73 个片段的采样验证、动画事件/切换/混合、动作到玩法的连接、带动画 GLB 导出及客户端实播、原材质和效果还原。
