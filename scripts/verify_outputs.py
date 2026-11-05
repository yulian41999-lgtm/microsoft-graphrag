import hashlib,json,sys
from pathlib import Path
import lancedb,numpy as np,pandas as pd,yaml
ROOT=Path(__file__).resolve().parents[1]
root=ROOT/('smoke' if len(sys.argv)<2 or sys.argv[1]=='smoke' else '')
cfg=yaml.safe_load((root/'settings.yaml').read_text())
tables={n:pd.read_parquet(root/'output'/f'{n}.parquet') for n in ['documents','text_units','entities','relationships','communities','community_reports']}
assert all(len(t)>0 for t in tables.values())
assert set(tables['relationships']['source'])|set(tables['relationships']['target']) <= set(tables['entities']['title'])
assert not tables['entities']['title'].str.contains('示例监管局|示例银行').any()
assert set(tables['entities']['type'])<=set(cfg['extract_graph']['entity_types'])
manifest=json.loads((root/'input/banking.manifest.json').read_text())
assert len(tables['documents'])==manifest['selected_documents']
assert tables['community_reports']['full_content'].str.contains('Data:').all()
db=lancedb.connect(str(root/'output/lancedb'))
vector_counts={}
for name,table in [('entity_description','entities'),('community_full_content','community_reports'),('text_unit_text','text_units')]:
 t=db.open_table(name);rows=t.to_arrow();vectors=rows['vector'].to_pylist()
 assert t.count_rows()==len(tables[table]), (name,t.count_rows(),len(tables[table]))
 assert set(rows['id'].to_pylist())==set(tables[table]['id'].astype(str))
 assert all(len(v)==1024 and np.isfinite(v).all() and abs(np.linalg.norm(v)-1)<0.01 for v in vectors)
 vector_counts[name]=len(vectors)
report={'status':'ready_for_query','scope':root.name,'counts':{k:len(v) for k,v in tables.items()},'embedding_vector_size':1024,'embedding_vector_counts':vector_counts,'all_vectors_finite_normalized':True,'relationship_endpoints_valid':True,'synthetic_example_entities_absent':True,'community_reports_have_citations':True,'source_manifest_sha256':hashlib.sha256((root/'input/banking.manifest.json').read_bytes()).hexdigest(),'settings_sha256':hashlib.sha256((root/'settings.yaml').read_bytes()).hexdigest(),'qa_data_ingested':False}
(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
