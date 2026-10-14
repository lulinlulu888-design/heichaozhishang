# 城市场景资源与环境导出

## 城市意图布局修正

`TutorialBattleView.selectBattleScene` 随城市左右站位同步设置敌方意图与玩家回合文本的位置。原布局的意图仍在右侧玩家上方，现改为左侧；玩家回合提示对应右侧。使用绝对位置避免重复切换累积偏移，序章位置保持原值。这是重建HUD适配，原版意图控件的精确位置和美术尚未恢复。

严格TypeScript、Creator Web构建通过；浏览器实际新开城市战斗、返回菜单和重入通过，无警告/错误。证据为 `city-intent-layout.png` 和 `city-intent-layout-restored.png`。新开测试仅为第一回合未完成战斗，已有通关记录保留；`verify_city_preview_save.mjs` 明确筛选已胜利记录后检查。原生包尚未包含本次布局修正。

## 开场89999递归追踪

属性边界追加：现已严格提取const6221的24项RpgPropMap构造，核对23/24映射及FloatPercentProp成员关系。结合BattleAddRpgProp.Start的false-isRatio分支，89990/89991传给addBasicPropModifier的数值为binary64 `0.99`（`0x1.fae147ae147aep-1`），不是整数99。这里只确认调用参数，没有确认实体最终属性或最终减伤率。Release方法仅调用super.Release，没有直接撤销修饰器调用；父类生命周期及实体聚合尚未恢复。

