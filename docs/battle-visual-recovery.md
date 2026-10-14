# 原版战斗画面恢复

用户明确指出现有界面与原游戏不符。当前界面是数值/HTTP/存档调试工具，不是原版画面恢复成果。优先恢复原场景、镜头、角色站位、卡面、战斗UI和动作表现；不要继续把矩形面板美化视为画面还原。

## 当前源数据锚点

原 APK 解码表 `maze_battle_table_6.py` 的战斗5000引用 `BattleScene=2081`。本轮使用现有只读字面量解析器，从脚本索引9650的 `common/cdata/scene_table.py` 提取2081行，输出 `analysis/battle-visual/scene-2081.json`，含源字节偏移与SHA-256。这是自编工具的静态证据，不是新REA Evidence或运行观察。

- 名称：战斗场景-红色城市。
- 场景逻辑路径：`scene/city_battle_3/city_battle_3.scn`。
- 默认镜头：`camera_1`。
- 玩家位置：[20.514759, -9.08, -35]。
- 敌人站位表含5个位置；朝向[0, 1.57, 0]。
- 音乐事件：`BATTLE_NORMAL_7`。
- 表内有Bloom/HDR参数；不代表新引擎可直接复用原渲染。

当前对完整路径和scene挂载相对路径的精确哈希查找均没有命中。仅说明这两种名字没有找到；尚未检查场景编译后后缀/打包重命名，不能推断APK缺少该场景。下一步跟踪场景加载器的路径转换后再定位载荷。

同时已定位原战斗UI自动生成脚本，如 `uires_FightPanel_SimUI_ModelUIArea.py`（9528）、`IntentionArea.py`（2885）、`CardDetailInfo.py`（636）及 `logic/scene/BattleScene.py`（9560）。需结合旧布局与虚拟图集解析还原，不可把脚本文件名当作视觉对照。

## 下一步验收

光照预览接入：精确路径哈希确认 `shader/built_in/common/function.hlsl` 对应索引430；内置common.hlsl（1336）引用该文件，系数为(0.299,0.587,0.114)。保留提取来源于lightmaps/shader目录，区别于另一套旧函数系数。新增 `prologue-lightmaps.js` 以原UV1、实例UV偏移/缩放和原scale/add解码7张线性光照图，157个实例绑定全部通过运行检查。简化预览将解码结果乘到颜色漫反射上，不等同于完整原BRDF、灯光与HDR后处理。

浏览器实际开关对比成功，未记录shader错误或警告；截图 `analysis/battle-visual/scene-export/preview-lightmap.png` 可见建筑阴影与红色烘焙光。仍需恢复高光、动态灯光、材质发光、雾、特效及原镜头裁切；此参考效果尚未移植到Cocos或Android。预览默认开启，按钮可回到颜色贴图对照。

光照资源进展：`tools/prepare_prologue_lightmaps.py` 校验APK及场景身份后提取并转换全部7张线性KTX光照图（1024×512或2048×1024），校验157项实例/子网格绑定均有UV1、合法贴图索引和匹配的子网格数量。原texture_index、uv_ofs、uv_scale、encode_type、lightmap_scale/add等保存在 `analysis/battle-visual/lightmaps/bindings.json`，没有用猜测值替代。

原default_functions.hlsl的UE4分支显示按scale/add还原后，经 `exp2(LogL*16-8)-0.00390625` 与0.6方向系数解码。进一步在shader.npk找到三个Luminance定义：索引430用(0.299,0.587,0.114)，索引1748/291用(0.2126,0.7152,0.0722)。必须继续确认该材质编译链采用哪一个，不能默选系数把错误亮度写进预览。此轮没有宣称光照已接入或画面已改善。

天空透明修正：源File_39至45的材质使用 `shader/common_nolightuv.fx::TShader`、TransparentMode=2；对应FX/NFX/HLSL均从原APK提取到 `analysis/battle-visual/sky-shader/` 并保留来源哈希。两张2048×2048天空纹理alpha范围均为0..255，HLSL `ps_main` 返回纹理alpha乘blendValue。导出器现仅对这组明确匹配的天空材质启用GLB BLEND，其他材质不猜测枚举。直通alpha混合是目前的移植参考，不声称已恢复原生混合状态或HDR逆变换。

浏览器重新加载后可见原先几条矩形云层接缝消失，截图 `analysis/battle-visual/scene-export/preview-sky-alpha.png`。外侧背景边缘仍可见，灯光、源模型可见条件、天空UV运动、源相机方向和完整原版色调仍待恢复。新GLB大小10,634,732字节；之前结构检查报告对应旧文件，不能视作此版独立校验。

实际预览：已新增 `tools/templates/prologue-preview.html` 和 `tools/prepare_prologue_preview.mjs`，使用固定Three.js 0.180.0作独立转换检查器，不替代Cocos客户端。全部脚本和GLB本地加载，复用7456静态服务，入口 `/prologue/`。浏览器实测加载成功、两台源镜头按钮切换成功；可见城市平台、建筑、异物、人物与天空贴片。截图 `analysis/battle-visual/scene-export/preview-camera2.png`。这也暴露了天空贴片边缘、光照缺失等问题；不是原版视觉一致性验收或战斗集成验收。

复现预览：先 `npm install --prefix tools/runtime/scene-preview --no-audit --no-fund --ignore-scripts three@0.180.0`，再运行 `node tools/prepare_prologue_preview.mjs`。Cocos重建会覆盖build目录，之后需重新执行该准备脚本。原相机采用+Z前向到glTF/Three -Z前向转换假设，尚待原运行截图核对。

整场景组装进展：`tools/export_prologue_scene.py` 重新校验原APK哈希及场景XML哈希，提取45个模型的GIM/mesh/MTG和14张Tex0图，形成 `analysis/battle-visual/scene-export/prologue-scene.glb`（10,633,996字节）。它含165个原模型实例、53材质；缺失的probe实例没有替代。所有源实例属性保留在节点extras，源镜头参数保留在场景extras。GLB范围、accessor尺寸、三角索引、材质引用和节点矩阵检查通过。

此文件仍为不受灯光影响的颜色参考：场景模型Flag/RenderCondition、透明度、光照贴图、雾、天空和特效未还原，源矩阵到glTF的约定尚待视觉核验；省略的变换字段暂用单位旋转/零平移/单位缩放。镜头目前只是保留数据，尚未成为已验证可用的运行镜头。不能把文件导出当作原版场景画面验收。

模型转换进展：`tools/export_prologue_building.py` 已将场景File_1建筑提取为GLB（`analysis/battle-visual/building/prologue-building.glb`），包含1,006顶点、561三角形和原128×128 ASTC Tex0颜色贴图。源GIM的边界保留到小数点后两位，独立边界误差0.00756在该精度范围内。当前是unlit颜色参考，未还原灯光、法线、混合纹理或源shader效果；不能当作原版画质验收。

进一步逐项提取并解析了AllFiles中的46个GIM对应mesh：45个解析成功，只有model/test/probe.mesh未找到，详细源哈希及结果在 `analysis/battle-visual/geometry/audit.json`。这表明场景几何转换可以继续推进；其余材质、贴图递归完整性与最终场景摆放仍需验证。

后续扫描进展：`tools/find_battle_scene.py` 对scene.npk全部1,150项进行了限长解压和尺寸校验，找到唯一包含city_battle_3字符串的载荷。它是索引220，SHA-256 `410761fae3aee0b8c67e9505831942d99eafb1dfa3380ea1a2e3699c963d53f7`；精确逻辑路径哈希进一步确认身份为 `scene/chess_xuzhang/chess_xuzhang.scn`，不是city_battle_3场景本身。载荷是可解析NeoX XML，含166模型实例、3台镜头、118灯光节点、16特效实例。AllFiles的53项引用中52项在APK索引唯一匹配，仅 `model/test/probe.gim` 未匹配；这不是递归资源完整性证明。已生成含源位姿与引用的 `analysis/battle-visual/prologue-scene-manifest.json`，下一步可据此转换真实序章场景。尚未导出场景几何或渲染。

先交付一个有原资源出处的完整战斗场景画面：场景和镜头、场上角色/敌人、原风格手牌与必要HUD；再把已有战斗状态驱动画面与动作。原版资源无法解析的地方明确列出，未恢复特效不冒充已还原。用户截图证明当前预览已显示胜利状态，但没有证明原版画面还原或Android完整通关。

2026-10-14 序章人物接入：`tools/export_prologue_actor.py` 独立锁定场景 File_26 的 GIM/mesh/MTG 哈希，验证其引用 ailisha.gisacl，使用场景版 12,677 顶点模型自己的 180 根骨骼及逆绑定矩阵。复用同源 Tex0 转换与已校验 ACL 样本，导出 `analysis/battle-visual/actor/prologue-elsa.glb`（3,844,212 字节）。全部 121 帧、540 动画通道回读验证通过；此模型不能与养成版模型混用绑定矩阵。stand_idle 是预览选择，未证明原序章脚本此时选择该动作。

独立场景预览通过源 UUID 精确替换一个静态人物节点，保留源实例变换，接入 AnimationMixer。浏览器实测输出 loaded 165 instances、lightmaps bound 157、original scene actor idle playing 4，无 error/warn；截图 `analysis/battle-visual/scene-export/preview-animated-actor.png`。人物材质仍是颜色参考，天空边界、镜头约定、特效与原版战斗 HUD 未完成；此预览尚未接入 Cocos 战斗操作。准备预览前增加运行 `python tools/export_prologue_actor.py`，再执行 `node tools/prepare_prologue_preview.mjs`。

2026-10-14 Cocos 接入：新增 prepare_cocos_prologue.py 校验两个已导出 GLB 的报告哈希后复制到 resources/recovered/prologue，提取源镜头 JSON；prepare_cocos_assets.py 已调用该步骤。PrologueSceneView.ts 通过导入 Prefab 构建场景，找到唯一 ailisha_1565 节点，以原位姿替换为场景版蒙皮人物，循环播放 stand_idle。主界面“查看序章场景”提供全屏 RenderTexture 与返回入口，模板同步保留。构建指纹加入场景脚本、两个 GLB 与镜头 JSON。

严格 TypeScript 检查（skipLibCheck）通过，Creator Web 实际构建 exit 36。浏览器真实点击后可见原场景与人物，日志 HCZS_PROLOGUE scene and original actor loaded，无 error/warn。截图 analysis/battle-visual/scene-export/cocos-prologue-first-run.png。本次验证仅 Web；Cocos 尚未接入烘焙光照，画面显著偏平，天空边界仍可见，尚无战斗 HUD/出牌驱动画面。没有把它称为原版画质或跨平台运行验收。

2026-10-14 Cocos 烘焙光照：新增 cocos-prologue-lightmap.effect 与 PrologueLighting.ts，将同一 source UV1、每实例缩放/偏移、encode_type=4 解码参数接入共享引擎。prepare_cocos_prologue.py 校验七张 PNG 的解码报告哈希并复制光照绑定 JSON、effect；依源唯一节点名字绑定 157 处材质，保留原基础颜色贴图。使用 getSharedMaterial/setSharedMaterial，清理首次运行的弃用警告。光照材质随场景销毁释放。

严格 TS 检查通过；Web 构建 exit 36。浏览器实际打开场景，最新运行日志 00:19:27 UTC 显示 lightmaps bound=157、scene and original actor loaded，最新运行无新增 warning/error；截图 analysis/battle-visual/scene-export/cocos-prologue-lightmaps.png 显示建筑明暗及红色烘焙光照已进入 Cocos。解码仍是参考漫反射乘法，不是完整原 BRDF/HDR 管线；动态灯光、雾、特效、天空边界和战斗集成仍未完成。尚未重建/运行原生平台版本。

2026-10-14 场景战斗集成：TutorialBattleView 以 PrologueSceneView 作为全屏场景，移除中央数值面板、立绘和敌人缩略图，将生命、能量、意图及动态手牌排布在场景上。空手牌位隐藏，最多十张按数量缩放排列。复用既有控制器、服务端与存档，不改变战斗规则。

battle 模式复用原场景艾尔莎位置，敌人991放在其 x+29 处，镜头采用近景重建位姿；这两项是重建展示配置，并非原脚本站位/镜头证据。独立序章查看入口仍使用源镜头2。敌人、角色都播放已恢复的待机；攻击、受击、死亡演出尚未接入，胜利时敌人仍显示，不能当作演出完成。原卡牌美术尚未加入。

严格 TS 检查通过，Web 实际构建通过。浏览器真实打开首战，恢复此前胜利存档；点击重开首战后回合1、能量5、敌方生命4600，再点击二连斩击，界面显示能量4、生命3878、手牌5与战斗操作已保存。截图 analysis/battle-visual/scene-export/cocos-battle-card-play.png。本次未在该新画面完整通关或验证 Android；15组既有真实 HTTP/存档控制器测试均通过，不能替代新界面完整游玩验收。

2026-10-14 结算场景同步与浏览器游玩验证：PrologueSceneView.setOutcome 接收战斗快照；胜利隐藏敌人、玩家被击败隐藏玩家、回合上限失败保留双方，结算时暂停待机。重新开始恢复模型与待机。该退场是显式重建处理，并非原死亡动画；fire 与技能关系仍未确认，未擅自绑定。

严格 TS 与 Web 构建通过。浏览器实际恢复上一轮保存的首回合（敌人3878、能量4），依次出牌，结束回合，第二回合击败敌人。实际战斗结果：玩家1466.8/1768.8、敌人0、回合2、能量1，敌方模型退场。随后完整重载页面并重新进入首战，仍恢复上述胜利状态且敌人不再出现，日志无 warning/error。截图 analysis/battle-visual/scene-export/cocos-battle-victory-restored.png。证据证明此次 Web 场景的继续战斗→结算→保存→页面重载恢复；未重启服务进程，未验证新版 Android，也不证明攻击/死亡演出完整。

2026-10-14 原卡图定位：tools/inspect_card_virtual_textures.py 从锁定SHA的APK重新提取 vt_config.jsondata 和 vt.table，对首战五张牌的 CHARACTER_IMAGE 做大小写规范化精确匹配，获得完整路径→相对图片名→四字段页映射。斩击15.png=[249,0,3,3]、猛力斩击219.png=[224,4,3,3]、强力斩击1.png=[352,0,3,3]、二连斩击aiersha2.png=[36,19,4,3]、疾驰斩击aiersha4.png=[162,9,3,3]。均没有独立资源直接匹配，不表示图像缺失。

vt.table 精确命中 packed_png.npk index1721，193,460字节；观察到版本0、47个NUL结尾名字记录，随后12,032个四uint32记录，恰好消费全部载荷。长度、重复key和尾部检查通过；截断、异常长度和尾部附加三种破坏样本均拒绝。完整证据 analysis/card-art/card-vt-links.json 与 vt-table-raw.json。四字段语义、块文件名、codec、拼图/裁剪旋转仍待确认，未生成可用卡图。该结果是本地静态解析，不是REA运行证据；REA会话查询确认当前无打开目标，未重复已知不可用的原生引擎调用。

2026-10-14 VT页表索引推进：本地LLVM Thumb反汇编 libclient.so 的 d32e7e..d32eaa 显示连续读取前三个uint32和偏移12的uint16，采用 ((word2 >> 14) & 511) | (halfword3 << 9) 写入16位索引。保存 vt-table-loader.thumb.txt 和 vt-page-loader.thumb.txt。全量表关联验证：word0全部0；word1在该层唯一；word3的47种值全部对应名字表，且每组256条，word2严格从16,384到4,194,304递增16,384。这是索引编码证据，尚不能把word2直接解释成文件末偏移或证明像素块尺寸。

2026-10-14 首战卡图像素恢复：继续跟踪 d37434 → d361ec，确认名称由目录/名字表项、斜杠、低9位索引左移14位后的十进制串构造。`packed_png/vt_data/astc/alluires_24/16384` 精确命中 index10250，解压为16384字节。d33fea 的上传宽高128与 d3454a 的虚拟坐标步长124对应物理页/有效页尺寸。保存 `vt-filename-builder.thumb.txt`，这些属于本地静态证据，不是REA运行观察。

新增 `tools/probe_card_vt_tiles.py` 对首战五张牌提取48个块，使用明确标记为合成的ASTC4×4 KTX包装，经块验证和解码后按512列虚拟坐标、每边2像素边界拼接。修复页表名字中末尾多NUL填充的解析，只接受首NUL之后全零。新增 `tools/find_card_sprite_frames.py` 有界扫描非物理页资源，精确找到五个图片名的原plist frame，均286×286、无旋转无trim；按原frame坐标裁出五张单独PNG。可复现顺序：inspect_card_virtual_textures.py → find_card_sprite_frames.py → probe_card_vt_tiles.py。

输出在 `analysis/card-art/tile-probe/card-{id}.png`，manifest保留每块来源哈希、解码验证、原plist坐标和输出哈希。已目视核对斩击拼图、艾尔莎两张单卡，内容连续且不混入邻图；原运行颜色空间仍未确认。尚未接入Cocos手牌，本次不宣称试玩界面已更新。

inspect_card_virtual_textures.py 增加上述全量不变量检查，输出 analysis/card-art/vt-table-index-evidence.json（含原生库与表哈希、指令范围、组关联）。在已知ASTC目录下试验50个常见命名候选均无资源哈希匹配，未当作资源缺失结论。仍需追踪物理块路径构造与加载器，未生成卡图。

2026-10-14 原卡图进入实际手牌：prepare_cocos_cards.py 校验五张提取PNG的SHA后复制至Cocos resources/recovered/cards，保留完整来源manifest；通用资源准备脚本和构建指纹已纳入卡图。TutorialBattleView按精确cardId加载SpriteFrame并管理引用，未知自定义牌保留文字显示。手牌改为156×220竖向展示，按数量等比缩放；卡框和布局仍是重建UI，不是原版卡框。

严格TypeScript检查、Web构建通过，15组真实HTTP/SQLite控制器测试通过。浏览器实际重开首战显示六张原图手牌，点击二连斩击卡面后能量5→4、敌人4600→3878、手牌6→5，随后重载页面并重新进入，恢复相同状态和对应卡图。最新浏览器日志无warning/error。证据截图 analysis/battle-visual/scene-export/cocos-original-card-art.png。此轮仅验证Web；Android/Windows未重新构建验证，攻击/受击动作与特效仍未接入。

2026-10-14 原技能动画资源映射：新增 tools/trace_card_animation_assets.py，从首战技能时间轴TYPE=0行关联艾尔莎ENTITY_ID=0的ANIM_STATES字段，再关联锁定哈希的ailisha.gisacl库。五张牌映射：斩击/强力斩击/疾驰斩击→fire_1，猛力斩击→crit_1，二连斩击时间轴2983列出ATK_3/ATK_5/ATK_2→fire_1_1/fire_1_3/fire_2。全部五个不同动作在原APK中精确命中并提取，180骨映射通过；帧数分别27/58/37/39/29，30Hz。输出 analysis/battle-visual/skill-animation/mapping.json 及各clip原载荷与来源哈希。

