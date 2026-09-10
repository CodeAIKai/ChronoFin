"""Offline verification of extended protocols, scores, labels and span binding."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from chronofin import brief
from chronofin.span_evidence import bind_judgment,candidate_spans
from chronofin.financial_operations import compile_requests
from run_external_human_audit_v2 import metrics

def load(p):return json.loads(p.read_text())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--with-source',action='store_true');args=ap.parse_args()
    checks=[];errors=[];count=0
    def check(name,condition,detail=''):
        checks.append({'name':name,'pass':bool(condition),'detail':detail})
        if not condition:errors.append(name)
    paths=[]
    for folder in ['grounded','external_human','native_pdf','semantic_stress','native_validation']:
        paths+=sorted((ROOT/'results'/folder).glob('*/protocol.json'))
    for p in paths:
        protocol=load(p);missing=[]
        for name,sha in protocol['files'].items():
            q=ROOT/name
            if not q.exists()or hashlib.sha256(q.read_bytes()).hexdigest()!=sha:missing.append(name)
        core={k:v for k,v in protocol.items()if k!='sha256'}
        check('protocol:'+str(p.relative_to(ROOT)),not missing and brief.digest(core)==protocol['sha256'],','.join(missing))
    _,cards,cases=brief.read_data(ROOT);byid={c['id']:c for c in cases}
    for p in (ROOT/'results/grounded/v1/application').glob('*.json'):
        r=load(p)
        if r.get('status')!='ok':continue
        check('score:'+p.name,brief.digest(brief.evaluate(r['record'],byid[r['case_id']],cards,r['semantic']))==brief.digest(r['scorecard']));count+=1
    for p in (ROOT/'results/grounded/v1/order').glob('*.json'):
        r=load(p)
        if r.get('status')!='ok':continue
        base=load(ROOT/'results/brief/v3'/(r['case_id']+'_counterbrief.json'))
        check('order:'+p.name,brief.digest(brief.evaluate(base['record'],byid[r['case_id']],cards,r['semantic']))==brief.digest(r['scorecard']));count+=1
    for folder in list((ROOT/'results/native_pdf').glob('v*'))+list((ROOT/'results/native_validation').glob('v*')):
        for p in (folder/'records').glob('*.json')if (folder/'records').exists()else folder.glob('*.json'):
            r=load(p)
            if r.get('status')!='ok' or 'replay_material'not in r:continue
            material=r['replay_material'];again=brief.evaluate(r['record'],material['reference_case'],material['audit_cards'],r['semantic'])
            check('native_score:'+str(p.relative_to(ROOT)),brief.digest(again)==brief.digest(r['scorecard']));count+=1
            sem=r['semantic']
            if 'raw_judgment'in sem:
                compiled,binding=bind_judgment(sem['raw_judgment'],candidate_spans(r['record']['answer']))
                check('candidate_span:'+str(p.relative_to(ROOT)),compiled==sem['judgment'] and binding==sem['span_binding'])
            record=r['record']
            if record.get('version')=='native-generation-5.0':
                draft=record.get('schema_repaired',record['initial']);cc,ee=compile_requests(draft.get('calculation_requests',[]),record['evidence'])
                check('compiled_operations:'+str(p.relative_to(ROOT)),cc==record['compiled_calculations']and ee==record['operation_errors'])
    folder=ROOT/'results/semantic_stress/v1';protocol=load(folder/'protocol.json');jobs={j['id']:j for j in protocol['jobs']}
    for p in (folder/'records').glob('*.json'):
        r=load(p)
        if r.get('status')!='ok':continue
        j=jobs[r['id']];check('stress_score:'+p.name,brief.digest(brief.evaluate(j['record'],j['case'],j['cards'],r['semantic']))==brief.digest(r['scorecard']));count+=1
    folder=ROOT/'results/external_human/v3';rows=[load(p)for p in (folder/'records').glob('*.json')];summary=load(folder/'summary.json')
    check('external_complete_matrix',len(rows)==600 and len({(r['uid'],r['method'])for r in rows})==600)
    for split in ['development','new_response_validation']:
        for method in ['holistic_v2','operational_v3']:
            rr=[r for r in rows if r['split']==split and r['method']==method]
            check('external_metrics:'+split+'/'+method,metrics(rr)==summary['groups'][split+'/'+method])
    matrices=[('grounded/v1/application',80),('grounded/v1/order',48),('native_pdf/v5',12),('native_validation/v2/records',30),('semantic_stress/v1/records',60),('external_human/v3/records',600)]
    for relative,expected in matrices:
        rr=[load(p)for p in (ROOT/'results'/relative).glob('*.json')]
        attempted=[r for r in rr if 'status'in r]
        check('actual_record_matrix:'+relative,len(attempted)==expected and all(r['status']=='ok'for r in attempted),f'{len(attempted)}/{expected}')
    final=load(ROOT/'results/final_status.json')
    for key,(done,total)in final['experiment_completion'].items():check('final_completion:'+key,done==total,f'{done}/{total}')
    if args.with_source:
        from run_external_human_v3 import samples
        ss={s['uid']:s for s in samples()};fail=[]
        for r in rows:
            s=ss[r['uid']]
            payload={k:s[k]for k in ['question','reference','candidate','evidence']}
            if r['human_label']!=s['human_label']or r['candidate_sha256']!=s['candidate_sha256']or r['input_sha256']!=brief.digest(payload):fail.append(r['uid'])
        check('published_labels_and_inputs_reconstructed',not fail,','.join(fail))
        source_audit={'pass':not fail,'records_verified':len(rows),'dataset_commit':'cc39aeb4afdf33909ee1412188bf89035950c2eb',
                      'source_manifest_sha256':hashlib.sha256((ROOT/'audit/financebench_download.json').read_bytes()).hexdigest(),
                      'same_text_across_dev_and_validation':sum(ss[q+'_dev']['candidate_sha256']==ss[q+'_val']['candidate_sha256']for q in {s['id']for s in ss.values()})}
        (ROOT/'audit/external_source_verification.json').write_text(json.dumps(source_audit,indent=2)+'\n')
    source_check=ROOT/'audit/external_source_verification.json'
    check('published_label_verification_record_present',source_check.exists()and load(source_check).get('pass'))
    models=set();endpoints=set()
    def traces(x):
        if isinstance(x,dict):
            if 'usage'in x and 'prompt_hash'in x and 'model'in x:models.add(x['model']);endpoints.add(x.get('base_url'))
            for value in x.values():traces(value)
        elif isinstance(x,list):
            for value in x:traces(value)
    for name in ['brief','grounded','external_human','native_pdf','semantic_stress','native_validation']:
        for p in (ROOT/'results'/name).rglob('*.json'):traces(load(p))
    check('all_recorded_model_calls_use_official_hy3',models=={'hy3'}and endpoints=={'https://tokenhub.tencentmaas.com/v1'},str(sorted(models)))
    result={'pass':not errors,'scores_recomputed':count,'external_metric_rows':len(rows),'online_model_calls':0,
            'raw_external_source_checked_in_this_run':args.with_source,'checks':checks,'errors':errors}
    (ROOT/'audit/extended_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='checks'},ensure_ascii=False,indent=2));raise SystemExit(bool(errors))

if __name__=='__main__':main()
