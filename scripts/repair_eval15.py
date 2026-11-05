import pathlib,sys,json,copy,os,hashlib,html
P=pathlib.Path.cwd();H=P.parent/'hipporag_local';R=sorted((P/'outputs').glob('evaluation15_*'))[-1]
sys.path.insert(0,str(H))
from settings import load_settings
from evaluation.repair import ReusingJudge,atomic_json
from evaluation.judge import JSONJudge
from evaluation.metrics import answer_correctness
from evaluation.run import summarize
from hipporag.utils.config_utils import BaseConfig
from local_embedding import LocalBGEEmbedding
settings=load_settings();original=json.loads((R/'scores/scores.json').read_text());report=copy.deepcopy(original)
out=R/'repair';out.mkdir(exist_ok=False)
config=dict(original['profile'],judge_max_tokens=8192,judge_timeout_seconds=240)
calls=[json.loads(l) for l in (R/'scores/judge_calls.jsonl').read_text().splitlines()]
delegate=JSONJudge(config,out/'judge_calls.jsonl');judge=ReusingJudge(calls,delegate,out/'reused.jsonl')
embedding=LocalBGEEmbedding(BaseConfig(embedding_model_name=settings['embedding_model_id'],embedding_return_as_normalized=True),dict(settings,max_seq_length=config['embedding_max_seq_length'],batch_size=1))
inputs={x['id']:x for x in json.loads((R/'eval_input.json').read_text())}
try:
 for record in report['scores']:
  for k,m in list(record['metrics'].items()):
   if m['status']=='ok':continue
   assert k=='answer_correctness'
   x=inputs[record['id']];score,details=answer_correctness(x['question'],x['generated_answer'],x['ground_truth'],judge,embedding,x['id'])
   record['metrics'][k]=dict(score=float(score),status='ok',details=details);print(record['id'],k,score,flush=True)
 for before,after in zip(original['scores'],report['scores']):
  for k,m in before['metrics'].items():
   if m['status']=='ok':assert m==after['metrics'][k]
 report['summary']=summarize(report['scores']);report['repair']={'source':str(R/'scores/scores.json'),'source_sha256':hashlib.sha256((R/'scores/scores.json').read_bytes()).hexdigest(),'judge_max_tokens':8192,'judge_timeout_seconds':240,'successful_scores_preserved':True}
 atomic_json(out/'scores.json',report)
 # Reuse the dashboard renderer without running the pipeline or creating a new run.
 source=(P/'scripts/run_eval15_dashboard.py').read_text();source=source[source.index('W=P/'):source.index('\ntry:\n render(')];source=source.replace("R/'scores/scores.json'","R/'repair/scores.json'")
 exec(source,globals());render('测评完成（R003 评分截断已修复）')
 print('REPAIR_COMPLETE',flush=True)
finally:delegate.close();embedding.close()
