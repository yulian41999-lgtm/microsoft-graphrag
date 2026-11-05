import sys,json,re,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'scripts'))
from compare_modes import usage_summary,atomic_json
R=P/'outputs/comparison_20261105';old=P/'outputs/evaluation15_20261102_094712'
report={}
for sub in ['scores','repair']:
    rows=[json.loads(l) for l in (old/sub/'judge_calls.jsonl').read_text().splitlines()]
    report[sub]=usage_summary(rows)
report['historical_qa']={'service_usage':'未记录','rows':len(json.loads((old/'predictions.json').read_text())),'core_seconds':sum(x['latency_seconds'] for x in json.loads((old/'predictions.json').read_text()))}
stats=json.loads((P/'output/stats.json').read_text());report['index_stats']=stats
text=(P/'logs/indexing-engine.log').read_text();matches=list(re.finditer(r'Metrics for ([^:]+): (\{.*?\n\})',text,re.S));last={}
for m in matches:
    try:last[m[1]]=json.loads(m[2])
    except ValueError:pass
report['historical_library_metrics']=last
report['historical_library_metrics_note']='Library cumulative usage from retained responses, includes cache hits; not actual new API-only usage. No repeated summation of cumulative snapshots.'
cache={};seen=set()
for directory in sorted((P/'cache').iterdir()):
    if not directory.is_dir():continue
    rows=[];files=0;errors=0;duplicates=0
    for f in directory.iterdir():
        if not f.is_file():continue
        files+=1
        try:
            value=json.loads(f.read_text());response=value.get('result',{}).get('response',{})
            if not isinstance(response,dict):continue
            if not response.get('usage'):continue
            ident=response.get('id') or hashlib.sha256(json.dumps(response,sort_keys=True).encode()).hexdigest()
            if ident in seen:duplicates+=1;continue
            seen.add(ident);rows.append(dict(response_received=True,usage=response['usage'],status='ok'))
        except Exception:errors+=1
    cache[directory.name]=dict(files=files,parse_errors=errors,duplicate_ids=duplicates,**usage_summary(rows))
report['retained_index_cache_responses']=cache
report['cache_scope_note']='Retained historical responses, deduplicated by response ID across cache directories; not all attempts or full historical consumption. Failed/noncached requests may be absent; API timing and complete historical calendar time 未记录.'
atomic_json(R/'historical_costs.json',report)
files=list((P/'output').glob('*.parquet'))+list((P/'output/lancedb').rglob('*'))
hashes={str(f.relative_to(P)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}
atomic_json(R/'index_content_hashes_before.json',hashes)
print('history complete',len(hashes),'index files',flush=True)
