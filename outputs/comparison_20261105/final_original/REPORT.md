# original 测评汇总

## 质量

- context_relevancy：0.8333333333333334；有效 15 / 15；失败 0。
- evidence_recall：0.7111111111111111；有效 15 / 15；失败 0。
- rouge_l：0.3185269966699332；有效 15 / 15；失败 0。
- answer_correctness：0.5352360552698598；有效 15 / 15；失败 0。

## 成本

- qa_total：{"mode": "original", "stage": "qa_total", "core_qa_seconds": 169.45075784623623, "calendar_seconds": 217.5069170985371, "saved_api_responses": 30, "attempts": 30, "responses_with_usage": 30, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 78828, "completion_tokens": 9067, "total_tokens": 87895}, "prompt_tokens": 78828, "completion_tokens": 9067, "total_tokens": 87895, "api_seconds_sum": 164.78867878299206, "api_seconds_average": 5.492955959433069, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- qa_generation：{"mode": "original", "stage": "qa_generation", "core_qa_seconds": null, "calendar_seconds": null, "saved_api_responses": 15, "attempts": 15, "responses_with_usage": 15, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 78375, "completion_tokens": 9067, "total_tokens": 87442}, "prompt_tokens": 78375, "completion_tokens": 9067, "total_tokens": 87442, "api_seconds_sum": 164.2731480533257, "api_seconds_average": 10.951543203555048, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- qa_embedding：{"mode": "original", "stage": "qa_embedding", "core_qa_seconds": null, "calendar_seconds": null, "saved_api_responses": 15, "attempts": 15, "responses_with_usage": 15, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 453, "completion_tokens": 0, "total_tokens": 453}, "prompt_tokens": 453, "completion_tokens": 0, "total_tokens": 453, "api_seconds_sum": 0.5155307296663523, "api_seconds_average": 0.034368715311090155, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- scoring_judge：{"mode": "original", "stage": "scoring_judge", "core_qa_seconds": null, "calendar_seconds": 790.3950753305107, "saved_api_responses": 90, "attempts": 90, "responses_with_usage": 90, "usage_complete": true, "recorded_usage_subtotal": {"prompt_tokens": 242587, "completion_tokens": 41429, "total_tokens": 284016}, "prompt_tokens": 242587, "completion_tokens": 41429, "total_tokens": 284016, "api_seconds_sum": 780.6562133254483, "api_seconds_average": 8.673957925838314, "failed_attempts": 0, "unknown_consumption_attempts": 0}
- scoring_local_embedding：{"mode": "original", "stage": "scoring_local_embedding", "saved_api_responses": 0, "prompt_tokens": null, "completion_tokens": 0, "total_tokens": null, "api_seconds_sum": 0, "note": "Local BGE computation; input tokenizer usage and separate compute timing 未记录; included in scoring calendar time"}

答题状态：{"ok": 15}

实际上下文、原始回答和入模请求见 predictions.json；API 尝试见各 calls 日志；引用记录 ID 检查见 citation_checks.json。图描述为历史派生记录；详细边界与对照条件见上级 REPORT.md 和 AUDIT.md。
