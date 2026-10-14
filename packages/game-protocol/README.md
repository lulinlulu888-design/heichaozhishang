# @hczs/game-protocol

从当前 APK 内静态证据恢复的 Node.js ESM 协议工具。目前包含两份 `mobile.server` Protobuf schema 的编解码，以及包内 Python RPC 参考实现的帧编解码。**尚无真实流量或原客户端兼容验证，不构成可登录的游戏服务端。**

## 安装与验证

在仓库根目录执行（已验证 Node.js 24.18.0、pnpm 11.17.0）：

```powershell
pnpm install --ignore-scripts --frozen-lockfile
pnpm test:protocol
```

唯一直接运行依赖为精确固定的 `protobufjs@8.8.1`；传递依赖由仓库锁文件固定。包不会启动网络监听器、执行 APK 脚本或请求游戏域名。

## Protobuf API

```js
import { loadProtocol } from '@hczs/game-protocol';

const protocol = await loadProtocol();
const bytes = protocol.encode('SessionSeed', { seed: '9007199254740993' });
const message = protocol.decode('SessionSeed', bytes);
// { seed: '9007199254740993' }

const request = protocol.encode('ConnectServerRequest', {
  type: 0,
  deviceid: Buffer.from('local-test'),
});
// 这里只编码消息体，不发送请求，也不声明此请求足以完成登录。
```

- `loadProtocol()` 异步加载 `schemas/client_gate.proto` 与其 `common.proto` 依赖，返回 `encode` / `decode`。
- 类型名接受 `SessionSeed` 或完整的 `mobile.server.SessionSeed`。
- 原始字段名保持 `snake_case`；拼错、未知字段、缺失 required、显式 null/undefined 会被拒绝，包括有默认值的 required 字段。
- `bytes` 输入接受 `Buffer` / `Uint8Array`，输出为 `Buffer`。不隐式解释 UTF-8 或 Base64。
- `int64` 输入接受十进制字符串、`bigint` 或安全整数，校验范围；输出始终为十进制字符串，避免超过 `2^53` 时丢失精度。
- 枚举输入为 schema 中的数值。省略的 optional 字段不自动补齐；显式的默认值仍保留字段存在性。
- 解码遵循 protobufjs 的未知 wire 字段处理，返回的数据对象不是保留所有未知字节的透明代理格式。需要原样转发时保留原始 payload。

实现基于 [protobuf.js 官方 API](https://protobufjs.github.io/protobuf.js/)。其 `.proto` 默认字段转换、显式校验与 64 位转换行为已结合安装版本源码及测试核对。

## Python 参考帧 API

```js
import { encodeFrame, FrameDecoder } from '@hczs/game-protocol';

const frame = encodeFrame(1, Buffer.from('0801', 'hex'));
// 0400000001000801：bodyLength=4，methodIndex=1，payload=0801。
// methodIndex=1 只是参考格式示例，不代表已确认的原生 seed_reply 路由。
const decoder = new FrameDecoder();
decoder.push(frame.subarray(0, 3)); // []
decoder.push(frame.subarray(3));   // [{ methodIndex: 1, payload: <Buffer 08 01> }]
decoder.finish();                 // 流结束时检查是否还有截断帧
```

恢复出的 Python `RpcChannel.CallMethod` 格式为：

```text
uint32 little-endian bodyLength
uint16 little-endian methodIndex
protobuf payload
bodyLength = payload.length + 2
```

`MobileRequest` 限制 bodyLength 不超过 `0xffffff`，随后 RPC 解析需要至少 2 字节；因此本工具接受 `[2, 0xffffff]`。该长度不包含 4 字节长度头。空 protobuf 消息体有效，完整帧最短为 6 字节。发送端按恢复到的断言限制 `0 <= methodIndex < 65535`；接收端只读出 uint16，不冒充已知 RPC 调度器。

`FrameDecoder.push(chunk)` 支持分片和粘包，返回本次完整帧数组；可传 `{ maxBodyLength }` 设置更小的本地内存上限。遇到非法长度或 `finish()` 检出截断后实例失效，不能尝试在同一流中跳字节重同步。

**实际 `net/CConnector.py` 调用的是原生 `AsioGateClient`，配置包含 `enforce_encryption=1`、`zipped_channel=1` 和 `loginkeypath='res/test_rsa.pub'`。当前帧实现仅复现包内 Python 参考实现，没有实现这些原生通道的加密、压缩、握手或校验，也没有将 `.proto` service 当作 gRPC。**

## 来源与测试范围

`schemas/provenance.json` 保存 native 库 SHA-256、descriptor 在库内的偏移/长度/SHA-256，以及复制出的 `.proto` 文本 SHA-256。两份文本来自 `analysis/bootstrap/proto/inventory.json` 中 `lib/armeabi-v7a/libclient.so` 的嵌入式 `FileDescriptorProto`；原生 options 保留在分析目录的 `.bin` / `.json`，当前文本副本主要恢复消息字段、枚举和 service 定义。

同一来源文件还记录 Python 帧参考来源：`RpcChannel.py` 的 NPK index 8758、`MobileRequest.py` 的 index 996，以及原生路径配置 `CConnector.py` 的 index 9509，附解密后 marshal 的 SHA-256。

测试的 golden vectors 是按静态 schema 字段号、类型及 Python 封包逻辑独立推导的固定字节，并非客户端抓包。覆盖 required 缺失、二进制字段、int64 边界、字段存在性、嵌套消息、帧分片/粘包及非法长度。下一步需恢复原生通道，再与实际 APK 验证。
