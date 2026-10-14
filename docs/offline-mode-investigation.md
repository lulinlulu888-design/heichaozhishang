# “离线模式”静态控制流调查

调查日期：2026-10-14。目标：当前目录 APK 的 `script.npk`，SHA-256 `6c075ef0e8712f47a502b3c93806d1e3ec5332220716c9496ed35c78c7f98e00`。

**结论：这份客户端确实识别 `--offline`，但恢复出的分支只跳过首次 UI 启动，分支内没有本地角色、关卡或战斗初始化。`isLocalDebug` 是调试器配置，不是离线游戏实现。另一个“直接进战斗”入口明确连接服务端，再请求 `debugQuickFight`。目前不能把这些开关当作可直接游玩的单机模式。**

本报告未修改 APK、未执行恢复出的代码、未连接任何游戏服务器。内容来自自写 marshal 数据解析器与部分 NeoX 字节码映射；保留未知指令，不把静态可达性写成运行成功。

## 证据约定

- `index` 是 [脚本索引](../analysis/assets/decoded/script/index.json) 的零起始 NPK 记录序号；同一索引可定位 `.marshal` 与其中保存的 SHA-256。
- `offset` 是所述函数 `co_code` 内的**十六进制字节偏移**，不是 APK 文件偏移，也不是源码行号。
- `const[n]`、`names[n]` 是该函数自己的常量表与名字表；恢复出的源码行号仅为辅助信息。
- 使用 [inspect_script_static.py](../tools/inspect_script_static.py) 的已确认部分映射：`99 LOAD_CONST`、`61 LOAD_FAST`、`60 LOAD_ATTR`、`83 CALL_FUNCTION`、`94 POP_JUMP_IF_FALSE`、`9c JUMP_FORWARD` 等。`ac` 在当前文本工具中仍显示 `UNKNOWN`，本调查与协议调查者交叉确认其条件用法为 `POP_JUMP_IF_TRUE`；本报告核心 `--offline` 分支不依赖该补充映射。

## `--offline` 的来源与启用条件

| 位置 | 指令证据 | 含义 |
|---|---|---|
| index 6526，`init.py:init(arg)`，`0x0010–0x0019` | `GameStartup.onEngineInit(arg)` | 启动参数由原生引擎传入 Python 入口。 |
| index 7329，`GameStartup.onEngineInit`，`0x000c–0x0012` | `LOAD_FAST arg` → `STORE_ATTR names[1]=StartupArgStr` | 写入 `Globals.StartupArgStr`。 |
| index 7329，`GameStartup.afterPatch`，`0x0018–0x0024` | 取 `Globals.StartupArgStr`，写入 `G.Vars.StartupArgStr` | 补丁后同步到 `Vars`。 |
| index 4260，`G.py:Vars.isOffline`，`0x0000–0x000c` | `LOAD_CONST const[1]='--offline'`；读取 `cls.StartupArgStr`；`COMPARE_OP 6`；返回 | 等价于 `'--offline' in cls.StartupArgStr`。 |

尚未追踪 Android Activity/JNI 如何构造此参数，故不能声称某个 `adb am start` extra 或命令行参数已经能启用它。仅修改 shell 启动参数不保证传到该字段。

`Vars.preloadCData()` 另有一处相关行为：index 4260，`0x0020–0x002f` 调用 `isOffline()`；为真时返回 `False`。这表示其“是否预载数据”判定为否。本次没有确认该方法在当前 Android 启动路径中的调用方，不能据此断言运行时所有数据表都不会加载。

## `startGame` 中离线分支实际做什么

index 7329，`GameStartup.startGame`（恢复源码行号 697），关键指令：

```text
00c2 LOAD_FAST G
00c5 LOAD_ATTR Vars
00c8 LOAD_ATTR isOffline
00cb CALL_FUNCTION 0
00ce POP_JUMP_IF_FALSE 0x00d4
00d1 JUMP_FORWARD 56             # 下一指令 0x00d4 + 56 = 0x010c
00d4 ... G.Vars.isSLG() ...
00e0 POP_JUMP_IF_FALSE 0x00ff
00e3 ... G.M.SceneMgr.switchScene(8000, SceneConfigType='SLG') ...
00fc JUMP_FORWARD 13             # 跳到 0x010c
00ff LOAD_FAST Globals
0102 LOAD_ATTR UI
0105 LOAD_ATTR startFirstUI
0108 CALL_FUNCTION 0
010b POP_TOP
010c ... time.time() ...
0118 LOAD_CONST None
011b RETURN_VALUE
```

