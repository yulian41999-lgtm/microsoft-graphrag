"""Reuse completed index; audited QA and existing four-metric evaluation."""
import sys, os, json, time, re, hashlib, subprocess, datetime, copy
from pathlib import Path
P=Path(__file__).resolve().parents[1]; H=P.parent/'hipporag_local'
sys.path.insert(0,str(P))
from structured_qa import make_engine, load_questions, atomic_json, final_answer, enrich_sources
from openai import OpenAI

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def log(path,row):
    with path.open('a') as f: f.write(json.dumps(row,ensure_ascii=False)+'\n'); f.flush(); os.fsync(f.fileno())
def usage_summary(rows):
    responses=[r for r in rows if r.get('response_received') or 'raw_response' in r or 'response' in r]
    us=[r['usage'] for r in responses if r.get('usage') is not None]
    keys=['prompt_tokens','completion_tokens','total_tokens']
    sums={k:sum(u.get(k,0) or 0 for u in us) for k in keys}
    complete=len(us)==len(rows)
    durations=[r['api_seconds'] for r in rows if 'api_seconds' in r]
    return dict(saved_api_responses=len(responses),attempts=len(rows),responses_with_usage=len(us),usage_complete=complete,recorded_usage_subtotal=sums,**{k:v if complete else None for k,v in sums.items()},api_seconds_sum=sum(durations) if len(durations)==len(rows) else None,api_seconds_average=sum(durations)/len(rows) if rows and len(durations)==len(rows) else None,failed_attempts=sum(r.get('status')!='ok' for r in rows),unknown_consumption_attempts=len(rows)-len(responses))

def qa(mode,out):
    start=time.monotonic(); started=now(); out.mkdir()
    engine,tables,meta,identity=make_engine(P,0)
    params=dict(engine.context_builder_params)
    if mode=='graph_only':
        # Fixed graph budget ablation: remove source data, keep original allocation.
        engine.context_builder.text_units={}
        # Preserve original graph budget; reserved source allowance remains unused.
    qs=load_questions(H/'data/banking/银行监管测试集/questions.json')
    from graphrag.config.load_config import load_config
    cfg=load_config(P); model=cfg.get_completion_model_config(cfg.local_search.completion_model_id)
    client=OpenAI(api_key=model.api_key,base_url=model.api_base,timeout=180,max_retries=0)
    embcfg=cfg.get_embedding_model_config(cfg.local_search.embedding_model_id)
    embclient=OpenAI(api_key=embcfg.api_key,base_url=embcfg.api_base,timeout=180,max_retries=0)
    class Embedder:
        def embedding(self, *, input):
            from types import SimpleNamespace
            for attempt in range(4):
                t=time.monotonic(); call=dict(phase='retrieval_embedding',attempt=attempt,input=input,model=embcfg.model,started_at=now(),response_received=False)
                try:
                    response=embclient.embeddings.create(model=embcfg.model,input=input)
                    call.update(response_received=True,response=response.model_dump(),usage=response.usage.model_dump() if response.usage else None,status='ok')
                    return SimpleNamespace(first_embedding=response.data[0].embedding)
                except Exception as e:
                    call.update(status='error',error=type(e).__name__)
                    if attempt==3: raise
                finally:
                    call['api_seconds']=time.monotonic()-t; log(out/'embedding_calls.jsonl',call)
                time.sleep(min(2**(attempt+1),30))
    engine.context_builder.text_embedder=Embedder()
    records=[]; core=time.monotonic()
    manifest=dict(started_at=started,mode=mode,index_identity=identity,**meta,context_builder_params=params,cache='generation cache bypassed; retrieval embedding cache bypassed; fresh engine per mode; existing ready embedding service reused without restart',graph_description_provenance='entities/relationships descriptions: historical model extraction and description merging from corpus; reports: historical model community summaries, derived records, not primary text; may contain quotations; no new descriptions generated',generation_transport='nonstream OpenAI compatible, server usage retained; same for both modes',preflight_api_calls=0)
    atomic_json(out/'manifest.json',manifest)
    for q in qs:
        ts=time.monotonic(); row=dict(q,mode=mode,generated_answer='',context=[],sources=[],status='retrieval_error',**meta)
        try:
            t=time.monotonic(); built=engine.context_builder.build_context(query=q['question'],**params)
            row['retrieval_seconds']=time.monotonic()-t
            ctx=str(built.context_chunks); data={k:json.loads(v.to_json(orient='records',force_ascii=False)) for k,v in built.context_records.items()}
            if mode=='graph_only':
                assert not data.get('sources') and '-----Sources-----' not in ctx
            messages=[dict(role='system',content=engine.system_prompt.format(context_data=ctx,response_type=engine.response_type)),dict(role='user',content=q['question'])]
            row.update(context=[ctx] if ctx.strip() else [],context_text=ctx,context_data=data,generation_messages=messages,sources=enrich_sources(data,tables),context_token_estimate=len(engine.tokenizer.encode(ctx)),estimate_tokenizer='GraphRAG configured tokenizer; not server usage')
            if not ctx.strip(): row['status']='no_context'
            else:
                for attempt in range(4):
                    call=dict(question_id=q['id'],phase='qa',attempt=attempt,started_at=now(),messages=messages,model=model.model,parameters=dict(temperature=0,max_tokens=4096),response_received=False)
                    t=time.monotonic()
                    try:
                        response=client.chat.completions.create(model=model.model,messages=messages,temperature=0,max_tokens=4096)
                        call['api_seconds']=time.monotonic()-t
                        call.update(response_received=True,response=response.model_dump(),usage=response.usage.model_dump() if response.usage else None)
                        raw=response.choices[0].message.content or ''; row['raw_response']=raw
                        if response.choices[0].finish_reason!='stop': raise ValueError('IncompleteCompletion')
                        row.update(generated_answer=final_answer(raw),status='ok',generation_usage=call['usage']); call['status']='ok'
                    except Exception as e:
                        call.setdefault('api_seconds',time.monotonic()-t); call.update(status='error',error=type(e).__name__); row.update(status='generation_error',error=type(e).__name__)
                    log(out/'api_calls.jsonl',call)
                    if call['status']=='ok': break
                    if attempt<3: time.sleep(min(2**(attempt+1),30))
        except Exception as e: row.update(error=type(e).__name__)
        row['latency_seconds']=time.monotonic()-ts
        row['refusal_heuristic']=bool(re.search('资料不足|无法确定|未提供|无法回答|没有足够',row['generated_answer']))
        cited=re.findall(r'\[Data:\s*([^\]]+)\]',row['generated_answer'])
        row['citation_check']=dict(markers=cited,status='requires_semantic_review' if cited else 'no_data_citation',note='Presence is not correctness; record-ID checks and source inspection in report')
        records.append(row); atomic_json(out/'predictions.json',records)
        print(mode,len(records),q['id'],row['status'],flush=True)
    embclient.close(); client.close(); rows=[json.loads(x) for x in (out/'api_calls.jsonl').read_text().splitlines()] if (out/'api_calls.jsonl').exists() else []
    manifest.update(finished_at=now(),core_qa_seconds=sum(r['latency_seconds'] for r in records),calendar_seconds=time.monotonic()-start,cost=usage_summary(rows),state='complete',statuses={s:sum(r['status']==s for r in records) for s in set(r['status'] for r in records)})
    manifest['retrieval_embedding_cost']=usage_summary([json.loads(x) for x in (out/'embedding_calls.jsonl').read_text().splitlines()])
    atomic_json(out/'manifest.json',manifest)

