"""Frozen equal-call application controls and order-robustness experiments."""
import argparse
import copy
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief,grounded
from chronofin.config import Hy3Config
from chronofin.llm import ChatCompletionsClient

def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def load(p):return json.loads(p.read_text())
def client():
    cfg=Hy3Config.from_env()
    if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('Hy3 required')
    return ChatCompletionsClient(cfg,max_attempts=2)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['application','order','summary','replay'],required=True);ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
    _,cards,cases=brief.read_data(ROOT);by_id={c['id']:c for c in cases};folder=ROOT/'results/grounded/v1';folder.mkdir(parents=True,exist_ok=True)
    files=['src/chronofin/grounded.py','src/chronofin/brief.py','src/chronofin/reliability.py','scripts/run_grounded_experiments.py','data/brief/cards.json','data/brief/cases.json']
    protocol={'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},'parent_v3_sha256':load(ROOT/'results/brief/v3/protocol.json')['sha256'],
              'application_methods':['full_context','counterbrief_first_pass','full_context_revision','counterbrief'],
              'order_cases':['D01','D02','D04','D05','E11','E12'],'orders':['original','reverse','shuffle','repeat'],
              'scope':'Visible author-designed regression; reused v3 generated drafts. Equal-call control uses a generic revision of the same saved full-context draft.'}
    sha=brief.digest(protocol);path=folder/'protocol.json'
    if path.exists() and load(path)['sha256']!=sha:raise SystemExit('New source requires new protocol directory')
    write(path,{'sha256':sha,**protocol})
    def app(job):
        case,method=job;path=folder/'application'/f'{case["id"]}_{method}.json'
        if path.exists() and load(path).get('status')=='ok':return
        source='full_context' if method.startswith('full_context') else 'counterbrief'
        base=load(ROOT/'results/brief/v3'/f'{case["id"]}_{source}.json')
        r={'case_id':case['id'],'split':case['split'],'method':method,'protocol_sha256':sha,'parent_record_sha256':brief.digest(base),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        started=time.monotonic()
        try:
            record=copy.deepcopy(base['record'])
            if method=='full_context_revision':record=grounded.neutral_revision(client(),record,case,cards)
            elif method=='counterbrief_first_pass':
                answer=record.get('schema_repaired',record['initial']);brief.validate_answer(answer)
                record.update(answer=copy.deepcopy(answer),answer_sha256=brief.digest(answer),strategy=method)
                record['traces']=record['traces'][:-1];record.pop('revision_raw',None);record.pop('calculator_results',None)
            r['record']=record;write(path,r)
            r['semantic']=grounded.judge(client(),record,case,cards)
            r['scorecard']=brief.evaluate(record,case,cards,r['semantic']);r['proof_feedback']=grounded.proof_feedback(record,cards)
            r['status']='ok'
        except Exception as e:
            if hasattr(e,'record'):r['record']=e.record
            r.update(status='error',error=str(e).replace(os.getenv('HY3_API_KEY','-not-set-'),'[REDACTED]')[:1000])
        r['new_work_wall_seconds']=round(time.monotonic()-started,3);write(path,r);print(case['id'],method,r['status'],r.get('scorecard',{}).get('score'),flush=True)
    def order(job):
        case_id,method,order_name=job;path=folder/'order'/f'{case_id}_{method}_{order_name}.json'
        if path.exists() and load(path).get('status')=='ok':return
        case=by_id[case_id];base=load(ROOT/'results/brief/v3'/f'{case_id}_counterbrief.json');ordered=copy.deepcopy(cards)
        if order_name=='reverse':ordered.reverse()
        elif order_name=='shuffle':random.Random(20260910).shuffle(ordered)
        r={'case_id':case_id,'method':method,'order':order_name,'protocol_sha256':sha,'answer_sha256':brief.digest(base['record']['answer'])}
        try:
            sem=(grounded.judge if method=='anchored' else brief.judge)(client(),base['record'],case,ordered)
            score=brief.evaluate(base['record'],case,cards,sem)
            r.update(status='ok',semantic=sem,scorecard=score)
        except Exception as e:r.update(status='error',error=str(e).replace(os.getenv('HY3_API_KEY','-not-set-'),'[REDACTED]')[:1000])
        write(path,r);print(case_id,method,order_name,r['status'],r.get('scorecard',{}).get('score'),flush=True)
    if args.phase in {'application','order'}:
        jobs=[(c,m) for c in cases for m in protocol['application_methods']] if args.phase=='application' else [(c,m,o) for c in protocol['order_cases'] for m in ['legacy','anchored'] for o in protocol['orders']]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(app if args.phase=='application' else order,jobs))
    if args.phase=='replay':
        errors=[];n=0
        for p in (folder/'application').glob('*.json'):
            r=load(p)
            if r.get('status')!='ok':continue
            for _ in range(5):
                if brief.digest(brief.evaluate(r['record'],by_id[r['case_id']],cards,r['semantic']))!=brief.digest(r['scorecard']):errors.append(p.name)
            n+=1
        for p in (folder/'order').glob('*.json'):
            r=load(p)
            if r.get('status')!='ok':continue
            base=load(ROOT/'results/brief/v3'/f'{r["case_id"]}_counterbrief.json')
            if brief.digest(brief.evaluate(base['record'],by_id[r['case_id']],cards,r['semantic']))!=brief.digest(r['scorecard']):errors.append(p.name)
            n+=1
        write(folder/'replay_verification.json',{'n':n,'errors':errors,'pass':not errors,'model_calls':0,'protocol_sha256':sha})
        if errors:raise SystemExit('Replay mismatch')
    summarize(folder,protocol)

