"""Bounded, isolated concurrency benchmark; never changes production configuration."""
import asyncio,contextvars,hashlib,json,logging,os,re,statistics,time,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT);os.umask(0o077)
import pandas as pd
from graphrag.config.load_config import load_config
from graphrag.index.operations.extract_graph.graph_extractor import GraphExtractor
from graphrag.index.operations.summarize_communities.community_reports_extractor import CommunityReportsExtractor
from graphrag.index.workflows.create_base_text_units import chunk_document
from graphrag_chunking.chunker_factory import create_chunker
from graphrag.tokenizer.get_tokenizer import get_tokenizer
from graphrag_llm.completion import create_completion
for name in ['graphrag','litellm','LiteLLM']:
 logger=logging.getLogger(name);logger.addHandler(logging.NullHandler());logger.propagate=False
CFG=load_config(ROOT)
CONFIG_HASH=hashlib.sha256((ROOT/'settings.yaml').read_bytes()).hexdigest()
OUT=ROOT/'outputs'/('concurrency_'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True,exist_ok=False)
CURRENT=contextvars.ContextVar('benchmark_item',default='unknown')
BUDGET=200
REPORT={'state':'running','started_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'output':str(OUT),'stages':[], 'logical_llm_call_limit':BUDGET,'production_config_sha256':CONFIG_HASH,'client_cache':False,'benchmark_retry':False,'production_configuration_changed':False,'full_index_started':False}
CALLS=[]

def save():
 p=OUT/'results.json';t=p.with_suffix('.tmp');t.write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,allow_nan=False)+'\n');t.replace(p)

def percentile(xs,p):
 if not xs:return None
 xs=sorted(xs);position=(len(xs)-1)*p;lo=int(position);hi=min(lo+1,len(xs)-1)
 return round(xs[lo]+(xs[hi]-xs[lo])*(position-lo),4)

def snapshot():
 model=CFG.get_completion_model_config(CFG.extract_graph.completion_model_id)
 url=model.api_base.rstrip('/').removesuffix('/v1')+'/metrics'
 wanted=['num_requests_running','num_requests_waiting','kv_cache_usage_perc','gpu_cache_usage_perc','generation_tokens_total','prompt_tokens_total','request_success_total']
 result={'at':time.time(),'metrics':{}}
 try:
  req=urllib.request.Request(url,headers={'Authorization':'Bearer '+model.api_key})
  with urllib.request.urlopen(req,timeout=4) as response:body=response.read(2_000_000).decode()
  for line in body.splitlines():
   if line.startswith('#'):continue
   for name in wanted:
    if re.match(r'(?:vllm:)?'+name+r'(?:\{|\s)',line):
     try:result['metrics'][name]=result['metrics'].get(name,0)+float(line.rsplit(' ',1)[-1])
     except ValueError:pass
 except Exception as exc:result['error']=type(exc).__name__
 return result

class TimedModel:
 def __init__(self,stage):
  self.stage=stage
  c=CFG.get_completion_model_config(CFG.extract_graph.completion_model_id).model_copy(deep=True)
  c.retry=None;c.call_args=dict(c.call_args,num_retries=0)
  self.delegate=create_completion(c,cache=None)
  assert self.delegate._cache is None and self.delegate._retrier is None
 async def completion_async(self,**kwargs):
  if len(CALLS)>=BUDGET:raise RuntimeError('BenchmarkCallBudgetExceeded')
  row={'stage':self.stage,'item':CURRENT.get(),'status':'running'};CALLS.append(row)
  start=time.monotonic()
  try:
   response=await self.delegate.completion_async(**kwargs)
   reason=response.choices[0].finish_reason
   row.update(finish_reason=reason,prompt_tokens=response.usage.prompt_tokens if response.usage else 0,completion_tokens=response.usage.completion_tokens if response.usage else 0)
   if reason!='stop':raise RuntimeError('IncompleteCompletion')
   row['status']='ok'
   with (OUT/'responses.jsonl').open('a') as f:f.write(json.dumps({'stage':self.stage,'item':CURRENT.get(),'content':response.content},ensure_ascii=False)+'\n')
   return response
  except Exception as exc:
   row.update(status='error',error=type(exc).__name__);raise
  finally:
   row['seconds']=round(time.monotonic()-start,4)
   with (OUT/'requests.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')

