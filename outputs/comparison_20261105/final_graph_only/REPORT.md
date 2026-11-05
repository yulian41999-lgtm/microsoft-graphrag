# graph_only 测评汇总

## 质量

- context_relevancy：0.4；有效 15 / 15；失败 0。
- evidence_recall：0.4666666666666667；有效 15 / 15；失败 0。
- rouge_l：0.24629405151809777；有效 15 / 15；失败 0。
- answer_correctness：0.4621463499937883；有效 15 / 15；失败 0。

## 成本

- qa_total：{"mode": "graph_only", "stage": "qa_total", "core_qa_seconds": 120.76756603270769, "calendar_seconds": 128.31663723755628, "saved_api_responses": 30, "attempts": 30, "responses_with_usage": 30, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 34456, "completion_tokens": 6311, "total_tokens": 40767}, "prompt_tokens": 34456, "completion_tokens": 6311, "total_tokens": 40767, "api_seconds_sum": 118.56651134416461, "api_seconds_average": 3.952217044805487, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- qa_generation：{"mode": "graph_only", "stage": "qa_generation", "core_qa_seconds": null, "calendar_seconds": null, "saved_api_responses": 15, "attempts": 15, "responses_with_usage": 15, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 34003, "completion_tokens": 6311, "total_tokens": 40314}, "prompt_tokens": 34003, "completion_tokens": 6311, "total_tokens": 40314, "api_seconds_sum": 117.96245959494263, "api_seconds_average": 7.864163972996176, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- qa_embedding：{"mode": "graph_only", "stage": "qa_embedding", "core_qa_seconds": null, "calendar_seconds": null, "saved_api_responses": 15, "attempts": 15, "responses_with_usage": 15, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 453, "completion_tokens": 0, "total_tokens": 453}, "prompt_tokens": 453, "completion_tokens": 0, "total_tokens": 453, "api_seconds_sum": 0.6040517492219806, "api_seconds_average": 0.04027011661479871, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- scoring_judge：{"mode": "graph_only", "stage": "scoring_judge", "core_qa_seconds": null, "calendar_seconds": 680.0318261310458, "saved_api_responses": 90, "attempts": 90, "responses_with_usage": 90, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 102185, "completion_tokens": 37385, "total_tokens": 139570}, "prompt_tokens": 102185, "completion_tokens": 37385, "total_tokens": 139570, "api_seconds_sum": 664.9179784413427, "api_seconds_average": 7.387977538237141, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- scoring_local_embedding：{"mode": "graph_only", "stage": "scoring_local_embedding", "saved_api_responses": 0, "prompt_tokens": null, "completion_tokens": 0, "total_tokens": null, "api_seconds_sum": 0, "note": "Local BGE computation; input tokenizer usage and separate compute timing 未记录; included in scoring calendar time"}

答题状态：{"ok": 15}

实际上下文、原始回答和入模请求见 predictions.json；API 尝试见各 calls 日志；引用记录 ID 检查见 citation_checks.json。图描述为历史派生记录；详细边界与对照条件见上级 REPORT.md 和 AUDIT.md。
