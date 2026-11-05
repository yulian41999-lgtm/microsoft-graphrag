"""Confirm screened settings with replenished workers and a measured steady window."""
import asyncio,hashlib,importlib.util,json,random,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('screening',ROOT/'scripts/benchmark_concurrency.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.BUDGET=600
m.REPORT.update(benchmark_type='sustained_confirmation',logical_llm_call_limit=600,warmup_seconds=20,measurement_seconds=90,max_chunks_per_setting=64)


def pool():
 tk=m.get_tokenizer(encoding_model=m.CFG.chunking.encoding_model)
 chunker=m.create_chunker(m.CFG.chunking,tk.encode,tk.decode);rows=[]
 for line in (ROOT/'input/banking.jsonl').read_text().splitlines():
  d=json.loads(line)
  for i,text in enumerate(m.chunk_document({**d,'raw_data':d},chunker,m.CFG.chunking.prepend_metadata)):
   size=len(tk.encode(text))
   if size>=120:rows.append({'id':d['id']+':'+str(i),'text':text,'tokens':size})
 rows.sort(key=lambda r:(r['tokens'],r['id']));selected=[];seen=set()
 for i in range(64):
  pos=int((i+.5)*len(rows)/64)
  for offset in range(len(rows)):
   row=rows[(pos+offset)%len(rows)]
   if row['id'].split(':')[0] not in seen:
    selected.append(row);seen.add(row['id'].split(':')[0]);break
 random.Random(20261030).shuffle(selected)
 (m.OUT/'samples.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
 return selected


async def sustained(c,items,warmup=20,measure=90,prefix="sustained"):
 label=prefix+'_c'+str(c)
 data={'kind':'extract','concurrency':c,'label':label,'items':[],'server_samples':[]}
 m.REPORT['stages'].append(data)
 started=time.monotonic();deadline=started+warmup+measure;next_item=0;done=False;call_begin=len(m.CALLS)
 class Model(m.TimedModel):
  async def completion_async(self,**kwargs):
   index=len(m.CALLS);a=time.monotonic()
   try:return await super().completion_async(**kwargs)
   finally:
    if len(m.CALLS)>index:m.CALLS[index].update(started_relative=a-started,finished_relative=time.monotonic()-started)
 model=Model(label)
 async def observe():
  while not done:
   data['server_samples'].append(await asyncio.to_thread(m.snapshot));m.save();await asyncio.sleep(3)
 async def worker():
  nonlocal next_item
  while time.monotonic()<deadline and next_item<len(items):
   if sum(r['status']!='ok' for r in data['items'])>=2:break
   i=next_item;next_item+=1;item=items[i];m.CURRENT.set(item['id']);a=time.monotonic();errors=[]
   row={'id':item['id'],'input_tokens_o200k':item['tokens'],'started_relative':a-started}
   try:
    extractor=m.GraphExtractor(model,(ROOT/m.CFG.extract_graph.prompt).read_text(),m.CFG.extract_graph.max_gleanings,on_error=lambda *args:errors.append('ExtractionError'))
    es,rs=await extractor(item['text'],m.CFG.extract_graph.entity_types,item['id'])
    row.update(entities=len(es),relationships=len(rs),status='ok' if not errors and len(es)>0 and set(es['type'])<=set(m.CFG.extract_graph.entity_types) else 'error')
   except Exception as exc:row.update(status='error',error=type(exc).__name__)
   row.update(seconds=time.monotonic()-a,finished_relative=time.monotonic()-started)
   data['items'].append(row);m.save()
 print('SUSTAINED_START',c,flush=True)
 observer=asyncio.create_task(observe());await asyncio.gather(*(worker() for _ in range(c)))
 elapsed=time.monotonic()-started;done=True;await observer
 end=min(elapsed,warmup+measure);duration=max(0,end-warmup)
 measured=[r for r in data['items'] if warmup<=r['finished_relative']<=end]
 calls=m.CALLS[call_begin:];window_calls=[r for r in calls if warmup<=r['finished_relative']<=end]
 data['summary']={'elapsed_with_drain_seconds':round(elapsed,3),'measurement_seconds':round(duration,3),'submitted_chunks':next_item,'completed_chunks':len(data['items']),'measured_valid_chunks':sum(r['status']=='ok' for r in measured),'valid_chunks_per_minute':round(sum(r['status']=='ok' for r in measured)*60/duration,4) if duration else 0,'failed_chunks':sum(r['status']!='ok' for r in data['items']),'logical_requests':len(calls),'request_errors':sum(r['status']!='ok' for r in calls),'truncated_responses':sum(r.get('finish_reason')=='length' for r in calls),'request_p50_seconds':m.percentile([r['seconds'] for r in calls],.5),'request_p95_seconds':m.percentile([r['seconds'] for r in calls],.95),'measured_output_tokens_per_second':round(sum(r.get('completion_tokens',0) for r in window_calls)/duration,4) if duration else 0,'observed_server_waiting_max':max((r['metrics'].get('num_requests_waiting',0) for r in data['server_samples']),default=0)}
 print('SUSTAINED_DONE',c,json.dumps(data['summary']),flush=True);m.save();return data


async def main():
 source=Path(sys.argv[1]).resolve();m.REPORT['screening_source']=str(source);m.save()
 while True:
  screen=json.loads(source.read_text())
  if screen['state']!='running':break
  await asyncio.sleep(5)
 if screen['state']!='complete':raise RuntimeError('ScreeningDidNotComplete')
 valid=[s for s in screen['stages'] if s['label'].startswith('extract_initial_') and m.usable(s)]
 choices=sorted(sorted(valid,key=lambda s:s['summary']['valid_items_per_minute'],reverse=True)[:3],key=lambda s:s['concurrency'],reverse=True)
 items=pool();m.REPORT['tested_concurrencies']=[s['concurrency'] for s in choices]
 results=[]
 for s in choices:results.append(await sustained(s['concurrency'],items))
 good=[s for s in results if s['summary']['failed_chunks']==0 and s['summary']['request_errors']==0 and s['summary']['truncated_responses']==0]
 top=sorted(good,key=lambda s:s['summary']['valid_chunks_per_minute'],reverse=True)
 if len(top)>=2 and top[1]['summary']['valid_chunks_per_minute']>=top[0]['summary']['valid_chunks_per_minute']*.85:
  for s in sorted(top[:2],key=lambda s:s['concurrency']):results.append(await sustained(s['concurrency'],items[:32],warmup=10,measure=60,prefix='repeat'))
 aggregate=[]
 for c in sorted({s['concurrency'] for s in results}):
  runs=[s['summary'] for s in results if s['concurrency']==c]
  seconds=sum(s['measurement_seconds'] for s in runs)
  aggregate.append({'concurrency':c,'measured_valid_chunks_per_minute':sum(s['measured_valid_chunks'] for s in runs)*60/seconds if seconds else 0,'measurement_seconds':seconds,'failed_chunks':sum(s['failed_chunks'] for s in runs),'request_errors':sum(s['request_errors'] for s in runs),'truncated_responses':sum(s['truncated_responses'] for s in runs),'worst_run_p95_seconds':max(s['request_p95_seconds'] for s in runs),'repeats':len(runs)})
 m.REPORT['aggregate']=aggregate
 acceptable=[r for r in aggregate if r['failed_chunks']==0 and r['request_errors']==0 and r['truncated_responses']==0 and r['worst_run_p95_seconds']<135]
 if acceptable:
  best=max(r['measured_valid_chunks_per_minute'] for r in acceptable)
  chosen=min((r for r in acceptable if r['measured_valid_chunks_per_minute']>=best*.95),key=lambda r:r['concurrency'])
  m.REPORT['recommendation']={'concurrent_requests':chosen['concurrency'],'criteria':'lowest setting within 5% of fastest measured sustained valid-chunk throughput, zero errors/truncation, p95 under 135 seconds','scope':'tested settings under current shared-server load; not a universal optimum'}
 m.REPORT.update(state='complete',logical_llm_calls=len(m.CALLS),configuration_unchanged=hashlib.sha256((ROOT/'settings.yaml').read_bytes()).hexdigest()==m.CONFIG_HASH)
 assert m.REPORT['configuration_unchanged'];m.save()
 (m.OUT/'sustained_requests.json').write_text(json.dumps(m.CALLS,ensure_ascii=False,indent=2)+'\n')
 print('SUSTAINED_COMPLETE',m.OUT,json.dumps(m.REPORT.get('recommendation')),flush=True)

if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as exc:m.REPORT.update(state='error',error=type(exc).__name__);m.save();print('SUSTAINED_ERROR',type(exc).__name__,flush=True);raise SystemExit(1)
