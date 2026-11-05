"""Validate and summarize actual saved requests, costs and quality."""
import json,csv,re,hashlib,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'))
from compare_modes import usage_summary,atomic_json
R=P/'outputs/comparison_20261105'
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
def citations(row):
    answer=row['generated_answer']; groups=re.findall(r'\[Data:\s*([^\]]+)\]',answer)
    valid={k.lower():{str(x['id']) for x in v if x.get('in_context',True)} for k,v in row.get('context_data',{}).items()}
    checks=[];unparsed=[]
    for group in groups:
        found=re.findall(r'(Sources|Entities|Relationships|Reports|Claims)\s*\(([^)]+)\)',group,re.I)
        if not found:unparsed.append(group)
        for table,ids in found:
            for ident in ids.split(','):
                ident=ident.strip()
                if ident in ('+more','more'):continue
                checks.append(dict(table=table,id=ident,in_actual_context=ident in valid.get(table.lower(),set())))
    return dict(marker_count=len(groups),references=checks,invalid_reference_count=sum(not c['in_actual_context'] for c in checks),unparsed=unparsed,status='missing' if not groups else 'invalid_record_id' if any(not c['in_actual_context'] for c in checks) or unparsed else 'record_ids_valid',semantic_support='not automatically established by record-ID checks')

out={}; per=[];costrows=[]
for mode in ['original','graph_only']:
    d=R/('final_'+mode); pred=read(d/'predictions.json');m=read(d/'manifest.json');s=read(d/'scores/scores.json'); sc=read(d/'scoring_cost.json')
    assert len(pred)==15 and len(s['scores'])==15
    sm={x['id']:x for x in s['scores']}; qc=lines(d/'api_calls.jsonl');ec=lines(d/'embedding_calls.jsonl');jc=read(d/'judge_attempts.json')
    checks=[]
    for row in pred:
        c=citations(row); checks.append(dict(id=row['id'],**c))
        assert row['context_text'] in row['generation_messages'][0]['content']
        assert row['generation_messages'][1]['content']==row['question']
        if mode=='graph_only':
            assert not row.get('sources') and not row['context_data'].get('sources') and '-----Sources-----' not in row['context_text']
        usage=usage_summary([x for x in qc if x['question_id']==row['id']]);item=dict(mode=mode,id=row['id'],question=row['question'],answer=row['generated_answer'],status=row['status'],refusal_heuristic=row['refusal_heuristic'],citation_status=c['status'],invalid_reference_count=c['invalid_reference_count'],context_token_estimate=row['context_token_estimate'],latency_seconds=row['latency_seconds'],retrieval_seconds=row['retrieval_seconds'],**{k:usage[k] for k in ['saved_api_responses','prompt_tokens','completion_tokens','total_tokens','api_seconds_sum']})
        item.update({k:sm[row['id']]['metrics'][k].get('score') for k in sm[row['id']]['metrics']})
        for prefix,subset in [('judge',[x for x in jc if x.get('task','').startswith(row['id']+'/')]),('embedding',[x for x in ec if x.get('input')==[row['question']]])]:
            u=usage_summary(subset)
            item.update({prefix+'_'+k:u[k] for k in ['saved_api_responses','prompt_tokens','completion_tokens','total_tokens','api_seconds_sum','failed_attempts']})
        per.append(item)
    atomic_json(d/'citation_checks.json',checks)
    out[mode]=dict(manifest=m,scoring=sc,quality=s['summary'],status_counts=m['statuses'],refusal_heuristic_n=sum(x['refusal_heuristic'] for x in pred),citation_status_counts={k:sum(x['status']==k for x in checks) for k in set(x['status'] for x in checks)},actual_context_sections={k:sum(len(row['context_data'].get(k,[])) for row in pred) for k in ['sources','entities','relationships','reports','claims']})
    for stage,rows,core,calendar in [('qa_total',qc+ec,m['core_qa_seconds'],m['calendar_seconds']),('qa_generation',qc,None,None),('qa_embedding',ec,None,None),('scoring_judge',jc,None,sc['calendar_seconds'])]:
        costrows.append(dict(mode=mode,stage=stage,core_qa_seconds=core,calendar_seconds=calendar,**usage_summary(rows)))
    # Local scoring embedding executes in-process, not through an API.
    costrows.append(dict(mode=mode,stage='scoring_local_embedding',saved_api_responses=0,prompt_tokens=None,completion_tokens=0,total_tokens=None,api_seconds_sum=0,note='Local BGE computation; input tokenizer usage and separate compute timing 未记录; included in scoring calendar time'))
