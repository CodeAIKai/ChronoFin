"""Local research workbench. Standard-library server; Hy3 key stays server-side."""
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from chronofin.brief import generate,read_data,judge,evaluate
from chronofin.config import Hy3Config
from chronofin.runtime import RateLimitedClient as ChatCompletionsClient
from chronofin import pdf_research_v5 as pdf_research
from chronofin import grounded
from chronofin.live_audit import partial_scorecard,judge_partial
from chronofin.review_notes import review_notes

SOURCES,CARDS,CASES=read_data(ROOT)
NATIVE_CASES=json.loads((ROOT/'data/native/cases.json').read_text())
LIMIT=threading.BoundedSemaphore(2)
DEMO_RECORDS={'TC01_demo':ROOT/'results/demo/TC01_demo.json'}

def native_choices():
    choices=[]
    for name,path in DEMO_RECORDS.items():
        if path.is_file():
            result=json.loads(path.read_text())
            if result.get('status')=='ok':
                q=result['record']['query']
                choices.append({'id':name,'label':'TC01 · 研究简报演示','question':q['question'],'as_of':q['as_of']})
    return choices+[{'id':j['id'],'question':j['case']['question'],'as_of':j['case']['as_of']}for j in NATIVE_CASES]


def runs():
    return sorted([p.name for p in (ROOT/'results/brief').glob('*') if p.is_dir() and (p/'protocol.json').exists()],reverse=True)

