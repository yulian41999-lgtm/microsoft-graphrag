from pathlib import Path
import shutil,yaml
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'prompts').exists(): shutil.copytree(ROOT/'tmp/template/prompts',ROOT/'prompts')
shutil.copy2(ROOT/'tmp/template/settings.yaml',ROOT/'upstream_defaults.yaml')
cfg=yaml.safe_load((ROOT/'upstream_defaults.yaml').read_text())
cfg['completion_models']['default_completion_model'].update(api_base='http://10.253.170.81:8006/v1',call_args={'temperature':0,'max_tokens':4096,'timeout':180},retry={'type':'exponential_backoff','max_retries':3,'base_delay':2.0,'max_delay':30})
cfg['embedding_models']['default_embedding_model'].update(api_base='http://127.0.0.1:18086/v1',api_key='local-bge-m3',call_args={'timeout':180},retry={'type':'exponential_backoff','max_retries':3,'base_delay':2.0,'max_delay':30})
cfg['vector_store']['vector_size']=1024
cfg['concurrent_requests']=6
cfg['input']={'type':'jsonl','file_pattern':r'banking[.]jsonl','text_column':'text','title_column':'title','id_column':'id'}
cfg['chunking'].update(size=800,overlap=120,prepend_metadata=['title','source_id','document_number','publication_date','effective_date','validity','agency'])
cfg['embed_text'].update(batch_size=4,batch_max_tokens=8191)
cfg['extract_graph'].update(entity_types=['ORGANIZATION','PERSON','GEO','REGULATION','BUSINESS','REGULATORY_ACTION'],max_gleanings=1)
cfg['summarize_descriptions'].update(max_length=600)
cfg['community_reports'].update(max_length=1500,max_input_length=6000)
cfg['cluster_graph'].update(max_cluster_size=10,use_lcc=False)
cfg['local_search'].update(text_unit_prop=0.65,community_prop=0.10,top_k_entities=15,top_k_relationships=20,max_context_tokens=10000)
cfg['global_search'].update(max_context_tokens=10000,data_max_tokens=6000,map_max_length=800,reduce_max_length=1500)
cfg['basic_search'].update(k=10,max_context_tokens=10000)
for sub in ['', 'smoke']:
    root=ROOT/sub;root.mkdir(exist_ok=True)
    cfg['vector_store']['db_uri']=str(root/'output/lancedb')
    (root/'settings.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
    if sub:
        for name in ['.env','prompts']:
            p=root/name
            if not p.exists():p.symlink_to(ROOT/name,target_is_directory=name=='prompts')
print('Configured banking GraphRAG and smoke roots')