哈希验证的SkillTimelineActions.py index7810及SkillHelper.py index2072静态指令表保存在同目录。getSkillDurationAndReactTimeList逐个读取attack和attack_1..20事件并累计动作时长；SkillPlayAnimationAction.doInit将攻击事件列表末项作为duration。BattleAnimRandomData存在实体0的随机动作配置，因此时间轴列表不应直接当成固定顺序播放证明。事件时间、状态机实际选择、根位移仍需追踪；新clip仅通过包装头/骨架映射检查，未进行完整ACL采样或接入渲染。本次未改变试玩画面。

2026-10-14 攻击姿态采样和模型导出：新增 sample_card_attack_animations.py，保持旧四动作采样器和provenance不变，在独立attack-wrapper/attack-build构建五个明确SHA输入的ACL1.2.0解码器。构建前核对官方archive SHA、已安装全部includes字节及参考wrapper SHA。原攻击数据has_scale=0，fire_1/fire_2无segment range reduction，依据官方compressed_clip.h字段定义调整专用检查为两轨/0或7段范围标志，仍仅接受五个固定SHA。实际采样全部通过，共34,200个骨骼帧，保留输入哈希、骨映射、采样器哈希与输出姿态哈希。

export_prologue_actor.py --with-attacks 将五个原攻击clip连同stand_idle导入场景版180骨/12,677顶点模型，输出独立 analysis/battle-visual/actor-attacks/prologue-elsa.glb（5,825,820字节）。六clip全部逐帧GLB回读通过，姿态保持原float32（允许等价四元数符号），每clip540通道；逐帧CPU蒙皮范围检查通过。原可玩版本actor目录未覆盖，未宣称引擎实际播放或攻击演出已接入。

CompAnimation.py index8905静态函数确认getAnimationEventTime通过getRealAnimNameByType映射，调用Model.getAnimationEventTimeMilliseconds，再除1000；GIM里的AnimTrigger记录引用fx_fire事件和原sfx路径，但本轮未找到事件时间。命中时间、动作序列/随机化与特效仍未恢复。

2026-10-14 原攻击事件轨定位：trace_attack_event_tracks.py 从原APK精确提取 character/player/ailisha/ailisha.ags，SHA12702cdbf02201e0637ca1410db6abe9787c29a05ea1514d4c5f5b9a7318e729，AnimationEventTracks Version2。五动作均找到attack事件；fire_1_1/3/2另有jump_next。原比例保留在event-tracks.json，乘ACL采样时长得出的秒数明确标记derived_seconds，不冒充原引擎观测。

首段fire_1_1的attack比率0.350154、jump_next比率0.454167（按1.2秒推导0.4201848/0.5450004秒）；fire_1_3对应0.409156/0.533619。SkillHelper.getAnimationListInTimelineData只在len(retAnimList)==1时进入random.choice，纠正此前“可能随机打乱二连列表”的疑虑。SkillState._realPlayAnimation明确在useJump且jumpTime>0时用jump_next替换animationTotalDuration。相关6025/2072/8905/8067/7522模块指令与哈希已保存。仍需追踪动画结束调度、玩家特写延时，以及视觉jump_next与伤害helper全时长累加之间的关系；当前未修改游戏演出。

2026-10-14 调度结论修正与首次客户端接线：补读SkillState._enterLogic/onEventAnimEnd，确认end事件调用_playNext；_realPlayAnimation中jump_next只缩短endPlayerFocus定时器，不能据此截断动画。二连斩击reactCount=2，两个动作各含一个attack，按完整长度播放fire_1_1→fire_1_3，第三项不是本次两击必须播放。先前有关“jump_next提前切换动作”的文字已被本段纠正。事件提取工具已更新并保存9615玩家特写配置原始指令。

prepare_cocos_prologue.py改用actor-attacks导出物；PrologueSceneView按服务端已确认CardPlayed播放源clip，二连接两个FINISHED事件，完毕回待机；TutorialBattleView用战斗id/revision避免刷新重播，播放期间锁操作，离开时取消并恢复。单段牌当前采用原时间轴默认动作，未恢复随机变体、特写位移、受击、武器特效；数值仍即时显示服务端快照，不宣称原命中同步。

严格TS、Web构建、15组控制器回归通过。浏览器确认出牌扣费/伤害正确、动画调用和完成后控件解锁、重载不重播。运行日志fire_1在0.3秒采样显示time=0.2836、weight=1。重要未解决项：连续截图中人物仍呈待机外观，尚未取得可见攻击姿态证据；不能把状态机运行当作蒙皮画面成功。已确认导入Prefab含SkinnedMeshRenderer、六动画以及一致NeoX skeleton roots/bip001路径，无error/warn，需继续检查蒙皮渲染/姿态绑定。证据attack-frame-0..15.png、cocos-attack-play.png。当前战斗存档已到首回合能量0，敌人2288。Android/Windows未更新。


### 2026-10-14：修复实时骨骼动画初始化顺序

人物在加载敌人时随 stage 提前激活，默认 baked 状态已经初始化；之后切换 useBakedAnimation=false，Creator 3.8.8 的 SkeletalAnimationState.setUseBaked 虽再次调用父类 initialize，但 _doNotCreateEval 仍为 true，导致状态时间前进却没有 clip evaluator。现于人物接入场景前设置实时模式。没有修改引擎内部实现。

浏览器真实出牌验证：猛力斩击 crit_1 在 0.2836 秒时，左上臂 quaternion 从 [0.01788,-0.22155,-0.45371,0.86299] 变为 [0.27282,0.12563,-0.18950,0.93481]；截图 analysis/battle-visual/scene-export/attack-fixed.png 可见俯身攻击姿态。临时逐骨骼诊断日志已移除。攻击后恢复待机，按钮重新可用。Web 构建和严格 TypeScript 检查通过。

这仅确认恢复动作在重建场景中播放；武器、原技能特效、原版镜头/移动、原版界面仍未完成。


### 2026-10-14：原武器绑定证据与校验缺口

新增 `tools/inspect_elsa_weapon.py`，只读核对 APK SHA-256 并按人物 GIM 的真实引用提取武器 GIM/mesh/MTG；重跑产生 `analysis/battle-visual/weapon/binding-report.json`。这是本地静态证据，不是 REA 原客户端运行证据。

- 原 `File_26.gim` 的 `wuqi` socket：BindType=263、MatrixToBone 为单位矩阵，Active=true，引用 `character/player/ailisha/ailisha_weapon.gim`。没有擅自解释 263 的原生语义。
- 武器网格 1,224 顶点、1,768 三角形、137 骨骼；所有顶点恰好单骨骼权重 1，唯一使用骨骼是索引 28 `bip001 prop1`。
- 武器与人物 prop1 全局绑定矩阵不同，最大元素差 30.810914。不可直接以人物绑定矩阵替换武器逆绑定。
- 原武器自身 GIM 也引用 `ailisha.gisacl`，并在 prop1 上挂 `weapon_dao.sfx`；模型材料另有 subsurface 表面与 lancer2 特效层，不能把噪声纹理当普通颜色图。
- 现有独立 AABB 校验失败：误差 5.6053896。记录局部盒中心约 (0,4.11387,0)、半径尺寸 (0.245405,4.11387,0.245405)，而网格经该逆绑定所得局部范围约 X[-1.15418,0.78711]、Y[-2.32383,13.83313]、Z[-0.44098,0.38440]。骨骼辅助包围盒是否过期、或武器存在不同坐标处理，尚未判定。

脚本明确记录 validated=false；本次没有绕过校验导出蒙皮或把未验证武器接入预览。下一步应追踪 BindType=263 的附件装配与动画骨骼绑定关系，并独立核对武器模型局部变换。现有已验证战斗预览不变。


### 原武器静态模型导出（绑定问题仍待解决）

`tools/export_elsa_weapon.py` 新增可复现的原坐标静态 GLB 导出。GIM 两个子网格的独立包围盒与 mesh 顶点分别相差最多 8.02e-5、7.11e-5，均通过既有 1e-4 容差；因此几何与材质槽对应得到独立验证。骨骼辅助盒失败仍保留，尚不能据此判定数据过期或原引擎处理方式。

导出 `analysis/battle-visual/weapon/elsa-weapon-static.glb`（446,060 字节，SHA-256 17e9dc3b061ead7aa333215f22920aef706f4403e44f32765cf476302fa7babe），只含表面层和恢复的 weapon_d 颜色纹理，不创建 skin、不推断挂载。lancer2 噪声特效层未冒充颜色材质。该文件是检查产物，尚未接入客户端或视觉验收。

导出后独立读取 GLB：612 个坐标和 884 个三角形逐项与源网格完全一致，嵌入 PNG 哈希与转换记录一致，确认没有 skin 字段。骨骼绑定方向、武器跟随攻击和原特效仍未完成。


### 2026-10-14：武器联合预览与 Cocos 实战挂载

新增 `tools/templates/weapon-preview.html` 和 `tools/prepare_weapon_preview.mjs`；运行前先执行 `node tools/prepare_prologue_preview.mjs`，再执行武器预览准备脚本。诊断页 `/prologue/weapon.html` 可选原动画、暂停、逐时间采样、隐藏武器。

联合预览采用明确的重建假设：顶点单骨骼权重为 1，因此以动画 prop1 节点世界矩阵乘武器源逆绑定矩阵变换静态网格。不替换为人物逆绑定，也不修改源顶点。fire_1 的 0.3 和 0.6 秒截图目视显示握柄与手相邻、刀身随挥击转动；stand_idle 中 prop1 把武器移出身体附近。此可视结果支持重建挂载方案，不证明原 BindType=263 或辅助骨骼包围盒的原生语义，原失败记录未删除。

已将相同挂载接入共享 Cocos 战斗视图，准备脚本按 GLB 哈希复制武器并输出绑定数据，按唯一骨骼名称挂载。客户端不执行未经确认的 GIM 特效触发器。严格 TypeScript 检查和 Web 构建通过；浏览器真实从存档进入战斗并打出“斩击”，敌人生命 843→458、能量 2→1，截图 `analysis/battle-visual/weapon/cocos-weapon-attack.png` 可见持刀挥击。诊断截图 `attachment-fire1.png` 保留。发光、拖尾、subsurface/lancer2 原材质、原引擎精确挂载语义仍未恢复；未将 Web 验证扩大为 Android/Windows/macOS/iOS 运行验证。


### 2026-10-14：lancer2 武器流动层诊断预览

新增 `tools/recover_weapon_effect.py`，原包哈希核对后提取原 `shader/lancer2.fx`、`shader/shaderlib/function.fxl` 和 noise_gq_rlt_01/noise_100 两份 KTX，解码原噪声并导出第二层网格 `weapon-overlay.glb`。全部路径、哈希、参数、转换记录及未恢复项位于 `analysis/battle-visual/weapon/effect/report.json`。

原片段公式：distortionUV=uv+t*(0.1,-0.1)，colourUV=uv+distortion.r*0.1+t*(0.1,0.2)，线性 RGB 为转换后的噪声颜色乘 3 再乘转换后的 (1,0.207843,0.470588)，alpha 取噪声 alpha。运行时宏可能改变分支；function.fxl 的 sRGB 转换包含分段 IEC、幂 2.2、平方三种，当前未证明原运行时选择。

仅在 `/prologue/weapon.html` 的诊断预览移植该公式，明确选择幂 2.2 与普通透明混合。没有将 TransparentMode=5 擅自等同于已恢复混合模式；未移植 HDR 编码、Bloom 或 -10 mip bias。主 Cocos 战斗仍使用已验证表面武器。

浏览器 shader 无错误/警告；固定 fire_1 的 0.3 秒姿态后，frame-a.png/frame-b.png 记录随时间变化的纹理。变化像素统计见本次工具输出。这证明独立预览中的纹理流动，不证明原生游戏视觉等价或全平台完成。


### 2026-10-14：敌方普通攻击接入战斗

原 `skill-timelines.json` 的时间轴 558：技能 990、TYPE=0、ANIMATION_LIST=[ATK_1]；`enemy-entity.json` 的实体 6605 将 ATK_1 映射为 fire。991 的时间轴 559 使用 SPL_1（skill_2），992 的时间轴 560 使用 SHD_UP_2，未用 fire 冒充两者。

PrologueSceneView 增加敌方动画引用和共用序列播放器；TutorialBattleView 对同一战斗新 revision 的 EnemySkillUsed 事件播放已知 990→fire，并在动作结束后回 idle、解除按钮锁定。离开/销毁仍通过现有取消路径清理 FINISHED 监听。伤害数值继续即时采用服务端快照，命中时点、受击动作和特效尚未同步。

严格 TypeScript 检查、Creator Web 构建通过。浏览器从第 2 回合存档继续，通过结束回合推进到第 4 回合普通攻击；源 fire 实播截图 `analysis/battle-visual/scene-export/enemy-fire.png` 显示魔方展开并前倾，角色生命 1064.8→762.8，第 5 回合动作结束后回 idle 且手牌/结束回合按钮重新可用。控制台无错误或警告。没有新增跨平台运行验证。


### 2026-10-14：强化攻击与护盾原动作

新增 sample_enemy_skills.py（独立哈希白名单的 ACL 解码器）、export_enemy_skills.py。原时间轴 559/560 对应实体 6605 的 SPL_1=skill_2、SHD_UP_2=skill_3。原片段分别 91/66 帧、61 骨骼，新增 9,577 组骨骼样本；连同原 idle/fire 导出四动画 GLB 后共 17,934 组采样回读通过，均有实际顶点运动。旧二片段产物保留，旧导出器默认校验保持不变。

新 enemy-skills.glb 为 1,541,720 字节，SHA-256 776f33dfc9a53ffaeafc4f0bdb3d9401a1e9391bc8a77bf11bac229d772ab8be。Cocos 通过新 recovered/prologue/enemy 路径加载。技能 990/991/992 分别播放 fire/skill_2/skill_3；原技能特效、受击和命中时间仍未同步。

严格 TypeScript、Web 构建通过。浏览器先完成旧战斗胜利，再重开并实际结束前 3 回合，确认普通攻击、强化攻击、护盾分别播放，截图 skill2-runtime.png/skill3-runtime.png 位于 analysis/battle-visual/enemy-skills。强化攻击后玩家生命 1466.8→1064.8；护盾回合敌方护盾增加 300。原始动画采样与共享客户端实播有证据，但不表示原规则全部恢复或 Android 实际运行通过。


### 2026-10-14：血量显示与动作命中标记

PrologueSceneView 对艾尔莎 fire_1/crit_1/fire_1_1/fire_1_3 按原 AGS attack 的 TimeRatio（.230700/.281831/.350154/.409156）乘实际导入片段时长安排表现回调。该秒数仍属推导，未冒充原生时间转换已验证。取消时移除计划回调，序列切换移除前一回调，离开视图的 generation 检查阻止陈旧 UI 写入。

TutorialBattleView 只暂存显示用 hp/shield，从服务端事件 previousHp/previousShield 开始，命中时按顺序应用 DamageApplied/ShieldAdded（同时推进其前的 ShieldCleared）；动作完成或失败后回归权威最终快照。胜负提示与最终事件摘要在动作完成后显示。能量、手牌、回合与意图仍使用最终快照，完整表现队列未实现。

敌方已知 GIM 的 MusicAgs 文件成功提取（SHA a1b79f1bfdf3c631231bdb410606ce1cda4ab7d3ebc0ed4ab8085ad9159acb26），仅含 Triggers/Sockets，没有找到 AnimationEventTracks。常规同名 .ags 未匹配资源；这不证明 APK 全部缺少命中信息。敌方当前采用动作结束更新血量/护盾的重建回退，尚未恢复精确命中时点。

严格 TypeScript 与 Web 构建通过。真实二连斩：起始敌人生命 4600/护盾300，画面动作启动仍保留该值；两个命中回调分别显示生命4539/护盾0、生命4178/护盾0（时间戳 01:07:27.220 与 01:07:28.537 UTC），最终快照一致。截图 hit-timing-first.png 显示动画启动尚未扣血；不是完整原游戏表现验收。


### 2026-10-14：敌方受击与死亡动作

原 entity_table 的实体6605（analysis/first-encounter/enemy-entity.json，decoded SHA b1468806b994f1217354a7cec6adb5b11e8a3bb0ee807d5e2a4bfd3e90800f26）明确指定 HIT_1/HIT_2=hit_1、DIE=death；原敌人 GISACL 库中分别为索引1/2。新增 sample_enemy_reactions.py 使用独立 SHA 白名单解码器提取25/63帧、61骨骼的原片段，共5,368组骨骼帧。hit_1 单段数据没有 segment range reduction，仅对这两个已固定哈希输入放宽该头字段，其他解析检查保留。属于本地静态解码证据，不是 REA 原生运行证据。

export_enemy_reactions.py 保留旧产物，组合六片段后回读验证23,302组骨骼采样。新GLB为1,839,660字节，SHA-256 4c43f8c85cb40a7ff6ecdad018aa341cfe3ef873606c23526cfcbd3eb3cc91b3。prepare_cocos_prologue.py 已切到新产物。

共享客户端在玩家命中回调处理敌方 DamageApplied 时，按生命或护盾实际损失触发 hit_1，致命伤触发 death。反应使用独立 FINISHED 监听和取消路径，不打断攻击者片段；玩家动作结束后等待反应结束，再解锁和显示最终胜负。死亡末帧显式采样并保留，重开恢复 idle。该调度是重建表现，未恢复原引擎受击选择、混合、消散特效或服务器流程。玩家受击与死亡仍未接入。

严格TypeScript检查和Creator Web构建通过。浏览器从第4回合继续，敌人生命4178→2731→2249→1767，控制台记录四次 hit_1；第5回合1767→320后斩击触发 death（01:13:50.670 UTC），最终生命0并显示胜利、魔方散开落地。截图 analysis/battle-visual/enemy-reactions/death-runtime.png。控制台无错误/警告，重开后敌人回到满血待机、手牌可用。本次没有重新打包Android，上一轮APK不包含新反应动画。


### 2026-10-14：玩家受击与倒地

新增 trace_player_reactions.py / sample_player_reactions.py。原实体0将 HIT_1 映射 hit_2、HIT_2映射hit_1、DIE映射death；本轮选用HIT_1对应的hit_2，未声称原生受击种类选择已恢复。源APK、演员网格和动画库均检查既有SHA，映射和提取来源写入 analysis/battle-visual/player-reactions。新片段hit_2为20帧、death为51帧，均180骨骼，共12,780组采样。独立解码器只接受两个固定ACL哈希，保留官方ACL头文件一致性校验。属于普通本地静态工具证据，不是REA原生执行证据。

export_prologue_actor.py 新增 --with-reactions，保留旧输出，导出8动画版本至 actor-reactions/prologue-elsa.glb。大小6,582,960字节、SHA-256 28e9f1cea8e16e0d755c6a9b9f29272cbe78bff8806d85c462c822ff125b5ad6；68,760组骨骼采样回读通过。共享客户端使用新产物，反应播放器支持双方，死亡末帧保留、重开恢复各自待机。敌方命中标记尚未恢复，所以玩家受击仍在敌方动作结束触发，属于明确的表现回退。护盾增加不触发受击。

