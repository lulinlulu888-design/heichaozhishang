# 大厅与不知火恢复

2026-10-14。入口：http://127.0.0.1:7456/hall/ 。这是原场景与角色的独立Three.js预览；共享Cocos大厅与原UI还未接入。

## 原场景证据

场景表9650的203行指定HallSceneHome、主角家、`scene/midgard_home_3d/midgard_home_3d.scn`、默认镜头camera_1；脚本7891为logic/scene/HomeScene.py。主界面脚本5795引用8262自动布局，原RES_FILE_NAME为`uires/HallMainPanel/NewHallPanel/HomeHallMain_ext.csb`。CSB布局仍待解析，当前按钮只用于预览。

`tools/prepare_hall_scene.py`复用场景依赖遍历与导出：513个依赖存在，两个反射探针未匹配，无网格解析错误；输出79份网格、116个实例、61张颜色纹理。原场景矩阵和相机属性保留，GLB SHA-256 `5384edd0dcd78e0868c174cc1c1d42444cf217f9d9ec7c83d0232d133d5092da`，26,320,740字节。

初次双面渲染被zheguangban_01_77背面遮挡；源材质有CullMode=2，预览采用FrontSide，其原枚举语义仍须原生核对。File_25指向visitor_position_1.gim，被player_position、npc_position、visitor_position实例引用；该定位标记在预览中隐藏，原数据保留。不是宣称已恢复原引擎全部Flag含义。

默认镜头按源参数载入，沿用当前Y180轴向适配；该约定仍受目标审计中投影方向未知限制。16:9、devicePixelRatio上限2、最高各向异性过滤；只有基础颜色参考，法线、PBR/toon、毛发、反射和原光照均未完整恢复。

## 不知火

英雄33、实体71、养成实体72、LOD250、模型行530–533均来自原表。预览选行530 `character/player/buzhihuo/buzhihuo_yangcheng.gim`，没有证明这是原运行时的大厅LOD选择。HOME_ENTITY_ID=0没有被当作艾尔莎；选择实体71明确的ANIM_STATES_HOME_STAND_IDLE=home_stand_idle_1。

动作库`character/player/buzhihuo/buzhihuo.gisacl`，该片段ACL SHA-256 `4e634f1691d6e807c9f98aed9e46dfc44a06d1b4a665735bad01bb5173e59883`，171帧、251骨、30Hz、格式[4,3,3,7,7,0,1]。独立固定哈希采样器保留格式边界，没有放宽既有艾尔莎/琳采样器。

导出复用export_character，保留原参考TRS、逆绑定及采样帧。753通道、42,921个骨骼帧往返校验通过；171帧全顶点CPU蒙皮有限，25,864顶点移动。毛发槽10没有Tex0，明确使用源TexBaseColor作为颜色参考，未模拟毛发壳层。

大厅放置使用源player_position标记的平移/旋转与实体71的SCALE_IN_HALL=0.86，作为本地预览装配；原脚本运行时是否选择此标记及完整附属物尚未验证。装饰表191扇子模型及独立待机已恢复；弹簧模拟、原SFX/角色互动仍未接回。近景按钮是新预览镜头，默认大厅视角保留独立按钮。

实际浏览器显示、近景切换通过，警告/错误为空；截图`analysis/hall/shiranui-preview.png`。原待机循环播放；不是完整大招或原版大厅验收。

## 复现

依次运行：

```powershell
python tools/prepare_hall_scene.py
python tools/recover_shiranui_hall.py
python tools/sample_shiranui_hall.py
python tools/export_shiranui_hall.py
node tools/prepare_hall_preview.mjs
```

Creator Web重建会覆盖输出目录，需要重新运行最后一步。原APK及分析资源不提交版本库。

## 用户提供的原版画面追加

用户提供历史录像截图：`analysis/references/user-historical-hall.png`，SHA-256 `e2b0210f16a7bf7c92c65dda86e30e34f71b59a873e349106232d2e1266b6e14`。画面明确电视右、窗户左，不知火有大型扇子与粒子演出，顶部/右侧/底部原UI布局完整。截图版本与本APK版本是否一致尚未核对；它是历史画面依据，不是原APK执行证据。

预览的Y180相机适配导致X方向反转，现对整个3D输出canvas纠正X方向，UI不随之镜像。原场景和人物源矩阵保留。颜色参考材质、光照、扇子/效果、主界面布局仍未完成，不能将方向修正升级为原版大厅一致验收。

`tools/inspect_hall_ui.py`复用公共CSB Reader，已提取HomeHallMain_ext.csb（13,416字节），版本2.1.0.0、47个节点。报告`analysis/hall/ui-tree.json`保留源身份；嵌套ProjectNode、原时间线和运行时布局约束未展开。源实体71的HOME_SUB_MODEL_LIST=[191]已追至HomeModelEntity418.updateUserData→MeshHelper5136.getModelPathListByMeshIndexList/getModelPathByMeshIndex→getDecorationTable；实际是装饰表9416行191，不是avatar_slave_table或entity_table的ID。关联证据与局部字节码见analysis/characters/shiranui/hall-attachment.json，可运行tools/trace_shiranui_hall_attachment.py复现。

## 扇子动作与显示追加

原扇子模型buzhihuo_weapon.gim有独立19骨动画库buzhihuo_weapon.gisacl。同名home_stand_idle_1为171帧、30Hz，ACL SHA-256 `965334500ad8406ce049ea76e60b30e1a8c0976d6b3e42c16275062fe7271d33`，格式[4,3,3,7,7,1,1]；没有将人物251骨轨道硬套到扇子。公共sample_pinned分别生成固定输入白名单采样器，人物与扇子各自导出。

扇子57通道、3,249骨帧及171帧全顶点CPU蒙皮验证通过，4,154顶点移动；在共同预览根节点中播放原同名待机，与人物采用相同起点。原运行时附属模型装配、弹簧以及事件同步未执行验证。源GIM的fx_ui_idle_1/2等socket明确绑定ui_idle_3.sfx、ui_idle_4.sfx，蓝色火焰尚未迁移。

实际浏览器已显示两片扇子、人物原待机以及修正后的房间左右；原光照、材质、UI仍未恢复。近景沿源camera_1方向对人物/扇子包围盒重新取景，是检查用镜头，不能宣称与历史截图逐像素一致。

最新实际预览截图为analysis/hall/shiranui-with-fans.png，浏览器警告/错误为空。共享采样/导出重构后重新采样并导出琳，Cocos资源来源哈希重新一致，Creator Web重建通过；大厅与独立场景入口已重新准备。
