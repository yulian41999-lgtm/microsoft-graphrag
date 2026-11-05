"""Control output-length failures using payloads already validated at concurrency one."""
import asyncio,hashlib,importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sustained',ROOT/'scripts/benchmark_concurrency_sustained.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
m=s.m;m.BUDGET=600
m.REPORT.update(benchmark_type='controlled_sustained_confirmation',logical_llm_call_limit=600,repeat_policy='fixed real payloads validated at concurrency one; no client response cache')

async def main():
 prior=Path(sys.argv[1]).resolve();screen=Path(sys.argv[2]).resolve()
 m.REPORT.update(previous_sustained=str(prior),screening_source=str(screen));m.save()
 while json.loads(prior.read_text())['state']=='running':await asyncio.sleep(5)
 data=json.loads(screen.read_text());initial=next(x for x in data['stages'] if x['label']=='extract_initial_c1')
 assert m.usable(initial)
 sample=json.loads((screen.parent/'samples.json').read_text());by_id={r['id']:r for r in sample}
 ids=[r['id'] for r in initial['items']]
 core=[by_id[i] for i in ids]
 # Interleave the same diverse workloads in the same order for every setting.
 items=[{**core[i%len(core)],'id':core[i%len(core)]['id']+'#'+str(i)} for i in range(64)]
 (m.OUT/'controlled_samples.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
 runs=[]
 for c in [8,6,4]:runs.append(await s.sustained(c,items,warmup=20,measure=90,prefix='controlled'))
 good=[r for r in runs if r['summary']['failed_chunks']==0 and r['summary']['request_errors']==0 and r['summary']['truncated_responses']==0]
 top=sorted(good,key=lambda r:r['summary']['valid_chunks_per_minute'],reverse=True)
 if len(top)>=2 and top[1]['summary']['valid_chunks_per_minute']>=top[0]['summary']['valid_chunks_per_minute']*.85:
  for r in sorted(top[:2],key=lambda r:r['concurrency']):runs.append(await s.sustained(r['concurrency'],items[:32],warmup=10,measure=60,prefix='controlled_repeat'))
 aggregate=[]
 for c in sorted({r['concurrency'] for r in runs}):
  summaries=[r['summary'] for r in runs if r['concurrency']==c];duration=sum(r['measurement_seconds'] for r in summaries)
  aggregate.append({'concurrency':c,'valid_chunks_per_minute':sum(r['measured_valid_chunks'] for r in summaries)*60/duration,'failed_chunks':sum(r['failed_chunks'] for r in summaries),'request_errors':sum(r['request_errors'] for r in summaries),'truncated_responses':sum(r['truncated_responses'] for r in summaries),'worst_run_p95_seconds':max(r['request_p95_seconds'] for r in summaries),'measurement_seconds':duration,'runs':len(summaries)})
 m.REPORT['aggregate']=aggregate
 valid=[r for r in aggregate if r['failed_chunks']==0 and r['request_errors']==0 and r['truncated_responses']==0 and r['worst_run_p95_seconds']<135]
 if valid:
  fastest=max(r['valid_chunks_per_minute'] for r in valid);chosen=min((r for r in valid if r['valid_chunks_per_minute']>=fastest*.95),key=lambda r:r['concurrency'])
  m.REPORT['recommendation']={'concurrent_requests':chosen['concurrency'],'selection':'smallest tested setting within 5% of maximum measured valid-chunk throughput, zero errors/truncations, p95 below 135s','scope':'current shared-server load and controlled real-data payloads'}
 # All embedding levels receive an identical warm-up first; repeat in reverse order.
 for c in [1,2,4,8,8,4,2,1]:await m.embedding_stage(c,core)
 embedding=[]
 for c in [1,2,4,8]:
  trials=[x for x in m.REPORT['embedding_stages'] if x['concurrency']==c]
  embedding.append({'concurrency':c,'median_texts_per_second':__import__('statistics').median(x['texts_per_second'] for x in trials),'failed_requests':sum(x['failed_requests'] for x in trials)})
 m.REPORT['embedding_aggregate']=embedding
 m.REPORT.update(state='complete',logical_llm_calls=len(m.CALLS),configuration_unchanged=hashlib.sha256((ROOT/'settings.yaml').read_bytes()).hexdigest()==m.CONFIG_HASH)
 assert m.REPORT['configuration_unchanged'];m.save()
 (m.OUT/'controlled_requests.json').write_text(json.dumps(m.CALLS,ensure_ascii=False,indent=2)+'\n')
 print('CONTROLLED_COMPLETE',m.OUT,json.dumps(m.REPORT.get('recommendation')),flush=True)

if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as exc:m.REPORT.update(state='error',error=type(exc).__name__);m.save();print('CONTROLLED_ERROR',type(exc).__name__,flush=True);raise SystemExit(1)