严格TypeScript检查及Creator Web构建通过。浏览器实际从满血连续结束回合，记录5次 player hit_2，第3回合护盾不增加受击记录；第7回合生命158.8→0，触发 player death（01:17:18.693 UTC），倒地可见、战败显示正常，控制台无警告/错误。保存 death-runtime.png；重开后满血、待机、手牌及按钮恢复。未新做Android/Windows打包或设备运行，原版镜头、音效、特效和受击选择仍未完全恢复。


### 2026-10-14：敌方命中事件的范围扫描与原脚本回退

新增可重跑工具 tools/scan_enemy_event_tracks.py。校验原APK哈希后，对 assets/res/character.npk 按索引偏移顺序读取并解码；每条存储和解码大小上限256 KiB。7,501条中解码6,729条、跳过772条，无解码/XML错误。85个文件含 AnimationEventTracks；无 EventTrack_fire，因此也没有 fire+skill_2 同时出现的候选。全条目索引、SHA、轨道名、跳过索引保存在 analysis/battle-visual/enemy-timing/scan.json。这只是限定范围的负结果：未覆盖其他包、大条目、其他字段编码或原生运行时合成，不能说原游戏没有魔方命中事件。按已知普通/紫色模型基名查询 .ags 也未匹配；已知 MusicAgs 和模型GIM只有音频/特效触发数据，不能把特效启动当作命中。

同工具从既有SHA校验的原模块重新导出 SkillHelper.getSkillDurationAndReactTimeList，保存 skill-helper.json、fallback.json。426..486字节分支先将 animLength 加入 nowDuration，findAttack为假时追加 nowDuration+max(reactTime,0)。此前attack及attack_N分支仅在返回时间大于0时标记命中。因而“无正命中事件时使用动画末尾”在原脚本中有条件依据，但魔方原生查询的返回值仍未知，不能把当前回退升级为原版精确时序。未修改共享客户端的时间或伪造事件，下一步仍需扩大资源范围或恢复原生事件加载来源。


### 2026-10-14：角色包事件轨扫描覆盖补齐

scan_enemy_event_tracks.py 新增 --large-entries，仅检查此前大于256 KiB的条目，单条上限32 MiB，旧 scan.json 保留。新增772条全部解码成功，无错误、无剩余超限条目，未发现新增 AnimationEventTracks 文件。coverage.json 核对两轮APK哈希、包索引哈希、跳过索引集合及计数，证明7,501个角色包条目的此次字节解码/XML标记扫描完整覆盖。85个事件轨文件中仍无 EventTrack_fire。

这收窄了上一轮的大条目覆盖缺口，但不覆盖其他包、其他编码或原生生成事件。该范围调查已完成，不应再重复扫描同一角色包来推断缺失；后续需转到原生加载来源或其他来源。客户端回退时序保持不变，没有新画面或跨平台运行验收。可重跑命令：python tools/scan_enemy_event_tracks.py（小条目），随后 python tools/scan_enemy_event_tracks.py --large-entries（大条目及集合覆盖核对）。


### 2026-10-14：原战斗UI布局与图集引用

新增 tools/trace_battle_ui.py，从哈希校验过的原 ui_auto 模块常量定位 FightMainPanel_ext.csb、EnergyArea_ext.csb、EnergyNumArea_ext.csb，并直接由APK提取至 analysis/battle-ui。三个CSB SHA分别为 df399c2fe51b01002b9dd6e8c2b64fe92f6968eb69f03eb0af48f41f662b38a4、b61656c2642f10468c9b6037d703c21a14ab93c7996384299337bdd7495146a8、909cb7ea7541805fa4df643fab91a3be43d868cf687646fa9f7074b6bde2eb31。这里只提取字节字符串及偏移，没有将字符串顺序当作布局层级或坐标。

uires/FightPanel.plist 在 uires.npk 索引1560、偏移264805116，声明4096×4096图集和673个精灵。三布局共引用72个唯一PNG路径，71个精确匹配此plist，另1个引用其他图集或待定位。包含 energy_bg（196×78）、energy_icon_l1（有旋转及裁切，需要恢复源尺寸58×66）、img_hparea_bg1（1280×102）等。完整引用/帧数据和来源见 layout-links.json。

声明的 uires/FightPanel.png 未在该挂载包按已知路径哈希直接匹配；纹理路径和像素仍未知。相邻索引5470解码后是字体头（非贴图），保留为排除证据 adjacent-texture.bin/source.json，不能用物理邻接关系归属图集。当前没有重绘、替换或宣称UI已还原；下一步需确定纹理加载路径，再解码原图及CSB层级/动画。


### 2026-10-14：原血条与能量底板接入

在 uires.npk 纹理盘点中识别2,403个KTX，4096×4096只有索引5100与4589。分别解码后，以FightPanel.plist的energy_bg、end_bg、img_boss_hp_low_normal、img_hp_normal坐标裁切比较：4589精确对应底板及红/绿血条，5100裁切破碎且内容不匹配。对照图 frame-correlation.png，完整候选 overview-5100.png/overview-4589.png。此归属为坐标及视觉关联推断，原生逻辑文件名转换未解出，不能称为路径匹配证据。

新增 recover_battle_ui_sprites.py，可从原APK固定索引重新提取、核对SHA、解码、处理plist旋转/裁切并输出6个精灵。plist SHA dced510b8dee2c8451b01475aeed05e756fa6d29c6044c456f160721f2303359，KTX SHA 1c1a54ff26bf934c9da8e8a558cd72ba8265ca2d74bec265ecf0d2cbaa7fa61c。像素与来源记录写入sprites.json及客户端battle-ui/provenance.json。共享客户端接入玩家/敌人血条及底图、能量底板，移除两块原纯色生命面板；结束回合底板已提取但未接入。位置/缩放为重建，尚未恢复CSB原布局、能量动画或完整卡牌外框。

严格TS与Web构建通过。首轮浏览器发现无贴图时设置Sprite填充会引发null width异常，改为加载完成后设置FILLED并刷新状态；重建加载后图鉴和首战正常，未产生新错误。实际二连斩使敌人4600→3878，红血条按84.3%显示，截图health-bars-runtime.png。旧错误保留在浏览器日志01:27:12.657，未把旧日志清除后伪称全程无错。没有新增原生平台运行验收。


### 2026-10-14：CSB节点解析与能量挂载位置

新增 inspect_battle_ui_layout.py，参考官方 Cocos2d-x 3.17.2 的 CSParseBinary.fbs 字段顺序，文件及许可证保存在tools/reference/cocos2dx，源URL及SHA写入layout-trees.json。官方来源：https://raw.githubusercontent.com/cocos2d/cocos2d-x/cocos2d-x-3.17.2/cocos/editor-support/cocostudio/fbs-files/CSParseBinary.fbs 。这是字段解析参考，不是证明NeoX分支完全等同于上游schema。解析器对文件大小、表/vtable偏移、字符串终止、节点循环/深度、节点数量和有限浮点值设界限；未知控件类型拒绝。

实际观察根Node直接包WidgetOptions，其余已观察控件还多一层专用Options。区分后成功解析FightMainPanel 62节点、EnergyArea 22节点、EnergyNumArea 4节点，新增OwnCardArea 37节点，共125节点；保留节点偏移、名字、actionTag、位置、尺寸、缩放、锚点、透明度、图集资源或ProjectNode路径。未执行动作时间轴，也未解析全部响应式layout constraints，不直接把局部坐标当作全局位置。

原OwnCardArea.py的initComponents在偏移131..143以EnergyArea和widget=self._wEnergy创建能量控件。OwnCardArea布局对应挂载路径 /Layer/Main/LeftBottom/EnteranceFEnergy/Energy，指向FightNewPanel/EnergyArea_ext.csb。该组件内部能量底板bg_s2为位置(130,0)、锚点(1,.5)、尺寸226×78；数字子布局在(80,-15)。多层能量图标初始alpha=0，需要原时间轴或运行态激活；不能全部显示后冒充原UI。当前顶部能量位置明显仍是重建，与恢复出的左下挂载结构不同；下一步需解析父节点适配并迁移完整组件。此轮未改变游戏画面。

### 2026-10-14：能量组件静态布局接入

- 扩展 `inspect_battle_ui_layout.py`，读取 LayoutComponentTable 的百分比、边缘、伸缩及边距字段，并导出 Text 的文字与字号。四份原始 CSB 共 125 个节点读取成功；仍不执行原始时间轴或原生运行时适配。
- OwnCardArea 的 Main 水平位置为父宽度的 0.5、尺寸为父尺寸的 1.0；1280×720 下其左下局部原点为屏幕左下。LeftBottom → EnteranceFEnergy 为 (0,165)，子 Energy 项目节点为 (0,0)。EnergyArea 的 bg_s2 为位置 (130,0)、锚点 (1,0.5)、尺寸 226×78；静态 icon_s2 为 (35.576,4.2697)、58×66、alpha 255。其它能量动画层 alpha 0，本次未擅自显示。
- 按上述设计尺寸接入底图及新增提取的 energy_icon_s2；Creator 中心坐标分别为 (-623,-195) 与 (-604.424,-190.7303)。原版数字是独立字体节点，本次保留可读的合并计数文本；最大值取重建规则 energyPerRound，不采用 CSB 示例文字 3 冒充原版规则。
- 严格 TypeScript 检查及 Web 构建通过。浏览器实际出牌“猛力斩击”：能量 4/5 → 2/5，敌人生命 3878 → 3155，红色血条同步缩短；本次浏览器 error 查询为空。截图 `analysis/battle-ui/energy-layout-runtime.png`。
- 本次验证为 Web；未重新构建或验证原生平台。卡框、操作按钮、原版战斗镜头、完整特效与 UI 动画仍未恢复。图集归属仍是坐标及视觉关联推断，原生文件名映射未解决。

### 2026-10-14：原版战斗小卡框定位与提取

- 上轮为有效进展：原版能量组件接入并有实际出牌验证。本轮继续处理用户明确要求的画面还原，不改变四平台重建目标。
- `trace_battle_ui.py` 新增 FightSmallCard、FightSelectedCard 两份原始布局提取，`inspect_battle_ui_layout.py` 增加标准 TextBMFont 节点包装识别。六份布局共 181 个节点读取成功。
- `trace_card_frames.py` 保存模块 4644、6992、9176、9257 的哈希校验静态指令证据。FightCard._assignShown 从 data['CardImgPath']['CardFramsSmall'] 取路径，再调用 _cCharImage_NL_S.loadTextureOld；card_img_table 中该字段包含 bg_atk_s、bg_skill_s、bg_def_s 等路径。这是静态本地工具证据，不是 REA 运行时证据。
- 对 uires.npk 中不超过 2 MiB 的 5704 条记录扫描攻击卡框标记，零匹配、零错误，3 条超限未扫描；不能由此断言 APK 缺少卡框。后续 VT 配置给出精确映射，转到 packed_png.npk 扫描全部 10900 条记录，无跳过及解码错误。
- packed_png 10583 的 plist SHA256 为 6478b44ef7ba724749931187f0a0d73d0870c426d17d46243e918e0b199cdf6a；9638 为 65471d0b7f2c6bdece546f8a6b9b92045a65d2e4c55a50b674df919de71c6afb。5755、69 是标记匹配但非 plist 的数据，未当作图集。
- `recover_card_frames.py` 重新提取源 VT 配置与页表，按原始映射解码 ASTC 瓦片、处理 plist 旋转/裁剪，输出 `analysis/battle-ui/card-frames/{atk,skill,def}.png` 及 provenance.json。沿用已有卡面提取的 512 列、124 像素步长、2 像素边框假设，运行时色彩仍未验证。
- FightSmallCard 的 CharImage_NL_S 原始尺寸 234×182、位置 (0,0)、rotation_skew (90,90)；Face_NL_S 为 120×120、位置 (-1,19)、同样旋转 90 度。Name_S 在 (0,-40)，Descr 在 (0,-50)。恢复贴图呈横向，与布局旋转证据一致。
- 尚未把卡框接入共享客户端：原图有青色区域、裁剪留白，需核对原始卡面合成/颜色处理与动态尺寸后再替换。不能把当前提取图宣称为完整原版卡牌。现有 Web 试玩保持上一轮已验证版本，本轮没有原生构建或新增运行验证。

### 2026-10-14：原版小卡框接入共享客户端

- 上轮提取为有效进展。本轮核对 atk.png 像素：青色采样 (60,60) RGBA=(49,182,222,3)，白色采样 (170,60)=(238,238,238,255)。青色样本接近透明，不能将图片检查器的背景呈现误判为游戏内不透明青底；未删除颜色或篡改原图透明度。
- FightCard._assignShown 静态指令 13..42 直接将 CardFramsSmall 载入 _cCharImage_NL_S；setBackgroundMode 仅切换敌我卡背，不是去色操作。采用原布局的卡面先、卡框后叠层，二者按源 rotation_skew=(90,90) 转成 Creator 顺时针 90 度，卡面位置 (-1,19)、尺寸120×120，卡框尺寸234×182；名称和说明放置于原始底部文字区。
- recover_card_frames.py 将源贴图与 provenance 独立暂存到共享客户端，且检查当前五张卡均为源 CARD_TYPE=0。当前预览只接入攻击框；技能/防御框已提取但未为未实现的玩法臆造映射。构建指纹包含 card-frames/provenance.json。
- 移除手牌按钮纯色背景，保留交互与忙碌状态限制；文字使用适合白色原版说明区的深色。费用底托仍是明确的可读性临时实现，未冒充原版费用动画组件。手牌排列、缩放、字体、提示信息仍是重建实现。
- 严格 TypeScript 检查通过、Web 重建成功。浏览器实际打出“强力斩击”，能量2/5→1/5，敌人生命3155→2673，手牌4→3，显示操作已保存；本次 error 日志查询为空。运行截图：analysis/battle-ui/card-frames/runtime.png。
- 本轮只验证 Web，共享源代码已更新，未重新构建 Android/Windows 或验证 macOS/iOS。原版费用图标、稀有度、选中/出牌动画及完整 UI 仍未恢复。

### 2026-10-14：原版费用底图与位图字体

- 上轮卡框接入和出牌验证为有效进展。本轮继续恢复费用控件。CardOtherControls.CardKaferArea.assign 的静态证据保存在 card-other-controls.json：数字调用 Fee_NL_S.setString，底图调用 Img_kafei_bg_S.loadTexture；refreshFntFile 分派 equal/more/less/notplay 状态，动画未执行或移植。
- 原始 card_img_table 的 CardFeeBg 映射到 uires/AllUIRes/Card/cost_s1.png。FightSmallCard 的 EffectKafei_Small 位于 (-45.9996,70)，scale=(0.5,0.5)。新增解析 kafei CSB（7节点），底图70×82，Fee_NL_S 位于带中心锚点的107×107父面板内 (54.7,52.7)。合成设计坐标对应数字约(-45.4,69.6)。七份布局总188节点。
- 扩展 TextBMFontOptions 读取，确认字体资源 CommonRes/Fnt/cost_normal.fnt。源 FNT 精确路径匹配 uires.npk 3894，包含 0..9 与 X 的11字形、495×46图片；该图片经过 VT 配置精确映射至 cost_normal.png。字体图集 packed_png 8734 SHA256=baf4fbfc60eb977b70e0d6acbd6bca630e55435bd16eb1b23e85c7edcdaab5a5；费用底图图集908 SHA256=8d0e8f7a3f54985d1c033f21fdc34a626941c9e8b9f166b24c0f608a41494dc4。
- recover_card_frames.py 可复现提取字体和底图，包含 VT 瓦片来源、源校验和及派生字体校验和。原FNT info size=-32 被 Creator 3.8.8 importer 保留为 fntConfig.fontSize=-32，bmfontUtils.ts 用它作为 originFontSize，首轮浏览器观察到数字倒置。仅共享客户端派生 FNT 改为size=32，分析目录原FNT保持不变；修正后数字方向与位置正常。
- 临时深色圆底已移除，使用原版蓝色六边形35×41和 BitmapFont 数字。正常字号16对应半尺寸，引用计数随界面释放。不可用状态的颜色仍为重建逻辑，不宣称源状态时间轴还原。
- 严格 TypeScript 检查通过，最终Web构建成功。浏览器验证结束回合：进入回合2，玩家1768.8→1466.8，能量恢复5/5，6张手牌的费用1和2方向/位置正常，操作已保存，error/warn查询为空。截图 analysis/battle-ui/card-frames/cost-runtime.png。没有新原生平台构建或运行验证。

### 2026-10-14：源手牌圆弧布局

- 上轮Windows编译及打包为有效进展。本轮读取原 CardTools.py（script index8168）并保存带源码哈希和指令偏移的 card-tools.json；可复现工具 tools/trace_card_geometry.py 输出常量校验与单角色1/2/5/6/10张局部坐标示例到 card-geometry.json，不执行原始脚本。
- 源常量 R=2800、D=R-90、thetaMax=3°、alpha=3.6°、dBeta=1°；beta=degrees(acos(D/R))-1。单一非空角色分组时alphaSum=0，角度范围min((n-1)*3,beta)，omega=90-range/2+i*step，x=-R*cos(omega)，y=R*sin(omega)-D，rot=omega-90。Creator旋转方向换算为负源rot。
- 共享客户端移除等距横排和随牌数缩放，接入上述单角色局部公式。为了避开尚存的调试按钮，以中心Y=-152作屏幕平移（不是源绝对屏幕位置）；三角色分组间隔、选中抬升和拖动出牌尚未移植。源getCardTypePlist按CharPos倒序累计三组，不能按攻击/防御类型误分组。
- 严格TypeScript检查及Web构建通过。浏览器六张手牌呈圆弧；点击倾斜的疾驰斩击正常出牌，能量5→3，敌方2673→1226，手牌6→5自动重排，操作已保存；error/warn查询为空。截图 analysis/battle-ui/hand-arc-runtime.png。
- 本轮改动只重新验证Web。此前Windows压缩包及Android APK对应上一版，不包含本次圆弧布局；它们的记录哈希仍作为各自历史产物依据。多平台目标、Android运行验收和完整玩法恢复均未完成。

### 2026-10-14：原版选牌与释放边界

上轮圆弧布局和浏览器出牌验证为有效进展。本轮新增可复现 tools/trace_card_gestures.py，读取四个哈希校验脚本模块、九个方法，并记录已安装Creator3.8.8 node-event-processor.ts的哈希和相关源码片段，结果为 analysis/battle-ui/card-gesture-evidence.json。

源 CardBaseArea._doTouchDown 选中最近的等待状态卡；_doTouchMove 通过向上位移进入出牌状态，DesignConst 的两个阈值分别5和30（取决于详情面板状态）。_doTouchUp清空选择；_doTouchCancel 在已有out-card且结束位置y>100时调用onSelectedOutRelease。FightTargetCard随后检查CanPlay及目标错误。因此现有点击即出牌仍属重建交互，并非原作行为。

