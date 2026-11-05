# Local Search结构化输出

入口为structured_qa.py。当前只支持Local Search，使用现有参数及提示词，不启动索引、评分或修改HippoRAG2代码。

## 调用

在项目目录运行，输出路径必须位于本项目outputs目录，且输出文件及同名run.json均不得已存在。

```bash
.venv/bin/python structured_qa.py --scope smoke --questions outputs/structured_smoke_v1/questions.json --output outputs/new_smoke_run/predictions.json
```

生产索引完成后，可改用scope full及相邻项目的questions.json。full模式会检查索引完成状态和所需表，缺失时直接退出，不触发建图。

输入为非空JSON数组，每条严格只允许id/question两个非空字符串字段，ID不可重复。带answer、evidence等额外字段时拒绝推理。

```json
[
  {
    "id": "adapter-smoke-001",
    "question": "烟金罚决字〔2024〕34号处罚的机构是什么，罚款多少？"
  }
]
```

## predictions.json

每条问题保存以下字段：

- id、question、method、schema_version、run_scope。
- generated_answer：最终答案；raw_response：模型原始正文，生成中断时保留已接收部分。未闭合的think块或非stop结束标记视为生成失败。
- context：实际用于该次生成的完整混合上下文，类型为字符串列表。Local当前是一项，包含实际使用的原文、实体及可能入模的其他表，不只保存来源段落。
- context_text：对应的完整上下文字符串；context_data：框架返回的各类结构化上下文记录。额外候选不能替代context用于评分。
- sources：入模原文的citation_id、text_unit_id、doc_id、title、source_file、text、context_order。context_order是入模顺序，不冒称向量检索排名。没有统一检索分数，retrieval_score为null。
- context_metadata：与context按下标对应，记录mixed_context类型及来源列表。
- retrieved_candidates为null；当前入口不宣称记录了所有召回候选。
- generation_messages：实际发送的system/user消息；保存前检查捕获上下文确实出现在该次请求中。
- generation_usage：服务端流式响应提供的用量，未提供时为null；token_usage_estimate是GraphRAG库内估算，二者不混同。
- latency_seconds、retrieval_seconds、generation_seconds、llm_calls、finish_reasons。
- generation_model、embedding_model、generation_parameters、prompt_sha256、index_fingerprint、community_level。
- status及失败时的error。只保存异常类型，不把可能带凭据的provider异常详情写入结果。

索引指纹基于索引位置、表文件大小和修改时间、配置及语料manifest哈希，详细信息保存于同名run.json；它不是所有parquet文件的内容哈希。

## 批量与失败行为

逐题执行，每题完成后原子保存整个预测数组和run.json进度；单题失败仍记录并继续后续问题。进程异常时已保存的预测保留，run.json标记interrupted_or_error。入口不覆盖已有结果；重跑需新目录，尚未实现resume。

- ok：生成成功。
- generation_error：保留已检索的context、来源及请求，generated_answer为空；部分响应保存在raw_response。
- retrieval_error：检索失败，保留该问题与错误类型。
- no_context：没有上下文，跳过生成调用。

批量全成功退出0，完成但存在失败题退出2，配置或未处理运行错误退出1。run.json记录expected_n、completed_n和complete/complete_with_errors等状态，不把部分结果标为完整评测。

## 评测兼容

predictions中的id、generated_answer、context可直接供原HippoRAG2的export_eval_input.py合并使用。正式运行仍由原工具在推理完成后才读取冻结金标准。

本次仅用独立的单题格式验证参考测试兼容性，不运行正式15题，不调用裁判，不输出效果分数。测试参考与正式金标准隔离。