for mode,details in out.items():
    d=R/('final_'+mode)
    report=['# '+mode+' 测评汇总','','## 质量','']
    for name,metric in details['quality']['overall']['metrics'].items():report.append(f"- {name}：{metric['mean']}；有效 {metric['valid_n']} / {metric['expected_n']}；失败 {metric['failed_n']}。")
    report+=['','## 成本','']
    for c in costrows:
        if c['mode']==mode:report.append('- '+c['stage']+'：'+json.dumps(c,ensure_ascii=False))
    report+=['','答题状态：'+json.dumps(details['status_counts'],ensure_ascii=False),'','实际上下文、原始回答和入模请求见 predictions.json；API 尝试见各 calls 日志；引用记录 ID 检查见 citation_checks.json。图描述为历史派生记录；详细边界与对照条件见上级 REPORT.md 和 AUDIT.md。']
    (d/'REPORT.md').write_text('\n'.join(report)+'\n')
a,b=out['original'],out['graph_only'];am,bm=a['manifest'],b['manifest']
for k in ['generation_model','embedding_model','generation_parameters','index_identity','prompt_sha256','community_level']:assert am[k]==bm[k],k
assert read(R/'final_original/scores/scores.json')['profile']==read(R/'final_graph_only/scores/scores.json')['profile']
assert [x['id'] for x in read(R/'final_original/predictions.json')]==[x['id'] for x in read(R/'final_graph_only/predictions.json')]
graph_differences=[]
for x,y in zip(read(R/'final_original/predictions.json'),read(R/'final_graph_only/predictions.json')):
    for k in ['entities','relationships','reports','claims']:
        if x['context_data'].get(k,[])!=y['context_data'].get(k,[]):graph_differences.append(dict(id=x['id'],section=k))
delta={}
for k in ['prompt_tokens','completion_tokens','total_tokens']:
    av,bv=am['cost'][k],bm['cost'][k];delta[k]=dict(original=av,graph_only=bv,saved=av-bv if av is not None and bv is not None else None,saved_fraction=(av-bv)/av if av else None)
for k in ['core_qa_seconds','calendar_seconds']:
    av,bv=am[k],bm[k];delta[k]=dict(original=av,graph_only=bv,saved=av-bv,saved_fraction=(av-bv)/av)
for k in ['api_seconds_sum','api_seconds_average']:
    av,bv=am['cost'][k],bm['cost'][k];delta[k]=dict(original=av,graph_only=bv,saved=av-bv,saved_fraction=(av-bv)/av)
for k in ['prompt_tokens','completion_tokens','total_tokens']:
    av=am['cost'][k]+am['retrieval_embedding_cost'][k];bv=bm['cost'][k]+bm['retrieval_embedding_cost'][k]
    delta['qa_total_'+k]=dict(original=av,graph_only=bv,saved=av-bv,saved_fraction=(av-bv)/av if av else 0)
for k in ['prompt_tokens','completion_tokens','total_tokens']:
    av,bv=a['scoring']['cost'][k],b['scoring']['cost'][k]
    delta['scoring_'+k]=dict(original=av,graph_only=bv,saved=av-bv,saved_fraction=(av-bv)/av if av else 0)