当前Creator节点事件处理器在物理TOUCH_END落点不命中原节点时，会改写为TOUCH_CANCEL；真正的输入取消也发同名事件。若直接把卡片TOUCH_CANCEL接到服务端出牌，会把真实取消误认为出牌。下一步应在完整战斗画布跟踪手势：按下绑定卡牌实例，释放时校验位移、目标和仍可操作状态；真实取消、数据刷新或切换界面均清除手势。本轮尚未改动可玩客户端，不能声称拖动出牌已经恢复。原始坐标适配、选中详情和目标判定仍待接入与实际操作验证。

### 2026-10-14：画布级拖动出牌接入

- 上轮选牌状态与引擎取消事件取证为有效进展。本轮共享TutorialBattleView移除卡片的直接点击提交回调监听，将手势绑定到整个1280×720战斗画布。普通操作按钮仍保持原有点击处理。
- 按下以反向绘制顺序命中卡片，绑定指针ID、卡牌实例ID、战斗ID和revision。只在同一手势释放、仍可操作、战斗/版本未变、卡牌仍在手中、向上位移至少5设计像素且命中敌方区域时调用controller.play。先清空手势再提交，避免同一释放重复触发。状态render、hide、cancel均清空；第二指针不替换首指针。
- 点按保留名称、费用和效果文本，不提交。拖动时显示目标框与松手提示。当前目标框是基于单敌人镜头的重建矩形x95..395、y-80..200，不是原版模型拾取；选中抬升、拖动箭头、三角色及多目标交互仍待恢复。原版30像素详情状态阈值未启用，因为该详情状态尚未移植。
- 严格TypeScript检查及Web构建通过。实际浏览器先验证点按、拖向玩家位置均保持能量3/5、敌人1226、手牌5不变；有效拖动强力斩击到敌人后仅一次扣费3→2、伤害482使1226→744、手牌5→4。刷新页面恢复该状态。
- 最终修正版本继续验证：拖出画布上边缘显示取消，能量2/5、敌人744、手牌4不变；随后点按显示卡牌详情，状态仍不变。error/warn查询为空。截图analysis/battle-ui/gesture-runtime.png。浏览器操作不能证明手机系统中断、多点触控或Android原生输入已验证；相关状态保护只经过代码检查，仍需后续设备验收。
- 本轮未重打Windows/Android包，当前可试玩Web包含新交互，此前原生产物保持各自记录版本。

### 2026-10-14：目标箭头静态调用链

- 新增 `tools/trace_target_arrow.py`，校验原 APK 和三个脚本模块，结果保存为 `analysis/battle-ui/target-arrow-evidence.json`。这是本地静态提取，不是 REA 运行时观察。
- UIConst 的 MonsterArrow 指向 `uires/shader_santu/arrowhead.png`、`arrowflow.png`、`arrowbg.png`；FightCard 通过 ArrowControl 传递卡牌世界位置、目标位置及贴图组。ArrowArea 使用缩放 0.7 的箭头头部与 SRCALPHA/ONE 混合的 DrawNode。
- 原生调用为 `drawArrow(basePos,targetPos,160,20,flow,bg,60,'ArrowHead')`；数字参数语义及曲线生成尚未解析，不能据此声称已恢复原箭头曲线。
- 从 common.npk 精确路径提取 arroweffect.vs（511）与 arroweffect.ps（370）。片元着色器让 flow 的 v 坐标随 CC_Time 循环，并按 flow alpha 与背景合成。三张贴图的直接路径和 VT 精确路径查询无匹配；路径转换仍待定位，不据此判定资源缺失。
- 本步骤没有替换客户端箭头，也没有新增原生构建。当前 Web 实际画面仍为已经接入的原 APK 场景、角色、敌人及卡面，镜头、部分控件和规则仍是重建版本。

### 2026-10-14：原版目标箭头贴图恢复

- 上轮保存证据与现状截图，但没有新增可玩画面。本轮沿用已验证的原生 UI `.png → .pkm` 后缀规则（见 resource-path-mapping.md，0xbfcd66..0xbfce0e），解决上述贴图查询缺口；此前无直接匹配不代表资源缺失。
- `trace_target_arrow.py` 现在从只读 APK 重新提取、校验并解码三张 MonsterArrow 贴图，输出 `analysis/battle-ui/target-arrow/`。arrowhead 精确命中 uires 2342，KTX SHA256 `49de2a2ce6c99945cc3fa06172ae4641b366095e9a320f02aacdd8cbbdb64d31`；arrowflow 命中2190，arrowbg命中197。每项均要求唯一匹配，完整源哈希、目录位置、PNG/RGBA哈希和解码器身份保存在 provenance.json、manifest.json。
- 箭头头部256×128，流动层及背景层各64×512；保留原始方向与透明通道。共2480个ASTC块，HDR块和错误块均为0；已视觉检查三张红色箭头素材。KTX头部 glBaseInternalFormat 异常由既有解析器明确记录，仅导出经过检查的ASTC载荷，不宣称原生色彩表现已验证。
- 本轮未修改可玩客户端，也未把普通拉伸贴图冒充原生曲线。原生动态符号表未检出 drawArrow 名称；该阴性结果不能证明实现不存在。下一步仍需定位原生绑定/曲线实现，随后接入流动着色及方向变换。四平台运行验收和完整游戏还原仍未完成。

### 2026-10-14：原生目标箭头几何定位

- 上轮三张贴图恢复为有效进展。本轮新增 `tools/trace_native_target_arrow.py`，验证已提取 libclient.so 的固定 SHA256，使用现有 Android NDK LLVM 做离线 Thumb 反汇编，保存三段代码与工具哈希到 `native-target-arrow-evidence.json`。不是 REA 运行时证据；未执行 APK。
- 绑定错误字符串 `self == NULL in pycocos_cocos2dx_DrawNode_drawArrow` 由 0xb45428 的 PC 相对加法精确引用，字符串地址0x24ccb4d。同一包装器在0xb4554c调用0xc93d28，实参对应两个Vec2、两个整数、两张纹理路径、一个整数、头部节点名；不依赖反汇编器显示的远处最近符号名。
- 根据指令数据流，脚本160是起点宽度，先以有符号整数除2，再在起点X两侧展开；20是终点宽度，除2后沿角度旋转方向展开。60是每侧采样数，两侧调用0xc93740后交错组合。角度换算常量为180及原二进制float32的3.14，不能擅自换成更精确的π后声称逐值还原。
- 0xc93740 的采样循环为i=1..N，沿两端直线取样，再加垂向位移；静态数学解释为 `h - 4*h*(s-L/2)^2/L^2`，其中h取该侧终点与起点的X差除4。两侧各自计算，不是直接套用一条猜测的三次贝塞尔曲线。
- 仍需核对0xc93a30角度辅助函数、节点虚调用、UV以及实际绘制效果。本轮没有改动试玩或重打原生包，不能声称拖牌箭头已显示。已将下一步从无符号搜索缩小到具体函数与参数。

### 2026-10-14：箭头切线角度与 UV 核对

- 上轮原生函数定位为有效进展。本轮扩展同一可复现工具为五段反汇编，增加顶点写入与向量归一化函数；每段输出及工具均保存哈希。0xd0a250经指令确认计算长度并将两分量乘倒数（含极小长度保护）。
- 校验ARM PLT机器码并读取ELF重定位：0x69e758 → GOT 0x2a9190c → atan2，0x69e0f8 → GOT 0x2a916ec → atan2f。由此确认角度辅助函数使用曲线导数 atan2(slope,1) 加直线方向 atan2f(dy,dx)，两项各乘180并除源float32的3.14。
- slope = 4*h/L - 8*h*s/L²，h=(target.x-base.x)/4。调用时N=20，循环i=1..N+1；第一个输出在i=N写入sp+0x4c用于末端宽度方向，第二个在i=N+1写入sp+0x48，再取负传给头部节点虚调用。两个方向不完全相同，不能合并成一个终点切线角度；该虚调用具体方法身份仍需确认。
- 顶点写入函数0xc9343c按交错两侧顶点数V=2*N生成UV：每对为(0,j/(V-1))和(1,j/(V-1))。N=60时j=0..59，v最大59/119≈0.495798，并非1。结合源shader的frac(v-CC_Time)可确定输入范围，但新引擎纹理方向和实际流动效果仍须渲染验证。
- 这些是固定APK下的静态代码证据。本轮没有新增可玩画面或设备运行验证；下一步可据明确的采样、UV与角度数据实现共享渲染，仍不能声称已恢复原生显示效果。

### 2026-10-14：共享箭头几何代码与边界验证

- 上轮角度与UV取证为有效进展。本轮新增模板 `cocos-target-arrow-geometry.ts` 与共享客户端 `TargetArrowGeometry.ts`，移植两侧独立抛物线采样、60对顶点、连续三角形、原UV范围与头部超出终点的切线角。创建项目脚本及Windows/Android/Web、Apple源文件指纹清单包含该文件。
- 继续核对PLT机器码和重定位，确认0x69e008是sinf、0x69dffc是cosf。因此末端偏移为 `(10*sin(angle), -10*cos(angle))`，另一侧相反；初稿顺序在证据复核中被纠正。垂直箭头末端横向展开20像素的解析检查通过。
- `node tools/test_target_arrow_geometry.mjs` 验证六个方向，包含顶点/索引边界、有限值、终点中心与宽度、源UV范围、平移不变性、垂直解析角度、头部超采样差异和非法/退化输入；输出 `target-arrow-geometry-checks.json`。模板与客户端一致，严格TypeScript检查通过。
- 该移植使用JavaScript数值，不承诺与ARM每步float32逐位一致。L<0.1时不生成图形是重建保护，未冒充原调用者完整退化行为。连续三角形顶点顺序保留原代码，渲染材质需要关闭面剔除。
- 几何模块尚未连接战斗渲染，未重新构建Web或原生包。下一步仍是原贴图、流动shader与输入手势联动，并通过真实拖动检查显示和清理行为。

### 2026-10-14：原素材目标箭头接入 Web 战斗

- 上轮共享几何模块为有效进展。本轮新增 `TargetArrowView`，使用独立正交摄像机、透明RenderTexture和网格绘制曲线，叠加原版0.7缩放头部。源片元混合公式移植到Creator effect，曲线使用SRC_ALPHA/ONE，离屏结果以ONE/ONE合成；关闭深度写入及面剔除。Creator3.8.8的UI混合字段属于固定版本内部接口，已在代码注明。
- `prepare_target_arrow.py` 对三张PNG逐项校验解码manifest哈希后暂存，保留源NPK证据。创建项目脚本及各构建指纹清单新增渲染代码、effect、资源provenance。原APK不变。
- 战斗画布向上拖动至少5像素时显示箭头，跟随指针；释放、取消、状态刷新与隐藏都清空。异步资源加载完成仅恢复仍有效的pending显示，销毁时释放材质、网格、RenderTexture和引用。当前起点取按下位置，尚未改为原版卡牌世界位置；目标框仍是重建矩形。
- 严格TypeScript检查、Web构建通过。实际无效拖动保持能量2/5、敌人744、手牌4；随后有效拖动强力斩击，截得真实手势中的曲线和头部（`analysis/battle-ui/arrow-live-22.png`），释放后能量2→1、敌人744→262、手牌4→3，显示操作已保存，箭头及目标框消失（`arrow-after-play.png`）。error/warn查询为空。
- shader用cc_time.x驱动纹理，但未与原客户端时钟速度、色彩管线逐帧对照；截图证明曲线/头部显示，不单独证明时间动画速度正确。头部顺逆时针作新旧引擎转换，仍待原版运行对照。未重新打包Windows/Android，macOS/iOS及原生输入验收仍未完成。

### 2026-10-14：箭头卡牌原点及 Android 同步

上轮箭头显示及真实出牌为有效进展。本轮按源FightCard.getWorldPos(_rootNode)的依据，将箭头起点从按下位置改为卡牌节点世界位置转换到战斗画布局部坐标；手势阈值仍取真实按下位置，避免误判点击。几何检查及严格TypeScript检查通过。

Web重建后恢复敌人262、能量1/5、手牌3的存档；从中间卡片靠下位置拖向玩家，截图arrow-origin-15.png可见曲线从卡牌中心发出。松手取消，状态不变，箭头消失，error/warn为空。仍未恢复原版选中抬升及插值追踪。

Android新版打包完成，9项内容检查及260项导出文件比对通过，详见android-build.md。没有Android运行验证，亦未重打Windows或构建Apple平台。

### 2026-10-14：选牌反馈的行为核对

上轮Windows同步包为有效进展。本轮新增tools/trace_card_selection.py，重新校验并导出5个源脚本模块、17个代码对象到card-selection-evidence.json。这是本地静态证据，不是原版运行观察。

FightCard.onSelected把normalPos复制到touchPos，进入Select光效及STAGE_TOUCHED；setZOrder在选中时使用200。TargetCard.update在未拖出时追踪touchPos，拖出后显示箭头并追踪normalPos。当前证据不支持直接添加统一的固定抬升/放大常量；该结论仅限所读方法，不能排除其它控件或时间轴改变变换。

EffectSelect按箭头样式读取S11/S12等两组颜色，给8个sprite上色，然后循环播放in动画；stop隐藏并暂停。OwnCardArea选中时同步能量预览并显示场景模型battle_screen_01，取消时清空预览并隐藏。这些是当前重建缺少的原版反馈，下一步应追踪对应布局、动画及素材，详情卡预览需独立追踪，不能用猜测的放大代替。

本轮没有更改可玩客户端、打包或新增运行验收。最新Web、Windows与Android产物仍对应上轮各自已记录版本。

### 2026-10-14：选中框布局、时间轴和图集定位

上轮选牌行为核对为有效进展。本轮沿FightSmallCard.EffectTouch的ProjectNode引用及ui_auto脚本9511，提取EffectCardSelected_SmallCard_ext.csb。trace_battle_ui.py扩展为8份布局，节点解析共200个；选中框含12节点，其中8个sprite使用4组边框贴图，保留原位置、镜像及非均匀缩放。

新增tools/inspect_selection_timeline.py，按已有CSParseBinary字段顺序有界读取NodeAction、AnimationInfo和帧变体，输出selection-timeline.json。源duration=23、speed=0.5，动画in范围0..23；22条时间轴、110条关键帧，属性仅FileData/Position/Scale。8条贴图轨各12帧，合计48张唯一图片，证明动态边框依赖序列帧素材，不能用一张框加缩放替代。帧号尚未换算成已验证的墙钟时间。

uires/CommonUI.plist精确命中5661，48张序列帧全部在该图集中，无缺项。图集元数据尺寸4096×4096，引用CommonUI.png；经既有png→pkm后缀规则，像素资源唯一命中uires 5100。已保存图集源哈希、帧矩形及映射，尚未解码该图集或把动画接入客户端。静态提取不是原版运行观察，颜色自定义属性及播放速度仍需后续核对。
# 选中框图集、配色与接入数据（2026-10-14）

`tools/recover_card_selection.py` 从路径确定的 `uires/CommonUI.plist`（索引 5661）和 `uires/CommonUI.pkm`（索引 5100）恢复选中框的 48 张 PNG。4096×4096 图集共有 419,840 个 ASTC 块，解码报告无错误块、无 HDR 块；图集 KTX SHA-256 为 `15fd120cf08c4e9b1e059d6a776563c3cf15be3d83feb59c4680b6aa6d7ffd09`。每帧保留原旋转、裁剪与恢复尺寸记录及 PNG/RGBA 哈希。`analysis/battle-ui/card-selection/contact-sheet.png` 是提取检查图，不是游戏截图。

布局读取器补充了 WidgetOptions 原始 ARGB、customProperty 和 SpriteOptions 的 BlendFunc。选中框 8 个精灵均为 OpenGL ONE/ONE；布局默认色为青绿与浅蓝，但实际脚本会覆盖，不能将默认色当作攻击选牌的最终颜色。节点 customProperty 为空，颜色来自生成的 Python 初始化脚本。

`tools/prepare_card_selection.py` 校验原脚本解码哈希，从模块 9511 的 `_initAutoWidgets` 中匹配 `LOAD_CONST value / LOAD_CONST key / STORE_MAP` 指令，恢复九个 ARGB 属性：

| 属性 | ARGB |
| --- | --- |
| S11 | 255,255,28,0 |
| S12 | 255,251,175,159 |
| S21 | 255,0,255,188 |
| S22 | 255,130,206,251 |
| S31 | 255,255,216,5 |
| S32 | 255,255,255,255 |
| S41 | 255,157,255,76 |
| S42 | 255,240,255,205 |
| DesignStatus | 255,255,255,255 |

既有 EffectSelect 证据将 MonsterArrow 关联 S11/S12、PlayerArrow 关联 S21/S22，另外两种效果关联 S31/S32 与 S41/S42。提取脚本将 48 张图和包含完整层级、22 条时间轴、配色和来源哈希的 `selection.json` 放入 `clients/cocos-poc/assets/resources/recovered/card-selection/`。所有输入哈希、时间轴节点绑定和混合常量在写入前检查。

时间边界：生成模块声明 FPS=30，但模块 6095 `CommonActionTimeline.initAuto` 仅存储 animList，没有应用 FPS；playAnimation 委托原生 timeline.play。因此不能直接用该常量证明实际播放速度。

随后使用 `tools/trace_native_selection_clock.py` 核对固定 SHA 的原 `libclient.so`：setTimeSpeed 错误字符串锚点确定包装函数，经 vtable+0x5c 指向 `0xe12f76`，写入对象偏移 0x50。create 包装函数在 `0xbc2712` 调用 `0xe10e10`，构造时将 float32 位模式 `0x3c888889`（约 1/60 秒）写到偏移 0x54。安装的虚表 VA 为 `0x29b4f94`，需按 ELF LOAD 段转换到文件偏移 `0x29b3f94`，不能直接当文件地址。虚表+0x2c 的 `0xe11858` 将 delta×speed 累加到 double 时间，再除以上述间隔得到帧索引；循环分支经 `0xe113ae` / `0xe113c6` 将时间重设为起始帧×间隔，丢弃溢出的时间。

`analysis/battle-ui/native-selection-clock.json` 与六份 Thumb 导出记录上述来源和范围。按照 CSB speed=0.5 推导约每秒 30 帧，已写入共享资源 manifest；这依赖加载器实际应用该源值，尚未完成加载器赋值边和原版实播核对。不能据此声称跨引擎逐帧时序、循环边界或颜色已与原版一致。

以上为本地静态工具证据，不是 REA 运行证据；提取阶段本身不证明原生混合颜色、播放速度或与原版画面一致。

## 选牌光效 Web 接入与实测

