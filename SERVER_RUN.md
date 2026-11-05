# 服务器后台建图

使用独立会话、忽略 SIGHUP，并将标准输入断开、输出写入文件。SSH、终端和本地电脑关闭不会向建图进程传递终端挂断信号。服务器关机、重启、管理员结束进程以及程序自身异常仍会导致任务结束。脚本不自动重试或自动重启。

在项目目录执行以下命令才会真正启动全量建图：

```bash
cd /home/ailab/data/HippoRAG/Microsoft_GraphRAG
.venv/bin/python scripts/start_index_detached.py --scope full
```

启动后输出 PID、独立会话 ID 和本次日志绝对路径。已有索引任务持有锁时，脚本拒绝重复启动；不会结束任何已有任务。现有模型调用缓存保留，能否命中取决于输入、提示词和模型配置是否一致。

重新连接服务器后查看进度：

```bash
cd /home/ailab/data/HippoRAG/Microsoft_GraphRAG
.venv/bin/python scripts/progress.py
cat logs/detached-full-run.json
ps -p "$(cat logs/full-index.pid)" -o pid,ppid,sid,tty,etime,stat,args
```

从 `logs/detached-full-run.json` 读取本次 `log_file`，使用 `tail -f` 加该绝对路径查看实时日志。按 Ctrl+C 仅退出日志查看。任务退出结果写入 `index-status.json`。

本启动方式仅解决本地终端和 SSH 连接断开问题；此前 CancelledError 的触发原因仍需排查。本文件与启动脚本准备时，没有重新启动全量建图。
