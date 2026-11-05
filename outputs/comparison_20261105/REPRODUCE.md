# 复现说明

在服务器项目目录执行。每次使用新的输出目录，保留旧结果；入口不会调用构图或索引重建。

```bash
.venv/bin/python scripts/compare_modes.py qa original outputs/NEW_RUN/original
.venv/bin/python scripts/compare_modes.py qa graph_only outputs/NEW_RUN/graph_only
```

父目录 NEW_RUN 需预先创建。每组均使用新进程；两组顺序运行。共享现有就绪模型服务，不停止或重启任何服务。qa 从现有完成索引读取表及向量，文本嵌入与回答 API 均绕过客户端调用缓存。仅图组移除全部 text_units，保留原有图预算，因此原文预算空置。不得将保留的图描述误写为原文正文，也不得把它当作与原文无关的独立事实。

推理完成后使用相邻项目已有工具合并冻结金标准，再评分：

```bash
../hipporag_local/.venv/bin/python ../hipporag_local/data/banking/银行监管测试集/tools/export_eval_input.py --predictions outputs/NEW_RUN/original/predictions.json --output outputs/NEW_RUN/original/eval_input.json
../hipporag_local/.venv/bin/python scripts/compare_modes.py score outputs/NEW_RUN/original
```

graph_only 同理。score 在当前进程包装原有 JSONJudge，仅增加 HTTP 请求/响应/usage/计时记录，统一裁判输出上限为 8192、超时 240 秒，原指标公式、提示词和验证规则不变。无需修改相邻项目代码或配置。

compare_modes.py 的 usage_summary 区分已保存响应、完整 usage、已记录小计与未知消耗；存在缺失 usage 或没有收到响应的尝试时，完整 token 合计为 null，不能当作零。响应格式失败仍保存和统计服务端 usage。调用日志不保存认证头或密钥。

本次任务目录使用 final_original 与 final_graph_only；最早的 original 为记录器验证运行，单列开销，不进入质量对比。run_comparison.py 与 report_comparison.py 为本次固定目录的编排和汇总脚本；重新复现实验应使用新目录并调整这两个脚本的 R 路径，不覆盖现有结果。
