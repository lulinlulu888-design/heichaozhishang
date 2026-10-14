# 首战敌人模型接入 Cocos

2026-10-14。首战界面的敌方意图区域加入幻眼魔方模型，加载已恢复的 `idle`，使用实时骨骼动画循环播放。**代码和三平台构建已完成；实际首战画面、触摸、XHR及动画播放尚未验收。**

## 资源与显示

来源为[已验证的敌人动画GLB](tutorial-enemy-animation-export.md)。`tools/prepare_cocos_assets.py` 核对固定SHA后复制到 `assets/resources/recovered/models/enemy991/enemy991.glb`，同时保存7项资源清单中的来源记录。模型UUID固定为 `c744184a-ec92-4c0e-8f59-7c763f7c5192`，既有导入metadata不会被覆盖。

`RecoveredCharacterView.ts` 增加可配置的模型目录、待机片段、相机和渲染层；图鉴艾尔莎的默认设置保持原值。`TutorialBattleView.ts` 使用独立层 `1 << 1`，不会进入艾尔莎的 `1 << 0` 相机；主UI相机的可见掩码不包含这两个层。敌人画面为172×132的Sprite，渲染目标688×528，保持相同比例。正交相机中心Y=12、半高11、Z=40，按已验证idle所有帧边界取景，原坐标没有缩放或翻转。

返回图鉴会停用敌人stage并暂停；重新进入会复用已加载资源并恢复播放；场景销毁会释放prefab引用、SpriteFrame与RenderTexture。异步显示回调检查可见状态、销毁状态及请求代次，载入失败显示简短占位文字。源码和 `tools/templates/` 对应模板同步。

两段动画均进入构建，界面仅使用idle。没有将 `fire` 猜测性地绑定到具体技能，没有补造攻击/受击/死亡动画；恢复的Tex0基础颜色也不等于原版紫色发光效果。待机循环是当前预览选择，不是已恢复的原游戏状态机。

## 真实导入与构建检查

`tools/verify_cocos_character.mjs --model enemy991` 读取Creator实际导入的Prefab、Skeleton、Material、Texture及CCON动画数据，使用与艾尔莎相同的逐采样检查。没有初始化引擎或操作UI。

- 61条骨骼路径全部可解析；每段63条节点轨道中，61条骨骼轨道映射到原片段，另2条辅助轨道对应Prefab静态变换。
- idle 6,161、fire 2,196组骨骼帧全部匹配；时间、平移、缩放误差为0，四元数等价符号比较的最大分量误差为 `5.960464477539063e-8`。
- 一个unlit材质、一条纹理到嵌入PNG的引用链和唯一Prefab资源路径均通过检查。
- Web、Windows实际EXE旁Resources、Android导出目录分别通过17项静态检查。动画二进制与被审计的library逐字节一致。打包后的Prefab/材质JSON仅记录包哈希，未独立反序列化，不扩大为全部导入语义已验证。
- 艾尔莎三平台17项检查仍通过。完整工程严格TypeScript检查通过；控制器源码未改，原15组HTTP/SQLite测试证据仍对应当前控制器。
- Web导出、Windows导出与编译、Android导出均退出36；Android Gradle退出0。敌人接入当轮APK为78,771,704字节，SHA-256 `390eb4c1bbe805b8caea83901569a5145a154e25dcdce4874fbff5691c24bece`，签名/ZIP CRC/16KB ZIP、ELF、GNU_RELRO对齐通过。后续关卡标题更新已重新构建并重验，最新产物见[首战构建说明](tutorial-client-build.md)。没有安装到Android设备。
- 整体构建验证28项通过，含三平台每次导出10项来源指纹、六份模型审计的当前输入SHA、Windows脚本资源，以及APK中整个resources目录逐文件与导出目录一致。

模型报告在 `analysis/cocos-enemy/import-verification-{web,windows,android}.json`；整体报告在 `analysis/tutorial-client/build-verification.json`。macOS/iOS预检重新记录19份metadata和7项恢复资源，仍未在Mac导出或运行。

## 复现

先准备转换产物，再执行 `python tools/prepare_cocos_assets.py`，按[首战构建说明](tutorial-client-build.md)构建和核验。新增敌人审计命令：

```powershell
node tools/verify_cocos_character.mjs --model enemy991
node tools/verify_cocos_character.mjs --model enemy991 --config clients/cocos-poc/build/windows-model/proj/Debug/Resources/assets/resources/cc.config.json --output analysis/cocos-enemy/import-verification-windows.json
node tools/verify_cocos_character.mjs --model enemy991 --config clients/cocos-poc/build/android/data/assets/resources/cc.config.json --output analysis/cocos-enemy/import-verification-android.json
```

当前Web静态服务返回HTTP 200；7458战斗服务仍未监听。PM2启动的管理管道权限问题见[本地服务说明](../server/README.md)。这仍阻止真实首战游玩验收，不能用构建或静态审计代替。
