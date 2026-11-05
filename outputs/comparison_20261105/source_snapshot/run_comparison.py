import os,time,json,subprocess,sys
from pathlib import Path
P=Path(__file__).resolve().parents[1];H=P.parent/'hipporag_local';R=P/'outputs/comparison_20261105'
os.chdir(P)
def run(args,logname):
    with (R/logname).open('a') as f: result=subprocess.run([str(x) for x in args],stdout=f,stderr=f,cwd=P)
    if result.returncode not in (0,2): raise RuntimeError(f'{logname}: exit {result.returncode}')
try:
    for mode in ['original','graph_only']:
        out=R/('final_'+mode)
        run([P/'.venv/bin/python','-u',P/'scripts/compare_modes.py','qa',mode,out],mode+'.pipeline.log')
        run([H/'.venv/bin/python',H/'data/banking/银行监管测试集/tools/export_eval_input.py','--predictions',out/'predictions.json','--output',out/'eval_input.json'],mode+'.pipeline.log')
        run([H/'.venv/bin/python','-u',P/'scripts/compare_modes.py','score',out],mode+'.pipeline.log')
    (R/'pipeline_status.json').write_text(json.dumps(dict(state='complete')))
except Exception as e:
    (R/'pipeline_status.json').write_text(json.dumps(dict(state='error',error=str(e))))
    raise