def prepare_samples():
 tk=get_tokenizer(encoding_model=CFG.chunking.encoding_model)
 ch=create_chunker(CFG.chunking,tk.encode,tk.decode)
 pool=[]
 for line in (ROOT/'input/banking.jsonl').read_text().splitlines():
  d=json.loads(line)
  for i,text in enumerate(chunk_document({**d,'raw_data':d},ch,CFG.chunking.prepend_metadata)):
   size=len(tk.encode(text))
   if size>=120:pool.append({'id':d['id']+':'+str(i),'text':text,'tokens':size})
 pool.sort(key=lambda x:(x['tokens'],x['id']))
 selected=[];used=set()
 for i in range(24):
  pos=int((i+0.5)*len(pool)/24)
  for delta in range(len(pool)):
   row=pool[(pos+delta)%len(pool)]
   if row['id'].split(':')[0] not in used:
    selected.append(row);used.add(row['id'].split(':')[0]);break
 (OUT/'samples.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
 REPORT['sample_stats']={'eligible_chunks':len(pool),'selected_chunks':len(selected),'tokens':[r['tokens'] for r in selected]}
 return selected

def report_samples(count=16):
 base=ROOT/'smoke/output'
 entities=pd.read_parquet(base/'entities.parquet');relationships=pd.read_parquet(base/'relationships.parquet');communities=pd.read_parquet(base/'communities.parquet')
 rows=[]
 for r in communities.sort_values(['size','community'],ascending=[False,True]).to_dict('records'):
  es=entities[entities['id'].isin(list(r['entity_ids']))]
  rs=relationships[relationships['id'].isin(list(r['relationship_ids']))]
  text='Entities\n'+es[['human_readable_id','title','description']].to_csv(index=False)+'\nRelationships\n'+rs[['human_readable_id','source','target','description']].to_csv(index=False)
  if len(es)>0:rows.append({'id':'community:'+str(r['community']),'text':text,'tokens':len(get_tokenizer(encoding_model=CFG.chunking.encoding_model).encode(text))})
 return rows[:count]

async def stage(kind,concurrency,items,label):
 data={'kind':kind,'concurrency':concurrency,'label':label,'n':len(items),'items':[],'server_samples':[]}
 REPORT['stages'].append(data);model=TimedModel(label);sem=asyncio.Semaphore(concurrency)
 begin=len(CALLS);done=False
 async def monitor():
  while not done:
   data['server_samples'].append(await asyncio.to_thread(snapshot))
   save();await asyncio.sleep(3)
 async def worker(item):
  async with sem:
   CURRENT.set(item['id']);started=time.monotonic();errors=[]
   row={'id':item['id'],'input_tokens_o200k':item['tokens']}
   try:
    if kind=='extract':
     extractor=GraphExtractor(model,(ROOT/CFG.extract_graph.prompt).read_text(),CFG.extract_graph.max_gleanings,on_error=lambda *args:errors.append('ExtractionError'))
     es,rs=await extractor(item['text'],CFG.extract_graph.entity_types,item['id'])
     row.update(entities=len(es),relationships=len(rs))
     valid=not errors and len(es)>0 and set(es['type'])<=set(CFG.extract_graph.entity_types)
    else:
     extractor=CommunityReportsExtractor(model,(ROOT/CFG.community_reports.graph_prompt).read_text(),CFG.community_reports.max_length,on_error=lambda *args:errors.append('ReportError'))
     result=await extractor(item['text']);valid=not errors and result.structured_output is not None and bool(result.structured_output.findings)
     row['findings']=len(result.structured_output.findings) if result.structured_output else 0
    row['status']='ok' if valid else 'error'
   except Exception as exc:row.update(status='error',error=type(exc).__name__)
   row['seconds']=round(time.monotonic()-started,4);data['items'].append(row)
   print('ITEM',label,len(data['items']),len(items),row['status'],flush=True);save()
 started=time.monotonic();observer=asyncio.create_task(monitor())
 print('STAGE_START',label,'concurrency',concurrency,'items',len(items),flush=True)
 await asyncio.gather(*(worker(item) for item in items))
 seconds=time.monotonic()-started;done=True;await observer
 calls=CALLS[begin:];success=sum(r['status']=='ok' for r in data['items'])
 waits=[s['metrics'].get('num_requests_waiting',0) for s in data['server_samples']]
 data['summary']={'seconds':round(seconds,3),'successful_items':success,'failed_items':len(items)-success,'valid_items_per_minute':round(success*60/seconds,4),'requests':len(calls),'request_errors':sum(r['status']!='ok' for r in calls),'truncated_responses':sum(r.get('finish_reason')=='length' for r in calls),'prompt_tokens':sum(r.get('prompt_tokens',0) for r in calls),'completion_tokens':sum(r.get('completion_tokens',0) for r in calls),'output_tokens_per_second':round(sum(r.get('completion_tokens',0) for r in calls)/seconds,4),'request_p50_seconds':percentile([r['seconds'] for r in calls],0.5),'request_p95_seconds':percentile([r['seconds'] for r in calls],0.95),'observed_server_waiting_max':max(waits,default=0)}
 print('STAGE_DONE',label,json.dumps(data['summary']),flush=True);save();return data

async def embedding_stage(concurrency,samples):
 import numpy as np
 name='embedding_c'+str(concurrency);sem=asyncio.Semaphore(concurrency);rows=[]
 payloads=[[samples[(i*4+j)%len(samples)]['text'] for j in range(4)] for i in range(12)]
 url='http://127.0.0.1:18086/v1/embeddings'
 def request(texts):
  req=urllib.request.Request(url,data=json.dumps({'model':'bge-m3','input':texts}).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=180) as response:data=json.load(response)
  vectors=np.array([r['embedding'] for r in data['data']])
  if vectors.shape!=(4,1024) or not np.isfinite(vectors).all() or not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=.01):raise ValueError('InvalidEmbeddings')
 async def worker(texts):
  async with sem:
   start=time.monotonic();row={}
   try:await asyncio.to_thread(request,texts);row['status']='ok'
   except Exception as exc:row.update(status='error',error=type(exc).__name__)
   row['seconds']=time.monotonic()-start;rows.append(row)
 start=time.monotonic();await asyncio.gather(*(worker(p) for p in payloads));elapsed=time.monotonic()-start
 data={'kind':'embedding','label':name,'concurrency':concurrency,'batch_size':4,'requests':12,'failed_requests':sum(r['status']!='ok' for r in rows),'texts_per_second':sum(r['status']=='ok' for r in rows)*4/elapsed,'seconds':elapsed,'request_p95_seconds':percentile([r['seconds'] for r in rows],.95)}
 REPORT.setdefault('embedding_stages',[]).append(data);print('EMBEDDING_DONE',json.dumps(data),flush=True);save();return data