def locate(run,name):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run) or not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('invalid record name')
    return ROOT/'results/brief'/run/(name+'.json')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):pass
    def send(self,obj,status=200,content='application/json; charset=utf-8'):
        body=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        url=urlparse(self.path);qs=parse_qs(url.query)
        try:
            if url.path=='/':return self.send((ROOT/'web/index.html').read_bytes(),content='text/html; charset=utf-8')
            if url.path=='/font.otf':
                return self.send((ROOT/'assets/fonts/NotoSansCJKsc-Regular.otf').read_bytes(),content='font/otf')
            if url.path=='/api/config':
                return self.send({'cases':[{k:v for k,v in c.items() if k in {'id','question','as_of','task','split'}} for c in CASES],
                                  'sources':SOURCES,'cards':CARDS,'runs':runs(),'live_available':bool(os.getenv('HY3_API_KEY')),
                                  'native_cases':native_choices()})
            if url.path=='/api/result':
                path=locate(qs.get('run',['v2'])[0],qs.get('name',['D01_counterbrief'])[0])
                if not path.exists():return self.send({'error':'此案例尚无该版本的实测结果'},404)
                result=json.loads(path.read_text())
                reliability_path=path.parent/'judge_reliability.json'
                if reliability_path.exists() and result.get('strategy')=='counterbrief':
                    result['reliability']=json.loads(reliability_path.read_text()).get('cases',{}).get(result.get('case_id'))
                return self.send(result)
            if url.path=='/api/native_result':
                name=qs.get('name',['meta24_after'])[0]
                if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('invalid record name')
                path=DEMO_RECORDS.get(name,ROOT/'results/native_pdf/v5'/(name+'.json'))
                if not path.exists():return self.send({'error':'该原生 PDF 实验尚无完成记录'},404)
                result=json.loads(path.read_text());result['mode']='replay_pdf';result['review_notes']=review_notes(result);return self.send(result)
            if url.path=='/api/experiments':
                run=qs.get('run',['v2'])[0];path=locate(run,'summary')
                out={'summary':json.loads(path.read_text()) if path.exists() else {},'metaeval':{}}
                m=path.parent/'metaeval/summary.json'
                if m.exists():out['metaeval']=json.loads(m.read_text())
                final=ROOT/'results/final_status.json'
                if run=='v3' and final.exists():out['final_status']=json.loads(final.read_text())
                for key,relative in {'grounded':'grounded/v1','external_human':'external_human/v3','native_pdf':'native_pdf/v5','stress':'semantic_stress/v1'}.items():
                    fp=ROOT/'results'/relative/'summary.json'
                    out[key]=json.loads(fp.read_text()) if fp.exists() else {}
                return self.send(out)
            self.send({'error':'not found'},404)
        except (ValueError,KeyError) as e:self.send({'error':str(e)},400)
    def do_POST(self):
        if self.path not in {'/api/ask','/api/ask_pdf'}:return self.send({'error':'not found'},404)
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send({'error':'cross-origin requests denied'},403)
        if not LIMIT.acquire(blocking=False):return self.send({'error':'正在处理两项任务，请稍后重试'},429)
        try:
            size=int(self.headers.get('Content-Length','0'))
            maximum=12_000_000 if self.path=='/api/ask_pdf' else 2_000_000
            if size<1 or size>maximum:raise ValueError('请求超过大小限制')
            req=json.loads(self.rfile.read(size));q=str(req.get('question','')).strip();cutoff=str(req.get('as_of',''))
            date.fromisoformat(cutoff)
            if not q or len(q)>4000:raise ValueError('问题须为 1 至 4000 字')
            if self.path=='/api/ask_pdf':
                raw=req.get('pdf_base64','')
                if not isinstance(raw,str):raise ValueError('PDF 数据格式不正确')
                data=base64.b64decode(raw,validate=True)
                cfg=Hy3Config.from_env()
                if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('需要官方 TokenHub Hy3')
                result=pdf_research.run(ChatCompletionsClient(cfg,max_attempts=3),data,req.get('metadata',{}),q,cutoff,ROOT)
                # Raw original source windows are reproducible from the PDF;
                # only validated fact quotes are returned to the browser.
                audit_cards=result.pop('native_replay_material')['audit_cards']
                generic={**result['record']['query'],'required':[],'counter':[],'limitations':[],'expected_answerability':result['record']['answer']['answerability']}
                result['semantic'],result['scorecard'],result['judge_attempts']=judge_partial(ChatCompletionsClient(cfg,max_attempts=3),result['record'],audit_cards)
                result['note']='已核查原文支持；未设独立参考清单，因此不报告总分和覆盖完成率。'
                result['review_notes']=review_notes(result)
                return self.send(result)
            cards=req.get('cards') or CARDS
            if not isinstance(cards,list) or len(cards)>300:raise ValueError('资料卡片须为列表且不超过 300 条')
            ids=[]
            for c in cards:
                if not isinstance(c,dict) or not {'id','source_id','text','entity','published_at','value','unit'}<=set(c):raise ValueError('资料卡片缺少必填字段')
                date.fromisoformat(c['published_at']);ids.append(c['id'])
            if len(ids)!=len(set(ids)):raise ValueError('资料 ID 重复')
            cfg=Hy3Config.from_env()
            if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('本应用需使用官方 TokenHub 的 hy3')
            case={'question':q,'as_of':cutoff}
            record=generate(ChatCompletionsClient(cfg,max_attempts=2),cards,case,'counterbrief')
            result={'status':'ok','record':record,'mode':'live','note':'自定义问题未配备预注册参考清单；未测维度不计为通过。'}
            # A preset is evaluated only when its complete input matches.
            preset=next((c for c in CASES if c['question']==q and c['as_of']==cutoff),None)
            if preset and cards==CARDS:
                result['semantic']=grounded.judge(ChatCompletionsClient(cfg,max_attempts=2),record,preset,cards)
                result['scorecard']=evaluate(record,preset,cards,result['semantic'])
            else:
                generic={**case,'required':[],'counter':[],'limitations':[],'expected_answerability':record['answer']['answerability']}
                result['semantic'],result['scorecard'],result['judge_attempts']=judge_partial(ChatCompletionsClient(cfg,max_attempts=2),record,cards)
            result['review_notes']=review_notes(result)
            self.send(result)
        except Exception as e:
            key=os.getenv('HY3_API_KEY','');msg=str(e)
            if key:msg=msg.replace(key,'[REDACTED]')
            self.send({'error':msg[:700]},400)
        finally:LIMIT.release()

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8787);a=p.parse_args()
    print(f'ChronoFin 个人活动作品: http://127.0.0.1:{a.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

if __name__=='__main__':main()