`CardSelectionView.ts`（对应 tools 模板）已读取上述共享资源，在当前教程攻击牌按下时使用 S11/S12 配色、原层级与序列帧。选中卡移至同级末尾，取消后恢复顺序；光效跟随卡牌变换。0/180 度 source rotationSkew 转成分别作用于 X/Y 的反射，保留负缩放。48 张直通 alpha PNG 在 Creator 中使用 SRC_ALPHA/ONE 进行叠加；这是适配后的混合配置，不能声称与原 ONE/ONE 的纹理预乘约定逐像素等价。时钟使用原生 float32 帧间隔及源 speed，循环清零；原加载器赋值边与完整跨引擎边界时序仍未验证。

Web 构建通过，严格 TypeScript 检查通过。浏览器 `http://127.0.0.1:7456/?apiPort=7458` 实测：

- 从中间斩击卡拖到空处：红橙光框与原箭头同时显示，截图 `analysis/battle-ui/selection-live-4.png`；取消后两者消失，能量 1、手牌 3、敌方生命 262 保持不变（`selection-after-cancel.png`）。
- 再拖到敌人：出牌成功，敌方生命 262→0、能量 1→0、手牌 3→2，显示胜利与已保存；光框及箭头均消失（`selection-after-play.png`）。
- 取消检查时浏览器捕获的 error/warn 为空。没有用截图证明完整动画速度或原版等价。

当前只支持教程攻击目标配色；队友/增效配色虽已提取，尚未绑定其他卡牌种类。四平台共用源码和生成入口已加入新组件，构建指纹加入组件与 manifest。本轮仅实际重建并检查 Web，之前的 Windows/Android 包不包含此次光效；macOS/iOS 仍未构建运行。


## 2026-10-14 回合结束控件常态外观

新增 EndArea 原布局提取，读取器支持其 Particle 节点资源记录（未运行粒子）及 Button 三态资源。九份布局合计220节点。EndArea挂接位置来自 OwnCardArea/RightBottom(1280,0)/EnteranceFEndTurn(0,165)，换算1280×720居中画布为(640,-195)。原背景226×78，锚点(0,.5)、位置(-108,0)；图标84×84，位置(-46,12)、X缩放-1；文字位置约(-50,-17.856)。

recover_battle_ui_sprites.py新增end-icon-normal与end-icon-active，并用原路径uires/FightPanel.plist、uires/FightPanel.pkm确定性提取，验证此前图集索引4589的相同哈希，取代早期仅按坐标/外观关联的归属说明。九张提取图已进入共享资源。

Web已用原底图、镜像图标及静态半透明glow替换底部调试按钮，位置移至原右下锚点。为覆盖图标/文字，触摸区域采用重建的116×100；字体沿用当前客户端字体。完整黑白序列帧、粒子、状态动画未移植，不声称等同完整原控件。原生成脚本8266的enemyturn/myturn仅切换文字状态，静态导出在analysis/battle-ui/end-turn-state-evidence.json，尚未据此恢复全部动画控制。

严格TypeScript检查和Web构建通过。浏览器实测重开首战后点击新位置：回合1→2，艾尔莎生命1768.8→1466.8，正常抽牌、洗回与存档，截图analysis/battle-ui/end-turn-live.png；捕获error/warn为空。此次没有更新Windows/Android分发包，其上次验证不包含本次控件。其余界面和完整原版演出仍未完成。

## 2026-10-14 回合按钮状态反馈

新增tools/trace_end_turn_control.py，可重复导出模块8266的文字属性/状态及4589的控件状态处理。原文字DesignStatus为“回合结束”，s2为“敌方回合”；_setBtnShow依getIsinRoundCanPlayCard切换，_setBtnTouch依_inSelfRound决定触摸。_refreshNonCardCanUseState还依据getIsNonCardCanUse选择black_in/white_in和退出动画，不能简单当成enabled/disabled两态。

共享视图增加presentationActor，敌方技能播放期间显示“敌方回合”，播放完成或关闭页面时清空；现有动作期间禁用输入继续生效。因重建服务一次提交整回合，按钮文字不能直接读已经进入下一回合的最终快照。Web构建与严格TS通过，浏览器实测回合2结束时捕获敌方动画及对应文字（analysis/battle-ui/end-turn-enemy-phase.png），结束后恢复“回合结束”，玩家生命1466.8→1064.8；error/warn为空。原动画层尚未移植，本轮未更新原生包。

实测也暴露剩余表现缺口：动作期间顶部回合号、敌意图和新手牌仍提前显示最终快照，尚未整体接入battle-presentation逐步投影；这不属于已恢复的原版时序，下一步需修复。

## 2026-10-14 敌方动作前缀投影

新增EnemyTurnPresentation.ts及生成模板，处理首战接口中首个EnemySkillUsed之前的CardMoved、ShieldCleared、EnergyChanged事件，生成只读显示状态。原始服务端快照保持不变；未知/缺失事件前缀退回前一快照。视图仅在同战斗连续版本时采用前缀；收到不同战斗/新版本使旧播放回调失效，关闭或播放结束清除投影。期间回合、能量、牌堆、意图采用显示状态，健康值继续采用既有命中回调。源事件格式与battle-presentation的通用DTO不同，本步没有声称已接入其全部队列能力。

node tools/test_enemy_turn_presentation.mjs使用实际battle-session.endTurn生成的事件，验证旧回合、手牌移入弃牌、延后伤害和抽牌、输入不变及未知前缀回退。严格TS与Web构建通过。浏览器实测第3回合敌方护盾技能：播放时仍回合3、手牌0/弃牌6，截图analysis/battle-ui/enemy-prefix-live.png；结束才显示回合4、手牌6、敌方护盾300及新意图，截图enemy-prefix-complete.png。error/warn为空。

限制：当前仍只驱动第一个EnemySkillUsed动画；多敌方技能的逐段队列、出牌抽牌的细分时序和逐张抽牌动画尚未实现。源APK完整表现时序未恢复，本次只修正重建客户端的提前显示问题。Windows/Android分发包未包含本轮修改。

## 2026-10-14 多动作分段播放

EnemyTurnPresentation.actionSegments按CardPlayed/EnemySkillUsed边界划分事件，视图顺序await每段动画，命中回调只消费本段健康事件，未找到命中点的剩余效果在本段结束时赋服务端final值，不越界消费下一个技能。保留generation取消检查和整轮投影，全部段结束才恢复最终快照。当前仍采用既有敌方动作结束命中回退，并非已恢复原命中时刻。

tools/test_enemy_turn_presentation.mjs增加实际battle-session生成的攻击→护盾→攻击三技能事件，验证顺序、每段伤害/护盾归属和连续生命100→93→86，测试及严格TS通过。Web构建成功；现有教程单技能回归实测队列日志EnemySkillUsed 990，完成后回合4→5、生命1064.8→762.8，恢复手牌，error/warn为空，截图action-queue-live.png与action-queue-complete.png。

三技能目前完成事件分段测试与共享视图接线，尚未在图形场景中执行三段连续演出验收；不能把单技能浏览器回归称作多技能完整验收。原生包未更新。

## 2026-10-14 三技能图形场景验收

自定义关卡加载器新增可选 enemyIntents，每项为一回合按顺序执行的已有技能 ID 数组；沿用 validateDefinition 校验数量、结构和引用，不增加可执行脚本。省略时保持基础关卡安排。server/data/custom/three-skill-preview.json 使用 [["990","992","990"]]，明确标记为自定义测试关卡。六项自定义配置测试通过，包括冻结、非法引用拒绝、持久化和基础配置隔离；事件分段测试通过。

独立测试服务使用临时端口53835与 runtime/server/three-skill-preview.sqlite，浏览器实际创建档案、开始战斗、点击回合结束。日志确认 fire → skill_3 → fire 依次启动，三次健康值回调分别为玩家1466.8/敌盾0、玩家1466.8/敌盾300、玩家1164.8/敌盾300。完成画面为回合2、能量3/3、手牌3、弃牌3，error/warn为空。证据：analysis/battle-ui/three-skill-live.png、three-skill-complete.png、three-skill-browser-logs.json。验收后关闭临时服务及测试页，常用7458服务保持运行。

这验证重建客户端的多段播放与数值分段，不证明原版命中时刻或完整演出一致。自定义卡尚无专属卡图；完整特效、音效、原版界面与原生包本轮未更新。

## 2026-10-14 回合控件原动画资源提取

tools/inspect_selection_timeline.py 的有界时间轴读取器抽为 read_timeline，旧选牌时间轴逐字段回归一致。新增 tools/recover_end_turn.py，从哈希校验后的 EndArea.csb 读取全部轨道、层级和片段，校验每条 action_tag 对应真实节点；按原 FightPanel 图集解码、裁切并还原透明边距，输出41张纹理和逐张PNG/RGBA哈希。另提取两份粒子plist配置，记录内嵌纹理存在性。产物位于 analysis/battle-ui/end-turn/，contact-sheet.png 仅为资源检查图。

原片段为 black_in(5–27)、black_out(30–41)、white_in(45–68)、white_out(75–87)、white_loop(90–185)，CSB speed=.5、duration=185；帧编号不能直接冒充已验证的原版墙钟时长。轨道包含FileData、Alpha、Position、Scale、CColor、RotationSkew和IsPlaying；存在非线性缓动及粒子启停。因此不能用单一图标透明度循环替代完整原动画。

本轮为普通静态工具证据，非REA运行时证据。41张PNG哈希核验通过，选牌及EndArea时间轴回读一致。资源尚未接入客户端，现有预览仍使用静态回合控件；后续需实现分层透明度、缓动、状态切换与粒子，验证后才能声称恢复播放。

## 2026-10-14 回合控件共享客户端播放

新增 EndTurnView.ts 和生成模板、prepare_end_turn.py，加载41张原纹理及两份粒子参数，渲染原层级、锚点、透明度、位移、缩放、颜色、纹理轨道和粒子启停。五段片段按有可用牌/无可用牌及敌方演出状态切换；无可用牌判断覆盖当前教程的能量条件，不代表原游戏所有卡牌限制。保留原静态控件作为资源加载失败回退。关闭页面停止粒子，销毁时释放资源及更新监听。

Creator 对两份原内嵌 zlib PNG 报 unknown image format；准备脚本无损解压原PNG，移除客户端副本中的纹理内嵌字段，以独立SpriteFrame绑定，原提取文件未修改。缓动映射参考标准Cocos2d-x 3.17.2的CCTweenFunction.h/cpp，保存在tools/reference/cocos2dx并记录URL/哈希于end-turn/easing-reference.json，未证明原生fork逐项相同。直通PNG的加法层采用SRC_ALPHA/ONE适配。

本轮实测发现选牌光效此前挂在不携带dt的Director BEFORE_UPDATE事件上，导致停留首帧；EndTurnView初次接线也受影响。两者现改读game.deltaTime。先前截图只能证明选牌资源显示，不能证明当时序列帧已播放。当前计时仍采用先前恢复的interval和CSB speed，未获得原客户端墙钟对照。

严格TS、Web构建、223个原关键帧精确采样/全区间有限性/纹理离散切换测试通过。实际浏览器在第5回合出三张牌至能量0，捕获black_out→white_in→white_loop，点击结束回合捕获white_out→black_in。证据为analysis/battle-ui/end-turn-white-loop.png、end-turn-transition.png、end-turn-black-restored.png、end-turn-animation-logs.json。验证期间曾出现getDeltaTime弃用警告，随后改用game.deltaTime并重新构建。原生分发包未更新；完整原版视觉一致性仍未验收。


## 2026-10-14 同步Android与Windows分发包

Android APK更新为 `e920e7c96254bf4fb4f6f8b36a741ec576e3bfbbcd4cdd344da8701231b4268e`，100,834,010字节；签名/结构通过，23项内容检查通过。Windows x64便携ZIP为 `runtime/dist/hczs-windows-x64-preview-994d087ca465.zip`，66,879,135字节，SHA256 `bfcfad668691de6e7dec526e911ad3dda40cb4c6a0e93996d51e87a2bbecf6a4`；导出、配置、编译成功，24项内容检查通过，ZIP CRC及每个文件哈希通过。两端各545个导出资源一致，包含原回合动画/粒子、连续技能和选牌计时修复。

本轮仅构建与静态包验证，没有实际启动这两个版本；macOS/iOS未构建，跨平台游玩验收仍未完成。完整原版战斗、剧情及表现缺口保持开放。


## 2026-10-14 回合按钮动画期间禁用输入

trace_end_turn_control.py新增五个原方法的静态导出，证据为end-turn-completion-evidence.json。_refreshNonCardCanUseState先setTouchEnabled(False)，_onAniBlackInEnd和_onAniWhiteInEnd调用_setBtnTouch，白色入场结束后启动white_loop；说明入退场期间不应接受结束回合操作。

EndTurnView新增acceptsInput及就绪状态回调；入退场和隐藏禁用，黑色入场完成或白色循环恢复，再与当前控制器canAct合并。提交回调另行检查就绪状态，防止旧按压跨越状态变化后提交。资源未成功加载时保留静态回退。严格TS、原关键帧采样测试和Web构建通过；本轮Android/Windows既有包未重新构建，仍是上轮哈希。

浏览器进入战斗后立即点击右侧按钮，回合保持6、生命460.8；入场完成后再次点击，正常执行敌方回合。提前点击测试同时经过异步存档加载，故仅作为入口防误触回归，不声称精确覆盖动画每一帧的边界。

## 2026-10-14 敌方命中查询链定位

新增tools/trace_enemy_event_query.py。未重复角色包扫描，转查原脚本与原生绑定：模块8905 CompAnimation.getAnimationEventTime先解析动画实名并检查hasAnimation，再调用Model.getAnimationEventTimeMilliseconds，非None结果除1000。模块4254实际从_animationEventTimeInfo字典读值；_initModelInfo通过RawModel.get_anim_names/get_anim_length/get_anim_event_count/get_anim_event_name/get_anim_event_time建立缓存。缺失键返回None，不能仅根据XML未命中推断原生返回值。

在固定SHA的libclient.so中，方法表文件偏移0x2ab7108/0x2ab7118/0x2ab7128分别绑定count/name/time，Thumb函数指针为0x9d8655/0x9d86ed/0x9d87a1。time包装器在RawModel非空时进入0x9d13b0；0x9d1470读取RawModel虚表+0x738，0x9d147a调用，以动画ID及16位事件索引为参数；返回float32转double给Python。静态导出和完整局部反汇编均带哈希，证据在analysis/battle-visual/enemy-timing/query-chain.json及关联文件。

本轮仍未定位具体RawModel虚表及底层事件存储/加载器，也没有魔方实际事件数和时间。不得据此改写命中比例；客户端继续采用已明确标注的动作末尾回退。此为普通本地静态工具证据，非REA运行时证据。下一步已有精确原生入口，应沿+0x738实现追踪，而非再次盲扫同一角色包。

## 2026-10-14 骨骼模型事件时间存储访问器

新增tools/trace_enemy_event_storage.py，通过ELF LOAD映射、RTTI类型名和虚表槽位校验定位neox::world::ModelSkeletal虚表VA 0x2984194，父类Model为0x2982fe8。四个事件接口槽+0x72c/+0x730/+0x734/+0x738分别转发到0xa4c0f8/0xa4c078/0xa4c110/0xa4c160，转发前读取模型对象+0x438。证据包含类型信息和四份局部反汇编，保存在analysis/battle-visual/enemy-timing/storage-chain.json。

时间访问器检查内部对象+8所指对象的+0x948/+0x94c容器是否为空，使用首项的+0x94动画指针数组，再从动画+8的事件指针数组按索引读取事件首字段float32；无容器或事件索引越界返回0.0。此处没有时长乘法或单位转换，Python消费者随后除1000。计数访问器还检查动画索引范围，调用动画对象虚表+0x1c并截断为unsigned16。名称查找失败返回-1，按索引取名越界返回空指针。

这确立了具体骨骼模型查询实现和缺失分支，未确立魔方的实际事件数据。事件数组的构建/填充与资源加载来源仍待追踪，不能把缺失分支0.0当成魔方所有事件均为零。客户端命中回退和现有分发包本轮未修改。

## 2026-10-14 触发器写入动画事件的分支

新增 tools/trace_enemy_event_loader.py，验证固定 libclient.so SHA、ELF映射、属性字符串及虚表。MeshSkeletalData 虚表 VA 0x2982d00 的 +0xe8 指向 AnimationEventTracks 处理函数 0x95d7b0；+0xec 指向另一个函数 0x95dd3c，后者从对象+0x720资源读取 Triggers。两者是不同函数，不能把中间字面量池或相邻代码当成同一加载流程。

后者在0x95e294读取 TimeRatio，输出至sp+0x3c，默认-1.0。在对象+0x754字符串长度条件为零的分支中，解析动画ID，按名称查询此前定位的+0x94 / +8事件数组。TimeRatio大于-1时，将它与动画容器虚表+0x44返回的float相乘，已有事件直接覆盖首字段，缺失事件经0x9970ee转发到事件对象虚表首槽创建。SkelAnimsData的+0x44返回所选动画+0x48c字段；该字段赋值及单位本轮尚未独立证明，不据此声称完整时长转换已经确认。

对固定SHA的enemy-music.ags（character.npk条目2191）逐项解析，六个clip含fire/hit_1/death/skill_1/skill_2/skill_3，没有attack或attack_N命名事件。声音触发点不能当作伤害命中比例。结果与五份局部反汇编保存为analysis/battle-visual/enemy-timing/loader-chain.json及关联文件，脚本运行通过。此为普通静态证据，非REA或原客户端运行时证据。

尚需解析原事件构建对象、主动画资源的事件加载和调用顺序，并验证魔方最终事件缓存。本轮未修改客户端命中时刻，也未重建分发包。

## 2026-10-14 主动画事件容器及版本化XML加载

沿SkelAnimsData的+0x94事件数组定位到构造函数0xaee550，计算其PC相对虚表地址为0x298cfbc，RTTI确认为neox::world::AnimTriggerContainer。构造参数float保存到+4，事件数组在+8；虚表首槽0xaf0250负责按时间定位并插入事件，同时间且非空名称走名称更新，空名称存在删除分支，不能将此接口简化为append。+0x1c槽0xaf0398按数组起止差除4返回事件数，闭合此前计数查询中未确定的虚调用。

主XML路径0x995c94读取AnimationEventTracks和Version（默认1），按轨道名称缓冲区+11解析动画名；这与EventTrack_前缀长度相符，但不证明原生会验证前缀。它用所选动画+0x48c字段构造事件容器，装入+0x94数组，再调用0xaef030。非Morph子节点在unsigned Version<=1时读取Time，否则读取TimeRatio并乘容器+4的float；结果存事件+0，Name存事件+4。动画+0x48c字段的赋值及单位仍需独立追踪，尚未声称原客户端墙钟时刻一致。

tools/trace_enemy_event_loader.py新增RTTI/虚表/版本及属性字符串校验，导出主XML分派、构造、XML读取、插入与计数四个范围，总计九份哈希绑定反汇编。脚本通过，loader-chain.json更新。它证明了具体存储类型和XML转换分支，不证明魔方最终加载的事件集；也不排除其他二进制加载路径。客户端和分发包未改动，魔方命中时刻仍未解决。

