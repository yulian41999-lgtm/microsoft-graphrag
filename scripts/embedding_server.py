"""Loopback-only OpenAI-compatible BGE-M3 dense embedding service."""
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import torch
from sentence_transformers import SentenceTransformer
ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT.parent/'hipporag_local/models/bge-m3'
torch.set_num_threads(2)
device=os.environ.get('BGE_DEVICE','cuda')
model=SentenceTransformer(str(MODEL),device=device,local_files_only=True,model_kwargs={'torch_dtype':torch.float16 if device.startswith('cuda') else torch.float32})
model.max_seq_length=8192
lock=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print(fmt % args,flush=True)
    def send_json(self,status,data):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health': self.send_json(200,{'status':'ready','model':'bge-m3','dimension':1024,'device':device,'max_sequence_length':8192})
        elif self.path=='/v1/models':self.send_json(200,{'object':'list','data':[{'id':'bge-m3','object':'model','owned_by':'local'}]})
        else:self.send_json(404,{'error':{'message':'Not found'}})
    def do_POST(self):
        if self.path!='/v1/embeddings':self.send_json(404,{'error':{'message':'Not found'}});return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=8*1024*1024:raise ValueError('Request size out of range')
            payload=json.loads(self.rfile.read(n));texts=payload['input']
            if isinstance(texts,str):texts=[texts]
            if payload.get('model')!='bge-m3':raise ValueError('Expected model bge-m3')
            if not isinstance(texts,list) or not texts or not all(isinstance(t,str) for t in texts):raise ValueError('input must be a string or nonempty string list')
            with lock,torch.inference_mode():
                token_ids=model.tokenizer(texts,add_special_tokens=True,truncation=False)['input_ids']
                if any(len(x)>8192 for x in token_ids):raise ValueError('Input exceeds BGE-M3 8192-token limit; rechunk source')
                tokens=sum(len(x) for x in token_ids)
                vectors=model.encode(texts,batch_size=4,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
            self.send_json(200,{'object':'list','data':[{'object':'embedding','index':i,'embedding':v.astype('float32').tolist()} for i,v in enumerate(vectors)],'model':'bge-m3','usage':{'prompt_tokens':tokens,'total_tokens':tokens}})
        except (ValueError,KeyError) as e:self.send_json(400,{'error':{'message':str(e),'type':'invalid_request_error'}})
        except Exception as e:
            print('Embedding failure:',type(e).__name__,flush=True)
            self.send_json(500,{'error':{'message':'Embedding failed; check service log','type':'server_error'}})
print(json.dumps({'state':'ready','model':str(MODEL),'device':device,'port':18086}),flush=True)
ThreadingHTTPServer(('127.0.0.1',18086),Handler).serve_forever()
