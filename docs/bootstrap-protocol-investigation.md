# 黑潮之上：启动、服务器发现与协议静态调查

本阶段已经从 APK 恢复脚本解码链、服务器列表解析方式、客户端连接配置，以及 7 份引擎/业务 protobuf 描述。**这些结果足以开始本地兼容服务原型；尚未证明原 APK 能与新服务完成握手、登录或战斗。**

这里将包内 Python 参考通道与实际脚本选择的原生 Asio 通道分别记载。未运行 APK，未联系旧运营服务器，未修改原 APK，未安装全局组件。

## 证据与重现

- 原 APK：`heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk`。
- `lib/armeabi-v7a/libclient.so` 解压后 50,532,672 字节，SHA-256：`54f7cfbc5c62c8ded1fec86d8aac5bae78a52548da56bd138278f8e1f38bc9ef`。
- `assets/script.npk`：26,159,752 字节，SHA-256：`6c075ef0e8712f47a502b3c93806d1e3ec5332220716c9496ed35c78c7f98e00`。
- [机器可读结论与校验信息](../analysis/bootstrap/findings.json) 包含模块索引、NPK 原始范围、密文/解码 SHA-256、原生函数地址及检验结果。
- [脚本索引](../analysis/assets/decoded/script/index.json) 由资源调查生成；本次复用其静态 marshal 结果。
- [部分字节码反汇编及完整结构 JSON](../analysis/bootstrap/scripts/) 保留原模块路径、函数名、源代码行号、函数内 bytecode offset、常量与名称表。
- [原生 protobuf 证据](../analysis/bootstrap/proto/inventory.json) 包含描述所在 ELF offset、长度和校验值。

所有 ELF offset 是解压后的 `libclient.so` 文件内偏移；本次涉及 `.text`、`.rodata` 的 VA 与文件偏移相同。`.data` 的 VA 比文件偏移大 `0x1000`，方法表的地址在本文明确写为文件偏移。Thumb 函数指针最低位为 1。

脚本 `.partial-dis.txt` 中的 opcode 名称是通过多处一致的调用和栈行为恢复的**部分映射**；未知指令保留 `UNKNOWN`。该输出不是完整源码反编译，也不表示执行过其中的任何分支。

## 1. 脚本导入器与解码

`redirect.py` 是脚本包中可直接静态解析的导入器。其 `NpkImporter.load_module` 对 `.nxs` 的处理顺序为：

1. `rotor.decrypt`，每个脚本重置 rotor 状态。
2. `zlib.decompress`。
3. 前 128 字节分别与 `154` 异或，再反转整个字节串。
4. `marshal.loads`。本项目工具以有边界检查的 `Marshal2` 将其读为普通数据，未构造或执行 Python 代码对象。

原生 `C_file` 导出给 Python 的三个方法提供密钥片段：

| 方法 | PyMethodDef 文件偏移 | Thumb 函数指针 | 字符串文件偏移 |
| --- | --- | --- | --- |
| `get_redirect_key_dn` | `0x2b04628` | `0xec4c79` | `0xec4ca4` |
| `get_redirect_key_dt` | `0x2b04638` | `0xec4cb5` | `0xec4ce0` |
| `get_redirect_key_df` | `0x2b04648` | `0xec4ce9` | `0xec4d14` |

方法表中的名称、函数指针、文档指针相互对应；函数的 Thumb ADR 指令加载字符串。完整证据见 [redirect_keys.thumb.txt](../analysis/bootstrap/redirect_keys.thumb.txt)。`init_rotor` 的字节码表明组合式为：

```text
DN*5 + DT*6 + '@' + (DT+DN+DF)*4 + '#!' + DF*3 + '^%'
```