def usable(stage):
 s=stage['summary'];return s['failed_items']==0 and s['request_errors']==0 and s['truncated_responses']==0

def select(stages):
 valid=[s for s in stages if usable(s)]
 if not valid:return None
 fastest=max(s['summary']['valid_items_per_minute'] for s in valid)
 near=[s for s in valid if s['summary']['valid_items_per_minute']>=fastest*.95 and s['summary']['request_p95_seconds']<135]
 return min(near or valid,key=lambda s:s['concurrency'])

async def main():
 samples=prepare_samples();core=[samples[i] for i in [1,4,7,10,13,16,19,22]];confirmation=[samples[i] for i in [0,3,6,9,12,15,18,21]]
 REPORT['parameters']={'max_tokens':4096,'temperature':0,'max_gleanings':CFG.extract_graph.max_gleanings,'chunk_size':CFG.chunking.size,'chunk_overlap':CFG.chunking.overlap,'completion_model':CFG.get_completion_model_config(CFG.extract_graph.completion_model_id).model,'initial_items_per_level':8,'adaptive_gain_threshold':.15,'plateau_tolerance':.05}
 save();initial=[]
 for c in [1,2,4,8]:
  result=await stage('extract',c,core,'extract_initial_c'+str(c));initial.append(result)
  if result['summary']['request_errors']>=2 or result['summary']['observed_server_waiting_max']>=16:break
 if len(initial)==4 and usable(initial[-1]) and initial[-1]['summary']['valid_items_per_minute']>initial[-2]['summary']['valid_items_per_minute']*1.15:
  result=await stage('extract',12,[samples[i] for i in range(0,24,2)],'extract_initial_c12');initial.append(result)
  if usable(result) and result['summary']['observed_server_waiting_max']<16 and result['summary']['valid_items_per_minute']>initial[-2]['summary']['valid_items_per_minute']*1.15:
   initial.append(await stage('extract',16,[samples[int(i*24/16)] for i in range(16)],'extract_initial_c16'))
 candidates=sorted([s for s in initial if usable(s)],key=lambda s:s['summary']['valid_items_per_minute'],reverse=True)[:2]
 confirm=[]
 for c in sorted([s['concurrency'] for s in candidates],reverse=True):
  confirm.append(await stage('extract',c,confirmation,'extract_confirm_c'+str(c)))
 chosen=select(confirm or initial)
 reports=[]
 if chosen:
  count=max(8,max(s['concurrency'] for s in candidates))
  report_items=report_samples(count)
  for c in sorted([s['concurrency'] for s in candidates],reverse=True):reports.append(await stage('report',c,report_items,'report_confirm_c'+str(c)))
  report_choice=select(reports)
  eligible=[s for s in (confirm or initial) if usable(s) and any(r['concurrency']==s['concurrency'] and usable(r) for r in reports)]
  global_choice=select(eligible)
  REPORT['recommendation']={'extract_concurrency':chosen['concurrency'],'report_concurrency':report_choice['concurrency'] if report_choice else None,'single_concurrent_requests':global_choice['concurrency'] if global_choice else None,'selection':'smallest concurrency within 5% of best confirmation throughput; no failed/truncated outputs; p95 under 135s preferred','scope':'best among tested settings under observed shared-server load'}
 for c in [1,2,4,8]:await embedding_stage(c,samples)
 good=[s for s in REPORT.get('embedding_stages',[]) if s['failed_requests']==0]
 if good:
  fastest=max(s['texts_per_second'] for s in good);REPORT.setdefault('recommendation',{})['embedding_http_concurrency']=min(s['concurrency'] for s in good if s['texts_per_second']>=fastest*.95)
 REPORT.update(state='complete',finished_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),logical_llm_calls=len(CALLS),configuration_unchanged=hashlib.sha256((ROOT/'settings.yaml').read_bytes()).hexdigest()==CONFIG_HASH)
 assert REPORT['configuration_unchanged'];save();print('BENCHMARK_COMPLETE',OUT,json.dumps(REPORT.get('recommendation')),flush=True)

if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as exc:
  REPORT.update(state='error',error=type(exc).__name__,logical_llm_calls=len(CALLS));save();print('BENCHMARK_ERROR',type(exc).__name__,flush=True);raise SystemExit(1)
