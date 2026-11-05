"""Refresh existing report entries from saved comparison artifacts; no model calls."""
import json,html,shutil,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1];R=P/'outputs/comparison_20261105';B=R/'previous_reports';B.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text())
def esc(x):return html.escape(str(x))
def number(x):return '未记录 / 不适用' if x is None else f'{x:.3f}' if isinstance(x,float) else str(x)
s=read(R/'summary.json');per=read(R/'per_question.json');labels={'context_relevancy':'上下文相关性','evidence_recall':'证据召回','rouge_l':'中文 ROUGE-L','answer_correctness':'答案正确性'}
for target in [P/'analysis/EVALUATION_ANALYSIS.md',P/'output/visualization/evaluation.html']:
 backup=B/(target.parent.name+'_'+target.name)
 if target.exists() and not backup.exists():shutil.copy2(target,backup)
base=(R/'REPORT.md').read_text()
text=base.replace('# 原文与仅图模式测评报告','# GraphRAG 测评分析：原文与仅图模式',1)
text=text.replace('\n\n两组复用', '\n\n更新日期：2026-11-05。本报告已由试跑阶段的方法分析更新为已完成的正式 15 题双模式结果。旧版保存在 `../outputs/comparison_20261105/previous_reports/analysis_EVALUATION_ANALYSIS.md`。\n\n两组复用',1)
text+='''
## 指标定义与适用范围

- 上下文相关性：裁判对整组实际入模上下文独立评分两次，每次 0、1、2，合计除以 4。不是相关块比例。
- 证据召回：判断实际上下文是否完整支持每条冻结标准证据，命中数除以证据总数。不是文档 ID 命中率。
- 中文 ROUGE-L：按既有中文分词与规范化实现计算文本重合 F1，不能单独证明事实正确。
- 答案正确性：0.75 × 原子事实 F1 + 0.25 × BGE 语义项；不是答对题数比例。

整体及题型分组均按有效题目宏平均，保留有效与失败题数，不把四指标再平均为总分。完整题型分组见 summary.json 与各组 scores/scores.json。

## 与 HippoRAG2 对照的边界

本次只比较同一份 GraphRAG 索引下的两种回答模式，并未重跑 HippoRAG2，不能据此得出跨系统优劣。旧报告中 1,711 与 1,700 篇语料差异属于当时的跨系统核对记录；本次两组均使用同一份 1,700 篇 GraphRAG 语料，不为补齐文档而改动索引。

## 产物入口

- [本次完整对照报告](../outputs/comparison_20261105/REPORT.md)
- [逐题对照 CSV](../outputs/comparison_20261105/per_question.csv)
- [机器可读汇总](../outputs/comparison_20261105/summary.json)
- [指标审计分类](../outputs/comparison_20261105/AUDIT.md)
- [复现说明](../outputs/comparison_20261105/REPRODUCE.md)
- [可视化测评报告](../output/visualization/evaluation.html)
'''
(P/'analysis/EVALUATION_ANALYSIS.md').write_text(text)
quality=''.join('<tr><th>'+label+'</th>'+''.join('<td>'+f"{s['modes'][m]['quality']['overall']['metrics'][k]['mean']:.4f}"+'</td>' for m in ['original','graph_only'])+'<td>'+f"{s['quality_change'][k]['change']:+.4f}"+'</td></tr>' for k,label in labels.items())
cost=''
for c in s['cost_rows']:
 cost+='<tr>'+''.join('<td>'+esc(number(c.get(k)))+'</td>' for k in ['mode','stage','saved_api_responses','prompt_tokens','completion_tokens','total_tokens','core_qa_seconds','calendar_seconds','api_seconds_sum','api_seconds_average'])+'</tr>'
