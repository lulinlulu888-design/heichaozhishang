# APK资源总账与转换管线

统计日期：2026-10-14。原APK约1.98GB，SHA-256 `aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。数据来自保留的清单、脚本索引和本轮恢复报告；普通脚本统计与REA Evidence分开。

## 总量与已完成范围

| 分类 | 包内数量/统计口径 | 当前已完成 | 尚未完成 |
|---|---|---|---|
| APK外层 | 4,360个ZIP条目 | 全部CRC检查通过、原包身份固定 | 不能据此证明线上热更新资源齐全 |
| NPK归档 | 17个包，68,768个索引项 | 全部目录结构、边界、索引读取与路径查找工具 | 未全量解压和按内容分类全部载荷 |
| 游戏脚本 | 9,698个模块条目，9,697唯一路径 | 全部静态解密与marshal解析 | 完整源码反编译、所有事件和执行语义 |
| 配置表脚本 | 1,489个cdata模块 | 公共字面量表提取器；完整角色主表已提取 | 不是所有表均已解析并关联到玩法 |
| Storyline相关模块 | 2,676条路径包含storyline | 已针对伤害、护盾、技能和参数图追踪 | 完整原调度器、全部图语义 |
| card_action/server | 531个模块 | 部分公式、卡牌状态/图已追踪 | 不等于原服务端全部恢复 |
| 英雄 | 35个UseRole=1配置 | 35名单；艾尔莎、琳、不知火模型/颜色参考/待机已转换并显示 | 其余英雄逐角色核验；完整技能、大招、战斗队伍 |
| 场景 | scene.npk中1,150项，识别99个XML场景；表内155条非空路径 | 原序章、城市一、城市二、大厅四份环境颜色参考导出 | 原材质/灯光/全部特效，剩余场景；教程city_battle_3精确路径未匹配 |
| UI与卡牌美术 | 见uires、packed_png归档；外层524张PNG含SDK/Android资源 | 三角色立绘与部分战斗UI/卡牌资源已显示 | 大厅原CSB布局、完整图集、全部交互 |
| 音频 | 外层3,126个WEM、101个BNK；另有wwise.npk31项 | 部分结算音效链已恢复 | 全量事件映射与大厅/剧情/技能声音验收 |
| 视频 | 外层48个MP4 | 已清点 | 播放链、剧情触发和字幕对应未完整验证 |
| 原生代码/Android | 外层24个SO、3个DEX | ARM库身份、部分入口/协议/资源格式追踪 | 原APK执行对照、登录协议兼容与完整引擎渲染语义 |

不能给出可信的“总体逆向完成百分比”：索引、解码、转成GLB、浏览器显示、原版等价是不同验收层级。35位英雄完整原版可玩验收目前为0；三个模型能显示不代表三位已完全恢复。

## 17个NPK分类

| 归档 | 索引项 | 主要用途（按包名） |
|---|---:|---|
| assets/res/uires.npk | 5,707 | UI布局、图集等 |
| assets/res/ui_model.npk | 24 | UI相关模型 |
| assets/res/packed_png.npk | 10,900 | 打包图像/纹理 |
| assets/res/character.npk | 7,501 | 角色模型、骨骼、动画、材质、贴图 |
| assets/res/shader.npk | 3,982 | 着色器及其辅助资源 |
| assets/res/certifi.npk | 1 | 证书数据 |
| assets/res/common.npk | 580 | 共享资源 |
| assets/res/effects.npk | 24,547 | 特效及依赖 |
| assets/res/scene.npk | 1,150 | 场景与依赖 |
| assets/res/textures.npk | 27 | 纹理资源 |
| assets/res/res.npk | 1 | 资源元数据 |
| assets/res/wwise.npk | 31 | 音频资源 |
| assets/res/track.npk | 181 | 演出轨道 |
| assets/res/model.npk | 4,089 | 场景物件/模型 |
| assets/res/animator.npk | 79 | 动作状态机 |
| assets/script.npk | 9,698 | 游戏脚本 |
| assets/assets.npk | 270 | 其它打包资源 |

归档名不是每项载荷类型证明；音频/纹理等还可能出现在其它包中。外层条目与NPK内部条目不能简单相加后称作独立游戏资源数。

## 共用脚本与角色专用脚本

| 环节 | 共用实现 | 专用脚本职责 |
|---|---|---|
| 归档/解包 | tools/extract_npk.py、tools/neox_resource_paths.py | 指定资源的逻辑路径、来源和输出目录 |
| 脚本数据 | tools/extract_game_data.py、tools/inspect_battle_rules.py | 追角色→实体→LOD→模型、卡牌→技能→状态→图；不执行游戏代码 |
| 模型 | tools/inspect_neox_model.py、tools/export_neox_gltf.py、tools/export_elsa_model.py | 选择有证据的网格、材质槽、骨骼，记录例外 |
| 贴图 | tools/decode_ktx.py及固定ASTC工具 | 保留原尺寸、颜色空间和alpha；选择源材质颜色字段 |
| 动画 | tools/inspect_neox_animation.py、tools/acl_sample.cpp、tools/sample_lynn_idle.py::sample_pinned、tools/export_elsa_animation.py | 琳、不知火本体及扇子复用采样构建函数；指定来源哈希、原动作名、格式与骨骼映射，保留已审查输入白名单 |
| 蒙皮/角色导出 | tools/verify_lynn_idle.py::verify_reference_skin、tools/export_lynn_model.py::export_character | 琳和不知火共用导出函数；不知火毛发材质TexBaseColor仅转颜色参考 |
| 场景 | tools/audit_city_scene_dependencies.py、tools/export_city_scene.py | 城市与大厅复用依赖遍历和导出；场景入口固定原表身份 |
| 预览/构建 | tools/prepare_*_preview.mjs、Cocos构建工具 | 哈希校验产物、准备入口、检查真实渲染与原生构建 |

因此不是手工一个一个解包。已实现公共格式解析和转换，按当前场景/英雄提取依赖；专用脚本承担证据与差异审查。也尚未实现一个能对全部英雄无条件一键成功的转换器。原模型、毛发、材质分支、空根字段、不同ACL格式等需要分型处理。

## 提升效率的具体顺序

1. 先建立角色清单→实体→LOD→动作/材质/附属物依赖清单，批量查路径、解析元数据和报告缺项；按资源哈希去重，不重复解压共享贴图。
2. 用艾尔莎、琳、不知火作为格式样本，把共用算法与配置分离。本轮已抽出export_character、sample_pinned和场景参数入口；保留每类已审查ACL格式与输入白名单。
3. 建立按输入哈希缓存的任务清单，阶段依次为提取→解析→转换→数值校验→渲染验收。每步失败记录类型、资源名和原因；失败不能自动换角色或编造资源。当前尚未实现完整缓存调度器。
4. 批量自动处理元数据、贴图和可支持格式；对材质差异、骨骼映射、镜头/特效、动态规则单独审查。优先大厅主链，不把所有英雄先转完当作恢复大厅的前置。
5. 每轮只跑受改动影响的格式与来源检查，随后做一个真实客户端场景验收；使用持续资源总账更新已解析/已转换/已显示，避免重复调查已固定结论。
6. 画质优先恢复原材质与光照、UV平铺、采样和渲染尺寸。原资源保留独立版本；高清增强若需要，作为可选衍生资源记录，不能用放大贴图冒充恢复高分辨率原图。

## 大厅画质记录

环境导出实际使用61张颜色纹理。以下只统计该导出消费的KTX，不混入全部法线/遮罩依赖：

| 源尺寸 | 数量 |
|---|---:|
| 4×4 | 1 |
| 32×32 | 1 |
| 64×64 | 11 |
| 128×128 | 16 |
| 256×256 | 18 |
| 512×512 | 7 |
| 1024×1024 | 3 |
| 2048×2048 | 4 |

当前大厅是Three.js独立预览，16:9画面、devicePixelRatio上限2、设备最高各向异性过滤。原颜色贴图尺寸没有主动缩小；未恢复完整原shader、法线、反射、光照和特效，画面清晰度和质感不能据此归因于Cocos性能。

## 相关文档

- [35位英雄恢复进度与燃尽基线](recovery-progress.md)
- [大厅与不知火恢复](hall-recovery.md)
- [目标对照审计](goal-alignment-audit.md)
- [逆向总记录与REA证据边界](investigation.md)
- [复现分析](reproduce-analysis.md)

运行 `python tools/build_resource_ledger.py` 可按当前保留清单重建此资源总账；机器结果位于analysis/resource-ledger/summary.json。
