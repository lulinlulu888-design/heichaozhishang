# 战斗待机动作修正

2026-10-14。原预览将序章 `stand_idle` 用于战斗；该姿态把武器骨骼移离身体附近，导致战斗中看起来空手。现在战斗使用原实体表对应的 `idle_1`，序章展示仍用 `stand_idle`。

## 原包证据

`tools/trace_battle_idle.py` 核对脚本哈希、导出局部字节码并提取动画，不执行 APK 代码。普通本地静态证据，不是 REA 或原客户端运行结果。

- 脚本 6025 `logic/fsm/BattleEntityStates.py` 的 `IdleState._enterLogic`：正常分支在偏移 201–228 调用 `CompAnimation.playViewAnimation(EntityAnimTypes.IDLE_1, True)`；另外保留睡眠、低血量 IDLE_2 和 RealHpLow IDLE_3 分支。
- 实体表 1955 的艾尔莎实体 0：IDLE_1 和 IDLE_2 映射 `idle_1`，IDLE_3 映射 `idle_2`。本轮只接入正常待机，未恢复低血量状态切换。
- `idle_1.gisacl` SHA-256：`02e2a046065cef91d3696b74229055ec21b23d874caea8cad3740b73b31afbe7`。
- ACL 载荷 SHA-256：`e877469c24e783bbb843ce792decd94c50c8a71fa1a636f9ec022044ad52cdf2`。180 骨骼、41 帧、30 Hz，独立哈希限定解码器采样 7,380 组骨骼帧。
- 导出 GLB 包含旧动作与新待机；源姿态往返和逐帧 CPU 蒙皮校验通过。GLB SHA-256：`acc7bbaa00b66a60165ce56341021055b55f1f73ca4c6af154e63036ee789463`。

## 重现与验证

依次运行 `python tools/sample_battle_idle.py`、`python tools/export_prologue_actor.py --with-battle-idle`、`python tools/prepare_cocos_prologue.py`，再执行既有 Cocos Web 构建。

共享 PrologueSceneView 按战斗/序章选择待机，覆盖初始加载、攻击返回、受击返回及死亡后重开。源码与生成模板同步。严格 TypeScript 检查及 Web 构建通过。

浏览器实际载入存档并拖出“斩击”：敌人生命 4600→4215、能量 5→4，攻击结束后角色回到持刀待机。截图为 `analysis/battle-visual/battle-idle/live-after-attack.png`，本次浏览器未报告 warn/error。

## 剩余问题

后续已处理序章朝向误用于战斗的问题，见下节。武器流光、拖尾、完整角色材质与技能演出仍未恢复。本次更新只验证 Web，尚未重新构建原生分发包。

## 战斗朝向追加

`tools/trace_battle_orientation.py` 从脚本 8067 导出带类名路径的 `BattlePlayerEntity.__init__` 与 `updateUserData`。后者偏移 225–249 将 `EntityData.ROTATION` 写入 `UserDataKey.RotationEulerRadian`，而构造器偏移 79–85 初始化 `rotOffset=None`；非空偏移仍会在后续相加。实体表 1955、实体 0 的 ROTATION 是 `[0,1.5708,0]`。这些是普通静态证据，不是原生运行结果。

原序章实例 `ailisha_1565` 无旋转字段，导出为单位矩阵。直接沿用它遗漏了战斗实体的旋转覆盖。当前共享客户端改为读取 `player-orientation.json` 并将源弧度转为 Creator 角度。

原战斗场景表 9650、场景 2081 的玩家 X=20.514759，敌方站位在负 X 侧；当前重建序章战场则将敌人放在玩家 X+29。直接应用源旋转在当前镜头下仍向左，所以另加明确的 **180° 重建站位适配**，不将其冒充原 `rotOffset` 或已验证的 NeoX Euler 转换。序章查看模式不使用此偏移。完整原镜头、站位与全部条件旋转尚未恢复。

严格 TypeScript 和 Web 构建通过。浏览器载入存档后，持刀方向改为右侧；再次拖出斩击，敌人生命 4215→3830、能量 4→3，攻击后返回适配后的持刀姿态。本次控制台无 warn/error，截图 `analysis/battle-visual/battle-orientation/live-after-attack.png`。当前镜头下角色背部仍占较大可视面积，不能据此宣称原构图一致性。

复现：运行 `python tools/trace_battle_orientation.py` 生成脚本/表证据；`prepare_cocos_prologue.py` 会自动运行它并同步资源。Windows/Android 与 Apple 构建指纹输入已纳入新 manifest，但本次没有重建或运行原生包。
