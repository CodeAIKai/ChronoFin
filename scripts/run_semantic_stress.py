"""Controlled synthetic money equivalence versus semantic corruption.

These are constructed unit tests of judging, not real company disclosures.
One exact amount per claim avoids ambiguous automated number correspondence.
"""
import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief,grounded
from chronofin.config import Hy3Config
from chronofin.runtime import RateLimitedClient,safe_error

def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def dataset():
    jobs=[]
    bases=[('1.55','USD billion','亿美元','10'),('2.9','USD billion','亿美元','10'),
           ('0.125','USD billion','万美元','100000'),('52103','USD million','亿美元','0.01'),
           ('43.2','USD billion','万美元','100000'),('17729','USD million','亿美元','0.01')]
    for i,(value,unit,target,factor) in enumerate(bases,1):
        correct=Decimal(value)*Decimal(factor)
        for mutation in ['equivalent','tenfold','period','entity','forecast_as_fact']:
            amount=correct*10 if mutation=='tenfold' else correct;company='虚构乙公司' if mutation=='entity' else '虚构甲公司'
            source={'id':'S1','source_id':'SYNTHETIC','entity':'虚构甲公司','published_at':'2025-02-01','value':float(value),'unit':unit,
                    'text':f'虚构甲公司 FY2024 全年营业利润为 {value} {unit}。','status':'observed','role':'context'}
            year='FY2023' if mutation=='period' else 'FY2024'
            if mutation=='forecast_as_fact':source.update(text=f'管理层预计虚构甲公司 FY2025 全年营业利润为 {value} {unit}；这是指引，没有实际结果。',status='forecast');year='FY2025'
            text=f'{company} {year} 全年已经实现营业利润 {amount} {target}。'
            answer={'answerability':'answerable','summary':text,'claims':[{'id':'C1','text':text,'kind':'fact','role':'context','evidence_ids':['S1'],
                    'numbers':[{'source_id':'S1','value':float(value),'unit':unit}]}],'calculations':[],'limitations':[],
                    'follow_up':[{'action':'查下一份年报同口径营业利润','reason':'检验利润变化的持续性','evidence_ids':['S1']}]}
            case={'id':f'U{i:02d}_{mutation}','question':'根据给定材料陈述该公司的营业利润。','as_of':'2025-06-01','required':['S1'],'counter':[],
                  'limitations':[],'expected_answerability':'answerable'}
            record={'answer':answer,'evidence':[source],'excluded_ids':[],'traces':[],'answer_sha256':brief.digest(answer)}
            jobs.append({'id':case['id'],'base':i,'mutation':mutation,'expected_supported':mutation=='equivalent','case':case,'cards':[source],'record':record})
    return jobs
def summarize(folder,jobs):
    rows=[json.loads(p.read_text())for p in (folder/'records').glob('*.json')];out={'planned':len(jobs)*2,'records':len(rows),'complete':sum(r.get('status')=='ok'for r in rows),'scope':'Constructed synthetic monetary and semantic contrast set; not real-world accuracy.','methods':{}}
    for method in ['legacy','anchored']:
        rr=[r for r in rows if r['method']==method];ok=[r for r in rr if r.get('status')=='ok']
        positive=[r for r in ok if r['expected_supported']];negative=[r for r in ok if not r['expected_supported']]
        out['methods'][method]={'n':len(rr),'accuracy_failure_wrong':sum(r.get('decision_correct',False) for r in rr)/len(rr) if rr else None,
          'equivalent_accepted':sum(r['predicted_supported']for r in positive),'equivalent_planned':6,
          'semantic_or_magnitude_errors_rejected':sum(not r['predicted_supported']for r in negative),'negative_planned':24,
          'by_mutation':{m:{'n':sum(r['mutation']==m for r in rr),'correct':sum(r['mutation']==m and r.get('decision_correct',False) for r in rr)}for m in ['equivalent','tenfold','period','entity','forecast_as_fact']}}
    write(folder/'summary.json',out);print(json.dumps(out,ensure_ascii=False,indent=2))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args();jobs=dataset();folder=ROOT/'results/semantic_stress/v1';folder.mkdir(parents=True,exist_ok=True)
    files=['scripts/run_semantic_stress.py','src/chronofin/brief.py','src/chronofin/grounded.py','src/chronofin/reliability.py','src/chronofin/runtime.py']
    protocol={'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in files},'jobs':jobs,
              'primary_decision':'Supported only when claim verdict supported AND kind/scope/numbers checks true. Deterministic money equivalence does not override semantic failures.'}
    sha=brief.digest(protocol);p=folder/'protocol.json'
    if p.exists() and json.loads(p.read_text())['sha256']!=sha:raise SystemExit('Protocol changed')
    write(p,{'sha256':sha,**protocol})
    if args.execute:
        cfg=Hy3Config.from_env()
        if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('Official Hy3 required')
        def work(pair):
            job,method=pair;p=folder/'records'/(job['id']+'_'+method+'.json')
            if p.exists():
                if json.loads(p.read_text()).get('status')=='ok':return
                write(folder/'attempt_history'/(p.stem+'.'+str(time.time_ns())+'.json'),json.loads(p.read_text()))
            r={k:job[k] for k in ['id','base','mutation','expected_supported']};r.update(method=method,protocol_sha256=sha)
            try:
                sem=(brief.judge if method=='legacy' else grounded.judge)(RateLimitedClient(cfg,max_attempts=3),job['record'],job['case'],job['cards'])
                r['semantic']=sem;r['scorecard']=brief.evaluate(job['record'],job['case'],job['cards'],sem)
                c=sem['judgment']['claims'][0];supported=c['verdict']=='supported' and all(c[k] for k in ['kind_valid','scope_valid','numbers_consistent'])
                r.update(status='ok',predicted_supported=supported,decision_correct=supported==job['expected_supported'])
            except Exception as e:r.update(status='error',error=safe_error(str(e),cfg.api_key))
            write(p,r);print(job['id'],method,r['status'],r.get('decision_correct'),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(work,[(j,m)for j in jobs for m in ['legacy','anchored']]))
    summarize(folder,jobs)

if __name__=='__main__':main()
