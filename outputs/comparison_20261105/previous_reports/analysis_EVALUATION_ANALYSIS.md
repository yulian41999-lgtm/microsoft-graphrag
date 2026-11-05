# GraphRAG与HippoRAG2评测分析

本次核对当前GraphRAG 3.3.0与相邻hipporag_local的实际代码；没有运行正式15题评分或启动全量建图。

## 当前检索验证

5篇文档已完成建图、向量索引和Local/Global问答，包含10个文本块、75个实体、93条关系、17个社区报告。临时问题的处罚机构与35万元罚款已人工核对原文；Global主题摘要尚未做事实覆盖评分。

本次额外执行只检索探针，不读取标准答案或证据，不调用生成模型。结果保存在retrieval_probe.json：目标DOC008801是首条来源，实际上下文含28个实体和6个原文块，覆盖全部5篇样本文档。因此可确认命中，不能据此宣称筛选精度高。该次预算限制下，关系表和社区报告未入模；图信息分配仍需验证。此次探针不是过去问答请求的完整追溯日志。

## 返回字段与评测接入

当前CLI保存回答Markdown。公开Python API返回response、context_data；底层SearchResult另含context_text、completion_time、llm_calls、prompt_tokens、output_tokens及可选分类统计。部分token统计由库内tokenizer估算，不能直接当服务端计费用量。

context_data可能含entities、relationships、reports、sources及启用时的claims，具体取决于模式和预算。此次只有entities和sources。实际评分以入模context_text为准；有in_context标记时检查标记，不把额外候选混入评分。

引用短ID可映射text_units.human_readable_id，取得text_unit_id、document_id，再关联documents.raw_data的source_file等字段。探针已保存sources_enriched，含context_order、citation_id、text_unit_id、doc_id、title、source_file、text；未取得的retrieval_score为null。实体连接度、关系权重、社区分数均不是统一检索置信度，不能与Hippo的PPR分数直接比较。

建议正式预测保存id、question、method、generated_answer、context、context_metadata、context_data、context_text、generation_messages、raw_response、status、latency_seconds、模型及索引版本。候选与入模内容分别保存。当前尚未实现正式批量导出。

## HippoRAG2当前四指标

当前有效方案以docs/evaluation-four-metrics.md与evaluation/config.json为准。六指标文档是历史方案；vendor保留的Recall@k、EM、token F1不是当前业务主表。

1. Context Relevancy：裁判只看问题和实际入模上下文，按无关0、部分包含1、完整包含2评分两次，总和除以4。它是整体信息充分性，不是相关块占比或Precision@k。
2. Evidence Recall：逐条判定标准证据是否由实际上下文完整支持，命中条数除以该题固定证据数。不是仅命中文档ID；裁判须完整且不重复地覆盖证据ID。
3. 中文ROUGE-L：NFKC规范化、英文casefold，汉字按字、英文和数字按串分词，以最长公共子序列计算F1。文本重合不能单独保证数字、否定或期限正确。
4. Answer Correctness：将答案和参考拆为原子事实，判定支持、错误与遗漏；事实F1=2TP/(2TP+FP+FN)。最终分数=0.75×事实F1+0.25×((cosine+1)/2)，语义项使用BGE-M3。它不是答对题数比例。

题库15题：10道Fact Retrieval、5道Complex Reasoning，共22处标准证据。推理只读id/question；保存预测后才在评分阶段合并标准答案与证据。当前outputs/banking只看到准备语料，没有正式15题预测或评分结果。

无上下文时检索分为0；无答案时生成分为0。生成失败仍保留成功检索的上下文。裁判失败记null/error，汇总显示expected_n、valid_n、failed_n和空答案数。整体及两种题型分别按逐题宏平均，不把四指标再平均为总分。

评分BGE独立设2048长度、batch=1，超长报错，不静默截断。当前裁判和生成使用同一Qwen，报告记录same_model_judge，正式结论应逐题人工复核或换独立裁判。正常非空输入约6次裁判调用/题，15题约90次，另有BGE编码；这只是调用量估算。当前judge保存原始输入、响应和用量，未实现历史文档建议的持久评分缓存。

## 如何公平对照

导出GraphRAG正式predictions后，可复用现有export_eval_input.py及evaluation.run，评分公式不必重写。Local的context应保留实际使用的原文和图信息；可将完整context_text作为字符串列表一项传入。原文专用诊断分可另报，不替换主要输入。

当前15题适合用Local作主对照，Basic作向量检索基线，Global的主题归纳独立报告。评价Global时分别保存map上下文、map输出和reduce上下文，明确检索指标评价哪一层，不能只保存最终答案。

固定同一语料、问题、金标准、生成模型、裁判、回答结构及输入输出预算。Hippo当前为候选20、入模最多5段、3072个BGE tokens，使用结论/法规依据/适用分析模板；GraphRAG当前10000个库内近似tokens且含图信息、回答偏简洁，不能直接称同预算对比。分块的512个BGE tokens与800个o200k tokens也不是同一单位。可分别报告原生配置和预算对齐配置，避免更多上下文或更长回答掩盖方法差异。

主指标沿用内容级Evidence Recall。若增加文档Recall@k，应按稳定DOC编号匹配并明确去重规则，不能把不同切块的原文字符串直接求交集。

## 语料差异

Hippo已准备1711篇、5387块；GraphRAG当前1700篇，ID为前者子集。缺少DOC000003、DOC000622、DOC000623、DOC000656、DOC000895、DOC000939、DOC001403、DOC001406、DOC001714、DOC001969、DOC001973。

这些旧source_file文件名为257至271个UTF-8字节，服务器访问返回errno 36（File name too long），与迁移的长文件名兼容问题一致。22处标准证据不引用这11个ID，但候选语料差异仍影响公平性。应补齐短文件名原始文件并保留原始标题元数据，或冻结双方一致的1700篇；共同文档也需核对内容哈希。本次未修改原数据。

建议顺序：统一语料与哈希；接入结构化记录；检查Local预算与回答模板；完成统一语料的索引；运行仅id/question的15题；复用四指标评分并逐题人工复核。15题属于诊断集，不足以支持广泛性能结论。

## 核对依据

本地读取hipporag_local下的business_qa.py、evaluation/metrics.py、evaluation/run.py、evaluation/tokenization.py、evaluation/judge.py、evaluation/config.json及data/banking/银行监管测试集/tools/export_eval_input.py，并检查当前GraphRAG安装包的API、SearchResult和LocalSearch源码。

- [GraphRAG官方Local Search说明](https://microsoft.github.io/graphrag/query/local_search/)