`tools/audit_property_modifier_boundary.py` 校验原APK和9696个decoded模块，跳过缺decoded哈希的9536/9537。精确add/remove/delBasicPropModifier符号仅命中7693的add调用，未发现同名Python函数定义；原APK的24个lib/*.so也没有这些UTF8明文。证据 `opening-buff/modifier-boundary.json` 保留覆盖、各库SHA及限制。改名、去符号、动态绑定或服务端实现均不能据此排除。

本轮REA重新确认libclient为ARM ELF，SHA为`54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`；search_strings返回provider_unavailable（Ghidra未配置且Windows当前适配不支持该ELF，Hopper不支持Windows，IDA MCP未配置）。没有把本地字节搜索冒充REA反编译。当前40级试玩行为没有变化，下一步需要继续追踪父类/实体接口或获得原服务实现证据。

`tools/trace_city_opening_buff.py` 已哈希校验并导出89999/89990/89991的三张源图、三条buff表记录、RpgBasicProp类和BattleAddRpgProp完整类方法，保存在 `analysis/battle-visual/city-scenes/opening-buff/`。受限静态图投影的7个边界案例通过：40/240级不进入；241级以上先检查PropAtkDef>0并添加89990，只有物防不为正才检查PropMgcDef>0并添加89991，因此两种防御都为正时不是两个buff都添加。

89990的BattleAddRpgProp输入为addValue99、isRatio=false、rpgPropType23；89991类型为24。源枚举23/24对应PropAtkDamageReduce/PropMgcDamageReduce，不能当作物理/精神防御直接加99。这两个名称同时出现在FloatPercentProp字面量列表。Start方法在isRatio=false分支经RpgPropMap查名称，若在该列表则除以100.0，再调用addBasicPropModifier；映射与实体修饰器最终生效/生命周期仍需继续追踪，尚未据此接入伤害减免。

当前明确的本地40级场景不能进入这张图的241等级门槛，因此此次没有擅自增加抗性或更改现有战斗数值。以上是本地哈希校验静态提取及分析器投影，未运行原APK逻辑，也不是REA运行证据；原buff事件触发顺序仍未验证。

## 城市加权选招（最新）

后续实际图形通关：seed2024019392这一局先空过两回合检查分解/防御，第三回合用疾驰斩击破906盾，随后二连斩击与强力斩击，承受分解168和敌人379×2后剩674.8生命；第四回合继续攻击并叠到分解4层，第五回合二连斩击击败剩681生命的敌人。整页重新加载、重新进入后恢复胜利；最终玩家506.8000000000002生命、4层分解，版本14、13次命令。浏览器没有警告/错误。

`tools/verify_city_preview_save.mjs --weighted` 只读SQLite，核对scenario哈希、源权重派生表、连续回执版本及终局，然后从保存seed创建初始状态并逐命令重放，验证每步state与events完全相等。输出 `weighted-victory-save-evidence.json`，截图 `weighted-victory.png` / `weighted-victory-restored.png`。不带参数仍核对旧固定轮换通关，不覆盖旧证据。以下“新局尚未打到胜利”是前一阶段记录，由本段补齐；新随机规则仍明确为本地重建算法，原生运行尚未验证。

原 XML 的玩家回合开始分支：回合模3余1固定66054，余2/0调用 RandomSkillAndShowIntentions；源怪物表给出66051/66052/66053权重45/35/20。新增 `tools/audit_city_random_operations.py` 对9696个有哈希的decoded模块检查精确符号，跳过缺少decoded哈希的9536/9537；非cdata命中7693（调用forceChooseRandomSkillAndShowIntentions）和8527（GM代码表字段引用）。这只是本地静态符号审计，不是REA或原运行时证据，未找到原PRNG实现，也不能排除动态、原生和服务端实现。

`server/src/weighted-intents.js` 定义显式本地策略 `sha256-weighted-intents-v1`：以战斗seed、回合、拒绝采样次数生成SHA-256前32位无符号大端数，拒绝范围外值后映射源整数权重；固定回合不抽样。该流独立于牌堆mulberry32。创建战斗时预计算最多30回合并存入scenario，种子、模板ID及算法记录在provenance，派生ID保留城市前缀并包含策略/seed/表的摘要。不是原服随机序列，也没有声称在每个回合动态执行原BT。

BattleStore在事务中先识别同一创建请求的回执，再生成新seed与表；重试不会换种子。旧存档始终使用已保存的scenario，不受服务更新影响。模板 `/tutorial` 的seed0表仅供模板展示，实际新建战斗使用各自seed。加载器身份还固定选招模块文件哈希。

验证：服务端44项测试全部通过，包括不同seed、固定回合、三招覆盖、非法权重拒绝、模板不可变、牌堆输入不变、无显式seed创建的重试和SQLite重开。浏览器重进旧胜利存档后重开新局，第二回合实际显示防御意图并结算906护盾，第三回合玩家1600.8生命；无浏览器警告/错误。只读SQLite证据 `weighted-live-save.json`（seed2024019392、revision3），截图 `weighted-intent-round2.png`、`weighted-defense-result.png`，均在 `analysis/battle-visual/city-scenes/`。该新局尚未由浏览器打到胜利，旧图形通关与新选招的服务端通关证据分别保留。

7460城市服务已重启到新版，本轮没有变更客户端或分发包。开场buff89999、防御/反击、多目标和原BT执行器仍未恢复。

## 客户端试玩切换入口

共享 `ToolchainProof` 新增“序章／分解试炼／城市试战”按钮，分别选择本机7458、7459、7460。Web首次进入仍尊重 `apiPort` 参数，未提供参数和原生首次进入默认7458；选择只影响本次会话，不迁移、删除或合并任何服务端存档。

切换时销毁旧战斗视图与控制器，清空本地档案/角色选择引用后重新读取目标服务。每个控制器的传输闭包固定创建时的地址，旧操作不能转发到新服务。读取/保存中、战斗界面打开、请求待确认或可重试时禁止切换；同服务按钮只重新读取。

验证：严格TS、Creator Web构建通过；`node tools/test_service_selection.mjs` 对实际菜单协调器检查操作锁、清空档案、同服务重读及旧传输地址隔离（Cocos渲染使用桩）。编译战斗控制器15项HTTP/SQLite检查通过。浏览器从无参数主页依次进入城市与分解试炼，分别恢复842.8生命/分解2层、1126.8生命/分解3层的第三回合胜利；无警告或错误。切回城市后只读SQLite仍为版本12、11命令，未产生额外战斗写入。画面证据 `analysis/battle-visual/city-scenes/service-selection.png`。

服务选择不会自动启动服务器。Android仍需设备端访问电脑服务的连接方案；原生构建内容检查不能证明设备运行。下节旧包默认地址限制由新选择入口解除，但只有重新构建后的包才包含该入口。

包含入口的新分发包（均 `runtime_verified=false`）：

| 平台 | 文件 | SHA-256 |
|---|---|---|
| Android arm64 | `runtime/dist/hczs-android-arm64-preview-8d85074eb996.apk` | `8d85074eb996930a214ebe2672f1736d698dfd12f44d09a5bbaf2a3c1f6eadc0` |
| Android x86_64 | `runtime/dist/hczs-android-x86_64-emulator-preview-313f97d59938.apk` | `313f97d59938a0c49af546d5916ac775f54a14eb047db5ee07ccbe62c9c27ff7` |
| Windows x64 | `runtime/dist/hczs-windows-x64-preview-ecf4ac7f8c69.zip` | `b6ff35418e9831f017cb15df94f0109f4a0fcb6c9295ee9b46a91dd1c128e7f0` |

Android各83项内容检查及签名/CRC/16KB静态检查通过；Windows711个导出文件一致性和分发ZIP校验通过。`verify_city_content.py` 追加选择入口编译标记检查。这是构建内容证据，设备端输入与游玩仍待验收。

## 最新原生打包验证（2026-10-14）

城市战斗适配、10405派生站位、四招动画和分解图标已进入新的 Android/Windows 构建。`verify_city_content.py` 核对源站位报告、四招映射、编译代码及包内完整JSON，`verify_health_content.py` 核对分解图标原提取哈希与包内PNG；构建指纹覆盖该图标。

| 平台 | 分发文件 | SHA-256 |
|---|---|---|
| Android arm64 | `runtime/dist/hczs-android-arm64-preview-d6f31ed64f4b.apk` | `d6f31ed64f4bccafdcf69a9ae4224ee6f99f9eb046c7801c932e293008e219af` |
| Android x86_64 | `runtime/dist/hczs-android-x86_64-emulator-preview-cc2497c02dac.apk` | `cc2497c02dacb15b5db5a95ef8a7c2cc97fc14d0c91e36752a01035e26193c76` |
| Windows x64 | `runtime/dist/hczs-windows-x64-preview-1fc409c694b1.zip` | `3eac4d42e2b4fc757bc51f61743767c6391e003bc18bad62de8265aa628d2627` |

Android 各82项内容检查、签名/CRC/ZIP及ELF 16 KB静态检查通过；Windows 711个导出文件通过内容一致性检查，分发ZIP文件哈希和CRC通过。城市服务4项专项测试全部通过，包括真实卡牌获胜、SQLite重开恢复和重试。

这些检查不代表原生设备游玩通过，三份分发报告均为 `runtime_verified=false`。原生API仍固定为 `127.0.0.1:7458`，仅Web支持 `apiPort=7460`；不能把原生新包声称为开箱连接当前7460城市服务。Android还需设备端连接方案。此次未安装或启动原生客户端，没有Mac/iOS构建。下文为累积追踪记录，最新Web可玩结论见“城市 Web 战斗闭环验证”。

## 原战斗关联与资源核对

### 比克卢行为树与状态图追加

`tools/trace_city_battle_skills.py` 校验原 APK，确认 `bt/M6605.xml` 出现在 assets.list，并从 assets.npk 索引95读取。报告、原 XML 与五份关联逻辑图保存到 `analysis/battle-visual/city-scenes/battle-skills`，全部为静态数据证据，未执行原 AI。

行为树不是三技能随机循环：在 PlayerRoundStart 且 RoundMod(3)=1 的分支，ShowSkillIntentions 指定 **66054“分解视线”**；余数2和0分支调用 RandomSkillAndShowIntentions。SelfRoundStart 分支调用 UseIntentionSkill，再 RoundEnd。原随机池仍为66051/66052/66053，权重45/35/20；首次回合编号、条件节点实现、随机抽样与意图保存尚未运行核验。

四招 OwnerSkill 与反向索引逐项一致，状态/时间线关联完整：

| 技能 | 源状态字段 | 表现动作 |
|---|---|---|
| 66051 鞭笞 | MonsterCauseDamage；PropAtk；默认公式字符串90；TIMES=2；目标类型18 | ATK_1 |
| 66052 痛击 | MonsterCauseDamage；PropAtk；默认公式字符串60；TIMES=1；目标类型17 | ATK_1 |
| 66053 防御 | AddShield；maxHp；默认公式字符串15 | SHD_UP_2 |
| 66054 分解视线 | TargetAddBuff；BUFF_ID=66051；BUFF_NUM=2；目标类型18 | ATK_H_1 |

原技能状态的 VALUE=0、默认公式字符串与运行时参数提供者仍需按现有公式证据对接，不能直接将上述90/60/15当最终伤害或比例。五份图为 MonsterCauseDamage、TargetAddBuff、AddShield、MB_breakdown、MB89999。

“分解”buff66051的 MB_breakdown 图连接 OnBeforeRoundEndPassCardsEventNode → GetPlayingBuffInfo → GetRpgProps → BuffDealDamage，并将层数×BUFF_RATIO(20)连入百分比输入；HPRecoverEventNode 连到自身buff数量-1。图中语义与描述相符，但事件筛选、提供者和伤害流程未执行。开场89999另接 MB89999，包含等级与防御比较，进一步引用89990/89991；这些下游buff尚未递归恢复。本次结论修正了此前只查三招随机池的缺口，没有新增可玩关卡。

### 10405 站位分支追加

`tools/trace_city_battle_placement.py` 读取原 `common/design/BattleMonsterBornTransData.py`（模块407）的28组字面量出生点方案；独立解析器只接受常量、字典/序列构造、唯一赋值和最终返回，拒绝调用等其他操作。原样提取和调用/重复键拒绝共3项测试通过。模块2471 `getBattleMonsterConfigPosRot`、9330 `CMonster.getConfigPosRot`、9555 同名帮助函数的静态指令报告已保存到 `analysis/battle-visual/city-scenes/battle-placement/`。

在已查看的帮助函数分支里，非零 MonsterSpawnIndex 对应方案存在且槽位有效时，优先取 `BattleMonsterBornTransData.data[index][slot]`；仅回退分支使用 scene_table.MonsterSpawnList。10405配置 index=5、SpawnPointIdx=0，源方案坐标为 `[-21.96,-9.08,-40.1]`、旋转 `[0,1.57,0]`；加实体6605的 ROTATION 后派生旋转为 `[0,1.22,0]` 弧度。该结果以运行时槽位等于配置 SpawnPointIdx 为前提，未执行原客户端验证。不能再直接用场景默认坐标 `[-5.83,-9.19,-62.27]` 作为此战斗的位置。

实体基础比例为0.7；若运行时 DifficultyType 选择 EliteBattle，帮助函数逐分量乘 SCALE_IN_ELITE_BATTLE=1.4，派生比例0.98。枚举选择、数据适配器覆盖及角色队伍槽位还未完整验证，报告保留条件，不把0.98作为无条件值。技能66051/66052/66053的 CLIENT_SKILL_REPLACE均为0，显示名分别为“鞭笞”“痛击”“防御”，配置时长均1.2秒；这些客户端字段不证明伤害、二连击命中时序、AI选择或效果执行已恢复。

`python tools/trace_city_encounters.py` 校验 APK SHA、复用严格字面量提取器，检查全部 232 个 `maze_battle_table` 主表/分片；232 个均可解析，无跳过错误。报告为 `analysis/battle-visual/city-scenes/encounters.json`，保留表源哈希、字节码位置、字段来源、元数据标量替换记录及扫描覆盖。

两城市共被五个场景配置引用：2001/2003（城市一普通/精英），2073/2077/2079（城市二普通/精英/镜像未来）。关联到 700 条战斗记录、269 个怪物配置、171 个实体，怪物/实体关联没有缺行。进一步经实体 LOD_ID → LOD_MODEL_LIST → MODEL_PATH 展开 339 个模型路径；31 个的 GIM、Mesh、MTG 及所列 GisFiles 均唯一匹配。该数包含颜色和 LOD 变体，不是 31 种完整可玩怪物；贴图、shader、动画解码及行为仍需验证。

资源核对优先读取 GIM 的显式 Mesh 引用；只有无该属性时才检查同名 mesh 候选。不能把所有网格都按 GIM 同名猜测，否则会误报大量缺失。已有场景 XML 内缺失的无颜色后缀角色，与战斗表引用的 purple 等变体路径不同；未擅自用变体替换编辑场景实例。

确认可复用已解码魔方模型的候选：分片 6500 的战斗 10405，原 Name 为“测试-比克卢”，Scene 2077（城市二），MonsterID/EntityID 6605。它是原测试配置，不能称为已恢复剧情关卡。该怪物有开场 buff 89999、随机技能 66051/66052/66053（权重 45/35/20）、M6605.xml 行为树与数值模板 37，三技能表行均存在；不同于序章 991，不能直接复用序章技能/血量。下一步需追踪 MonsterSpawnIndex=5 的运行时站位规则、技能替换与行为树/数值输入，再做可玩接入。当前没有新增可玩关卡。

## 共享 Cocos 客户端接入

### 原生构建追加

本次运行 `tools/cocos.ps1 -Action build-android`、`-Action build-windows -WindowsVariant model`、`-Action build-android -AndroidVariant emulator`，三者均完成。新增 `tools/verify_city_content.py`，由 Android/Windows 包验证共同调用：校验源与派生 GLB 哈希、除唯一节点名称外完整 JSON 与二进制一致、原镜头/角色实例未改、实际导出 JsonAsset 包含准确清单、场景/材质路径及三张云层 PNG 确实存在。检查属于静态包内容证据，不代替引擎运行。

三份原生输出各 707 项资源与导出目录一致，Android 各 75 项内容检查通过，Windows 76 项通过。Android APK 签名、CRC、ELF/ZIP/RELRO 16 KB 对齐检查通过。分发包如下：

| 平台 | runtime/dist 文件 | 字节数 |
|---|---|---:|
| Android arm64 | hczs-android-arm64-preview-d26f1c7ab2d3.apk | 116449937 |
| Android x86_64 模拟器 | hczs-android-x86_64-emulator-preview-16005c45c330.apk | 119568429 |
| Windows x64 | hczs-windows-x64-preview-c68cd246c728.zip | 81888083 |

Windows ZIP SHA256：`842f7e2bacb2aaac34526dfe776959affed34536c10288d8cdfe5d4f281c83bd`。详细报告分别在 `analysis/cocos-android`、`analysis/cocos-android-emulator`、`analysis/cocos-native-model` 的 `content-verification.json` 与 `package-verification.json`。构建 stderr 有 Creator 窗口状态 JSON 恢复失败提示，但实际编译成功退出及完整包验证已确认；未修改用户全局窗口配置。所有新包仍标记 `runtime_verified=false`，没有执行安装或原生游戏启动。城市尚未接入战斗，macOS/iOS 构建未完成。

`tools/prepare_cocos_city.py` 校验上游两个场景 GLB 的导出哈希，提取云层三纹理与参数，保存源镜头/角色实例，复制两份环境到 `assets/resources/recovered/city`。唯一几何文档修改是为环境节点生成唯一名称，用于确定性绑定材质；二进制几何/贴图内容不改。派生 GLB 哈希和源哈希记录在该目录的 `provenance.json`。

`CitySceneView.ts` 与对应模板使用共享的角色和武器 Prefab、源矩阵、`idle_1` 待机及武器逆绑定。独立渲染层/1280×720 RenderTexture 防止与序章画面相互渲染；加载后隐藏、返回及销毁有对应清理。主界面“城市景观”入口提供两场景切换与返回，覆盖层阻止触摸穿透。仍是源编辑场景检查，不是战斗队伍。

原材质基础颜色采用无光照参考；`cocos-city-cloud.effect` 移植先前网页预览同一云层分支，常规混合未代表源模式 5。Cocos 导入的不透明材质最初把纹理 alpha 写入 RenderTexture，导致 Sprite 合成时天空缺块；`cocos-city-opaque.effect` 对导出标记 OPAQUE 的环境槽强制 alpha=1，实测缺口消失。云层不应用此修正，继续使用原遮罩。角色/武器仍用现有 Cocos 颜色参考，网页的武器流动覆盖层此次没有移植进 Cocos。

2026-10-14 验证：严格 TypeScript 检查通过，Creator 3.8.8 Web 构建成功；浏览器实际进入城市一、切换城市二、返回图鉴通过，警告/错误日志为空。截图 `cocos-city-1-live.png`、`cocos-city-2-live.png`。构建源码指纹已包含 CitySceneView 与城市资源。构建日志有既有 Web 压缩选项回退提示，不影响本次构建成功。原生构建/安装未重新验证，原 shader、完整光照/特效和城市战斗尚未完成。

## 最新追加：源实例角色预览

武器追加：城市预览已通过 `city-weapon.js` 接入源武器静态模型、覆盖网格与两张流动噪声纹理。按原 GLB 节点身份解析唯一 `bip001 prop1`，挂载采用源单骨骼权重所支持的“动画骨骼 × 武器逆绑定”关系，并拒绝无效/奇异矩阵。没有使用角色自身的绑定矩阵替代武器矩阵。沿用已有武器检查页的流动公式，gamma 2.2 与常规透明混合仍是参考选择；源武器 bind/AABB 差异和 BindType 263 原生语义尚未解决，不称为完整原生挂载验证。

打包脚本校验武器 GLB、覆盖 GLB、纹理导出哈希后复制到城市预览；两个场景的持刀待机实际显示，控制台无警告/错误。截图 `city-1-weapons-live.png` 与 `city-2-weapons-live.png`。下方“武器未装配”描述是之前阶段状态，现已补上预览装配，但尚未改变可玩关卡和原生构建。

导出 extras 现在保留 `sourceActorInstances`，包括资源路径、完整原属性和矩阵。预览仅加载其中 `character/player/ailisha/ailisha.gim` 对应的已验证动画 GLB（SHA256 `acc7bbaa00b66a60165ce56341021055b55f1f73ca4c6af154e63036ee789463`），直接沿用源矩阵，不追加战斗方向适配或改比例。城市一显示两个源实例，城市二一个；其他角色缺口仍不填充。采用恢复的 `idle_1` 作动画参考，原场景运行时是否选择此片段尚未证实。

预览固定 16:9 横屏并留边，避免窄窗口按竖屏裁切；这属于预览布局选择，不是原镜头适配规则证据。两场景切换和渲染通过，控制台警告/错误为空，截图为 `city-1-actors-live.png`、`city-2-actors-live.png`。武器未装配，原角色 shader、光照、特效及真实战斗站位未验收，尚未接入可玩关卡。

增加实例元数据后 GLB 大小为 8,483,360 / 6,676,564 字节，SHA256 为 `17911447bd9f474658a6783c5adde7429c3f9c5c7f5733ae33fdc785d147b3eb` / `d90e48dfac744f1c44805acb41621c18beb0933942204e406e1131db4c61988a`。下方为先前环境阶段记录。

2026-10-14。本轮处理 APK 里确实存在的 `city_battle_1`、`city_battle_2`，没有将其替换为教程要求的 `city_battle_3`，没有修改当前战斗画面。

## 分解状态节点边界（追加）

后续追踪已扩展到8模块38代码对象。7554 `(5,13)` 从初始属性加顺序修正项，仅 PropAtk 限制为非负，strengthFactor 参数在该函数内未使用；`(5,14)` 的 maxHp 直接读 self.maxHp，其他键读 rpgProp.get(key,0)。5485 `(13,60)` 属于客户端视图，读取 buff.get(buffID,{}).get('times',0)，不确定服务端怎样聚合不同施加者。已有 battle-core.propertyValue 覆盖当前属性计算；新增 rpgPropertyPercent 覆盖节点百分比/取整。11个独立 Python 数值向量和2项组合/输入检查、ES2015严格类型检查通过。源事件系统、状态修改及最终HP应用仍未接入。

运行 `python tools/trace_city_breakdown_buff.py`，输出到 `analysis/battle-visual/city-scenes/breakdown-buff/`。6个模块35个代码对象均由已校验解码哈希的源数据导出；这是普通本地静态证据，不是 REA 运行时记录。没有执行 APK 脚本或改变现有战斗。

- 模块3681 `(19,11)`：注册监听时传 `EVENT_NAME, targetType, context.owner, callback`；图配置 targetType=1。模块3921 `(15,2)` 的 afterRoundEvent 只转发 roundNum；`(79,8)` 的 onHPRecoverEvent 只转发 oldHP/curHP/delHP/source/overHp，不自行过滤正治疗量。全局监听实现与事件发出端未定位，不能据此确定过量或零治疗是否减层。
- 模块8895 `(11,8)`：nowTimes 取 `buffOwner.getBuffTimes(buffID)`，不是直接取当前 buffObj.times。跨来源聚合语义仍需沿提供者检查。
- 原 MB_breakdown 图把 srcEntity 接到 GetRpgProps、当前层数×20 接到 percent。模块2905 `(147,8)` 在 isInit=false、method=0 下执行当前属性提供者调用，再乘 percent/100.0 并 `int(math.floor(...))`；strengthFactor 默认1。此结果作为 finalExtraDamage，不是已结算生命损失。
- 模块4956 `(10,)`：getBuffSource 在缺少 RPG_TARGET 时返回 context.owner；66051 表确实没有此字段。`(13,7)` 的 DamageInfo 来源和上述属性来源应分开；base damage=0，extraDamage 为图提供值，NEED_TIME=false 不再乘层数。canUseOnDie 默认false，所选 source.preDie 时跳过 fakeMultiDamage。
- 治疗图向 BuffTargetAddBuff 请求 num=-1、isCommonChange=false；其 setSrcEntity 默认采用 context.owner。继承的 TargetAddBuff 通过 fakeAOE 执行闭包，扣层、移除、合并及闭包未识别操作码尚未完整恢复。

索引范围搜索没有找到 registerGlobalListener、fakeMultiDamage、onHPRecoverEvent 同名函数定义；这不是证明实现不存在。getRpgPropByKey 定义位于模块7554，getBuffTimes 位于5485，是下一步的明确入口。当前报告不构成城市战斗可玩或原规则完整还原的验收。

## 可复现产物

1. `python tools/audit_city_scene_dependencies.py`：校验原 APK SHA，提取两份场景，遍历 XML 路径属性和文本、GIM 同名 mesh/mtg、材质纹理；记录原路径与 KTX 候选映射。输出 `analysis/battle-visual/city-scenes/dependencies.json` 及带哈希的独立源文件。
2. `python tools/export_city_scene.py`：逐源 SHA 验证，导出两个环境 GLB，保留原实例变换、材质 XML、镜头参数和缺口，不导出编辑场景中的角色或动态特效。
3. `python -m unittest discover -s tests -p test_neox_model.py`：15 项通过，包括显式非单位法线读取、源向量不变、默认严格检查不变及零向量拒绝。

引用遍历结果：447 项有匹配，10 项缺失，0 项多重匹配。这里的“有匹配”不是全部可渲染；shader 内部 include、非 XML 特效、动画和隐式运行依赖仍未完整遍历。缺失列表包括三个怪物 GIM、测试天空球、三个 cube 引用、两个 shader 和一项烟雾 mesh；详见 JSON，不用占位资源掩盖。

## 修正网格解析限制

两份城市主背景及云层等六个网格的法线长度约为 0.446828 或 0.297885，被旧解析器的单位法线检查拒绝。源几何均能通过目录边界、总尺寸、索引和有限数值检查。

`parse_model(..., preserve_nonunit_normals=True)` 现在可显式保留非零源向量；默认行为不变，既不改写原数据，也不自动归一化。城市环境采用无光照 Tex0 颜色参考，GLB primitive 不绑定这些非单位 NORMAL 属性，源向量与长度范围保留于审计。尚未恢复原 shader 法线使用方式。

## 导出结果与验证

| 场景 | 网格 | 实例 | 贴图 | GLB 大小 |
|---|---:|---:|---:|---:|
| city_battle_1 | 6 | 7 | 7 | 8,477,652 字节 |
| city_battle_2 | 4 | 4 | 5 | 6,673,760 字节 |

输出分别位于 `analysis/battle-visual/city-scenes/city_battle_1/scene.glb` 和 `city_battle_2/scene.glb`。导出报告保留全部源哈希；加入云雾遮罩/扰动贴图后 SHA-256 分别为 `ff565f85f9963938b83d00a035a96ad01056344939290b0836fa5855b5391bc8`、`f9929abaaebe80adc895665c2585b59b9ab4b20985f3a830a3fd8c854959c87d`。

首次导出的独立 GLB 读取后，7+5 个 primitive 的位置和三角形索引与源模型逐项一致，结果保存在 `geometry-verification.json`；该记录对应加入额外贴图之前的 SHA，不覆盖新材质代码。后续浏览器结果见下节。

两份源镜头均为 `camera_1`，FOV 45、Near 1、Far 10000，Transform 含比例 10.941514 及 Z=30，已原样保存；引擎镜头轴向和缩放解释尚待实际预览核对。背景素材主要是带贴图的平面，不能自动当成完整立体城市。

`battle_screen_01` 使用缺失的 `dark_color.fx` 且没有 Tex0，本次明确跳过；模式 2 暂采用常规 alpha blend。原灯光、反射探针、完整透明排序及技能/场景特效未复现。下一步是预览原镜头构图并修正有证据的变换问题，再考虑接入其对应关卡；不得称作教程原场景已恢复。

## 浏览器预览与云雾修正

执行 `node tools/prepare_city_preview.mjs`，会校验导出 GLB 哈希和固定 Three 0.180.0，再生成 `http://127.0.0.1:7456/city/`。这是本地场景检查工具，不是已接入战斗的关卡。Creator Web 重建后需重新运行此命令。

实际加载两份环境后，最初看到 `plane_yun` 变成灰白矩形。其原材质使用 `shader/lancer2.fx::TShader` 与 `ALPHA_MASK=TRUE`，Tex0 本身并不是可直接显示的最终云雾图。现已将源材质的 TexDistortion、TexMask、平铺/流动、扰动强度、颜色和遮罩强度带入导出元数据；`city-materials.js` 仅移植该 plane_yun 分支的 UV 扰动、颜色乘法、alpha 遮罩公式。实例使用 GLTFLoader 派生材质，需要按源模型元数据匹配，不能仅比较原材质对象引用。

此移植没有声称复现模式 5 的原生混合状态、HDR/雾、所有采样器状态、场景 RenderCondition 和其他 lancer2 材质分支；当前用常规透明混合参考。镜头使用源 FOV/近远面/平移旋转，去掉比例，并沿用 NeoX +Z 到 Three -Z 的 180° 轴向适配，尚未与原 APK 镜头实播比较。

浏览器实测两场景切换、全景检查和恢复源镜头参数通过，警告/错误日志为空；矩形遮挡消失，城市前后景与道路可见。截图为 `city-1-live.png`、`city-2-live.png`。仍没有角色、可玩战斗、完整特效与灯光的一致性验收，未改变教程场景缺失结论。
# 玩家战斗站位来源（2026-10-14）

用户历史战斗截图追加：`analysis/references/user-historical-battle.png`，SHA-256 `c9fdc12de7354ea956ef243605b226a9be9cf631cf83f4338fa858e26c10bacc`，可见本方三人在左、敌人在右。当前城市共享视图已对完整RenderTexture输出纠正X方向，血条回到原HUD左右布局、拖牌目标和意图区改到右侧、结果区改到左侧。未交换源角色坐标或篡改网格；使用Cocos3.8.8实际SpriteFrame.flipUVX属性。严格TS、Web构建及编译控制器15项检查通过，实际画面核验另记录。原生包尚未重建，原渲染器具体投影实现仍未完全追通；下文“玩家右”是修正前历史记录。

## 城市 Web 战斗闭环验证

独立城市服务现运行于 `http://127.0.0.1:7460`，浏览器入口 `http://127.0.0.1:7456/?apiPort=7460`。使用 `node server/src/index.js --port 7460 --city-preview`，独立存档为 `runtime/server/city-preview.sqlite` 及 `.battles`，当前由本地Node进程运行，未由PM2托管。

共享客户端根据明确的城市定义ID选择 city_battle_2，复用原场景与角色资源；城市渲染器提供角色实例给现有攻击/受击/死亡表现队列。玩家血条移到右侧、敌方移到左侧，拖牌目标框同步落到敌人位置。目标框仍为重建屏幕区域，不是原生模型拾取。入口文案统一为“进入战斗”，敌人名称改由存档定义读取。

已在浏览器实际创建档案、开始城市战斗、拖牌至左侧敌人、播放分解/二连击，第三回合击败比克卢。整页刷新后重新进入，恢复胜利标题与敌人死亡姿态。`tools/verify_city_preview_save.mjs` 独立只读SQLite确认版本12、11次操作、玩家842.8000000000002生命、分解2层、敌人0生命，最后出牌导致胜利；存档哈希与连续版本一致。截图 `city-battle-victory.png`、`city-battle-victory-restored.png` 在 `analysis/battle-visual/city-scenes/`。

严格TS、Creator Web构建、实际编译控制器15项HTTP/SQLite检查及v2状态校验通过；浏览器无警告/错误。当前可重开的是明确40级本地重建试玩，不是原服挑战上下文。完整特效、原始随机AI、多角色目标与原生平台运行尚未验证，原生包未更新。下文“尚未图形接入”为先前阶段记录。

## 本地城市战斗配置

新增 `server/src/city-scenario.js` 与 `server/data/city-preview-policy.json`，由 `tools/prepare_city_battle_policy.py` 重跑原表/图追踪并固定输出哈希。加载器校验两个证据报告，复用已验证的教程玩家基线、卡牌和牌堆，通过共享公式生成比克卢技能。

明确的本地政策：怪物40级（不是原挑战等级），基础HP6041、攻击422；地图/挑战倍率中性，原防御/克制和开场89999不执行。敌方第1/4/7…回合用分解，其余按鞭笞/痛击/防御轮换，未声称恢复45/35/20随机选招。技能输出为二次379伤害、单次253伤害、906护盾、2层分解；分解时序继续采用已记录的重建政策。单目标替代原群体目标。

命令行新增 `--city-preview`，默认独立存档 `runtime/server/city-preview.sqlite`，与 `--custom-scenario` 互斥。城市服务未作为常驻服务启动，客户端还没有用城市战斗替换序章场景，当前浏览器仍是动作预览。

验证：新增4项真实证据/状态/SQLite/HTTP检查，第三回合实际卡牌命令获胜并恢复终局；分解168后接二连379+379，重试不重复执行。修改后的服务器完整41项检查通过，随后新增的通关检查单独通过。不是原客户端或图形城市游玩验收，亦未更新原生包。

## 城市技能动作接入

`prepare_cocos_city.py` 直接读取哈希校验的技能9333、时间线6655、实体1955数据，生成66051/66052→fire、66053→skill_3、66054→skill_2映射；不接受非零时间或后效列表。共享 CitySceneView 已能按这份映射播放并返回idle，离开场景会取消播放及移除结束监听。

Web实际点击鞭笞、痛击、防御、分解视线，观察到对应动作；完成后恢复待机，播放中切到城市二并返回通过，控制台无警告/错误。证据为 `city-action-browser-evidence.json`、`cocos-city-decompose.png`、`cocos-city-defense.png`，均在 `analysis/battle-visual/city-scenes/`。严格TS和Web构建通过，原生包未更新。

这里只恢复骨骼动作，不执行伤害或推断命中时刻，原技能目标特效和关卡控制器仍待接入。`audit_city_encounter_references.py` 对9696个可校验模块扫描独立整数10405，找到4个候选；两个redirect模块缺decoded哈希被记录跳过。该扫描不覆盖JSON文本/地图归档/动态引用，未证明挑战入口不存在，也未确定等级。

## 比克卢基础属性追踪

`tools/trace_city_monster_properties.py` 从模块6708恢复精英类型1–400级共400行，结合5304、3510和9419的哈希校验代码对象，输出 `analysis/battle-visual/city-scenes/monster-properties/`。`getMonsterMouldData` 按怪物 Math_model 和传入等级查表；`getMonsterHP/ATK/AtkDef/MgcDef` 先检查 `enforce_<属性>` 是否不为 None，否则按顺序计算 `基础值 × 怪物倍率 × 地图倍率 × 挑战倍率`。强制0也必须生效。

共享 battle-core 新增 `monsterProperty`，保留整数/浮点类型及乘法次序，要求调用者显式提供已解析倍率。16组独立Python向量和1项缺失依赖检查通过，battle-core完整111项测试通过。此函数尚未作为城市关卡属性提供者接入。

怪物6605的 `shuzhi_moban=37` 不是等级，该属性链不读取它。UI等级计算有地城、旧挑战等级加MazeLevelDelta、最高三名角色等级等分支；目前缺少该测试战斗的实际挑战上下文，未选定等级。`UseChallengeLevel` 的服务端使用者未恢复。未提供battleID时，已观察的地图倍率函数起值为0，不能擅自补1。基础曲线不是最终伤害或真实关卡血量，亦不代表原客户端运行验证。

## Cocos 对阵画面验证

共享客户端的“城市景观 → 城市对阵”现使用 city_battle_2 环境与源镜头，显示一个艾尔莎和比克卢模型。底部三个站位按钮选择同一个角色的 posIndex，不伪造三名队员。`prepare_cocos_city.py` 每次重新运行玩家/怪物追踪后生成 `formation-10405.json`；环境导出仍按哈希校验。

浏览器实际进入、三个站位切换、切回城市景观、返回对阵均通过；没有警告/错误。证据截图为 `analysis/battle-visual/city-scenes/cocos-formation-slot-{0,1,2}.png`（文件索引从0开始）。严格 TypeScript 检查与 Creator Web 构建通过。原生包尚未更新。

这是站位预览，尚无城市战斗控制器和关卡结算。敌人采用实体基础比例0.7，未套用尚未验证运行条件的精英倍率1.4；完整材质/光照和镜头与原客户端的一致性尚未验收。现有分解试炼仍使用原来的序章重建场地。

`tools/trace_city_player_placement.py` 已保存哈希校验的脚本证据与场景/实体数据，输出 `analysis/battle-visual/city-scenes/player-placement/report.json`。这是本地静态解析，不是原客户端运行证据。

原调用链为 CAvatarChar.getConfigPosRot → CBattle.createBattleEntity → BattleScene.addPlayerEntity → BattleModelEntity/BattlePlayerEntity.updateUserData。场景2077基点为 `[20.514759,-9.08,-35]`，按收到的 posIndex 加三槽偏移，得到约 `[13.514759,-9.08,-46.5]`、`[21.960759,-9.08,-40.1]`、`[35.064759,-9.08,-46.5]`。艾尔莎实体0的旋转覆盖场景旋转，再加零旋转偏移，结果 `[0,1.5708,0]`；基础比例为1。

这些是艾尔莎可处的三个槽位，不是原阵容包含三个艾尔莎。服务端槽位分配、运行镜头、聚焦/换位尚未执行验证；没有改动现有预览。另发现怪物偏移模块9150含重复键2003，严格解析器正确拒绝，不能将其报告成完整恢复的映射。



## 左右站位镜头审计（2026-10-14）

用户提出原APK站位疑问后，tools/audit_city_camera_side.py量化了当前转换。
源camera_1去缩放后旋转为diag(-1,1,-1)，位置(0,0,30)；原玩家三个槽位
在源镜头局部X均为负、Z为正，敌人X为正。当前额外Y180使X/Z同时反号，
从而得到本方右、敌方左。这是适配结果，不能独立证明原版左右站位。
若源投影为+Z向前且+X向右，则原数据导出本方左、敌方右；该投影约定仍
未由原渲染器矩阵或运行截图验证。下一步核对源投影及坐标手性，不能只
交换演员位置而忽略场景、剔除和输入目标。报告camera-side-audit.json。
本轮没有修改镜头或战斗站位。

实际城市Web验证：既有胜利存档恢复后，本方角色及血条在左、敌方残骸及头图区在右，结果文字正常未镜像，截图analysis/battle-visual/city-scenes/player-left-corrected.png。没有重开或改写用户战斗存档。终局没有手牌，拖牌区域改变已通过代码核对，但本轮尚未实际新局拖牌验证。
