# 分解状态试玩

入口：http://127.0.0.1:7456/?apiPort=7459 。本轮启动的Node服务监听127.0.0.1:7459，独立存档 `runtime/server/breakdown-preview.sqlite` 及 `.battles`；没有替换7458原首战服务，也没有声称由PM2托管。

启动命令：

```powershell
node server/src/index.js --port 7459 --save-path runtime/server/breakdown-preview.sqlite --custom-scenario server/data/custom/breakdown-trial.json
```

这是明确标记的自定义“分解试炼”，沿用现有重建场地与模型，不是原版城市10405。新增配置格式 `hczs-custom-tutorial-v2` 允许显式statusRules、namespaced addEnemySkills和enemyFallback；旧v1扩展字段约束保持。敌人自定义首轮施加2层并造成100伤害；玩家卡牌可施加分解或恢复300生命，实际恢复才减1层。两张新卡尚无专用插画，当前显示卡框和效果文字。

原图标来自buff_table391/66051的BUFF_ICON：`uires/AllUIRes/Fight/Buff/fenjie2.png`。独立png/pkm查找无匹配，沿VT别名、唯一plist frame和4块ASTC瓦片恢复48×48原像素。运行 `python tools/recover_monster_portrait.py --actor breakdown` 可复现，完整哈希、源位置、裁切与假设在 `analysis/battle-ui/health/breakdown-portrait/report.json`。界面位置和层数字体属于重建排版，不是原版布局一致性结论。

Web实测：创建独立档案、进入试炼、拖拽分解卡成功，敌方显示2层；结束首轮后艾尔莎1668.8生命/2层，魔方4400生命/2层；拖拽治疗后艾尔莎恢复1768.8生命/1层。刷新网页再进入，恢复回合2、能量4、手牌5张及相同层数。独立只读SQLite确认版本4、玩家1层/敌人2层及对应精确TaggedScalar生命。控制台警告/错误为空。

截图：`analysis/test/status-client/breakdown-heal-live.png`、`breakdown-restored-live.png`。Creator Web构建、严格TS检查、实际编译控制器检查通过；新增HTTP配置/治疗/重启重放测试和完整工作区测试通过。

后续通关验证：实际浏览器继续至第三回合，先将魔方压至198生命，再结束回合，由200点分解结算击败。显示原胜利标题和敌方死亡姿态；刷新网页重新进入仍恢复胜利，控制台无警告/错误。`node tools/verify_status_preview_save.mjs` 独立只读检查SQLite，确认版本10、9条连续操作记录、最后请求end-turn、最后伤害来自分解，玩家精确生命1126.8000000000002、玩家3层/敌人2层。证据为 `analysis/test/status-client/victory-save-evidence.json`，截图为 `breakdown-victory-live.png`、`breakdown-victory-restored.png`。该工具不改动存档，要求最新试炼已获胜。

限制：状态事件时序/盾与HP结算仍是显式重建政策，非原服务器验证；角色攻击动作并非新自定义技能的原版演出。原生包未重建，Android设备与macOS/iOS验收未完成。