def score(out):
    # Run unchanged metric implementation in original environment; instrument actual HTTP API calls.
    sys.path.insert(0,str(H)); from evaluation.judge import JSONJudge
    oldinit=JSONJudge.__init__; oldlog=JSONJudge._log
    def init(self,*a,**kw):
        a[0].update(judge_max_tokens=8192,judge_timeout_seconds=240); oldinit(self,*a,**kw)
        self.client.timeout=240; self._timings=[]
        original=self.client.chat.completions.create
        def create(**kw):
            t=time.monotonic(); record=dict(started_at=now(),messages=kw['messages'],parameters={k:v for k,v in kw.items() if k!='messages'},response_received=False)
            try:
                response=original(**kw);record.update(response_received=True,response=response.model_dump(),usage=response.usage.model_dump() if response.usage else None,status='ok');return response
            except Exception as e: record.update(status='error',error=type(e).__name__);raise
            finally:
                record['api_seconds']=time.monotonic()-t;self._timings.append(record);log(out/'judge_http_calls.jsonl',record)
        self.client.chat.completions.create=create
    def logged(self,record):
        if self._timings: record.update(api_seconds=self._timings[-1]['api_seconds'],started_at=self._timings[-1]['started_at'])
        oldlog(self,record)
    JSONJudge.__init__=init;JSONJudge._log=logged
    import evaluation.run as run
    sys.argv=['evaluation.run','--input',str(out/'eval_input.json'),'--output-dir',str(out/'scores')]
    start=time.monotonic(); started=now()
    try: run.main()
    except SystemExit as e:
        if e.code not in (0,2,None): raise
    calls=[json.loads(x) for x in (out/'judge_http_calls.jsonl').read_text().splitlines()]
    validated=[json.loads(x) for x in (out/'scores/judge_calls.jsonl').read_text().splitlines()]
    assert len(validated)==len(calls)
    for api,check in zip(calls,validated):
        api.update(api_status=api['status'],status=check['status'],task=check['task'],attempt=check['attempt'],validation_error=check.get('error'))
    atomic_json(out/'judge_attempts.json',calls)
    atomic_json(out/'scoring_cost.json',dict(started_at=started,finished_at=now(),calendar_seconds=time.monotonic()-start,cost=usage_summary(calls),preflight_api_calls=0))

if __name__=='__main__':
    os.chdir(P);os.umask(0o077)
    if sys.argv[1]=='qa': qa(sys.argv[2],Path(sys.argv[3]))
    elif sys.argv[1]=='score': score(Path(sys.argv[2]))
