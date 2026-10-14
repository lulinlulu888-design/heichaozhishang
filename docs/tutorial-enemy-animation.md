# 教程幻眼魔方原始动画采样

已从原 APK 的幻眼魔方 GISACL 库恢复 `idle`、`fire` 两段原始采样，执行的是单独编译的官方 ACL 1.2.0 数据解码器，没有运行 APK 或游戏字节码。两段都完成实际 native 解码、样本回读及数值检查，不只是解析文件头。当前没有 Cocos/原游戏实播验收，也没有证据把 `fire` 等同于技能 990、991 或 992。

生成器为 `tools/sample_tutorial_enemy_animation.py`；机器可读总表为 `analysis/tutorial-enemy-animation/summary.json`。该工具只接受下面的固定 APK、资源和两段动画，不是任意 GISACL 导入器。

## 来源与布局

原 APK SHA-256 为 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。来源链由 `analysis/first-encounter/resources.json`（SHA-256 `eec6d24ba0c3d71f82c43cd1e44d3a0d640ee40dc9fe88bc7a5e9d98d82630a1`）和重新读取的原 APK NPK 表核查。

以下偏移都是 `assets/res/character.npk` 内部偏移；库记录偏移则相对于解包后的 GISACL 库。

| 对象 | NPK 索引 | NPK 偏移 | 解包字节数 | 库片段索引/记录偏移 |
| --- | ---: | ---: | ---: | --- |
| 动画库 | 6081 | 19194576 | 13278 | 8 个片段 |
| 原网格 | 1902 | 20526264 | 314503 | 不适用 |
| idle | 3383 | 19735572 | 40309 | 3 / 7738 |
| fire | 7051 | 19568148 | 26313 | 0 / 4414 |

固定 SHA-256：

| 对象 | SHA-256 |
| --- | --- |
| 库 | `cfcca30bb7ffd1c2bcdfbc43d50af89fa4797ec947816f2605db26af97ddeeb0` |
| 网格 | `21ca9ce44e167ddeeae391c653189176b8d22b784f9f8e944abafd17f41a79fa` |
| idle 包装文件 | `19eecbdc601b10887652a2b1fa30582e5f71fce270f61d5875cf0ff3facfaf8e` |
| fire 包装文件 | `5a35d68491d1cf79509f0c966f24d9ec541705e652334f1dbab290f826b8d5a0` |
| idle ACL | `26de4e5657227f27f19f64dc2c91aefe1dc5c23face79af10cb8811d5bc88a3f` |
| fire ACL | `7615d852c5356a2dd11f2c2e7fc04953e21a71bb5364e245fafaa8de4decbfbc` |

库逻辑路径为 `character/monster/yuanjieguai_yijiemofang/yuanjieguai_yijiemofang.gisacl`。片段按既有 native 读者证据构造为同目录的 `yuanjieguai_yijiemofang_gis_acl/{idle,fire}.gisacl`；提取时同时检查路径散列、NPK 索引/偏移和内容 SHA。

库为 RGIS `0x03070000`，61 个骨名位于偏移 14（每名 32 字节），reference TRS 位于 1966（每骨 40 字节），片段记录起于 4414（每项 1108 字节）。片段包装的 61 个骨 ID 从偏移 4 开始；两段 ACL 缓冲均从 264 开始。包装中的 `53860791`、`00004e2a` 和库片段记录的 opaque tail 仍未解释，原字节及散列保留。

既有静态 native 证据见 `docs/animation-recovery.md`：`libclient.so` SHA-256 `54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`，RGIS reader `0x993ee8..0x9945a4`，clip wrapper reader `0x98fe00..0x99028c`，StringIDMurmur3 `0x18eaf44`，MurmurHash3A `0x18eb5f4`（seed `0x9747b28c`）。本轮没有新增 REA native Evidence；资源解析和自编数据解码器结果分别记录，不能冒充引擎运行观察。

## 实际采样产物

| 片段 | 骨骼 × 帧 | 采样率 | 时长 `(frames-1)/rate` | `.poses` 字节 | 非静止骨数 |
| --- | --- | --- | --- | ---: | ---: |
| idle | 61 × 101 | 30 Hz | 3.3333333333333335 秒 | 246460 | 60 |
| fire | 61 × 36 | 30 Hz | 1.1666666666666667 秒 | 87860 | 61 |

`idle.poses` SHA-256 为 `f3701f3ab70cf0998a185463af3d2c8f27f2445d40f18bb2453575c628b90d22`；`fire.poses` 为 `4807abe1058d438b2873bb73bd266fe397a142a7063b8e57f6cc6cdca22bdcf6`。样本所有分量均有限，回读最大四元数模平方误差分别为 `1.5430266397942205e-7`、`1.7254831607971255e-7`。

每段 `{name}.json` 含源表项、片段骨映射、ACL header、native sampler 收据及 poses hash；`{name}.motion.json` 含逐骨运动范围及首/中/末帧。`acl_hash_verified=true` 只有解码器成功并核对收据后才写入。较早的 `.inspection.json` 只表示 header 勘察，不是解码成功凭据。

样本格式为 20 字节头：`HCZPOSE1`、little-endian `u32 boneCount`、`u32 frameCount`、`f32 sampleRate`；其后按帧、片段 track 顺序储存 10 个 little-endian float32：`qx qy qz qw tx ty tz sx sy sz`。值保留原解码 float32，不做坐标转换、比例校准、四元数符号调整或首尾修补。采样时刻为 `frame / sampleRate`，使用 ACL nearest 采样策略；不能据此断言目标引擎在帧间的插值与循环行为。