片段及组合实现保留在 [neox_rotor.py](../tools/neox_rotor.py)。算法依据 [CPython 2.3.7 的 rotormodule.c](https://raw.githubusercontent.com/python/cpython/v2.3.7/Modules/rotormodule.c) 移植，原许可证保留在文件中；[原版源码副本](../analysis/bootstrap/cpython-v2.3.7-rotormodule.c) 的 SHA-256 为 `f0d9d9a960d40a0a49dd2a57a4aa4306903553a702feda23de40aa7351c47077`。

验证使用 NPK 第 0 项真实密文：解密后得到 zlib 头 `78da`，后处理得到 `lib\json\__init__.py`，marshal 完整消费 12,997 字节；另做了 768 字节合成数据的加解密往返校验。资源调查已将此算法用于全部 9,698 项，全部完成 marshal 静态解析。

## 2. 启动与服务器发现

`init.py` 的 `init` 调用 `GameStartup.onEngineInit`，`start` 调用 `GameStartup.startHeadCode`。后者还有补丁、配置初始化、资源下载和 UI 启动步骤；离线分支的具体可用性由独立调查记录。

`common/Version.py`（NPK index **4240**）直接赋值：

| 设置 | 值 |
| --- | --- |
| `CLIENT_VERSION` | `1.222180.224889` |
| `APP_INTERNAL_ID` | `u1` |
| `CLIENT_BUILD_LANGUAGE` | `chinese` |
| `PACKAGE_BRANCH` | `publish` |

`common/config_u1.py`（**6944**）携带服务器列表域名 `https://u1.update.netease.com`，以及三个路径：`/server_list_normal.txt`、`/server_list_all.txt`、`/server_list_apple_review.txt`。`net/extconfigs.py`（**1256**）根据审核/发布开关选择其一。SDK 登录基址配置是 `https://mgb.matrix.netease.com/u1/gb/`。这些是包内历史配置，未检查其当前可达性。

`common/config.py`（**8197**）还有远程配置入口 `https://u1.update.netease.com/config_%s`，能覆盖部分服务器/补丁参数。`net/patch/Config.py`（**1187**）包含更新域名及缓存服务配置。因此仅替换游戏 TCP 端口可能仍会停在更早的配置、补丁或列表阶段。

### 服务器列表的实际文本结构

`ui/ui_data/LoginDataTools.py`（**246**）的 `parseOneServerInfo`（原文件第 152 行）使用 `split(' ')`，不是自动折叠空白的 `split()`。正常服务器行至少有 10 个字段：

| 索引 | 字段 | 转换 |
| --- | --- | --- |
| 0 | `zone` | 字符串，作为返回的分区键 |
| 1 | `numberSt` | `int` |
| 2 | `netSt`，结果字典键为 `net` | `int` |
| 3 | `serverSt` | `int` |
| 4 | `name` | 字符串 |
| 5 | `oriName` | 字符串 |
| 6 | `ipAndPort` | 字符串 |
| 7 | `groupID` | `int(strip(...))` |
| 8 | `logicID` | `int(strip(...))` |
| 9 | `group` | 字符串 |

不足 10 列且首字段非空的行，会返回 `('Network', first_token[9:].strip())`；空行返回 `(None,None)`。这是解析器行为，尚未获得旧服响应样本来证明这种特殊行应使用什么前缀。

`getServerListByContent`（第 245 行）按换行拆分，调用上述解析器，然后按 `ipAndPort` 中的冒号拆出 IP 和整数端口。`isValidServerInfo` 还会按发布、审核、分组和渠道设置过滤。`getServerIpInfo`（第 284 行）确有 `127.0.0.1:4000` 默认数据，但目前不能据此断言发布 APK 会走本地默认分支。

## 3. 实际连接入口与加密配置

`net/CConnector.py`（**9509**）的模块 bytecode `0xce..0xed` 构造以下字典：

```python
client_config = {
    'enforce_encryption': 1,
    'use_keyczar': 0,
    'loginkeypath': 'res/test_rsa.pub',
    'zipped_channel': 1,
}
```

`_Connector.connect`（第 84 行）的 bytecode `0x92..0xa4` 构造 `AsioGateClient(ip, port, client_config)`；`0xc4..0xd3` 调用 `start_game(2)`。因此实际脚本选择的是 **AsioGateClient/原生 asiocore 路径**。

`net/mbsengine/client/AsioGateClient.py`（**4267**）本身仍有可读的 Python 控制流程，继承原生 `asiocore.rpc_handler`，通过 `dispatch_rpc` 进入原生发包逻辑。本次恢复了它的握手调用顺序，尚未核对原生每个字节的最终发送形式。

## 4. 原生 protobuf 描述

[extract_native_proto.py](../tools/extract_native_proto.py) 以 protobuf wire 格式解析 `libclient.so` 内嵌的 FileDescriptorProto。7 份相关描述及其源 offset：

| 描述 | ELF 文件偏移 | 长度 |
| --- | --- | ---: |
| `client_gate.proto` | `0x28d0030` | 1628 |
| `common.proto` | `0x28d0cb8` | 2553 |
| `mb.proto` | `0x28d36d8` | 296 |
| `mbcommon.proto` | `0x28d3920` | 155 |
| `dbmanager.proto` | `0x28d3f98` | 4265 |
| `gamemanager.proto` | `0x28d5910` | 3834 |
| `gate_game.proto` | `0x28d6e68` | 4310 |

另恢复了标准 `google/protobuf/descriptor.proto`。描述结构的解释对照 [Google protobuf 官方 descriptor.proto](https://raw.githubusercontent.com/protocolbuffers/protobuf/v3.5.1/src/google/protobuf/descriptor.proto)。输出 `.proto` 便于阅读；选项/扩展可能没有全部渲染，完整原始描述保留在 `.proto.bin` 和 `.proto.json` 中。

`client_gate.proto` 长度还通过原生函数 `_ZN30protobuf_client_5fgate_2eproto18AddDescriptorsImplEv`（Thumb 指针 `0x1575ba5`，代码从 `0x1575ba4` 开始）核对：`0x1575bd4` 设置 `r1=0x65c`，后续将该长度及描述地址传入 protobuf 注册函数。见 [client_gate_descriptor.thumb.txt](../analysis/bootstrap/client_gate_descriptor.thumb.txt)。

关键消息包括：

- `SessionSeed`：必填 `int64 seed=1`。
- `SessionKey`：必填 `bytes random_padding_header=1`、`bytes session_key=2`、`int64 seed=3`、`bytes random_padding_tail=4`。
- `ConnectServerRequest`：`routes=1`、必填 `RequestType type=2`、`deviceid=3`、`entityid=4`、`authmsg=5`；类型枚举 `NEW_CONNECTION=0 / RE_CONNECTION=1 / BIND_AVATAR=2`。
- `ConnectServerReply`：必填 `type=2`，其中 `CONNECTED=1`，还有 `BUSY / RECONNECT_SUCCEEDED / RECONNECT_FAILED / FORBIDDEN / MAX_CONNECTION`。
- `EntityMessage`：`routes=1`、`id=2`、必填 `Md5OrIndex method=3`、`parameters=4`、`reliable=5`、`localid=6`。

`IGateService` 含 `seed_request/session_key/connect_server/entity_message` 等；`IGateClient` 含 `seed_reply/session_key_ok/connect_reply/create_entity` 等。描述中的服务方法顺序已保留，但其在原生线上包中的具体 ordinal/封装仍需逐项核对。

## 5. 握手：脚本已证实的部分

`AsioGateClient` 的调用链：

1. `channel_cb`（第 172 行）在加密开关开启时调用 `_session_seed_request`。
2. `_session_seed_request`（第 227 行）调用 `dispatch_rpc('send_seed_request')`。
3. `seed_reply(seed)`（第 230 行）保存服务端 seed 并调用 `_send_session_key`。
4. `_send_session_key`（第 234 行）构造 `SessionKey`。头尾填充长度默认分别随机选自 `16..64`；会话 key 是对 32 个随机字节执行 `Crypto.Hash.SHA.new(...).digest()` 的结果；消息 seed 取服务端提供的值。
5. 该函数 bytecode `0xee..0xfd` 先调用原生 `delay_enable_encrypt(session_key)`，然后 `0xfe..0x11f` 调用 `dispatch_rpc('send_session_key', keyencrypter.encrypte(sessionkey.SerializeToString()))`。
6. `session_key_ok`（第 258 行）进入 `_on_rcp_channel_establised`，再根据新连接/重连分支发起连接。
7. 新连接 `_connect_server`（第 277 行）先安排 `delay_enable_compress()`，再 `dispatch_rpc('send_connect_server', NEW_CONNECTION, deviceid, '', '')`。

`net/mbsengine/common/SessionEncrypter.py`（**299**）的 `LoginKeyEncrypterNokeyczar.__init__`（第 24 行）明确使用 `RSA.importKey` 和 `PKCS1_OAEP.new`；`encrypte`（第 36 行）调用其 `.encrypt`。这是 RSA-OAEP 握手载荷的静态证据。

**尚未确认**：原生 `delay_enable_encrypt` 与 `delay_enable_compress` 在什么字节边界切换状态、发送与接收 cipher 是否分别维护、压缩与加密的先后、原生新/旧握手模式，以及是否存在额外标志或包头。

包内 `res/test_rsa.pub` 是公钥路径。后续本地恢复应使用自有密钥，并适配本地客户端副本的公钥或连接配置；公钥和这些描述本身不能恢复旧服私钥。

## 6. Python 参考通道的已恢复格式

`net/mbsengine/mobilerpc/RpcChannel.py`（**8758**）的 `MobileRpcChannel.CallMethod`（第 100 行）在 bytecode `0x27..0x34` 计算 `total_len=len(serialized_proto)+2`，在 `0x46..0x67` 组装：

```text
uint32le(2 + protobuf字节数) | uint16le(method_descriptor.index) | protobuf字节
```

4 字节长度不包含自身，包含后面的 2 字节方法编号。`CallMethod` 显式断言编号 `<65535`，负数还会被无符号 `struct.pack('<H', ...)` 拒绝。

`MobileRequest.py`（**996**）的 `request.get_size`（第 11 行）用 `unpack('<I', size)[0]`；`request_parser` 默认最大 body 为 `16777215`。其 `parse`（第 47 行）拒绝长度 `<1` 或 `>max_data_len`；上层 `RpcChannel.parse`（第 108 行）再拒绝 body `<2`。因此这条 Python 参考路径的完整最短帧为 6 字节，空 protobuf 消息可合法使用 2 字节 body。

`net/mbsengine/client/GateClient.py`（**3637**）参考路径在会话密钥协商后安装 `ARC4Crypter`；`SessionEncrypter.py` 中该类包装 `Crypto.Cipher.ARC4`。`Compressor.py`（**9228**）持有跨调用的 `zlib.compressobj`/`decompressobj`，输出 `compress(data)+flush(2)`，不是每帧重新创建 zlib 对象。

**上述 frame、ARC4 和 zlib 细节属于包内 Python 参考实现。实际连接入口已确定使用 AsioGateClient，尚不能把全部参考细节自动视为原生线上事实。**

## 7. 登录后的业务缺口

`net/mbsentity/CAccount.py`（**3091**）提供 `Account.login`（第 42 行）、`onUnisdkLoginback`（第 88 行）、`onLoginOK`（第 119 行）、`onLoginFailed` 等。`login` 通过 `serverProxy.call_server_method` 发送业务请求。

这意味着成功建立传输连接后，还需要服务器创建对应 Account/Avatar 等实体，并提供客户端需要的属性、RPC 回复及存档状态。单独返回一个 `connect_reply(CONNECTED)` 不能证明能进入大厅或战斗。旧服账号数据、活动状态和服务端权威规则也不能仅由接口定义推得。

## 8. 下一阶段与保留工具

下一阶段按以下顺序推进：核对原生通道编码与状态切换；实现自有密钥的本地握手；准备可回退的本地客户端适配；在隔离本地运行环境记录首个失败节点，再实现必要的列表/配置/实体与业务响应。APK 运行、客户端修改及本地握手尚未在本阶段进行。

保留的工具：

- [inspect_bootstrap.py](../tools/inspect_bootstrap.py)：提取 DEX/ELF，生成带 offset 和哈希的字符串/符号清单。
- [neox_rotor.py](../tools/neox_rotor.py)：脚本 rotor 解码。
- [extract_native_proto.py](../tools/extract_native_proto.py)：提取原生内嵌 protobuf 描述。
- [inspect_script_static.py](../tools/inspect_script_static.py)：对指定 NPK 索引生成结构 JSON 和部分反汇编。
- [collect_bootstrap_findings.py](../tools/collect_bootstrap_findings.py)：校验密钥、样本解码、descriptor 等证据并更新紧凑结论账本。

本机已使用的原生反汇编器是现有 NDK 的 `D:\Android\Sdk\ndk\27.0.12077973\toolchains\llvm\prebuilt\windows-x86_64\bin\llvm-objdump.exe`，参数 `--triple=thumbv7a-linux-android`。未下载或安装另一套反汇编引擎。
