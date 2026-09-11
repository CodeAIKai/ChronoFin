"""Check submission integrity independently of project score targets.

A valid package may explicitly contain incomplete online work. Such a package
must never set all_online_completed=true or readiness='ready'.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chronofin.brief import digest,evaluate,read_data

def main():
    errors=[];checks=[]
    def check(name,condition,detail=''):
        checks.append({'name':name,'pass':bool(condition),'detail':detail})
        if not condition:errors.append(name)
    required=['README.md','.env.example','requirements-lock.txt','research_app.py','web/index.html',
       'docs/官方要求与原项目审计.md','docs/调研与方案选择.md','docs/开放式评估方法.md',
       'docs/数据与复现说明.md','docs/最终实验分析报告.md','docs/迭代与评审问题记录.md',
       'docs/项目说明.md','demo/时政_demo.mp4','demo/使用说明.md',
       'results/demo/TC01_demo.json','results/demo/revision_protocol.json','assets/chronofin_demo_actual.gif','audit/demo_recording.json',
       'audit/ui_verification.json','audit/ui_live_verification.json','audit/extended_verification.json',
       'audit/external_source_verification.json','audit/final_tests.log','results/final_status.json']
    check('required_files',all((ROOT/n).is_file() for n in required),','.join(n for n in required if not (ROOT/n).is_file()))
    demo_files=sorted(p.name for p in (ROOT/'demo').iterdir())
    check('single_demo_version',demo_files==sorted(['使用说明.md','时政_demo.mp4']),', '.join(demo_files))
    sources,cards,cases=read_data(ROOT);index={c['id']:c for c in cases}
    check('dataset_unique_and_sourced',len(index)==20 and len({c['id'] for c in cards})==len(cards) and all(c['source_id'] in {s['id'] for s in sources} for c in cards))
    restored=[]
    for version in ['v1','v2','v3']:
        p=json.loads((ROOT/'results/brief'/version/'protocol.json').read_text());missing=[]
        for name,sha in p['files'].items():
            candidates=[ROOT/name,ROOT/'audit/v1_source'/name,ROOT/'audit/v2_source'/name]
            if not any(f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest()==sha for f in candidates):missing.append(name)
        restored.append({'version':version,'missing_frozen_files':missing})
        check('frozen_protocol_'+version,not missing,','.join(missing))
    folder=ROOT/'results/brief/v3'
    paths=[p for p in folder.glob('[DE][0-9][0-9]_*.json') if '.failed_' not in p.name]
    rows=[json.loads(p.read_text()) for p in paths]
    check('complete_attempt_matrix',len(rows)==60 and len({(r['case_id'],r['strategy']) for r in rows})==60)
    recomputed=0;binding_errors=[];models=set()
    all_rows=rows+[json.loads(p.read_text()) for p in (folder/'metaeval').glob('D*.json')]
    for r in all_rows:
        if r.get('status')!='ok':continue
        try:
            card=evaluate(r['record'],index[r['case_id']],cards,r['semantic'])
            if digest(card)!=digest(r['scorecard']):binding_errors.append(r['case_id']+': changed score')
            for t in r['record']['traces']+[r['semantic']['trace']]:models.add(t['model'])
            recomputed+=1
        except Exception as e:binding_errors.append(r['case_id']+': '+str(e))
    check('all_successful_scores_recomputed',not binding_errors,str(recomputed)+' records; '+','.join(binding_errors))
    check('all_models_hy3',models=={'hy3'},str(sorted(models)))
    status=json.loads((ROOT/'results/final_status.json').read_text())
    incomplete=sum(r.get('status')!='ok' for r in rows)
    check('incomplete_work_disclosed',status['final_app_incomplete']==incomplete and status['all_online_completed']==(all(r.get('status')=='ok' for r in all_rows) and all(a==b for a,b in status['experiment_completion'].values())))
    ui_path=ROOT/'audit/ui_verification.json'
    check('real_browser_flows',ui_path.exists() and json.loads(ui_path.read_text()).get('pass') is True)
    live=json.loads((ROOT/'audit/ui_live_verification.json').read_text())
    check('real_live_hy3_flows',live.get('pass') is True and live.get('mocked_model') is False)
    extended=json.loads((ROOT/'audit/extended_verification.json').read_text())
    check('extended_protocols_and_scores',extended.get('pass') is True and extended.get('scores_recomputed',0)>=291 and extended.get('external_metric_rows')==600)
    testlog=(ROOT/'audit/final_tests.log').read_text() if (ROOT/'audit/final_tests.log').exists() else ''
    check('full_tests_pass',bool(re.search(r'Ran (1[6-9][0-9]|[2-9][0-9]{2,}) tests',testlog)) and testlog.rstrip().endswith('OK'))
    gif=ROOT/'assets/chronofin_demo_actual.gif'
    try:
        from PIL import Image
        with Image.open(gif) as im:
            duration=0;unique=set();frames=im.n_frames
            for i in range(frames):
                im.seek(i);duration+=im.info.get('duration',0);unique.add(hashlib.sha256(im.convert('RGB').tobytes()).hexdigest())
        check('actual_demo_under_120_seconds',0<duration<=120000 and frames>=8 and len(unique)>=8,
              f'{duration} ms, {frames} frames, {len(unique)} unique frames')
    except Exception as e:check('actual_demo_under_120_seconds',False,type(e).__name__)
    secret_files=[];secret_pattern=re.compile(rb'sk-[A-Za-z0-9]{24,}')
    for p in ROOT.rglob('*'):
        if not p.is_file() or any(x in p.parts for x in ['.git','__pycache__','.venv','.pytest_cache']):continue
        if p.suffix in {'.py','.json','.jsonl','.md','.txt','.log','.toml','.html','.csv'} or p.name.startswith('.env'):
            if secret_pattern.search(p.read_bytes()):secret_files.append(str(p.relative_to(ROOT)))
    check('no_key_shaped_values',not secret_files,','.join(secret_files))
    check('no_real_environment_file',not (ROOT/'.env').exists())
    report={'integrity_pass':not errors,'all_online_completed':status['all_online_completed'],
            'readiness':'completed_experiments_integrity_passed' if status['all_online_completed'] and not errors else 'needs_completion_or_fix','checks':checks,
            'protocol_snapshots':restored,'errors':errors}
    (ROOT/'audit/artifact_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(bool(errors))

if __name__=='__main__':main()
