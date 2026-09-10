"""Reproducible native-PDF experiment, preserving every successful stage."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief,pdf_research_v3 as native
from chronofin.config import Hy3Config
from chronofin.runtime import RateLimitedClient,safe_error

def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sources():
    original,_,_=brief.read_data(ROOT);pins=json.loads((ROOT/'data/brief/source_snapshots.json').read_text())
    out=json.loads((ROOT/'data/native/sources.json').read_text())
    for s in original:
        if s['id'] in {'meta24','amazon24'}:
            p=next(p for p in pins if p['source_id']==s['id']);out.append({**s,'sha256':p['sha256'],'cache_path':'data/cache/brief/'+s['id']+'.pdf'})
    return {s['id']:s for s in out}
def get_pdf(s):
    p=ROOT/s['cache_path']
    if not p.exists():
        req=urllib.request.Request(s['url'],headers={'User-Agent':'Mozilla/5.0'})
        raw=urllib.request.urlopen(req,timeout=60).read()
        if not raw.startswith(b'%PDF'):raise ValueError('Official URL did not return PDF. Download in a normal browser to '+str(p))
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=s['sha256']:raise ValueError('Official source bytes changed')
    return raw
def export(result):
    full=result.pop('native_replay_material',None)
    if full:
        result['raw_source_audit_sha256']=brief.digest(full)
        result['replay_material']={'audit_cards':[c for c in full['audit_cards'] if c['id'].startswith('F')],'reference_case':full['reference_case']}
        if result.get('scorecard'):
            replay=brief.evaluate(result['record'],full['reference_case'],result['replay_material']['audit_cards'],result['semantic'])
            if brief.digest(replay)!=brief.digest(result['scorecard']):raise ValueError('Exported score mismatch')
    return result
def summarize(folder,jobs):
    rr=[json.loads((folder/(j['id']+'.json')).read_text()) for j in jobs if (folder/(j['id']+'.json')).exists()]
    out={'planned':len(jobs),'complete':sum(r['status']=='ok' for r in rr),'scope':'12 questions, five official PDFs; three source documents first introduced after v3 application freeze. Author-defined criteria, not external expert gold.',
         'records':[{'id':r['id'],'status':r['status'],'split':r['split'],'score':r.get('scorecard',{}).get('score'),'error':r.get('error'),
                     'extraction':r.get('record',{}).get('extraction_audit'),'wall_seconds':r['wall_seconds'],'source':r.get('record',{}).get('source_document')} for r in rr]}
    write(folder/'summary.json',out)
    import csv
    with (folder/'complete_results.csv').open('w',newline='') as f:
        fields=['id','status','split','score','error','wall_seconds'];w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(out['records'])
    print(json.dumps(out,ensure_ascii=False,indent=2))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    jobs=json.loads((ROOT/'data/native/cases.json').read_text());ss=sources();folder=ROOT/'results/native_pdf/v3';folder.mkdir(parents=True,exist_ok=True)
    files=['scripts/run_native_pdf_v3.py','src/chronofin/pdf_research_v3.py','src/chronofin/native_generation.py','src/chronofin/pdf_research.py','src/chronofin/runtime.py','src/chronofin/grounded.py','src/chronofin/brief.py','data/native/cases.json','data/native/sources.json']
    protocol={'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},'jobs':jobs,'sources':ss,
              'change_from_v2':'Explicit numeric registry, first-draft binding feedback, required verbatim candidate quotes; all twelve cases rerun, including prior losses. No score-triggered retries.',
              'author_reference':'Written before these 12 generations; judge only, never passed to extractor or generator.'}
    sha=brief.digest(protocol);p=folder/'protocol.json'
    if p.exists() and json.loads(p.read_text())['sha256']!=sha:raise SystemExit('Protocol changed: create new version')
    write(p,{'sha256':sha,**protocol})
    if args.execute:
        cfg=Hy3Config.from_env()
        if cfg.model!='hy3' or cfg.base_url!='https://tokenhub.tencentmaas.com/v1':raise ValueError('Official Hy3 required')
        for j in jobs:
            p=folder/(j['id']+'.json')
            if p.exists():
                if json.loads(p.read_text()).get('status')=='ok':continue
                write(folder/'attempt_history'/(j['id']+'.'+str(time.time_ns())+'.json'),json.loads(p.read_text()))
            started=time.monotonic();s=ss[j['source_id']];case=j['case']
            def checkpoint(value):write(ROOT/'data/cache/native_stages_v3'/f'{j["id"]}.json',value)
            try:
                result=native.run(RateLimitedClient(cfg,max_attempts=3),get_pdf(s),s,case['question'],case['as_of'],ROOT,case,checkpoint)
            except native.NativePDFError as e:result=e.result;result['error']=safe_error(str(e),cfg.api_key)
            except Exception as e:result={'status':'error','error':safe_error(str(e),cfg.api_key)}
            result=export(result);result.update(id=j['id'],split=j['split'],protocol_sha256=sha,
                finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_seconds=round(time.monotonic()-started,3))
            write(p,result);print(j['id'],result['status'],result.get('scorecard',{}).get('score'),flush=True)
    summarize(folder,jobs)

if __name__=='__main__':main()
