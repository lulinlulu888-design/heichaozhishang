# 幻眼魔方动画 GLB

2026-10-14。已将首战敌人991的颜色参考模型与原包 `idle`、`fire` 动画合成一个可移植GLB。**这是通过数值验证的资源文件；后续已接入Cocos首战显示代码，但引擎实播仍未验收。** 导入与构建结果见[Cocos接入](cocos-tutorial-enemy.md)。

产物：`analysis/tutorial-enemy-animated/tutorial-enemy-991.animated.glb`，1,075,216字节，SHA-256 `fb9286f587c7c24b7344e5116318c45224add56deaacf36d21ed22b2aa0276ea`。包含4,208顶点、6,246三角形、61骨、单个基础颜色材质和两段动画。

| 片段 | 原采样 | 时长 | 导出通道 | 验证骨骼帧 |
| --- | --- | --- | --- | --- |
| idle | 101帧，30 Hz | 100/30秒 | 183 | 6,161 |
| fire | 36帧，30 Hz | 35/30秒 | 183 | 2,196 |

## 来源与保留范围

- 模型身份、绑定矩阵和材质依据见[敌人模型恢复](tutorial-enemy-model.md)。输入GLB锁定SHA `c39eaba279687e3dd1f3c786d627a6738d6aa6138990ffba20bc4990a79095f5`。
- 动画采样来自[原始动画恢复](tutorial-enemy-animation.md)，按片段track ID → GISACL骨骼名字 → mesh joint映射，未假定三个数组顺序相同。
- 导出工具再次锁定APK、GISACL动画库、两段包装文件和采样文件SHA。原mesh、inverse-bind矩阵、纹理二进制与材质定义保持不变；节点名字保持不变。
- 动画节点从matrix转为TRS，最大矩阵元素误差 `3.76e-7`。动画每个原采样点的translation/scale float32值完全一致；rotation只允许等价的四元数正负号变换，以避免相邻符号不连续。
- 原28字节骨骼辅助字段不满足艾尔莎的AABB解释，未知语义仍保留。绑定依据是独立GISACL参考姿态与原global bind的对应关系，没有修改辅助字段或放宽通用模型验证器。

这里只含Tex0基础颜色。Tex6紫色发光、法线/混合贴图、原shader、粒子、动画事件、状态切换、物理和声音尚未接入。`fire` 名称不能证明它对应战斗技能990/991/992中的哪一个。

glTF `LINEAR` 对旋转使用SLERP，ACL 1.2.0在采样间使用归一化LERP；因此只能声明原采样点一致，不能声明两个采样点之间逐时刻相同。原始首尾微小差异未修补：CPU蒙皮待机末帧相对首帧最大位移约0.00723，攻击末帧约0.00508，单位为原资源单位。

## 复现与验证

先运行模型与采样文档中的恢复步骤，再执行：

```powershell
python tools/export_tutorial_enemy_animation.py
python -m unittest discover -s tests -p "test_tutorial_enemy*.py" -v
```

本轮27项敌人资源相关测试实际通过：模型10、动画采样11、GLB导出6。其中导出测试用独立二进制回读器核对全部8,357组骨骼帧、源采样率、名字映射、原资源字节及TRS，另外以独立矩阵公式检查两段动画首/中/末帧蒙皮。身份错误的输入在写出前拒绝，保留旧产物。

共享ACL采样器原9项回归测试也通过；本轮白名单仅从艾尔莎两段扩为已确认的四段，不接受任意ACL输入。另一代理对最终SHA版本独立回读全部动画通道与逐帧蒙皮，结果一致。

导出器还对两段每一帧的4,208个顶点做CPU蒙皮计算，检查数值有限与空间边界，并将结果保存为 `analysis/tutorial-enemy-animated/export-report.json`；`manifest.json` 记录产物SHA与片段名单。这些检查证明数据转换的一致性，不替代引擎渲染、镜头取景、动画循环和原版视觉的实际验收。

源APK归档身份沿用已有REA Evidence；本轮采样、转换及数值验证属于普通本地工具证据，没有执行APK游戏代码或产生新的REA原生反编译证据。