av,bv=a['scoring']['calendar_seconds'],b['scoring']['calendar_seconds']
delta['scoring_calendar_seconds']=dict(original=av,graph_only=bv,saved=av-bv,saved_fraction=(av-bv)/av)
qd={k:dict(original=a['quality']['overall']['metrics'][k],graph_only=b['quality']['overall']['metrics'][k],change=b['quality']['overall']['metrics'][k]['mean']-a['quality']['overall']['metrics'][k]['mean']) for k in a['quality']['overall']['metrics']}
hashes=read(R/'index_content_hashes_before.json');changed=[f for f,h in hashes.items() if not (P/f).is_file() or hashlib.sha256((P/f).read_bytes()).hexdigest()!=h]
current={str(f.relative_to(P)) for f in list((P/'output').glob('*.parquet'))+list((P/'output/lancedb').rglob('*')) if f.is_file()}
new_files=sorted(current-set(hashes));assert not changed and not new_files,(changed,new_files)
history=read(R/'historical_costs.json')
validation=read(R/'original/manifest.json');validation['run_role']='recorder_validation_preflight';validation['cost']=usage_summary(lines(R/'original/api_calls.jsonl'))
summary=dict(new_construction=dict(executed=False,model_api_responses=0,model_tokens=0),comparability=dict(same_model=True,same_generation_parameters=True,same_prompt=True,same_index=True,same_scoring_profile=True,client_caches_bypassed=True,fresh_process_per_mode=True,graph_records_identical=not graph_differences,server_cache_controlled=False,os_cache_controlled=False),graph_record_differences=graph_differences,modes=out,cost_rows=costrows,qa_savings=delta,quality_change=qd,historical=history,index_verification=dict(checked_files=len(hashes),changed_files=changed,new_files=new_files),validation_run=validation,limitations=['15-question diagnostic sample; same model judge','Sequential runs cannot control shared service load or server prefix cache; historical audit disk reads overlapped part of original QA, calendar savings are not controlled startup speedup','Graph-only preserves graph record budget and omits sources; source allocation left unused','Citation IDs checked, semantic citation entailment needs manual inspection','Historical retained cache usage is a lower bound over retained responses, not full historical cost'])
atomic_json(R/'summary.json',summary)
with (R/'per_question.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(per[0]));w.writeheader();w.writerows(per)
atomic_json(R/'per_question.json',per)
text=['# 原文与仅图模式测评报告','','两组复用同一份现有图谱、向量索引、1,700 篇语料与 15 题冻结题库；未重新构图或重建索引。原文模式使用原文与图记录混合上下文。','',f'索引校验：{len(hashes)} 个文件内容哈希一致。实际上下文及完整生成请求见各模式 predictions.json，逐次响应与服务端 usage 见 api_calls.jsonl、embedding_calls.jsonl 和 judge_http_calls.jsonl。','','## 质量','']
labels={'context_relevancy':'上下文相关性','evidence_recall':'证据召回','rouge_l':'中文 ROUGE-L','answer_correctness':'答案正确性'}
for k,v in qd.items():text.append(f"- {labels[k]}：原文 {v['original']['mean']:.4f}，仅图 {v['graph_only']['mean']:.4f}，变化 {v['change']:+.4f}；有效题 {v['original']['valid_n']}/{v['graph_only']['valid_n']}。")
text += ['',f'两组图记录核验：差异 {len(graph_differences)} 项；详细列表见 summary.json。']
text+=['','## 问答与评分开销','']
for k,v in delta.items():text.append(f"- {k}：原文 {v['original']:.3f}，仅图 {v['graph_only']:.3f}；节省 {v['saved']:.3f}（{v['saved_fraction']:.1%}）。负数表示仅图增加开销。")
text+=['','## 各阶段成本','']
for row in costrows:
    text.append(f"- {row['mode']} / {row['stage']}：已保存 API 响应 {row['saved_api_responses']}；输入/输出/总 token {row.get('prompt_tokens')} / {row.get('completion_tokens')} / {row.get('total_tokens')}；API 耗时之和 {row.get('api_seconds_sum')} 秒；平均 {row.get('api_seconds_average')} 秒；日历耗时 {row.get('calendar_seconds')} 秒。")
text+=['','qa_total 已包含 qa_generation 与 qa_embedding，不重复相加。null / None 均表示未记录或不适用，不能作为零消耗；本地评分嵌入 API 响应为 0，但仍执行本地计算。评分日历耗时包含模型加载和本地 BGE 计算。问答核心耗时为逐题检索与生成累计，不含引擎初始化和题间写盘；日历耗时包含这些步骤。API 耗时包含失败尝试，除以全部尝试数得到平均耗时。','','## 状态与引用','']
for mode,x in out.items():text.append(f"- {mode}：答题状态 {x['status_counts']}；含拒答/不足表述 {x['refusal_heuristic_n']} 题（启发式，可能是部分拒答）；引用 ID 检查 {x['citation_status_counts']}；实际图与原文记录总数 {x['actual_context_sections']}。")
text+=['','引用检查验证引用 ID 是否出现在实际上下文，不冒称已验证每条引文的语义支持。仅图模式的 Sources 记录及原文块均为零；图描述和社区报告仍为从原文派生的历史模型产物，可能含引语。当前安装版本 create_community_reports 使用实体、关系与可选 claims 的图上下文生成报告，不直接读取原文块。','','## 历史构图与历史评分','','历史索引流水线记录总耗时 87769.77694320679 秒（约 24.38 小时）；完整跨启动日历耗时未记录。库层聚合与保留缓存响应的 usage 单列在 historical_costs.json，不将含缓存的累计统计当作新 API 消耗；未保留的尝试无法补齐。历史 QA 服务端 token 未记录，故两组均重新运行；历史评分及修复的消耗另列，未混入新评分。','','## 解释边界','','上下文预算上限均为 10000 个库内 tokenizer tokens，输出上限均为 4096；图模式保留原图预算比例并删除全部原文块，原文预算空置。两组实体、关系和报告记录另行逐题核验是否一致，应以实际 token 差值为准。两组裁判规则一致，输出上限统一为 8192，以避免历史评分截断；所有格式失败响应和重试均计入成本。','', '两组均为新进程，客户端生成及查询嵌入缓存均绕过，顺序运行且共享现有就绪服务，不控制服务端前缀缓存或其他用户负载。历史审计的磁盘读取与原文组部分重叠；原文组与仅图组的初始化/题间写盘开销分别约 48.1 / 7.5 秒，启动开销并非受控冷启动对照，整体日历时间差不得解读为仅图模式的稳定加速比。核心问答耗时和 API 耗时单列。因此时间差属于本次观察值，不能当作稳定加速比。15 题是诊断集，裁判与生成同模型，不足以支持普遍质量结论。','','初次记录器验证运行的消耗单列 validation_run，不计入最终组比较；未新增其他付费预检。审计分类和复现入口见 AUDIT.md。']
text += ['', '## 历史留存响应明细', '']
for stage,c in history['retained_index_cache_responses'].items():
    text.append(f"- {stage}：保留响应 {c['saved_api_responses']}；输入 {c['prompt_tokens']}、输出 {c['completion_tokens']}、总计 {c['total_tokens']} tokens；完整 API 耗时未记录。")
for stage in ['scores','repair']:
    c=history[stage];text.append(f"- 历史 {stage}：响应 {c['saved_api_responses']}；输入 {c['prompt_tokens']}、输出 {c['completion_tokens']}、总计 {c['total_tokens']} tokens；耗时未记录。")
text += ['', '## 记录器验证消耗', '', '验证运行（不纳入两组质量对比）：'+json.dumps(validation['cost'],ensure_ascii=False), '', '验证阶段查询嵌入沿用旧检索包装器，实际 API 响应与 usage 未单独记录，不能冒称零；两组正式运行已完整记录查询嵌入。']
text += ['', '以上历史缓存为留存范围小计，可能跨多次启动；不与包含缓存命中的库层累计统计相加。缺失的历史失败调用或未留存响应不补跑。']
(R/'REPORT.md').write_text('\n'.join(text)+'\n')
print(json.dumps(dict(qa_savings=delta,quality_change=qd,index_files=len(hashes)),ensure_ascii=False,indent=2))
