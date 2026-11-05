"""Read-only retrieval probe on existing smoke index; no answer generation or gold access."""
import json,os,time
from pathlib import Path
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
import pandas as pd,numpy as np
from graphrag.config.load_config import load_config
from graphrag.config.embeddings import entity_description_embedding
from graphrag.utils.api import get_embedding_store,load_search_prompt
from graphrag.query.factory import get_local_search_engine
from graphrag.query.indexer_adapters import read_indexer_entities,read_indexer_reports,read_indexer_text_units,read_indexer_relationships
r=Path(__file__).resolve().parents[1];root=r/'smoke';c=load_config(root)
t={n:pd.read_parquet(root/'output'/f'{n}.parquet') for n in ['entities','communities','community_reports','text_units','relationships','documents']}
engine=get_local_search_engine(config=c,reports=read_indexer_reports(t['community_reports'],t['communities'],0),text_units=read_indexer_text_units(t['text_units']),entities=read_indexer_entities(t['entities'],t['communities'],0),relationships=read_indexer_relationships(t['relationships']),covariates={},description_embedding_store=get_embedding_store(config=c.vector_store,embedding_name=entity_description_embedding),response_type='简洁中文',system_prompt=load_search_prompt(c.local_search.prompt),callbacks=[])
q='烟金罚决字〔2024〕34号处罚的机构是什么，罚款多少？'
start=time.monotonic();result=engine.context_builder.build_context(query=q,**engine.context_builder_params)
records={k:json.loads(v.to_json(orient='records',force_ascii=False)) for k,v in result.context_records.items()}
report={'query':q,'scope':'5_document_smoke','generation_called':False,'context_text':result.context_chunks,'context_data':records,'retrieval_seconds':round(time.monotonic()-start,3),'context_record_columns':{k:list(v.columns) for k,v in result.context_records.items()},'index_table_columns':{k:list(v.columns) for k,v in t.items()}}
(r/'analysis/retrieval_probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['context_text','context_data','index_table_columns']},ensure_ascii=False,indent=2))
print('RECORD_COUNTS',{k:len(v) for k,v in records.items()})
print('SOURCE_RECORD_SAMPLE',records.get('sources',[])[:1])