该段可可靠还原为：

```python
if G.Vars.isOffline():
    pass
elif G.Vars.isSLG():
    G.M.SceneMgr.switchScene(8000, SceneConfigType='SLG')
else:
    Globals.UI.startFirstUI()
```

因此它跳过的是**首次 UI 初始化与进入登录阶段的调用**，没有替代这些调用来创建离线世界。`startGame` 更早的 `0x0024–0x00b5` 还有独立的 shader cache 分支；若 `Globals.shaderCacheSceneLevel` 为真，会先启动相应 helper 并返回，也不进入 `--offline` 判断。

被跳过的 `UISystem.startFirstUI(showLoginPanel=True)` 位于 index 6140：

- `0x0000–0x005a` 为若干 UI manager 调用 `doInit()`。
- `0x005b–0x0064` 检查 `showLoginPanel`；为假则返回。
- `0x0065–0x0074` 调用 `getOutput().setCurPhase(const[1]='LoginVideo')`。

`showLoginPanel=True` 默认值由 `UISystem` 类体 `0x0033–0x0039` 加载 `True` 并 `MAKE_FUNCTION 1` 确认。`--offline` 连 UI manager 的这些 `doInit` 都一并跳过，不能把跳过登录视频解释为已经进入可玩状态。

## `isLocalDebug` 的作用

index 5462，`Globals.py` 模块体 `0x026f–0x0272` 将 `isLocalDebug` 初始化为 `False`。

index 7329，`GameStartup._initDebug`（恢复源码行号 729）：

| 条件与位置 | 后续行为 |
|---|---|
| `const[3]='--debug'`，`0x002d–0x0036` | `0x0039–0x003f` 写 `Globals.isLocalDebug=True`；加入 `C:/Python27/Lib` 与对应 debug egg；`0x008a` 导入 `pydevd`；`0x0090–0x00b1` 调用 `settrace('localhost', port=7687, stdoutToServer=True, stderrToServer=True, suspend=False)`。 |
| `const[14]='--pycharm_latest'`，`0x00b8–0x00c1` | `0x00c4–0x00ca` 写同一标志；加入 `debug/pydevd-pycharm.egg`；`0x00f3` 导入 `pydevd_pycharm`；`0x00f9–0x011a` 调用 `settrace`，端口为 `const[16]=18888`。 |

`GameStartup.initGlobals` 的 `0x0114–0x0126` 读取该标志，构造 `ExceptionReporter(localDebug=Globals.isLocalDebug)`。这条路径没有用于生成账号、绕过连接、加载本地战斗的控制流。相关调试 egg 在本次 APK 顶层文件清单中也没有直接同名成员；不应未经必要性评估就启用该标志。

## “直接进战斗”仍是联网调试入口

| 位置 | 证据 |
|---|---|
| index 1896，`ui/UIInput.py:UIInputHandler.onDirectGoToBattle`，`0x0000–0x0006` | 将 `Globals.IsDirectEnterBattle=True`。 |
| 同函数 `0x0021–0x0065` | 通过 `game3d.get_udid()` 或 `get_mac_address()`，配合 `const[2]='__debug'` 与时间戳构造调试账号。 |
| 同函数 `0x0068–0x008b` | 调用 `Globals.UI.DataSource.getServerIpInfo()`，读取 `const[3]='IP'`、`const[4]='Port'`。 |
| 同函数 `0x008e–0x00b2` | 调用 `onRequestLogin(ip=..., port=..., account=..., pwd=...)`。 |
| index 1896，`onRequestLogin`，`0x0010–0x0024` | 调用 `Connector.connect(kwargs['ip'], kwargs['port'])`。 |
| index 1703，`net/mbsentity/CAthlete.py:Athlete.onEnterHall`，`0x0000–0x0020` | 若直进标志为真，调用 `_compatibilityOldTask()`、`directEnterDungeon()` 后返回。 |
| index 1703，`Athlete.directEnterDungeon`，`0x0000–0x0019` | `self.serverProxy.call_server_method(const[1]='debugQuickFight', {'battleID': const.DebugBattleID})`。 |