rows='';pred={m:{x['id']:x for x in read(R/('final_'+m)/'predictions.json')} for m in ['original','graph_only']}
for a in [x for x in per if x['mode']=='original']:
 b=next(x for x in per if x['mode']=='graph_only' and x['id']==a['id'])
 rows+='<tr><th colspan="9">'+esc(a['id']+' · '+a['question'])+'</th></tr>'
 for x in [a,b]:
  rows+='<tr>'+''.join('<td>'+esc(number(v))+'</td>' for v in [x['mode'],x['status'],x['total_tokens'],x['latency_seconds'],x['context_relevancy'],x['evidence_recall'],x['rouge_l'],x['answer_correctness'],x['citation_status']])+'</tr>'
  p=pred[x['mode']][x['id']]
  rows+='<tr><td colspan="9"><details><summary>'+esc(x['mode'])+'：答案与实际上下文</summary><h4>生成答案</h4><pre>'+esc(p['generated_answer'])+'</pre><h4>实际入模上下文</h4><pre>'+esc(p['context_text'])+'</pre><p>拒答/资料不足表述检测：'+esc(x['refusal_heuristic'])+'（启发式，含部分拒答）。引用检查只核对记录 ID，不能代替语义支持核验。</p></details></td></tr>'
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GraphRAG 双模式质量与成本测评</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:1400px;margin:32px auto;padding:0 20px;color:#182230;background:#f5f7fb}section{background:white;padding:24px;margin:20px 0;border-radius:12px;overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #d9e0eb;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f9;padding:16px}summary{cursor:pointer;color:#1459a1}.notice{border-left:4px solid #d58800;padding:12px;background:#fff5d9}a{color:#1459a1}</style><h1>GraphRAG · 原文与仅图模式测评</h1><p>更新：2026-11-05 · 两组各 15 题已完成 · 同一语料、模型、索引及评分规则</p><p>原文模式提交原文和图记录；仅图模式保留相同图记录、移除全部原文块。两组实际图记录完全一致，5580 个索引文件内容哈希未变，没有新增索引文件。</p><div class="notice">仅图生成 token 减少 53.9%，核心问答耗时减少 28.7%，答案正确性由 0.5352 降至 0.4621。仅图 Compliance-F007 的 2 个引用 ID 未出现在对应实际上下文表中。启动耗时受到缓存与审计磁盘读取影响，日历时间差不能解释为稳定加速比。</div>'''
page+='<section><h2>四项质量指标</h2><table><tr><th>指标</th><th>原文 + 图</th><th>仅图</th><th>仅图减原文</th></tr>'+quality+'</table><p>各指标有效题数均为 15/15；均分按题宏平均，不合成总分。15 题属于诊断集，裁判与生成使用同一模型。</p></section>'
page+='<section><h2>分阶段模型用量与耗时</h2><table><tr>'+''.join('<th>'+x+'</th>' for x in ['模式','阶段','已保存 API 响应','输入 token','输出 token','总 token','核心问答秒','日历秒','API 秒之和','API 平均秒'])+'</tr>'+cost+'</table><p>qa_total 包含 qa_generation 和 qa_embedding，不重复相加。未记录与零严格区分；本地 BGE 评分没有 API 调用，但有本地计算，计入评分日历时间。完整 token 均取服务端 usage，库内估算另存。</p></section>'
page+='<section><h2>历史成本与可比条件</h2><p>历史索引流水线总耗时约 24.38 小时；历史保留缓存响应有服务端 usage，但不代表完整跨启动成本。生成聚合含缓存命中，不与留存响应重复相加。缺失项未记录，不重新构图补齐。两组生成温度 0、输出上限 4096、上下文上限 10000；裁判上限 8192、超时 240 秒。客户端生成与查询嵌入缓存绕过，保留现有就绪服务，不控制服务端内部缓存或共享负载。</p><p>实体和关系描述来自历史抽取与描述合并，社区报告来自历史图上下文汇总；均为原文派生记录，可能含引语，不是独立原始证据。</p></section>'
page+='<section><h2>逐题结果与实际上下文</h2><table><tr>'+''.join('<th>'+x+'</th>' for x in ['模式','生成状态','生成 token','问答秒','上下文相关性','证据召回','中文 ROUGE-L','答案正确性','引用 ID 检查'])+'</tr>'+rows+'</table></section><p>完整结果目录：'+esc(R)+'</p><p>已有旧版报告保留在 outputs/comparison_20261105/previous_reports。本页面为静态已完成结果，不自动刷新，不触发问答、评分或构图。</p></html>'
(P/'output/visualization/evaluation.html').write_text(page)
assert len([x for x in per if x['mode']=='original'])==15
assert page.count('：答案与实际上下文</summary>')==30
assert '未运行正式15题' not in text and '没有运行正式15题' not in text
print(json.dumps(dict(updated=['analysis/EVALUATION_ANALYSIS.md','output/visualization/evaluation.html'],qa_rows=len(per),backup=str(B),api_calls=0),ensure_ascii=False))
