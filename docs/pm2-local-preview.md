# 本地战斗预览：PM2 当前故障

2026-10-14 04:41（本机时间）只读检查：7458 没有监听。`pm2 start ecosystem.config.cjs --only hczs-battle` 曾返回 `connect EPERM \\.\pipe\rpc.sock`，没有成功启动战斗服务。

当前存在四个 PM2 `Daemon.js` 进程：34624、48220、10072、46024，均属于 `DESKTOP-5MHS9IQ\5090B`；最新 `pm2.pid` 指向 46024。同一账号不代表相同的权限级别，也不能据此确定谁占有 RPC 管道。未读取到足以确定管道所有者、ACL 或进程完整性级别的证据。

本机安装的 PM2 `paths.js` 在环境变量处理后，将 Windows RPC/PUB 地址设置为固定命名管道。因此，仅更改 `PM2_HOME` 不能证明能隔离此冲突。不要反复尝试 `pm2 start`：失败输出中包含尝试创建 daemon，现有多个进程需要先在原管理环境中核对。不要执行 `pm2 kill`、删除整个 PM2 目录或停止所有 Node 进程，可能影响其他项目。

后续应在原先能正常管理现有 PM2 应用的终端中先确认 `pm2 ls` 可用，再运行：

```powershell
cd D:\hczs
pm2 start ecosystem.config.cjs --only hczs-battle
```

如果仍是相同 EPERM，停止重试并保留输出。尚无证据证明必须提权，因此不将“管理员运行”写成已验证解决办法。

启动成功后检查 `http://127.0.0.1:7458/api/rebuild/v1/status`，确认支持 tutorial-battles，再打开 `http://127.0.0.1:7456/?apiPort=7458`。`gameplayReady: false` 表示完整原版玩法尚未恢复，不能单凭该字段认定教学战斗接口启动失败。

独立存档为 `runtime/server/tutorial-preview.sqlite`，日志为 `runtime/server/pm2-battle.out.log` 和 `pm2-battle.err.log`。本轮没有启动替代后台服务、重启其他服务或修改 PM2 安装文件。

原始检查结果：`analysis/pm2/diagnostic.json`。这些 PID 仅为当时快照，后续任何操作前必须重新核对。
