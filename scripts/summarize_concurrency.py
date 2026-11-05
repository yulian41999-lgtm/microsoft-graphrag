"""Create an auditable summary after all bounded concurrency tests finish."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
reports={}
for p in sorted((ROOT/'outputs').glob('concurrency_*/results.json')):
 d=json.loads(p.read_text());reports[d.get('benchmark_type','screening')]=(p,d)
required=['screening','sustained_confirmation','controlled_sustained_confirmation']
if any(t not in reports or reports[t][1]['state']!='complete' for t in required):raise SystemExit('Benchmarks have not all completed')
screen_path,screen=reports['screening'];controlled_path,controlled=reports['controlled_sustained_confirmation']
requests=json.loads((controlled_path.parent/'controlled_requests.json').read_text())
rows=[]
for c in sorted({s['concurrency'] for s in controlled['stages']}):
 stages=[s for s in controlled['stages'] if s['concurrency']==c]
 summaries=[s['summary'] for s in stages];labels={s['label'] for s in stages}
 times=sorted(r['seconds'] for r in requests if r['stage'] in labels)
 def p95(xs):
  pos=(len(xs)-1)*.95;a=int(pos);b=min(a+1,len(xs)-1);return xs[a]+(xs[b]-xs[a])*(pos-a)
 measure=sum(s['measurement_seconds'] for s in summaries);elapsed=sum(s['elapsed_with_drain_seconds'] for s in summaries)
 completed=sum(s['completed_chunks']-s['failed_chunks'] for s in summaries)
 samples=[x for s in stages for x in s['server_samples']]
 rows.append({'concurrency':c,'steady_valid_chunks_per_minute':sum(s['measured_valid_chunks'] for s in summaries)*60/measure,'amortized_valid_chunks_per_minute_including_drain':completed*60/elapsed,'measurement_seconds':measure,'runs':len(stages),'completed_valid_chunks':completed,'request_p95_seconds':p95(times),'failed_chunks':sum(s['failed_chunks'] for s in summaries),'request_errors':sum(s['request_errors'] for s in summaries),'truncated_responses':sum(s['truncated_responses'] for s in summaries),'server_running_max':max(x['metrics'].get('num_requests_running',0) for x in samples),'server_waiting_max':max(x['metrics'].get('num_requests_waiting',0) for x in samples)})
# The first embedding group is retained as warm-up, not counted as a warm throughput trial.
embedding=[]
for c in [1,2,4,8]:
 tests=[r for r in controlled['embedding_stages'][1:] if r['concurrency']==c]
 embedding.append({'concurrency':c,'warm_trials':len(tests),'median_texts_per_second':statistics.median(r['texts_per_second'] for r in tests),'failed_requests':sum(r['failed_requests'] for r in tests)})
good=[r for r in embedding if r['failed_requests']==0];top=max(r['median_texts_per_second'] for r in good)
bge=min(r['concurrency'] for r in good if r['median_texts_per_second']>=top*.95)
production_hash=hashlib.sha256((ROOT/'settings.yaml').read_bytes()).hexdigest()
assert all(reports[k][1]['production_config_sha256']==production_hash for k in required)
result={'status':'complete','recommended_concurrent_requests':controlled.get('recommendation',{}).get('concurrent_requests'),'recommendation_scope':'current shared-server load; tested levels 1,2,4,6,8; controlled sustained comparison 4,6,8','selection':'lowest tested concurrency within 5% of fastest successful sustained throughput, zero errors/truncations on controlled payloads','controlled_results':rows,'embedding_recommended_http_concurrency':bge,'embedding_warm_results':embedding,'embedding_batch_size':4,'production_configuration_changed':False,'full_index_started':False,'source_reports':{k:str(reports[k][0]) for k in required},'logical_llm_calls':sum(reports[k][1].get('logical_llm_calls',0) for k in required),'output_length_issue':{'sample':'DOC001566:1','concurrencies':[4,8],'limit':4096,'description':'The same unseen payload reached the output cap at both settings; not evidence that high concurrency caused truncation.'}}
p=ROOT/'outputs/concurrency_recommendation.json';p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
