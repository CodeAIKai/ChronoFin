"""Run actual official PDFs through the new end-to-end workflow."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief,pdf_research
from chronofin.runtime import RateLimitedClient,safe_error
from chronofin.config import Hy3Config

def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    sources,cards,cases=brief.read_data(ROOT);index={c['id']:c for c in cards};folder=ROOT/'results/native_pdf/v1';folder.mkdir(parents=True,exist_ok=True)
    jobs=[]
    for cid,sid in [('D01','meta24'),('D02','amazon24')]:
        c=copy.deepcopy(next(c for c in cases if c['id']==cid));s=next(s for s in sources if s['id']==sid)
        # Same material requirements, now self-contained because PDF chunk IDs differ.
        c['required']=[k+': '+index[k]['text'] for k in c['required']]
        c['counter']=[k+': '+index[k]['text'] for k in c['counter']]
        jobs.append({'id':sid+'_after','source':s,'case':c})
    c=copy.deepcopy(jobs[0]['case']);c.update(as_of='2025-01-28',required=[],counter=[],limitations=['给定原件尚未在截止日前公开，不能根据其内容作答。'],expected_answerability='unanswerable')
    jobs.append({'id':'meta24_before','source':jobs[0]['source'],'case':c})
    files=['src/chronofin/pdf_research.py','src/chronofin/runtime.py','src/chronofin/grounded.py','src/chronofin/brief.py','scripts/run_native_pdf_trials.py']
    protocol={'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},'jobs':jobs,'source_pins':json.loads((ROOT/'data/brief/source_snapshots.json').read_text()),
              'scope':'Three native-PDF end-to-end cases from two already-known official reports; not unseen-company generalization.'}
    sha=brief.digest(protocol);p=folder/'protocol.json'
    if p.exists() and json.loads(p.read_text())['sha256']!=sha:raise SystemExit('Create a new version after code changes')
    write(p,{'sha256':sha,**protocol})
    if args.execute:
        cfg=Hy3Config.from_env()
        if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('Official Hy3 required')
        for job in jobs:
            p=folder/(job['id']+'.json')
            if p.exists() and json.loads(p.read_text()).get('status')=='ok':continue
            if p.exists():
                archive=folder/'attempt_history'/(job['id']+'.'+str(time.time_ns())+'.json');archive.parent.mkdir(parents=True,exist_ok=True);archive.write_bytes(p.read_bytes())
            source=job['source'];case=job['case'];started=time.monotonic()
            try:
                data=(ROOT/'data/cache/brief'/(source['id']+'.pdf')).read_bytes()
                pin=next(x for x in protocol['source_pins'] if x['source_id']==source['id'])
                if hashlib.sha256(data).hexdigest()!=pin['sha256']:raise ValueError('PDF bytes mismatch')
                result=pdf_research.run(RateLimitedClient(cfg,max_attempts=3),data,source,case['question'],case['as_of'],ROOT,case)
                full=result.pop('native_replay_material')
                # Raw full-page windows stay in excluded cache. Deterministic score
                # replay needs only cited fact excerpts and the saved judgment.
                write(ROOT/'data/cache/native_replay'/f'{job["id"]}.json',full)
                result['replay_material']={'audit_cards':[x for x in full['audit_cards'] if x['id'].startswith('F')],'reference_case':case}
                result['raw_source_audit_sha256']=brief.digest(full)
                again=brief.evaluate(result['record'],case,result['replay_material']['audit_cards'],result['semantic'])
                if brief.digest(again)!=brief.digest(result['scorecard']):raise ValueError('Exported score replay mismatch')
            except Exception as e:result={'status':'error','error':safe_error(str(e),cfg.api_key)}
            result.update(id=job['id'],protocol_sha256=sha,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_seconds=round(time.monotonic()-started,3))
            write(p,result);print(job['id'],result['status'],result.get('scorecard',{}).get('score'),flush=True)
    rows=[json.loads((folder/(j['id']+'.json')).read_text()) for j in jobs if (folder/(j['id']+'.json')).exists()]
    summary={'planned':len(jobs),'complete':sum(r['status']=='ok' for r in rows),'records':[{'id':r['id'],'status':r['status'],'score':r.get('scorecard',{}).get('score'),'error':r.get('error'),
                'extraction':r.get('record',{}).get('extraction_audit'),'source':r.get('record',{}).get('source_document')} for r in rows]}
    write(folder/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
