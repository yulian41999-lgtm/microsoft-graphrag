import pathlib,subprocess,json,time,datetime,html,traceback
P=pathlib.Path.cwd();H=P.parent/'hipporag_local';R=P/'outputs'/('evaluation15_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));R.mkdir()
W=P/'output/visualization/evaluation.html'
M={'context_relevancy':'上下文相关性','evidence_recall':'证据召回率','rouge_l':'中文 ROUGE-L','answer_correctness':'答案正确性'}
def read(p,d):
 try:return json.loads(p.read_text())
 except:return d
def render(stage):
 pred=read(R/'predictions.json',[]);report=read(R/'scores/scores.json',{});scores=report.get('scores',read(R/'scores/scores.partial.json',[]));cards='';rows=''
 for k,label in M.items():
  vals=[x['metrics'][k]['score'] for x in scores if x['metrics'].get(k,{}).get('status')=='ok'];v=sum(vals)/len(vals) if vals else None
  text=f'{100*v:.1f} / 100' if v is not None else '待评分'
  cards+=f'<article>{label}<h2>{text}</h2><progress max="1" value="{v or 0}"></progress><p>有效 {len(vals)} / 15</p></article>'
 sm={x['id']:x for x in scores}
 for x in pred:
  cells=''
  for k in M:
   m=sm.get(x['id'],{}).get('metrics',{}).get(k,{});v=m.get('score');cells+='<td>'+(f'{v*100:.1f}' if v is not None else m.get('status','待评分'))+'</td>'
  rows+='<tr><td>'+html.escape(x['id'])+'</td><td>'+html.escape(x['question'])+'</td><td>'+html.escape(x['status'])+'</td>'+cells+'</tr><tr><td colspan="7"><details><summary>生成答案</summary><pre>'+html.escape(x.get('generated_answer',''))+'</pre></details></td></tr>'
 page='<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="20"><title>GraphRAG 测评</title><style>body{font:16px system-ui;background:#101827;color:#e5edf8;margin:30px}section{display:flex;gap:18px}article{background:#223047;padding:20px;flex:1;border-radius:12px}table{width:100%;border-collapse:collapse;margin-top:25px}td,th{padding:12px;text-align:left;border-bottom:1px solid #40516b}pre{white-space:pre-wrap}progress{width:100%}</style><h1>Microsoft GraphRAG · 15 题测评</h1><p>'+html.escape(stage)+f' · 推理 {len(pred)}/15 · 评分 {len(scores)}/15</p><p>Local Search · 1,700 篇文档 · 四指标独立报告，不计算总分。分数按有效题目宏平均。裁判与生成使用同一模型，15 题属于诊断集；跨系统比较需注意语料及上下文预算差异。</p><section>'+cards+'</section><table><tr><th>ID</th><th>问题</th><th>生成状态</th>'+''.join('<th>'+v+'</th>' for v in M.values())+'</tr>'+rows+'</table><p>结果目录：'+str(R)+'</p><p>每20秒刷新；待评分及错误均不作为零分。</p>'
 tmp=W.with_suffix('.tmp');tmp.write_text(page,encoding='utf-8');tmp.replace(W)
 (R/'status.json').write_text(json.dumps({'stage':stage,'predictions':len(pred),'scored':len(scores),'path':str(R)},ensure_ascii=False))
def run(args,cwd,stage):
 render(stage)
 with (R/'pipeline.log').open('a') as log:
  proc=subprocess.Popen(list(map(str,args)),cwd=cwd,stdout=log,stderr=log)
  while proc.poll() is None:render(stage);time.sleep(5)
  return proc.returncode
try:
 render('启动中')
 rc=run([P/'.venv/bin/python',P/'structured_qa.py','--scope','full','--questions',H/'data/banking/银行监管测试集/questions.json','--output',R/'predictions.json'],P,'正在生成答案')
 if rc not in (0,2):raise RuntimeError('推理失败 '+str(rc))
 rc=run([H/'.venv/bin/python',H/'data/banking/银行监管测试集/tools/export_eval_input.py','--predictions',R/'predictions.json','--output',R/'eval_input.json'],H,'校验评分输入')
 if rc:raise RuntimeError('评分输入校验失败')
 rc=run([H/'.venv/bin/python','-m','evaluation.run','--input',R/'eval_input.json','--output-dir',R/'scores'],H,'正在进行四指标评分')
 render('测评完成' if rc==0 else '评分存在错误，请检查日志及逐题结果')
except Exception:
 (R/'error.log').write_text(traceback.format_exc());render('流程异常，请检查 error.log 和 pipeline.log')
print(R,flush=True)