## 2026-10-14 动画时长字段与缺省事件

原生固定记录读取器0x990128在0x9901d0将RGIS记录+0x44c复制到BonesAnimData+0x48c，末尾前进0x454即1108字节；0x994556为其调用点。inspect_neox_animation.parse_library现解析该字段为duration_ms并记录绝对源偏移，拒绝负值及非有限值，保留其余不明字段。魔方fire/idle/skill_2/skill_3四份独立ACL头部时长与该字段除1000相符，误差均小于0.001毫秒。fire约1166.666626毫秒，idle约3333.333252毫秒，skill_2为3000毫秒，skill_3约2166.666748毫秒。这补上了前轮未确定的固定记录赋值和毫秒单位证据，非墙钟实测。

同时定位缺省分支：0x994112遍历+0x94事件槽，只有空槽才调用0xaef810，用动画+0x48c构造容器并创建start(0)及end(传入值)，没有attack。该分支解释了没有显式事件轨时仍可能查询到开始/结束事件，不能把缺省容器称为零事件。魔方最终是否经过此分支以及之后的所有覆盖仍需确认。

trace_enemy_event_loader.py新增五份局部反汇编及四个源哈希绑定的独立时长对照，现有14份导出。13项动画解析测试通过，包括实际艾尔莎stand_idle时长与ACL对照及负值/NaN/Infinity拒绝。原生ACL上下文亦独立计算(samples-1)/sample_rate，但这是另一字段，不能与动画对象的毫秒字段混用。客户端视觉及分发包未改动；主库仍有不明固定字段，不把结构完整覆盖当成所有语义已经恢复。

## 2026-10-14 终局存档恢复死亡姿势

当前原死亡动作已接入，但旧setOutcome在重载终局存档时直接隐藏落败模型。PrologueSceneView现对没有播放过程的won/defeated恢复原death动画末帧并暂停；重开playing清除死亡标记并恢复待机。TutorialBattleView显式传入presentationBusy，整个动作队列完成之前不提前套用终局姿势，内部完成回调保持该等待标记，避免致命攻击尚未播放就把目标判为已死、跳过死亡演出。此次是重建客户端存档表现修复，不声称原版终局界面一致。

模板与生成的两份客户端源码同步；严格TS与Web构建通过。浏览器实际从第7回合玩家158.8生命结束回合，日志顺序enemy fire→player death，玩家归零后保持倒下姿势；重载页面并进入战斗，日志出现restored terminal death pose，人物仍显示原死亡末帧；点击重开首战恢复第1回合满血和待机。warn/error为空。证据：analysis/battle-ui/terminal-live-death.png、terminal-restored-death.png、terminal-restarted-idle.png及terminal-pose-logs.json。

本轮图形验收覆盖玩家失败及重开；敌方胜利存档使用相同恢复方法，但本轮未另做胜利重载实测。Android/Windows既有包未重建，macOS/iOS环境和原生运行验收仍未完成。

## 2026-10-14 终局姿势修复同步原生分发

Android和Windows现已重新构建，包含上轮终局存档姿势修复与此前的回合动画输入控制。Android APK为100,834,380字节，SHA256 `cb3e134d744e30ec0ba7dd5604d415dc0a83ff3a7e5d36a23e79df02a2163e5a`；签名、CRC、arm64和16KB对齐通过，24项内容检查通过。

Windows便携包为 `runtime/dist/hczs-windows-x64-preview-28b6a73690e4.zip`，66,879,426字节，SHA256 `438971d6f87a7ab2e9ef332155cde815210f93506a2b63f3a056b06787a68795`；导出、配置、编译均成功，25项内容检查通过。两端各545个导出数据文件与实际分发资源一致，ZIP CRC和逐文件哈希通过。Windows模板检查补入PrologueSceneView，两端增加终局恢复与输入控制的编译标记检查。

本轮未执行原生客户端，未证明最新包的图形、输入或网络兼容性；macOS/iOS未构建运行。已有Web实测不能替代四平台实际游玩验收，持续目标保持未完成。

## 2026-10-14 胜利闭环与存活角色初始化修复

浏览器7456连接本地7458，使用现有5能量、6张起始手牌的自定义预览配置，通过真实拖牌在第二回合击败魔方。最后斩击前敌方262生命，动作日志依次为CardPlayed 110001、fire_1、enemy death、生命0；画面显示胜利并保存。重载页面后进入战斗，第二回合、玩家1466.8生命、敌方0、手牌和胜利结果保持，原death末帧恢复。该配置不是原版战斗规则完整还原。

实测发现存活艾尔莎在终局加载时，待机动画尚未采样就被暂停，停在初始模型姿势。PrologueSceneView及模板现于加载存活角色时先sample待机，再应用终局暂停。死亡角色跳过待机采样，直接恢复death，避免先采样idle影响未覆盖的变换。严格TypeScript和Web构建通过；再次重载胜利存档，艾尔莎恢复正面待机姿势，魔方保持与修复前一致的死亡末帧。浏览器warn/error为空。

证据为analysis/battle-ui/terminal-live-victory.png、terminal-restored-victory.png（修复前）、terminal-restored-victory-fixed.png（修复后）、terminal-victory-logs.json及terminal-victory-fixed-logs.json。本轮仅更新Web，Android/Windows分发包尚不含本次初始化修复；未验证原生运行、macOS/iOS或完整原版效果。

## 2026-10-14 存活角色终局待机修复同步分发

已将胜利存档中存活角色先采样待机、再应用终局暂停的修复重新导出到Android和Windows。死亡角色跳过待机采样，保持原death末帧恢复路径。此行为的Web实测证据见terminal-restored-victory-fixed.png。

Android调试APK为100,834,436字节，SHA256 `2eadb2d507f495bc0895785f35659b69a0a0c873410b3aa56b50049359d136e5`。签名、CRC、arm64及16KB ZIP/ELF/GNU_RELRO检查通过，内容检查通过，545个导出文件与APK一致。

Windows包为runtime/dist/hczs-windows-x64-preview-e10acebac65f.zip，66,879,482字节，SHA256 `831f9e6556119ce6a4760f4106adf88141c9f4f32fd19c0fb1564fa65fa42a04`。导出、配置、编译及内容检查通过，545个数据文件一致，ZIP CRC与逐文件哈希核对通过。

本轮仅证明打包内容同步，未运行两个原生客户端；Android实际设备闭环、Windows输入和图形验收、macOS/iOS构建运行仍未完成。证据位于analysis/cocos-android及analysis/cocos-native-model的verification JSON。

## 2026-10-14 魔方音效元数据与实体文件缺口

新增tools/inspect_enemy_audio.py，只读校验固定APK SHA，重新提取wwise.npk条目24并与既有SoundBanksInfo XML逐字节核对。元数据的m_mofang（bank ID 1920512335，版本120）列出14个事件与16个IncludedMemoryFiles，包括fire、death、hit和skill声音。原enemy-music.ags也明确引用wwise/m_mofang.bnk中的事件。

实际ZIP目录没有assets/res/wwise/m_mofang.bnk，按已有资源哈希/挂载规则查询wwise.npk也无对应路径。16个音频ID均没有assets/res/wwise/<ID>.wem独立文件。完整范围和元数据原始来源保存为analysis/battle-visual/enemy-audio/report.json及SoundbanksInfo.source.json。脚本成功结束并明确bank_present=false，不能把元数据存在当成音频载荷存在。

未排除声音位于其他合并bank、别名路径或未解析载体中；没有宣称全部声音不可恢复。动画ObjectFileID与BoundObject/Wwise事件的映射仍未知，未用事件名相似性代替映射。本轮没有解码、播放或修改客户端音效。此为普通本地静态工具证据，不是REA运行时证据。下一步应检查现有合并skill/voice库是否包含这些确切事件ID及其媒体引用，或转向APK明确存在的艾尔莎音频库，不能直接播放占位音效冒充原声。

## 2026-10-14 合并音频库检查与艾尔莎技能音频提取

新增scan_enemy_audio_banks.py，校验APK及SoundBanksInfo哈希后，对全部101个独立.bnk解析BKHD/HIRC/DIDX有界记录。101个均通过边界检查；魔方14个事件ID在所有HIRC对象ID中零命中，16个媒体ID在全部DIDX中零命中。结果为analysis/battle-visual/enemy-audio/merged-bank-scan.json。包含skill.bnk和voice.bnk；两者各5/22个声明事件均命中，提供解析一致性检查。结论仅覆盖独立bank，不排除未解析封装或不同ID别名。

正向发现：ailisha_skill.bnk含120个HIRC对象，元数据32个事件全部命中，32个媒体存在。新增extract_elsa_skill_audio.py，将原bank和32个WEM原字节提取到analysis/battle-visual/elsa-audio，验证DIDX与元数据集合完全相同、范围与RIFF大小、各文件哈希。bank SHA256为109253cf1afd44f9aeb40a3eec3fd937d9b4878378cb866cdfbbc1f467602e42。32个媒体format_tag均为65535，不能当普通PCM WAV使用。

新增test_audio_bank_records.py，4项测试覆盖正常偏移、截断记录、长度不足、超限数量、尾随字节及重复chunk拒绝，全部通过。尚未解析事件动作/随机容器与媒体关系，未解码试听、接入客户端或验证原版时序。没有采用同名文件推断播放关系。以上均为普通静态工具证据，不是REA或运行时证据。

## 2026-10-14 艾尔莎事件到媒体的直接引用链

使用官方bnnm/wwiser仓库标签v20260808，固定commit 94580dd3de3280933d69c435e96d4e2c3b443207，保存于.tools/wwiser。运行wwiser.py -d xml -dn analysis/battle-visual/elsa-audio/wwiser-bank analysis/battle-visual/elsa-audio/ailisha_skill.bnk，解析无错误，输出wwiser-bank.xml。该外部工具提供字段语义，不能当作原客户端执行证据。

新增trace_elsa_audio_routes.py，对固定SHA bank和固定wwiser commit建立引用链，核对XML给出的ulID、ulActionID、ulActionType、idExt、fileID、ulPluginID、StreamType、sourceID、uInMemoryMediaSize的绝对偏移与原bank字节，再核对所指WEM长度和SHA。32个事件共33个动作，其中31个可直接到CAkSound媒体，2个动作保留为未解析分支。结果保存于analysis/battle-visual/elsa-audio/event-routes.json。

例如ailisha_fire_1：事件908995403→动作974931932（Play 0x0403）→声音301766640→sourceID 506616962；ailisha_crit_1：事件3973666223→动作3691022→声音934761255→sourceID 660670305。两者为bank内嵌VORBIS媒体（plugin 0x40001、StreamType 0），对应长度5028和14373字节。此处依据显式引用及原字节，不依据文件名近似。

尚未恢复音量/音高、总线、效果、动作属性、动画ObjectFileID映射，也未解码试听或接入客户端。构建包未变化。该进展只证明这批直接事件的媒体路由，不证明原版声音播放效果一致。参考工具说明：https://github.com/bnnm/wwiser/blob/v20260808/doc/WWISER.md 。

## 2026-10-14 艾尔莎原始技能声音PCM解码

从vgmstream官方GitHub发布r2117取得vgmstream-win64.zip，上游API SHA256为6c4a8a3813864fefed081bbd337dbc0ad93bf88e0b92f5db98d7ab258b22dc6c，下载后核对一致，工具单独放置.tools/vgmstream-r2117。新增tools/decode_elsa_audio.py，每次先验证发布ZIP哈希及解压EXE/DLL逐字节一致，再核验WEM与bank原始范围和哈希。

32段原始WEM全部成功解码为16位PCM WAV，保存analysis/battle-visual/elsa-audio/pcm。逐文件验证采样率、声道数及解码器报告的源样本总数一致，PCM非空且非全静音，记录峰值、RMS、输出哈希；总时长78.129365079秒。报告为decode-report.json，逐条stdout/stderr保留在pcm/<ID>.log。

例如普攻事件所指506616962.wem是44100Hz单声道，34112采样，约0.774秒；其PCM可作为源载荷试听。此处使用-i忽略循环，只解码一次原媒体，不实现Wwise事件音量、音高、总线/效果、空间混音或动画触发。非静音和格式检查不等同听感验收，未在游戏客户端播放，未更新四平台构建。

复现：先运行extract_elsa_skill_audio.py，再运行decode_elsa_audio.py。官方工具来源：https://github.com/vgmstream/vgmstream/releases/tag/r2117 。

## 2026-10-14 动画声音对象哈希与触发比例

原艾尔莎gim的MusicAgs显式指向character/player/ailisha/ailisha_music.ags，已从character.npk条目6122提取（SHA256 90287a47b0b2cfa55e866d539fa8016e9953e6c1119b84e5cb5f9a513984ec8a）。新增trace_animation_audio.py保留BoundObject.Name的原始斜杠，使用已有原生静态验证的StringIDLegacy按UTF-8原字节计算，48个唯一trigger ID全部对应到对象名，且所有显式ObjectFileName均一致。共61个触发；魔方同法13个唯一ID、14个触发全部匹配。结果animation-cues.json。这解决了前轮对声音对象ID套用资源路径标准化而无法匹配的问题。

当前使用动作的音效TimeRatio为crit_1=0.0011、death=0.0012、fire_1_1=0.2783、fire_1_3=0.2160。对应ailisha_skill原bank路由已逐级连接。fire_1的sound比例0.0023，但原对象名为wwise\\skill.bnk:skill/Event|ailisha_fire_1，不能在未解析加载/别名行为时直接改称ailisha_skill.bank路由。语音事件指向ailisha_voice或voice，尚未解析对应媒体。保留原bank引用，避免同名事件掩盖加载差异。

此为源配置与普通静态工具证据，未证明原客户端墙钟时机、混音或动态选择；未向客户端接入声音，现有安装包不变。下一步可优先接入已有精确路由的暴击/二连斩音效，但需恢复音量等播放属性并明确尚未覆盖的语音。

## 2026-10-14 艾尔莎声音混音父链

新增trace_elsa_audio_mix.py，从已验证事件路由的31个直接声音对象逐级解析DirectParentID，所有父链均在ailisha_skill.bnk闭合，最大深度4。对对象链接、属性ID、计数和Volume/Pitch/UserAuxSendVolume0的float值逐个按XML绝对偏移核对原字节；保留每层RTPC原XML，并检查保存数量与ulNumRTPC相同。结果为analysis/battle-visual/elsa-audio/mix-ancestry.json。

暴击声音934761255本层无静态属性，经333088761父节点Volume=-3.0到336509105父节点Volume=-1.5，再到683721515。普攻声音301766640有Pitch随机范围[-150,150]，其父724937876的Volume=-5.0，再到相同上层。336509105有3个RTPC，683721515有1个，包含游戏参数驱动的音量/音高等动态曲线。因此不能把静态父链音量和直接称作原版最终响度。

另已从APK提取init.bnk并用固定wwiser版本导出wwiser-init.xml，供后续追踪参数默认值与总线使用；本轮没有解析或实现完整总线图、空间混音或播放调度，也未向客户端加入音效。所有结论来自普通本地静态数据，不是原客户端运行证据。

## 2026-10-14 double_speed默认值与零区间

新增trace_elsa_audio_defaults.py，直接用APK内init.bnk/ailisha_skill.bnk核验已提取字节，并从wwise.npk条目6重新提取名称表。名称行将54353430唯一绑定到double_speed。init字段RTPC_ID位于452，fValue位于456，默认1.0；rampType为0、上下坡时间0、无内置参数绑定。

对mix-ancestry中的所有曲线逐字段核对原bank偏移。double_speed的四条曲线分别作用于上层Volume、Pitch、LPF和再上层LPF；默认1.0处于0到1.9980751276016235的恒定零区间，区间两端输出0，Interp=9。保存完整关键点与源哈希至analysis/battle-visual/elsa-audio/dynamic-defaults.json。只评价这个已核验的零区间，不冒充通用插值/缩放实现。

另有3条其他参数曲线保留为unresolved_curves，没有对其默认行为作推定。原游戏可以运行时覆盖double_speed；本次只确认bank的作者默认值，不证明运行值。总线、效果和完整混音仍未完成，未改客户端或安装包。

## 2026-10-14 首批原声音效接入Web战斗

新增prepare_cocos_audio.py，按已核验的事件路由准备crit_1、fire_1_1、fire_1_3、death四个PCM及cues.json；源比率分别0.0011、0.2783、0.216、0.0012。静态父链音量分别-4.5、-6.5、-6.5、-7.5 dB，仅用于重建预览；原Wwise总线、效果、随机音高、语音与完整动态混音仍未实现。fire_1旧bank别名及魔方原音频继续保持未接入，不播放替代声音。

新增共享BattleAudio组件（模板及客户端同步），预加载AudioClip，以动画时长乘原比例调度，AudioSource播放并在ENDED销毁节点；取消动作清除待触发回调，隐藏/销毁战斗停止声音并释放引用。正常动作结束允许已启动的声音尾段自然结束，读回终局存档不会重播死亡音效。create_cocos_poc已增加组件复制。

严格TypeScript和Web构建通过。实际UI重开首战并拖出二连斩击、猛力斩击，先后记录fire_1_1、fire_1_3、crit_1三次AudioSource STARTED；控制台warn/error为空。证据为analysis/battle-ui/audio-first-integration.json和.png。STARTED证明引擎启动播放，不等同扬声器听感/原版混音一致性。死亡音效、取消与退出清理尚未另做运行时专项验证；Android/Windows包未同步，四平台完整游玩未完成。

## 2026-10-14 音效生命周期回归

新增tools/test_battle_audio.mjs，直接载入与客户端逐字节一致的BattleAudio模板，以确定性调度器和AudioSource替身验证取消前/后的回调、已开始尾音、活动声音清理、异步加载期间销毁、无效比例拒绝。首轮发现仅unschedule不能防御已从调度队列取出但尚未执行的回调：取消后直接执行所捕获回调仍创建声音节点。

BattleAudio.schedule新增cancelled标记并在回调入口检查，disposed后schedule直接返回空清理函数。模板与客户端同步。五组场景重跑通过：取消无声音；正常结束不截断已开始尾音；stop清理活动节点与未来任务；重复destroy不重复减引用；销毁后到达的加载不保留clip。严格TS和Web构建通过。

这是组件隔离测试发现并修复的竞态边界，不声称已在浏览器实际复现该调度竞争。上轮真实出牌STARTED证据仍仅覆盖二连斩与暴击；死亡声音、原生播放和完整混音尚未验收。Android/Windows现有分发包尚未包含新音效组件，本轮未重新打包。

## 2026-10-14 首批原声音效同步原生分发

Android和Windows已重新导出并编译，共享客户端包含BattleAudio、四段原始解码PCM、AGS触发比例及取消标记修复。新增verify_audio_content.py，验证组件模板相同、编译后加载/取消标记、四个资源入口、源WAV与cue哈希、实际分发文件中四段PCM哈希存在。与既有逐文件导出比对联合使用，仅证明打包而非播放。