这个入口可作为后续本地兼容服务端的较短测试路径。它需要服务端连接和战斗请求处理，不能用于证明客户端具有独立战斗模拟器。

## 哪些前置步骤不会被 `--offline` 自动替代

1. **引擎与资源环境。** `onEngineInit` 在 `0x0029–0x0061` 调用 `_addPaths`、`_loadDlls`、`_initCocos`、语言和渲染初始化，`0x0083–0x0089` 调用 `setCCZkey`。这些调用没有 `isOffline` 条件。APK 提供的是 `armeabi-v7a/libclient.so` 与配套资源；上述纯数据反汇编并未替代原生 `game3d`、`render`、Cocos 绑定或 Android 运行环境。

2. **HeadCode 与补丁流程。** index 6526 `init.start()` 的 `0x0010–0x0016` 无条件调用 `GameStartup.startHeadCode()`。index 7329 `startHeadCode` 的 `0x001a–0x0036` 调用 `HeadCode.getInstance().init()`。index 6543 `HeadCode.init` 的 `0x000c–0x001e` 依据 `ENABLE_HEADCODE_HOTFIX` 决定是否直接 `onSuc()`；没有 `--offline` 判定。index 891 `PatchManager.init` 的 `0x0018–0x0045` 使用 `ENABLE_PATCH` 与 `IsPublishForProfile`，在禁用补丁时仍调用 `checkVersion()` 与 `patchFinish()`。本调查没有将其未检查的网络行为视作已消除。

3. **发布开关。** index 144 `switches_publish.py` 模块体将 `ENABLE_PATCH=True`（`0x0054–0x0057`）、`ENABLE_HEADCODE_HOTFIX=True`（`0x0270–0x0273`）。index 3099 `switches_trunk.py` 对应项是 `False`。index 8368 `switches.py:isEnginePublishVersion` 的 `0x000f–0x0018` 查询 `game3d.is_release_version()`；模块体 `0x01e9–0x01f8` 与 `0x02d9–0x02e2` 选择 publish/trunk。原生实际返回值未做运行验证，但选择条件本身不是 `--offline`。

4. **全局对象与渠道/SDK。** index 7329 `initGlobals` 无 `isOffline` 检查：`0x003d–0x0046` 调用 `G.M.init()`；`0x02c9–0x02e2` 构造 `ChannelManager`；`0x0367–0x0386` 构造 `PhaseManager`；`0x03ab–0x03cd` 仅以 `IsEngineMaster` 决定是否构造 `EnvSdkHelper`；`0x03d3–0x040b` 初始化本地推送与直播系统；`0x0418–0x0431` 构造 `GameWorld`；`0x0434–0x0455` 在 `isOpenDLCPackage()` 时调用 `onRequestLoginDLCDatas()`。没有据此声称这些构造函数一定联网，但 `--offline` 不会自动跳过它们。

## 覆盖范围与下一步含义

本次遍历恢复的 9,698 条脚本的符号/短字符串索引，精确字符串 `--offline` 只命中 `G.py`；`isOffline` 只命中 `G.py` 和 `GameStartup.py`；`isLocalDebug` 只命中 `Globals.py`、`GameStartup.py`。再对上述函数、初始化前置步骤、直进战斗链进行了指令级检查。未进行完整动态调用图或任意反射调用证明，未排除尚未追踪的编辑器、回放或测试工具存在其它局部功能。

可以继续复用该客户端的资源、规则数据与接口来建设本地兼容服务端；现有证据不支持“仅加 `--offline` 就能游玩”的实施路线。若希望保留原客户端正常流程，应处理 HeadCode/补丁、渠道登录与网关响应，再实现实体状态及战斗 RPC；`debugQuickFight` 可能缩短战斗验证链。

详细指令文本保存在 [analysis/assets/offline](../analysis/assets/offline/)。主要原始静态对象是 [GameStartup](../analysis/assets/decoded/script/07329_c170536a.marshal.json)，完整文件身份与偏移见 [index.json](../analysis/assets/decoded/script/index.json)。
