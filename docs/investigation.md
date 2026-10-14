# 逆向调查记录

日期：2026-10-14。当前阶段：资源与脚本恢复；尚未运行游戏或验证服务端兼容。

## 调查问题

| 问题 | 当前状态 | 证据与下一步 |
| --- | --- | --- |
| APK 身份与架构 | 已确认 | 包名 com.tencent.tmgp.uf，版本 1.222180.224889，ARMv7；见 analysis/android-badging.txt |
| 安装包是否只有启动壳 | 已回答：包含大量资源 | 17 个 NPK、角色/模型/UI、视频、音频；analysis/assets/inventory.json |
| 发布包资源是否完整 | 对包内声明清单已验证 | filelist.txt 的 3,295 个文件均存在，MD5 全匹配；不能据此判断最后线上热更新资源是否齐全 |
| NPK 能否读取 | 已确认 | 17 个包共 68,768 个索引项结构/边界检查通过；tools/extract_npk.py；analysis/assets/npk_catalogue.json |
| 游戏脚本能否恢复 | 9,698/9,698 静态解码成功 | 9,697 个唯一模块路径；含重复 redirect.py。已解密并完整解析 marshal 数据，不等于所有自定义字节码已反编译为源码 |
| 原客户端的服务器发现、登录及会话协议 | 未完成 | 继续在恢复的脚本中跟踪请求构造、响应处理、封包及状态机 |
| 角色/卡牌/关卡/战斗规则 | 部分数据已找到 | 1,489 个配置表模块、2,600 个 storyline 模块、531 个 card_action/server 路径下的数据脚本，另有怪物行为树及队伍/迷宫 JSON；具体运行职责尚未验证 |
| Node.js 服务端实现 | 技术方向已确认，兼容协议待恢复 | 参考 so-im 的 ESM 模块、独立协议包及 handler 分层；见 node-server-architecture.md |
| Android 实机/模拟器验证 | 未完成 | adb 无已连接设备；现有 Android SDK 无 emulator 目录；用户目前只有 APK |

## REA 已执行操作与环境限制

已执行 `open_binary`、`inspect_artifact`、`export_evidence_bundle`，完整归档证据保存在 `analysis/rea/initial-artifact-evidence.json`。

- APK SHA-256：`aae6c23e44a016ddb93f90f8d5934356960614a61545a4bf35c87820e4a645e4`。
- 归档检查 Evidence：`ev_bee2065741a233af9b819f150944baa02d65ea316389d5ff03839f2464bd16e3`。
- 内嵌 inventory Evidence：`ev_3e4b1103bcfe10d520a6347dadc634e2844476a4f2eecf36b9eef61afae46220`。
- `inspect_android_package` 返回能力不可用：未提供 `REA_JADX_MCP_JAR`（要求 jadx-headless-mcp 0.7.1）。
- 已通过 `open_binary` 选定 ARM ELF `libclient.so`，随后 `search_strings` 返回 `provider_unavailable`。Ghidra 未配置，并且本机 REA 的 Windows Ghidra P0 仅支持 PE；Hopper 不支持 Windows；IDA MCP 未配置。只补装 Ghidra 并不能消除当前 ARM ELF 的宿主适配限制。

以上缺口属于已安装 REA 的分析后端配置/适配边界，不是 APK 不可恢复的结论。不重复运行 setup，不把普通脚本输出标成 REA Evidence。

## 本地工具的独立静态证据

- Android SDK aapt2：解析 Manifest、版本和 ABI。
- Python zipfile：ZIP 成员清单和校验。无批量解压整个 APK。
- 自编 NPK 解析器：校验索引范围、解压长度，保存成员偏移与 SHA-256。
- Android NDK llvm-objdump：检查 libclient.so 的 ARM Thumb 指令，定位脚本加载器所调用的三个 key getter。
- 安全 marshal 解析器：将 Python 2 格式数据解析为普通数据结构，不创建或执行游戏 CodeType，不导入 APK 模块。
- rotor 算法：由 CPython 2.3.7 官方 rotormodule.c 移植，来源与原许可保留在 tools/neox_rotor.py。

这些结果是静态观察及解析验证。游戏协议实现和实际游玩结果需要后续单独验证。

## 已恢复的网络结构

`libclient.so` 中解析出 7 份游戏/引擎 Protobuf 描述符，另有标准 descriptor。网关相关的 `client_gate.proto`（原生文件偏移 `0x28d0030`，1,628 字节）声明种子、会话密钥、连接及实体消息；`common.proto` 定义实际字段及枚举。原始描述符、文本和来源哈希保存在 `analysis/bootstrap/proto/`，它们尚不证明线上封包或加密握手已经复现。

包内 Python 参考实现 `net/mbsengine/mobilerpc/RpcChannel.py` 的 `CallMethod`（脚本索引 8758）显示帧结构为 `uint32le(payload.length + 2) + uint16le(method.index) + protobuf payload`。`MobileRequest.py`（索引 996）给出 4 字节长度头及 `MAX_DATA_LEN = 16777215`。实际客户端存在 AsioGateClient 路径，必须继续核对原生实现/运行证据，不能把这条静态参考结构直接当成已经验证的连接。

## 验证记录

`tests/test_npk.py` 的 15 项测试通过，覆盖截断、索引/偏移越界、解压预算、长度不符、尾部压缩垃圾、marshal 引用边界，并校验 APK 中两份 redirect 数据一致且完整消费。原 APK 未改动，未执行游戏字节码。