Android APK为101,367,421字节，SHA256 04f9bdba64870c52fbb6a2435d292ff443489f776fda15b5c49d833f8f216371；签名、CRC、arm64和16KB静态检查通过，29项内容检查通过，554个数据文件与APK一致。Windows包runtime/dist/hczs-windows-x64-preview-c438988ee542.zip为67,253,874字节，SHA256 950b18963ccdd32af2be094afd736e89dd77e34e50af6c777aededd3296fd67b；30项检查通过，554个数据文件一致，ZIP CRC和逐文件哈希通过。

未运行原生客户端，没有设备音频/触摸/图形验收；Web STARTED证据仅支持Web。死亡声音实测、普攻旧bank加载、完整语音/混音和macOS/iOS仍未完成。

## 2026-10-14 艾尔莎轻重攻击及技能语音链

从APK提取ailisha_voice.bnk并用固定wwiser v20260808导出wwiser-voice.xml。新增trace_elsa_voice.py，对轻攻击1341919569、重攻击145566836、技能485176467三个显式语音事件解析动作引用，逐项按bank偏移核对动作ID、目标ID、列表条目及声音sourceID/StreamType/plugin。报告voice-routes.json保留有序动作与列表。

轻攻击和重攻击均先指向CAkActionStop，再播放CAkRanSeqCntr，最后还有另一个外部目标的CAkActionPlay。两个容器eMode=1（Sequence），不是直接随机选句；轻攻击列表5项、重攻击4项，含重复共享声音。技能事件也有Stop、直接CAkSound及外部Play。三事件合计定位并提取7个独立流式WEM到voice-media，每个保留APK成员名、字节数和SHA。

额外播放目标222648278、837669331、1021955510未在全部101个独立bank的HIRC对象ID中找到。只证明该范围内缺失，不能断言运行时没有其他载体或热更bank。未省略这些动作并冒充完整复现。列表的reset/global等运行语义、混音、解码试听和客户端语音播放尚未实现；现有音效构建不变。原始XML保留完整字段以供后续跟踪。

## 2026-10-14 Web游戏视口替换默认演示外框

旧入口使用Creator默认1280×960外框，叠加标题、白底和页脚，16:9战斗在框内另留黑边。新增tools/templates/cocos-web及对应项目build-templates/web-desktop，以原1280×720设计比率随可用窗口等比缩放、居中；移除演示页标题、边框、阴影和页脚。create_cocos_poc.py同步复制模板，Creator实际Web构建已验证采用模板，保留官方引擎启动脚本插入点。

浏览器实际验证1280×720窗口内canvas为1280×720、原点(0,0)，无页面滚动；拖出强力斩击，敌人生命3155→2673、能量2→1、手牌4→3。390×844窄窗口canvas为390×219.375、居中且无裁切/滚动；这只证明等比显示，不代表竖屏操作体验或移动设备验收。测试后恢复默认窗口。截图analysis/battle-ui/responsive-landscape.png、responsive-portrait.png。

这是Web入口显示改进，不是原版HUD/镜头/三人队伍还原。原生安装包未改变，尚未补齐的战斗表现仍按原缺口记录。

## 2026-10-14 原始头像血条布局及槽位证据

新增tools/trace_battle_health_ui.py，从哈希验证的APK和脚本提取PlayerHeadArea、MonsterHeadArea、BossHeadArea、HpShieldArea、FightMainPanel五个原CSB；独立保存analysis/battle-ui/health/layouts.json、各模块_initAutoWidgets反汇编和runtime-placement.json。复用有边界检查的CSB读取器，新增标准LoadingBarOptions的textureData、percent、direction字段读取（缺字段采用schema默认80/0）。这是普通静态工具证据，不是REA运行证据，未执行原客户端。

PlayerHeadArea与MonsterHeadArea的hp_bg和hp尺寸均154×18；BossHeadArea为464×18。玩家hp使用img_hp_normal.png，普通敌人作者默认img_hp_low.png，Boss作者默认img_boss_hp_low_normal.png；运行时refreshBloodTexture仍可换图，不能把作者默认当作所有战斗状态。原shield另有独立背景、条和图标，并非现预览的纯文本。当前预览两条404×18顶部血条属于重建简化，尚未按本证据替换。

FightMainPanel的LeftTop=(0,720)、RightTop=(1280,720)，三玩家槽x=120/290/460，三敌人槽x=-120/-290/-460。PlayersHeadArea.initComponents构建槽数组的顺序是left_3、left_2、left_1；MonstersHeadArea按right_1、right_2、right_3。getHeadAreaPos字节码在Group2长度为1时返回槽数组[1]，否则返回[idx]。不能把单角色简单放进最左槽后称为原版。

_canUseBossHead包含非从属敌人存活计数及IsBoss判断，尾部有未在当前opcode表标注的短路跳转；完整选择谓词及首战魔方IsBoss数据仍需核验。原层级Panel锚点(0.5,1)、尺寸180×140，其Node位置(90,84)，必须计入父锚点再换算屏幕坐标；不能直接把hp_bg的(0,-30)当成屏幕位置。动画、运行时缩放、血量插值及布局控制尚未移植，本轮未更改可玩预览和原生包。

## 2026-10-14 首战魔方精英分类链

新增tools/trace_tutorial_health_kind.py，重新通过哈希验证的静态表解析器提取monster_table的991行，并导出CMonster.IsBoss/getPropertyData、const.MonsterType、UIDataSource.getMonsterStaticData及MonsterDataTools的映射证据到analysis/battle-ui/health。源991行difficulty_type=1；MonsterType枚举Normal=0、Elite=1、Boss=2。MonsterDataTools模块偏移413–428把constant_path=[44]的lambda与DifficultyType键绑定；该lambda三条指令读取monsterData.difficulty_type并返回。CMonster.IsBoss比较getPropertyData()['DifficultyType']与const.MonsterType.Boss。

因此自带表及该静态调用链下，魔方991为精英而非Boss；应使用MonsterHeadArea作为本地恢复的血条布局来源，不能因单敌人就选BossHeadArea。工具对枚举值、表值、lambda结构作变化检查，保存tutorial-kind.json；没有执行APK代码。原服务端覆盖、完整LazyDict行为及场景选择分支不在此证明范围。当前预览尚未替换旧Boss血条，下一步应结合原槽位和锚点恢复MonsterHeadArea，而不只换颜色。

## 2026-10-14 普通敌人血条首批接入

recover_battle_ui_sprites.py新增MonsterHeadArea原hp、hp_bg和护盾图标，累计12张图；沿用固定APK、plist、纹理SHA校验及旋转/裁边恢复。TutorialBattleView模板与客户端同步，把魔方原先404×18 Boss贴图改为普通敌人的154×18血条。单敌人right_2位于设计坐标(990,720)，扣除Panel锚点和Node偏移后的局部原点为(990,664)，hp_bg(0,-30)落在(990,634)，转换至居中画布为(350,274)。血量数字居中叠在条上；护盾非零时显示原图标和重建数字补充，未猜测护盾容量分母。

严格TypeScript及Web构建通过。浏览器实际拖出强力斩击，魔方生命2673→2191，条长同步缩短，能量1→0；控制台warn/error为空。截图analysis/battle-ui/health/monster-hud-live.png。玩家血条仍为旧布局；头像、伤害预览条、多血条及运行时换色没有完整恢复。现hp采用原CSB作者默认img_hp_low.png；原MonsterBaseArea.refreshBloodTexture还引用UIConst.MONSTER_MUL_BLOOD_FILES，不能声称当前颜色在所有状态与原版一致。

魔方表MonsterHead指向uires/AllUIRes/Icon/HeadIcon/enemy/gw02p.png；该路径及经已知加载器映射后的.pkm均无直接NPK命中，只证明独立资源路径没有命中，不证明图集内缺失。头像仍待追踪图集。未重打Android/Windows包，未作原生UI验收。

## 2026-10-14 玩家原尺寸血条与受击验证

trace_battle_health_ui.py新增导出UIDataSource及FightDataTools的getBattlePlayerHeadInfos。后者从Group1实体读取posIndex作为listIndex，再交给PlayersHeadArea的left_3、left_2、left_1槽数组。当前本地首战没有原服posIndex证据，因此客户端明确以本地重建选择0号槽，不声称这是原教程服务器发出的值。

TutorialBattleView模板和客户端同步采用154×18玩家血条，0号槽对应源x=460（居中画布x=-180），同样按Panel锚点换算到y=274；当前生命数字居中。护盾非零显示原图标和重建数字，尚不实现原护盾容量/预判条。原服槽位、头像和完整运行时布局继续保留为缺口。

严格TS与Web构建通过；实际UI结束第1回合后，艾尔莎生命1768.8→1466.8、绿色条同步缩短，并进入第2回合，控制台warn/error为空。截图analysis/battle-ui/health/player-hud-hit.png。此验证支持Web现有受击显示，不证明原版命中帧时序或原生端表现。Android/Windows包未更新。

## 2026-10-14 魔方头像VT恢复与Web接入

新增recover_monster_portrait.py，重新验证APK并从monster_table 991的MonsterHead字段追踪原虚拟纹理配置。fullPathToPng匹配到icon/headicon/enemy/gw02p.png，pngsToPageID为[363,2,3,3]。在packed_png.npk扫描50个有界非tile元数据候选，找到唯一同名plist帧；提取9个ASTC原tile，沿用既有512列、124像素步长及2像素边界解码拼接，按原帧裁边/旋转信息恢复180×180透明头像。源表、VT配置、plist、tile和输出哈希保存analysis/battle-ui/health/monster-portrait/report.json。目视确认是紫色魔方头像，而非模型截图。此前独立资源未命中不代表缺失，本轮已闭合该图集路径。

原MonsterBaseArea.refreshHeadShow非Boss分支读取MonsterHead，Boss分支读取MonsterStripeHead；相应静态指令已加入health/runtime-placement.json。CSB的icon位置(32,-36)、尺寸180×180、scale=.5、底部锚点(.5,0)转换为当前画布中心(382,313)、90×90显示；head-back/head-front两个原背景按顺序翻转，第二背景透明度51/255。模板和客户端同步，recover_battle_ui_sprites新增两背景，recover_monster_portrait输出复制到recovered/battle-ui/monster-head.png。

严格TS、Web构建及真实浏览器显示通过，warn/error为空，截图health/monster-portrait-live.png。仍未证明原运行时色彩配置、所有头像状态/过渡或三人队伍；艾尔莎头像与原生包同步尚未完成。

## 2026-10-14 艾尔莎BattleIcon图集恢复

PlayerHeadArea.refreshHeadShow读取getCharStaticData(...).BattleIcon。CharDataTools模块将CharOtherData绑定getCharacterHomeBattleChessData，后者查询character_chess_battle_home；BattleIcon的两个lambda（constant_path 168、541）读取该对象.get('BattleIcon','')。原表8185的1号角色BattleIcon为uires/AllUIRes/Character/choose/1.png，不是IntentionHeadIcon或CharImage。静态链保存health/player-battle-icon-binding.json和runtime-placement.json。

recover_monster_portrait.py增加--actor player入口，复用VT解析/有界plist查找/解码流程，从3个原tile恢复212×124透明头像，源表和全部哈希写health/player-portrait/report.json，并复制player-head.png到客户端资源。CSB原icon=(1,-36)，scale=.75，anchor=(.5,0)，flipX=true，显示尺寸159×93；已按此接入既定重建0号槽，原背景层次及51/255叠层同步。

严格TS和Web构建通过，真实浏览器成功显示双方头像、当前第2回合存档和血条，控制台warn/error为空。截图health/both-portraits-live.png。未恢复死亡头像切换、受击状态、原服务器posIndex或三人战斗；原生分发包仍未同步这批HUD变更。

## 2026-10-14 头像死亡/存活状态接入与恢复验证

原HeadArea.showKilled切换alive/dead状态；两个自动布局模块的dead状态设Node Color.black，隐藏名字、护盾、Buff和属性图标，显示txt_dead并隐藏txt_hp。_initAutoWidgets中black实际为ARGB=[255,128,128,128]，并非更换DeadHeadIcon贴图。玩家txt_dead为“重创”，普通敌人为“消灭”。trace_battle_health_ui.py已保存状态方法及onUpdateDead/showKilled/refreshHpShow静态指令。

客户端按当前展示血量<=0切换已有头像/背景层的RGB128，保留透明叠层alpha；隐藏名字/护盾，生命文字改为相应死亡文字。恢复存活状态时复原RGB255、名字和生命文字。判定使用healthDisplay的动画展示值，回合上限失败且HP仍大于0不会误标死亡。现未有Buff/属性图标与预判击杀特效，因此这些原节点的完整状态尚未移植。

严格TS和Web构建通过。实际从第2回合击败魔方，验证头像变暗、名字隐藏、“消灭”标签；刷新网页重新进入后相同；重开首战后头像恢复亮度、名字及4600血量。控制台warn/error为空，截图health/defeated-hud-live.png、defeated-hud-restored.png、defeated-hud-restarted.png。玩家倒下“重创”分支本轮未实际触发，不能据敌人验证声明已完成；原生包未同步。

## 2026-10-14 玩家重创、死亡音效与读档实测

在现有Web客户端通过实际结束回合操作连续承受敌方攻击，没有编辑存档或直接调用调试接口。观察玩家生命1768.8→1466.8→1064.8，第三轮敌方施加300护盾且玩家不扣血，后续762.8→460.8→158.8→0，第7回合进入战败。玩家头像变暗、名字隐藏、血量位置显示“重创”、模型保留倒地姿态。敌方护盾图标/300数字实际显示，下一回合清盾后隐藏；该数字补充仍是重建显示，不等于完整原护盾条。

浏览器记录death/ailisha_death请求于2026-10-14T04:12:13.552Z，AudioSource STARTED于.578Z，ratio=.0012、gain=.4216965034285822。日志保存health/player-death-audio.json；这补齐四个已接入音效中death的Web启动验证，不代表扬声器听感或原Wwise混音一致。刷新重新进入战败存档后HUD与倒地姿态保持，音频日志仍只有先前一对请求/启动，没有新增死亡触发；warn/error为空。重开后恢复1768.8、站姿与正常头像。

截图health/player-dead-live.png、player-dead-restored.png、player-dead-restarted.png及enemy-shield-live.png。本轮无代码变动，完成此前未实际覆盖的玩家分支验证；原生包/设备声音、完整玩法与四平台交付仍未完成。

## 2026-10-14 HUD变更同步原生分发包

Android、Windows均从当前源码重新导出并编译；新增verify_health_content.py接入两端校验，覆盖头像提取物哈希、九项活跃HUD原图哈希、资源入口、实际包内PNG字节与状态逻辑编译标记。Android 36项内容检查通过，575个数据文件与APK一致，签名/CRC/arm64/16KB检查通过；APK101,483,803字节，SHA256 eb899f71d20bf21b70e05c878deba126b4dfb0c33429d2347a3938ed34809343。

Windows分发runtime/dist/hczs-windows-x64-preview-cf95c5510483.zip为67,368,122字节，SHA256 4e2aa753bb406ddabd098e4e72d64a4d16eaa5064082f66ddd3ac63e7170a43c。575资源文件与导出一致，ZIP CRC和逐文件哈希校验通过；客户端与DLL/Resources同包，Node服务仍需单独启动。没有执行原生游戏，校验仅证明构建及资源打包；macOS/iOS实际构建、设备输入/渲染/声音及完整游玩目标未完成。

## 2026-10-14 战斗语音 PCM 恢复与顺序参数证据

`tools/decode_elsa_audio.py --voice` 新增语音模式：重新校验原 APK SHA-256，将 voice-routes.json 中七个流式 WEM 与 APK 原成员逐字节比较，并校验声音库身份、RIFF 长度及格式。使用既有固定版本 vgmstream r2117（发行 ZIP 与解码器/DLL 字节校验）输出 `analysis/battle-visual/elsa-audio/voice-pcm/`，报告 `voice-decode-report.json` 保留源/输出哈希、采样数、峰值及 RMS。七段均为 32000 Hz 单声道 16-bit PCM，总时长 3.48396875 秒；均非静音且帧数与解码器所报源样本数一致。原技能音效模式复跑仍为 32 段、78.12936507936509 秒。

`trace_elsa_voice.py` 额外记录两个顺序容器的循环修正、过渡参数及 byBitVector 原字节和各位，逐字段/逐位回查 BNK。当前 flags=0x12：ResetPlayListAtEachPlay=1、Global=1、Continuous=0、RestartBackward=0、UsingWeight=0。该记录不意味着已经实现 Wwise 的重置和停止语义，尤其不能仅凭 reset 位声称每次从首段开始。三个外部对象 222648278、837669331、1021955510 在现有 APK loose BNK 搜索边界内仍无匹配。

本轮为普通本地静态工具证据，不是 REA runtime Evidence。没有将语音加入客户端，没有验证听感、事件增益、动态参数、总线处理或原混音；不会因此声称战斗语音已还原。后续需闭合语音触发、顺序状态及停止作用域，再接入现有动画调度并进行实际浏览器/原生验证。

## 2026-10-14 战斗语音触发、延迟与父级增益闭合

新增 `tools/trace_battle_voice_cues.py`，通过原 MusicTriggers 的完整对象路径和 SoundbanksInfo 事件名/ID，将 fire_1、fire_1_3、crit_1 的语音绑定到三个已提取事件；保留 10 个声音对象变体（共用 7 份 WEM），按源播放列表顺序输出。fire_1_1 的 vo 仍引用旧 voice.bnk/char01_attack，未用艾尔莎声音别名替代。报告 `analysis/battle-visual/elsa-audio/battle-voice-cues.json`。

扩展 trace_elsa_voice：逐字节验证 Stop_E/Play 类型、fileID、DelayTime/TransitionTime 整数参数、渐变曲线原字节和空排除列表，保留完整 action XML。三个事件均对 599096545 组执行 200ms Stop 渐变，Play 带额外 200ms 延迟；原渐变枚举为 4（Linear）。这说明动画 TimeRatio 之后仍有事件延迟，不能直接在比例位置播放 WAV。

trace_elsa_audio_mix 新增 --voice，恢复 10 条声音对象父级链，最大深度 5；所有已恢复声音均落在上述 Stop 目标组之下。每级静态 Volume 浮点值已回查原字节，RTPC 原 XML 保留。静态增益存在正值，个别声音还有 HPF，不能无声地把所有线性音量裁到 1 或声称静态增益即最终原混音。旧技能模式复跑仍成功恢复 31 条链、最大深度 4。三个外部 Play 目标仍未找到。

语音解码报告已随更新后的路由报告重新生成并校验引用哈希。以上均是普通本地静态证据；本轮未改客户端，也没有完成语音实播。下一步应将额外延迟、语音组渐停、顺序状态与增益处理一起接入，保留外部事件及总线/RTPC差异说明，并实测重复出牌、切场景和读档时无残留语音。