独立字节偏移抽查包含：idle 的 root（track 60）第 0 帧平移 `(0.005366206634789705, 12.751466751098633, -1.0059787034988403)`，第 50 帧 Y 为 `13.966865539550781`；fire 的 bone_huan（track 59）第 17 帧平移 `(12.542064666748047, 9.61611270904541, -2.9542524814605713)`，缩放 `(1.3193359375, 1.3193359375, 1.3193349838256836)`。这些是局部变换，不是世界坐标或画面位移。

idle 与 fire 的首末帧最大平移差分别约 `0.000289798`、`0.000691334`，最大转角差约 `0.0405705°`、`0.0462290°`。工具保留差异，没有假定或修复无缝循环。运动骨判定阈值为平移/缩放 `1e-6` 或旋转 `1e-4°`；不是游戏逻辑分类。

## 61 骨绑定与独立 GLB 复核

身份链严格为 clip bone ID → 库名称 → mesh 同名骨。两段均获得 61 个唯一映射；测试使用反转的模型名称表，证明映射由名称确定，不依赖数组顺序巧合。root 的 mesh joint 为 60（ID `4e7443d6`），bone_huan 为 59（ID `64e65c29`）。逐骨映射保存在各片段 JSON 的 `bone_mapping`。

用库 reference TRS 构成局部 `T*R*S`，对比 `inverse(parent raw global bind) * child raw global bind`，61 骨最大元素误差 `8.908938533558342e-7`，完整结果在 `reference-bind-comparison.json`。这里四元数只在比较用矩阵计算时归一化；源采样不变。

独立回读 `analysis/tutorial-enemy/tutorial-enemy-991.colour-reference.glb`（SHA-256 `c39eaba279687e3dd1f3c786d627a6738d6aa6138990ffba20bc4990a79095f5`）和 `bone-map.json`（SHA-256 `fc971450f76fb9a4d47dacf94979aa3bf61f6f639f218eeff07415b8720f030a`），没有调用该 GLB 的导出器：

- mesh node 为 0，mesh joints 0..60 对应 glTF nodes 1..61；node 62 为 identity skeleton 根。父子关系、名字、源 global bind 和导出 local bind 全量比对通过。
- GLB 累积 global bind 对原 mesh 最大误差 `2.6645352591003757e-15`，float32 IBM 对 source inverse 最大误差 `4.564255675632012e-7`。
- 4208 顶点的静止 CPU 蒙皮回读最大位置误差 `7.619430313354769e-7`；导出权重是原权重归一化后的 float32，位置与影响骨映射未改变。
- 两段完整 track → mesh joint → glTF node 映射保存在 `glb-independent-review.json`。复现审查脚本为同目录 `review_glb.py`。

这项复核支持现有骨架与动画名称映射，不解释 native auxiliary bounds，也不验证材质保真或实际引擎蒙皮画面。原先 Elsa 的 auxiliary AABB 假设在本敌人样本不成立；本轮没有放宽共享解析器阈值或篡改源 bind 来消除该差异。

## 解码器与验收

经协调只在 `tools/acl_sample.cpp` 增加上述 idle/fire 两个已核查 ACL SHA，保留原 Elsa 两个 SHA、布局检查、预算限制、输出验证和原子发布。同步更新 `tools/setup_acl_sampler.py` 的 provenance；允许输入总数严格为四个，不接受重算 FNV 后的其它内容。

官方源固定为 [ACL v1.2.0 tag archive](https://codeload.github.com/nfrechette/acl/zip/refs/tags/v1.2.0)，压缩包 SHA-256 为 `167ea61e953e074d5fa0dcaf5b74f009104da0935ef27d0593b989a14cb0c5f8`。已用本机 VS 2022 重新构建，C++ wrapper SHA-256 为 `c2f3e96fc84a7413fd1b060cbea77b48b3cf3818c8b4fc0a754d9802d2b1fdd8`，实际 `acl-sample.exe` SHA-256 为 `2cf331dbfea6146000c770d8bcae223d4b3e0a474c0707e7350a76099df09916`。构建命令和四项白名单见 `decoder-build.json`。

原 `test_acl_sampler.py` 9/9、新 `test_tutorial_enemy_animation.py` 11/11 通过。新增检查包括真实两段解码和固定输出 hash、61 骨身份映射、错误/重复骨名、包装篡改、重新计算内嵌散列仍不能绕过 SHA 白名单、拒绝错误输入时保留既有输出、独立字节偏移样本、reference bind、NaN/截断数据和输出目录逃逸。测试不执行游戏字节码，也没有用静态帧数字段代替实际采样成功。

在项目根目录的 PowerShell 复现：

```powershell
$py = 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py tools/setup_acl_sampler.py
& $py tools/sample_tutorial_enemy_animation.py
& $py -m unittest discover -s tests -p test_acl_sampler.py -v
& $py -m unittest discover -s tests -p test_tutorial_enemy_animation.py -v
& $py analysis/tutorial-enemy-animation/review_glb.py
```

后续动画 GLB 包装和表现层接入应读取这里稳定的元数据/pose hash。游戏技能与片段的关联、循环/过渡选择及播放效果仍需分别验收。
