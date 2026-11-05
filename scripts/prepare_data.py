"""Convert raw banking sources only; never ingest question/answer datasets."""
import argparse, hashlib, html, json, re
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'hipporag_local/data/banking'
def parse(path):
    raw = path.read_text(encoding='utf-8-sig').replace('\x00', '\ufffd')
    title = path.stem.split('__', 1)[-1]
    if path.suffix.lower() in {'.html','.htm'}:
        match = re.search(r'<h1\b[^>]*>(.*?)</h1>', raw, re.S | re.I)
        if match: title = html.unescape(re.sub('<[^>]+>', '', match.group(1))).strip()
        text = re.sub(r'<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', '', raw, flags=re.S | re.I)
        text = re.sub(r'</(?:p|div|tr|h[1-6])\s*>|<br\s*/?>', '\n', text, flags=re.I)
        text = html.unescape(re.sub('<[^>]+>', '', text))
        text = '\n'.join(line for line in (re.sub(r'\s+', ' ', x).strip() for x in text.splitlines()) if line)
    else: text = raw.strip()
    return title, text

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int);ap.add_argument('--output',default='input/banking.jsonl');a=ap.parse_args()
    groups={}
    for p in sorted(SOURCE.rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.txt','.html','.htm'} and p.name.startswith('DOC'):
            groups.setdefault(p.stem.split('__',1)[0],[]).append(p)
    docs=[];skipped=[]
    for docid,files in sorted(groups.items()):
        selected=[p for p in files if p.suffix.lower() in {'.html','.htm'}] or files
        if len(selected)!=1:raise ValueError(f'Ambiguous source for {docid}')
        path=selected[0];title,text=parse(path)
        if not text:skipped.append(docid);continue
        metadata={}
        if path.suffix.lower() in {'.html','.htm'}:
            raw=path.read_text(encoding='utf-8-sig')
            for key,tag in [('document_number','cchcndocumentnumber'),('publication_date','cchcnpromulgatingdate'),('effective_date','cchcneffectivedate'),('validity','cchcnvaliditystatusid'),('agency','cchcnpromulgatingagencyid')]:
                m=re.search(r'id="'+tag+r'"[^>]*>(.*?)</span>',raw,re.S)
                metadata[key]=html.unescape(re.sub('<[^>]+>','',m.group(1))).strip() if m else ''
        docs.append({**metadata,'source_id':docid,'id':docid,'title':title,'text':text,'source_file':str(path.relative_to(SOURCE)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    total=len(docs)
    if a.limit:
        # Deterministic short documents exercise graph extraction with bounded cost.
        docs=sorted(docs,key=lambda d:(len(d['text']),d['id']))
        docs=[docs[min(len(docs)-1,int(q*(len(docs)-1)))] for q in ([0.10,0.40,0.60,0.75,0.90][:a.limit])] if a.limit<=5 else docs[:a.limit]
    dest=ROOT/a.output;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(''.join(json.dumps(d,ensure_ascii=False)+'\n' for d in docs),encoding='utf-8')
    report={'source_root':str(SOURCE),'unique_source_documents':len(groups),'nonempty_documents':total,'selected_documents':len(docs),'characters':sum(len(d['text']) for d in docs),'skipped_empty':skipped,'duplicate_policy':'prefer HTML with same DOC id','qa_data_ingested':False,'output_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'selected_ids':[d['id'] for d in docs]}
    dest.with_suffix('.manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='selected_ids'},ensure_ascii=False))
if __name__=='__main__':main()