## 2026-10-14 三类原战斗语音接入 Web

prepare_cocos_audio.py 将 3 个已绑定语音事件加入 cues，与 4 个技能音效共 7 个触发项、11 份独立 WAV。BattleAudio 模板与客户端同步：事件标记后延迟 200ms，同语音组新事件取消旧待播放项并对正在播放者做 200ms 线性渐停；按已恢复容器播放列表逐次推进。正常动画结束只取消未来标记，已触发的延迟播放继续；stop/destroy 清理全部延迟与渐停。声音对象结束时取消其 tween 并释放节点，资源引用在销毁时释放。

由于 Cocos AudioSource 音量范围为 [0,1]，采用显式预览 master=0.8，统一作用于 SFX 和语音，保留各声音静态增益比例而不裁掉正 dB；不是原版总线音量。序列状态保留在当前 BattleAudio 实例，destroy 后清空；原版全局序列跨场景生命周期、停止后的序列语义仍未实测。新事件取消旧待播项是重建调度行为，未声称与原引擎完全一致。HPF、RTPC、外部 Play 目标和总线/效果仍未实现；fire_1_1 的旧 voice.bnk/char01_attack 不替换。

严格 TS、Web 构建通过。test_battle_audio.mjs 原 5 组加新增 3 组通过：200ms 延迟、正常结束保留延迟、序列循环、同组排队替换、无关 SFX 保留、退出清理及正增益余量。Tween mock 只验证调度和最终值，不证明真实声学渐变。

真实浏览器出牌：crit_1 技能语音事件04:24:19.036Z，requested .236Z，STARTED .237Z；两次 fire_1 顺序使用1071055798和147481426，事件到requested分别199/201ms；二连斩击的 fire_1_3 重击语音事件04:24:45.091Z，requested .291Z，STARTED .292Z。战斗血量4600→3877→3395→2913→2191。控制台warn/error为空。日志 voice-web-logs.json，截图 voice-web-live.png 均位于 analysis/battle-visual/elsa-audio。证明浏览器引擎启动和时序，不证明人耳听感或原混音相同。Windows/Android 分发包尚未同步本轮声音变更。

本轮退出实测补充：首次点击返回图鉴发现 `cancel is not a function`。真实 Creator 产物将 Set 展开编译成 `[].concat(this.pending)`，同样影响语音组和节点遍历；源码 mock 未覆盖此编译差异。已将四处 Set 快照改为 Array.from，模板与客户端同步，再次通过源码测试、严格TS及Web重建。修复后真实点击返回图鉴成功，重新进入后2191敌方HP及手牌恢复，21条已有音频日志没有新增，未重播历史语音。日志仅保留04:24:54.374Z修复前错误，无新增warn/error；证据 voice-exit-fixed.png、voice-web-final.png、voice-exit-audit.json。该退出检查在声音已结束后执行；有声音正在播放时退出的清理目前由mock覆盖，尚不作为真实设备实测。

## 2026-10-14 原语音与退出清理修复分发包

本轮已重新编译 Android arm64 和 Windows x64，把三类原战斗语音、200ms延迟/渐停、序列播放以及 Array.from 退出清理修复同步到原生包。共享音频校验新增路由证据输入哈希、逐项触发时间/容器顺序/静态增益、显式0.8主音量余量及Creator Set展开回归检查；并继续核对实际包内PCM字节。Android41项、Windows42项内容检查通过，两端589个导出数据文件均与分发内容一致。

Android APK101,714,821字节，SHA256 `94d81a98a57042286f5e54600a1d78756707069510c1f430a186d6f0da4e480a`；稳定分发路径 `runtime/dist/hczs-android-arm64-preview-94d81a98a570.apk`，复制后再次核对哈希。签名、CRC、arm64及ZIP/ELF/RELRO16KB检查通过。

Windows ZIP67,569,787字节，SHA256 `7c2b7c53bcfc43418631cc8b1163016734666cd3b5b22d975a5158a3a2c82d42`；路径 `runtime/dist/hczs-windows-x64-preview-890f46f10a3f.zip`。含EXE、相邻DLL和Resources，ZIP CRC及逐文件哈希通过；Node预览服务仍独立运行。

证据为 analysis/cocos-android 和 analysis/cocos-native-model 下 content-verification.json、package-verification.json，Android另有apk-verification.json。仅静态构建/打包验证，本轮未安装或运行原生客户端，不把Web语音实播视为原生设备验证；macOS/iOS构建、完整玩法及四端实际闭环仍未完成。

## 2026-10-14 Creator 实际编译产物回归检查

针对上一轮 Set 展开在 Creator 中错误编译的问题，新增 `tools/load_cocos_test_module.mjs`：读取当前 Web 导出的 `src/chunks/bundle.js` 与 `assets/main/index.js`，保留两文件 SHA256，仅实例化指定 BattleAudio 或 TutorialBattleController 及其原始 Babel helper，cc 仅提供测试替身，不启动游戏引擎。其他编译模块只登记，不执行。

`node tools/test_battle_audio.mjs --compiled` 用实际发布 JavaScript 通过原有8组调度/取消/延迟/顺序/清理/增益检查，日志 `analysis/battle-visual/elsa-audio/creator-audio-tests.log`；源码模式复跑也通过。`node tools/test_tutorial_client.mjs --compiled` 用实际控制器产物通过15组真实回环HTTP和独立SQLite检查，包括创建、出牌、结束回合、服务重新打开后恢复及胜利；幂等重试、重复点击、版本冲突、旧响应及异常数据隔离也通过。测试创建的独立服务和临时存档已清理。报告 `analysis/test/tutorial-client/creator-evidence.json`，不覆盖原源码模式报告。

`pnpm test:creator` 可在当前Web构建后复跑上述两项。测试证据绑定实际产物字节，不声称自动证明任意后续源码已经重新构建。当前主模块 SHA256 `92a612a3c36840cff0ed6bfdf8106ee415c78d06cc429a0c746a6ae760fbc82c`，helper包 SHA256 `fb0d6d3a84e27f4a8c564419dc043bc2bbff0b65cc155373af24250ac1d2e6fb`。

本轮未修改游戏行为或重建分发包。测试运行在Node并替代Cocos调度/音频服务，不是浏览器/原生设备验证，也不能证明真实声音、触摸、渲染或原版玩法一致。其意义是防止源码测试通过而Creator编译后的同一逻辑失败。

## 2026-10-14 原牌堆入口与重建只读概览

新增trace_card_pile_ui.py，校验原APK并保存OwnCardArea、OtherCardPile、btn_card自动布局及两个旧牌堆模块的静态证据。UnusedCardPile/UsedCardPile在本APK中均只有LOAD_CONST None/RETURN_VALUE空模块，不能依据文件名还原独立入口。OwnCardArea.initComponents在偏移271/280引用OtherCardPile与_wDeckNode，OtherCardPile导入btn_card且触摸处理调用showFightCardsDialog(UNUSED_PILE)。对应CSB、源哈希与模块指令保存在analysis/battle-ui/piles。

原OwnCardArea DeckNode位置(118,70)，btn_card Panel72×72，中部Img_hand使用FightPanel/FightNewPanel/res/icon/btn_deck.png，56×56，Text_deposit为“牌堆”、20号字、alpha153。recover_battle_ui_sprites增加deck-icon，使用既有固定哈希图集恢复，现共15项。客户端按1280×720画布转换为(-522,-290)入口并保留原文字偏移；模板和客户端同步。

将原本浮在场景上的手牌/抽牌/弃牌计数移入只读概览，增加按名称汇总的三列，不暴露抽取顺序。按钮图像及入口位置有原始依据，概览弹窗布局和内容组织是当前重建实现，未冒充原FightCardsDialog，也尚未恢复原入口特效/完整筛选/卡牌详情。概览在退出战斗时关闭，未加载战斗时清空内容，全屏BlockInputEvents阻止底层误操作。

严格TS和Web构建通过。浏览器原存档第1回合显示手牌2/抽牌1/弃牌4，明细与已执行出牌一致；打开时点击底层回合结束无效，关闭后正常进入第2回合。再次打开显示手牌6/抽牌1/弃牌0：强力斩击2、斩击2、猛力斩击1、疾驰斩击1，抽牌堆二连斩击1。控制台warn/error为空。截图piles/overview-live.png与overview-round2.png。尚未同步原生分发包或进行设备输入测试。

## 2026-10-14 原FightCardsDialog布局与图集恢复

trace_card_pile_ui新增FightCardsDialog脚本、窗口自动布局、CardDeckTab、FightCardsArea、CardDeckItem和CardDeckCharTab，现共11个模块、6份CSB布局，均从固定APK校验提取。Reader按本地Cocos2d-x 3.17.2 schema增加ListView的WidgetOptions、innerSize、方向、间距及裁剪字段读取；报告记录schema与parser哈希，仍是部分静态解析，不执行原布局引擎。

原窗口为全屏遮罩、中心卡牌列表和底部标签，非三列文字表。CardDeckItem的ListView静态尺寸1000×540，行容器1000×280，五个CardItem横坐标约126.67、311.67、496.67、681.67、866.67。原底部标签为抽牌堆/弃牌堆/湮灭牌堆，FightCardsDialog.refreshCardShow分别调用getPlayerUnUsedCardInfo/getPlayerUsedCardInfo/getPlayerConsumedCardInfo；另可切换角色标签。尚未恢复这三种源数据提供者与当前重建zone的全部映射。尤其当前battle-session不支持非空终端牌堆，不应把湮灭页做成声称完整实现的固定0。

新增recover_pile_ui_sprites.py，从CSB中的确切path/plist绑定恢复两个原图集中的8张PNG：966×102标签背景、三张308×54选中态、382×8分隔线（原CSB显示40×8）、1280×60底遮罩、24×22切换图标及148×38切换按钮。提取/解码/裁边/旋转范围校验通过，输入/输出哈希保存在analysis/battle-ui/piles/sprites/report.json。已目视检查标签背景；PNG仍在analysis，没有提前替换客户端布局。

本轮静态资源与布局恢复为实际进展，现有可玩概览保持上一轮实现。接下来按原五列卡牌和底部切页结构替换概览，继续追踪原空态、卡牌图样、关闭入口与数据映射；不把资源提取当成原版窗口已经可用。普通本地静态工具证据，不是REA runtime Evidence。
# 2026-10-14：牌堆卡牌浏览接入

`tools/stage_pile_ui.py` 校验恢复报告中 8 张 PNG 的 SHA-256 后复制到客户端 `recovered/pile-ui`，并保存报告哈希和来源。`TutorialBattleView` 与生成模板已同步：原版底部标签素材、五列卡牌浏览、抽牌/弃牌数量、空牌堆提示、关闭操作已接入。卡牌复用已恢复的 FightSmallCard 美术；页面分页、遮罩强度及部分位置为重建适配，不声称完整恢复原 CardShowListArea 运行时。湮灭页明确提示规则尚未恢复。

严格 TypeScript 检查和 Creator Web 构建通过。实际浏览器读取既有第二回合存档，显示手牌 6、抽牌 1、弃牌 0，抽牌页显示二连斩击及卡图；弃牌页正确为空。点击遮罩下原结束回合位置后关闭，仍为第二回合、能量 5/5、生命 1466.8/2191，没有穿透操作。控制台 warn/error 为空。截图为 `analysis/battle-ui/piles/gallery-live.png` 和 `gallery-empty.png`。当前真实存档不足 11 张同堆卡牌，跨页浏览尚未做实际运行验收；本轮未重打 Windows/Android 包。

# 2026-10-14：牌堆数据来源及角色查看

新增 `tools/trace_pile_providers.py`，对已提取的 marshal 文件逐个校验索引 SHA-256，导出七个相关模块的静态指令证据；大体量 UIDataSource 仅导出相关方法。结果位于 `analysis/battle-ui/piles/providers`，`pile-mapping.json` 保存方法字节码哈希和成员读取偏移。它是普通本地静态分析，不是 REA 执行证据；REA 会话检查显示原生分析引擎仍未配置，不据此声称原游戏已运行。

- FightDataTools `getPlayerUnUsedCardInfo` 在偏移 129 读取 `ViewDrawPileInfos`；iCCardPile 对应 getter 偏移 6/9 读取 `_viewCardPileMgr.DrawPile`。
- `getPlayerUsedCardInfo` 偏移 87 读取 `ViewDiscardPileInfos`，对应 `_viewCardPileMgr.DiscardPile`。
- `getPlayerConsumedCardInfo` 偏移 87 读取 `ViewExhaustedPileInfos`，对应 `_viewCardPileMgr.ExhaustedPile`。此映射不证明进入/离开湮灭区的完整规则，不启用服务端尚不支持的终止牌区。
- FightCardsDialog `on_btn_changeview_ButtonUp` 切换 `view_char/view_paidui`，角色页 `onCharSelect` 调用 `getPlayerAllCardsByCharId`。FightDataTools 的该方法遍历 `BattlePlayer.cardObjs`，按动态卡牌数据 `IsEnemy` 和 `CharID` 过滤；不是仅查看当前牌堆。

当前单玩家首战已接入“按角色查看/按牌堆查看”，使用恢复的 change-view 图片。角色模式展示所有真实战斗卡牌实例；尚无多角色卡牌归属模型，因此不伪造另外两位角色。按钮位置为适应预览分页而移至顶部，不称为原版布局精确复刻。

严格 TypeScript 和 Web 构建通过。浏览器实测角色页显示 7 张卡牌（第一行 5、第二行 2），与手牌 6/抽牌 1/弃牌 0 一致；切回抽牌页重新只显示二连斩击。warn/error 为空。截图：`analysis/battle-ui/piles/gallery-character.png`。本轮未更新原生安装包，未验证 Android/iOS/macOS 运行。

# 2026-10-14：牌堆点击查看详情

依据已导出的模块 9317 `CardItem.onGetCardTouchUp`：普通浏览分支调用 `showCardInfoShowPanel`，选择模式则另行派发选择事件。新客户端牌堆卡牌已增加只读详情入口，显示恢复的卡图、卡框，以及当前重建战斗定义中的费用和效果；不触发出牌。详情复用小卡美术放大，布局是重建适配，并未移植原 `CardInfoShowPanel` 的布局、升级比较或关键词弹窗。

详情使用独立全屏输入遮罩。返回保留牌堆模式与页码，隐藏战斗时清空详情选择；资源晚加载后按现有视图刷新。模板和客户端源码同步。

严格 TypeScript 与 Creator Web 构建通过。真实浏览器实测二连斩击显示费用 1、伤害 361×2，返回后仍为原抽牌页；点击详情背后的湮灭标签未切换底层页面。切到角色模式再点击猛力斩击，正确换成费用 2、伤害 723，无残留前张卡片内容。warn/error 为空。截图位于 `analysis/battle-ui/piles/card-detail-live.png`、`card-detail-heavy.png`。未重新打包原生客户端，未以此宣称原版详情完整恢复。

# 2026-10-14：牌堆及详情原生构建同步

最新共享源码已完成 Android arm64 和 Windows x64 导出、编译及分发。Android：`runtime/dist/hczs-android-arm64-preview-8a25e28da7a6.apk`，101,933,377 字节，SHA-256 `8a25e28da7a6cd6fc8d27a9773b312014834a116861cdbbe70b0837195d9ec03`。Windows：`runtime/dist/hczs-windows-x64-preview-4568df281335.zip`，67,784,953 字节，SHA-256 `146601086a08b2eb9cf45a33c8fb7d2b084f36c17a6ec1720684473d6d3ad185`。

两个平台各有 617 个导出资源通过包内一致性核验。新增共享检查器 `verify_pile_content.py` 覆盖牌堆提取报告与 staging 来源、使用中的七张 PNG、资源入口、打包字节和卡牌详情/角色模式编译标记。Android 47 项内容检查及签名/CRC/arm64/16 KB 检查通过，Windows ZIP CRC 与每个文件哈希通过。所有断言都是构建/内容证据，并非原生输入、音频或设备兼容性验证；两个分发报告均保留 `runtime_verified=false`。

# 2026-10-14：原版详情大卡框与布局

新增 `trace_card_detail_ui.py`，校验 APK 身份后导出 CardInfoPanel（2109）、详情自动布局（5602）、CommonBigCard 自动布局（9566）、NormalBigCard（7133）的脚本证据与两个 CSB。产物在 `analysis/battle-ui/card-detail`。源详情 CardNode 居中且 scale=.9；大卡 Face 为 (-2,76)、286×286，框为 612×432、旋转90度，名称中心 (0,-64)，说明区顶部 y=-92、高94，费用节点 (-115,200)、70×82。新视图已采用这些几何数据；关闭按钮、文字效果内容和部分字体仍为重建适配。

大卡框 `card/bg_atk.png` 与小卡不在同一份已恢复图集，首次提取明确失败而非回退伪造。扩展精确资源扫描后，在 packed_png 图集 6039 找到它，图集 SHA-256 为 `4b6a3e565077be87898956b8f745a908d64102df27348570c28cb82c23a1b829`。复用 VT 重组工具恢复 612×432 PNG，SHA-256 `c235cd4ba4a3b5170942e8920daade2d07ab4f5312ac6b5afa21170117064373`，保存源裁剪、透明边距和瓦片来源。原攻击类卡框已同步到客户端 `card-frames/big-atk.png`。

浏览器首次检查暴露 Sprite 默认 trim 裁透明边距后按完整尺寸拉伸的问题；大卡框显式 `trim=false` 后，原尺寸中的透明边距得到保留，卡面与框对齐。严格 TypeScript、Web 构建通过，真实二连斩击详情正常，无 warn/error。截图：`analysis/battle-ui/card-detail/original-big-frame-live.png`。Native 内容检查器新增大卡 PNG/资源入口/编译标记要求；本轮未重打原生包，上轮分发包仍为旧详情布局。升级对比、关键词提示和关联卡牌尚未恢复。

# 2026-10-14：手牌和缩略图透明边距修正

沿大卡问题检查小卡：原攻击小框 `sourceSize=234×182`，有效矩形为 `(19,15,194,152)`；费用图 `sourceSize=70×82`，有效矩形 `(1,2,66,78)`。恢复 PNG 已还原完整画布，原 CSB 也是完整尺寸，故 Creator 默认 trim 后按完整尺寸伸展可见区域会造成比例误差。`skin` 对 `card-frames` 统一设置 `trim=false`，涵盖手牌、牌堆缩略图和费用底图，不改变牌堆规则或卡牌数据。

严格 TypeScript 与 Web 构建通过。浏览器中卡图与边框贴合；实际拖出一张斩击，敌方生命从 2191 减至 1806，能量从 5 减至 4，手牌从 6 减至 5。弃牌页随后显示刚打出的斩击，抽牌 1/弃牌 1，控制台 warn/error 为空。截图 `analysis/battle-ui/card-detail/small-frame-drag-live.png` 与 `small-frame-discard-live.png`。这证明本次比例修正后的 Web 输入和列表更新仍可用，不替代原生平台验收；本轮未重打原生包。

