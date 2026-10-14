# 胜利语音恢复

2026-10-14。普通工具静态证据与重建 Web 客户端运行记录；不是原 APK 运行或 REA Evidence。

`NewResultPanel.ResultDialog.onFirstUpdate` 先请求 UI_JIESUAN，再按 `getBattleIsBoss()` 请求 BATTLE_WIN_BOSS / BATTLE_WIN_NORMAL。`audio_common_voice_table.py`（441）角色 1 的两项分别对应 ailisha_battle_win_boss / ailisha_battle_win_normal。SoundbanksInfo.xml 中精确匹配至 ailisha_voice.bnk 的事件 3858243926 / 3453401124。

二者都只有一个 CAkActionPlay，音频对象 171092430 / 380623742 分别引用 WEM 226981844 / 1005417443。事件、动作、字段和媒体引用均按原 bank 字节偏移校验；媒体与只读原 APK 内字节一致。两条音频合计 2.7213125 秒，PCM 采样数、声道、采样率、非静默检查通过。普通胜利语音 1.2133125 秒，PCM SHA-256 为 `c8b193f1592e985a07772debfe7d344fb4088022a403464c33461fe651a47391`。

分支证据：UIDataSource.getBattleIsBoss 比较 DungeonDataTools.getDungeonBattleType 与 SceneType.BossBattle。后者读取 maze_battle_table 的 SceneType；教程原 BattleID 5000 所在 4664 分表的 SceneType=0，为 NormalBattle（BossBattle=2）。客户端仅为现有 tutorial-5000 场景、艾尔莎接普通胜利语音，不给自定义关卡自动套用台词。

播放参数来自 actor-mixer 四层祖先的静态音量，线性系数 0.9440608762859234，乘明确重建的 master=0.8。动作无显式延迟，按默认立即 Play 接入；Wwise 的总线、RTPC、滤波、效果及原版时间一致性未恢复。UI_JIESUAN 对应 `ui/Event|ui_jiesuan`，当前 SoundbanksInfo 没有同名事件，未猜测替代音效。

复现：`trace_result_audio.py` → `decode_elsa_audio.py --result-voice` → `trace_elsa_audio_mix.py --result-voice` → `stage_result_audio.py`。分析输出位于 `analysis/battle-ui/result/audio-links.json` 与 `analysis/battle-visual/elsa-audio/result-voice-*`。这组产物与攻击语音报告分开保存。

## UI_JIESUAN 的边界调查

`trace_ui_result_audio.py` 进一步确认 Python 路径：ResultDialog 传 `cover=False` → AudioManager 的 `_event_music_map` → `_ui_event_channel_noncover` → AudioDevice 创建的 DecorationChannel → `audio.event(clip_path).start()`。此路径上没有观察到修改 `ui/Event|ui_jiesuan` 的操作。

名称 ID 候选算法（小写 UTF-8、32 位 FNV-1）与 SoundbanksInfo.xml 的全部 5,684 个不同名称/ID 对一致。对短名称 `ui_jiesuan`（2879110091）和完整路径（482383616）的两个候选 ID 扫描全部 101 个独立 BNK，均未匹配 HIRC 对象。报告为 `analysis/battle-ui/result/ui-audio-boundary.json`。这不覆盖 NPK 内的其他潜在资源、后续下载 bank，也不证明不存在通过别名抵达的等价音效。

`trace_native_audio_entry.py` 对固定 SHA-256 的 ARM ELF 检查 LOAD 映射，定位 load_events 邻近 PyMethodDef 形状的音频入口表：set_alias 表项在文件偏移 0x2b03778，Thumb 函数指针 0xec218d。离线反汇编显示它按 `ss` 接收两个字符串，经过 vtable+0x2c 间接调用。9,698 条脚本哈希校验后未找到字面量 set_alias 引用；两个未加密 redirect.py 条目使用原 payload 哈希校验。结果保存在 `native-audio-entry.json` 和 `audio-set-alias.thumb.txt`。

仍未知的是原生 audio.event 的实际路径解析、别名实现与注册调用。当前不能据此将 UI_JIESUAN 判为原版必然无声，也不能自行替换成别的结算音效。下一条具体调查线索是原生音频设备的 vtable+0x2c 实现及 event 类型构造入口。本轮仅增加证据工具与报告，没有改变客户端听感。

接入：BattleAudio 支持独立 manifest 与显式事件播放。胜利状态在当前攻击表现完成后触发，同一战斗重复刷新不重复播放；退出时停止并允许下次进入重新触发。延迟加载完成后仅在仍显示胜利界面时触发，已销毁对象不触发。

验证：严格 TypeScript、Creator Web 构建及实际 Creator 模块音频回归检查通过，新增显式结果事件身份/清理检查。浏览器实际进入胜利存档，收到 AudioSource STARTED，资源为 recovered/result-audio/1005417443，音量 0.7552487010287388。点击刷新战斗后 STARTED 仍为一条；无浏览器警告/错误。日志 `analysis/battle-ui/result/audio-live-log.json`。该事件证明浏览器音频源开始播放，不等同于扬声器听感或原版混音验收。此次语音尚未进入上一轮 Android/Windows 分发包。
