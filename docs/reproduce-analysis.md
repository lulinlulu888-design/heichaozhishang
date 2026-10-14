# 重现本地分析

在 `D:\hczs` 打开 PowerShell。以下命令只分析 APK 或提取物，不启动游戏。

本机 `python.exe` 的 PATH 项是 Windows 商店别名，因此示例明确使用已存在的 Codex Python；换环境时将变量改为实际 Python 3 路径。以下原包分析工具均为标准库实现；新增贴图转换另使用 Pillow 和 ARM astcenc，见文末链接。

```powershell
$analysisPython = 'C:\Users\5090B\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$gameApk = 'D:\hczs\heichaozhishang_v1.222180.224889_ervajk_anfensi.com.apk'

# ZIP 清单、NPK 目录以及发布文件 MD5 验证
& $analysisPython .\tools\inspect_assets.py --verify-filelist --catalogue

# 有选择地提取 DEX 与原生库，建立字符串/符号证据
& $analysisPython .\tools\inspect_bootstrap.py $gameApk

# 提取原生库中内嵌的 Protobuf 描述符
& $analysisPython .\tools\extract_native_proto.py

# 检查脚本/资源 NPK，输出明文成员及元数据
& $analysisPython .\tools\extract_npk.py

# 批量解密脚本并解析 marshal 数据；不会执行其字节码
& $analysisPython .\tools\extract_npk.py --member assets/script.npk --decode-scripts

# 解析边界及原包样本验证
& $analysisPython -m unittest discover -s tests -p test_npk.py -v
```

结果位于 `analysis/`，多次运行会重建对应生成文件；原始 APK 保持只读。`decoded/script/index.json` 保存脚本索引、路径、偏移及哈希；`symbols.jsonl` 是函数、名称和常量的搜索入口。marshal JSON 和部分反汇编是分析产物，不是可以直接运行的原始 Python 源码。

REA 的证据通过 MCP `export_evidence_bundle` 保存，位于 `analysis/rea/`。自编解析器结果不冒充 REA Evidence。后端可用性限制详见 `investigation.md`。

后续恢复流程：[角色与卡牌静态数据](game-data-recovery.md)、[ASTC 贴图转 PNG](texture-conversion.md)。这些转换输出均为引擎中立数据，尚未等同于可玩的客户端。