def summarize(folder,protocol):
    rows=[load(p) for p in (folder/'application').glob('*.json')]
    orders=[load(p) for p in (folder/'order').glob('*.json')]
    result={'application_planned':80,'application_complete':sum(r.get('status')=='ok' for r in rows),'order_planned':48,'order_complete':sum(r.get('status')=='ok' for r in orders),'application':{},'order':{},'paired':{}}
    for split in ['dev','evaluation']:
        for method in protocol['application_methods']:
            rr=[r for r in rows if r['split']==split and r['method']==method];ok=[r for r in rr if r.get('status')=='ok']
            if not rr:continue
            tokens=[]
            for r in ok:
                ts=r['record']['traces']+[r['semantic']['trace']];tokens.append(sum(t.get('usage',{}).get('total_tokens',0) for t in ts))
            result['application'][split+'/'+method]={'n':len(rr),'complete':len(ok),'mean_score_failure_zero':statistics.mean(r.get('scorecard',{}).get('score',0) for r in rr),'mean_pipeline_tokens':statistics.mean(tokens) if tokens else None,'note':'Pipeline tokens count saved draft generation once per method; actual newly billed calls reported separately.'}
        for control in ['full_context','full_context_revision','counterbrief_first_pass']:
            ids=sorted({r['case_id'] for r in rows if r['split']==split});diff=[]
            for cid in ids:
                a=next((r for r in rows if r['case_id']==cid and r['method']=='counterbrief' and r.get('status')=='ok'),None)
                b=next((r for r in rows if r['case_id']==cid and r['method']==control and r.get('status')=='ok'),None)
                if a and b:diff.append(a['scorecard']['score']-b['scorecard']['score'])
            if diff:result['paired'][split+'/counterbrief-minus-'+control]={'n':len(diff),'mean':statistics.mean(diff),'wins':sum(d>0 for d in diff),'ties':sum(d==0 for d in diff),'losses':sum(d<0 for d in diff)}
    for method in ['legacy','anchored']:
        out={}
        for cid in protocol['order_cases']:
            rr=[r for r in orders if r['case_id']==cid and r['method']==method and r.get('status')=='ok']
            if rr:
                values=[r['scorecard']['score'] for r in rr];out[cid]={'scores':{r['order']:r['scorecard']['score'] for r in rr},'range':max(values)-min(values),'n':len(values)}
        result['order'][method]=out
    write(folder/'summary.json',result)
    import csv
    with (folder/'complete_results.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case_id','split','method','status','score','gates'])
        for r in rows:w.writerow([r['case_id'],r['split'],r['method'],r.get('status'),r.get('scorecard',{}).get('score'),json.dumps(r.get('scorecard',{}).get('gates',[]))])
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
