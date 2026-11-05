# Microsoft GraphRAG 银行监管问答

本仓库为服务器 `/home/ailab/data/HippoRAG/Microsoft_GraphRAG` 的源码、语料与测评产物快照（2026-11-05），私有保存。

## 上传内容

保留项目源码、依赖与配置模板、业务语料／题库、报告、当前正式测评的实际上下文与API用量；HippoRAG的vendor源码保留且移除其嵌套Git元数据。详见 `UPLOAD_MANIFEST.json`。

模型权重、Python虚拟环境、密钥、LLM缓存、原始大型图／向量索引、运行日志及上游基准数据未上传。模型与现有索引继续保留在服务器；本仓库不是完整磁盘备份，克隆后不会自动恢复大型索引。

## 保持原项目相对路径

两个仓库在同一父目录克隆，并分别命名为 `hipporag_local` 和 `Microsoft_GraphRAG`，以保留项目间引用。配置中原有服务器绝对路径按实际部署目录调整。API密钥在环境变量或本机 `.env` 设置，不提交到Git。

## 原项目文档

以下保留原文，其中部署阶段与旧结果以实际运行清单及最新正式测评产物为准。

# Microsoft GraphRAG 银行监管数据复现

工作目录：`/home/ailab/data/HippoRAG/Microsoft_GraphRAG`。

## 环境与数据

- GraphRAG 3.3.0，独立Python 3.12虚拟环境 `.venv`。
- BGE-M3使用独立Python 3.10虚拟环境 `.venv-bge`，通过已有依赖的只读副本离线构建，CUDA FP16，复用相邻项目的现有模型权重，不修改权重或原项目。
- 原始数据：`/home/ailab/data/HippoRAG/hipporag_local/data/banking`。整理后的1,700篇文档在 `input/banking.jsonl`，来源和摘要校验在旁边的manifest文件。
- 生成接口：`http://10.253.170.81:8006/v1`，模型 `qwen3.8-27B-raw`。API密钥只放在权限600的 `.env`，不提交到版本控制。
- 嵌入接口：`http://127.0.0.1:18086/v1`，模型 `bge-m3`，1,024维归一化dense向量；只监听本机。
- 项目所在 `/home/ailab/data` 是独立磁盘，创建时约416GB可用。依赖缓存、临时文件、索引均放在项目目录。

## 参数

参见 [PARAMETERS.md](PARAMETERS.md)。全量与试跑使用同一套领域参数，数据、缓存和输出分开。`upstream_defaults.yaml`保留上游默认配置快照。

## 启动嵌入服务

```bash
cd /home/ailab/data/HippoRAG/Microsoft_GraphRAG
bash scripts/start_embedding.sh
curl -fsS http://127.0.0.1:18086/health
```

服务日志在 `logs/embedding.log`，PID在 `logs/embedding.pid`。如服务已就绪，脚本复用现有服务。

## 小样本建图与问答

```bash
bash scripts/index.sh smoke
bash scripts/query.sh smoke local '这些资料涉及哪些监管机关和银行？请引用依据。'
bash scripts/query.sh smoke global '这些资料反映了哪些银行监管主题？请引用依据。'
```

试跑样本为5篇，覆盖短处罚文书、中等批复和较长规则文件，未包含测试问答或答案。

## 全量建图与问答

首次全量建图会产生较多模型调用。并发设为2，可通过缓存复用已完成的相同请求。

```bash
nohup bash scripts/index.sh full > logs/full-index.log 2>&1 < /dev/null &
echo $! > logs/full-index.pid
tail -n 30 logs/full-index.log
bash scripts/query.sh full local '在此输入你的银行监管问题'
```

索引完成后才能针对该索引问答。`output/`是全量产物，`smoke/output/`是小样本产物。脚本用文件锁防止同范围索引并发写入。修改模型、提示词、分块或数据后，应选择新的索引目录并记录配置，不将旧索引结果与新配置混用。

## 重新准备原始数据

```bash
.venv/bin/python scripts/prepare_data.py
.venv/bin/python scripts/prepare_data.py --limit 5 --output smoke/input/banking.jsonl
```

只选择DOC编号开头的HTML/TXT原始文档，同编号优先HTML。测试题、参考答案、审计报告不会进入索引。

## 操作约束

遵守父目录AGENTS.md：操作在HippoRAG项目目录及其子目录内进行；未经明确授权不停止、暂停或重启已有任务和服务。

## 结构化问答与评测输出

参见 [STRUCTURED_OUTPUT.md](STRUCTURED_OUTPUT.md)。入口为structured_qa.py，推理输入严格只允许id/question，输出与HippoRAG2评测导出格式兼容。已通过6项测试、一条真实Local查询及原评测工具的输入校验；产物位于outputs/structured_smoke_v1。正式15题评分和全量建图尚未运行。

## 复用现有索引的双模式成本测评

新增入口 `scripts/compare_modes.py` 支持 `qa original`、`qa graph_only` 与 `score`。原文模式沿用 Local 的原文与图混合上下文；仅图模式删除原文块，保留原图预算与图记录。两组生成响应、服务端 usage、重试、请求上下文及计时分别保存；评分包装原四指标实现，不修改评分公式或启动构图。

本次完整产物位于 `outputs/comparison_20261105`。审计分类见其中 `AUDIT.md`，复现命令见 `REPRODUCE.md`，质量与开销对比见 `REPORT.md`，各模式目录也有独立汇总。`summary.json` 与 `per_question.csv` 可用于进一步分析。历史构图及历史评分成本单列；缺失项标为未记录，不重新构图补齐。

旧 `structured_qa.py` 及 dashboard 入口保留原行为；需要上述完整成本记录时使用新入口。复现需选择新输出目录，避免覆盖历史测评。该模式比较保留相同图记录并仅移除原文，不能解释为图检索策略优化。
