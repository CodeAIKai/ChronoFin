"""Resume only missing stages under the unchanged v3 protocol.

Default dry-run does not make API calls. --execute explicitly resumes online.
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('brief_runner',ROOT/'scripts/run_brief_experiments.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
from chronofin.brief import digest,generate,judge,evaluate,read_data,validate_answer

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--workers',type=int,default=2);args=ap.parse_args()
    folder=ROOT/'results/brief/v3';p=runner.protocol();expected=json.loads((folder/'protocol.json').read_text())
    if p['sha256']!=expected['sha256']:raise SystemExit('v3 protocol changed; restore frozen source before resuming')
    _,cards,cases=read_data(ROOT);by_id={c['id']:c for c in cases};pending=[]
    for path in list(folder.glob('[DE][0-9][0-9]_*.json'))+list((folder/'metaeval').glob('D*.json')):
        if '.failed_' in path.name or '.before_resume_' in path.name:continue
        r=json.loads(path.read_text())
        if r.get('status')!='ok':pending.append((path,r))
    plan=[]
    for path,r in pending:
        valid=False
        if 'record' in r:
            try:
                validate_answer(r['record']['answer']);valid=r['record'].get('answer_sha256')==digest(r['record']['answer'])
            except ValueError:pass
        plan.append({'file':str(path.relative_to(ROOT)),'case_id':r['case_id'],'can_reuse_generation':valid,
                     'stage':'semantic_only' if valid else 'generate_then_semantic'})
    runner.write(folder/'pending_online.json',{'count':len(plan),'stages':plan,'model_calls_in_dry_run':0})
    print(json.dumps({'pending':len(plan),'semantic_only':sum(x['can_reuse_generation'] for x in plan),'execute':args.execute},ensure_ascii=False))
    if not args.execute:return
    # Stop submission of new work promptly after a persistent account failure.
    import threading
    blocked=threading.Event()
    def work(item):
        path,r=item
        if blocked.is_set():return
        c=by_id[r['case_id']]
        archive=folder/'resume_history'/path.parent.name/(path.stem+'.before_resume_'+str(time.time_ns())+'.json')
        archive.parent.mkdir(parents=True,exist_ok=True)
        archive.write_bytes(path.read_bytes())
        started=time.monotonic()
        previous_wall_seconds=r.get('wall_seconds',0) or 0
        try:
            can_reuse=next(x['can_reuse_generation'] for x in plan if x['file']==str(path.relative_to(ROOT)))
            if not can_reuse:r['record']=generate(runner.client(),cards,c,r['strategy'])
            judge_cards=list(reversed(cards)) if r.get('mutation')=='repeat_3' else cards
            r['semantic']=judge(runner.client(),r['record'],c,judge_cards)
            r['scorecard']=evaluate(r['record'],c,cards,r['semantic'])
            r['status']='ok';r.pop('error',None);r.pop('error_type',None)
        except Exception as e:
            if hasattr(e,'record'):r['record']=e.record
            msg=str(e);key=os.environ.get('HY3_API_KEY','')
            if key:msg=msg.replace(key,'[REDACTED]')
            r.update(status='error',error=msg[:1500],error_type=type(e).__name__)
            if 'HTTP 402' in msg:blocked.set()
        r['resume_wall_seconds']=round(time.monotonic()-started,3)
        r['wall_seconds']=round(previous_wall_seconds+r['resume_wall_seconds'],3)
        r['timing_scope']='Cumulative active processing across attempts; excludes downtime between attempts. Not fresh-run latency.'
        r['finished_utc']=runner.stamp()
        r['resumed_utc']=runner.stamp();r['resume_history_file']=str(archive.relative_to(ROOT))
        runner.write(path,r);print(path.name,r['status'],flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(work,pending))
    runner.summarize(folder);runner.summarize_meta(folder/'metaeval');runner.replay(folder,cards,cases,p)
    import subprocess
    subprocess.run([sys.executable,str(Path(__file__).resolve())],check=True) # refresh zero-call pending manifest
    if blocked.is_set():raise SystemExit('Account quota unavailable; remaining items kept pending')

if __name__=='__main__':main()
