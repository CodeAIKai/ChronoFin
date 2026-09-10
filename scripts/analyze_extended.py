"""Derive cross-experiment statistics from saved observations, no model calls."""
import collections
import datetime
import hashlib
import json
from pathlib import Path
import random
import statistics

ROOT=Path(__file__).resolve().parents[1]
def load(p,default=None):return json.loads(p.read_text())if p.exists() else default
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def cluster_interval(groups):
    if not groups:return None
    rng=random.Random(20260910);names=sorted(groups);values=[]
    for _ in range(2000):values.append(statistics.mean(x for n in rng.choices(names,k=len(names))for x in groups[n]))
    values.sort();return [values[49],values[1949]]
def main():
    cases={c['id']:c for c in load(ROOT/'data/brief/cases.json')}
    out={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model_calls':0}
    rows=[load(p)for p in (ROOT/'results/grounded/v1/application').glob('*.json')]
    index={(r['case_id'],r['method']):r for r in rows};paired={}
    for control in ['full_context','full_context_revision','counterbrief_first_pass']:
        groups=collections.defaultdict(list);diff=[]
        for cid,c in cases.items():
            if c['split']!='evaluation':continue
            a=index.get((cid,'counterbrief'));b=index.get((cid,control))
            if a and b and a.get('status')==b.get('status')=='ok':
                d=a['scorecard']['score']-b['scorecard']['score'];diff.append(d);groups[c['source_group']].append(d)
        paired[control]={'n':len(diff),'mean_difference':statistics.mean(diff),'source_group_bootstrap95':cluster_interval(groups),
                         'source_groups':len(groups),'note':'Small author-visible regression; cross-source cases overlap other groups. CI is exploratory.'}
    out['grounded_paired']=paired
    order=load(ROOT/'results/grounded/v1/summary.json')['order'];out['order_reliability']={}
    for method,ss in order.items():
        rr=[s['range']for s in ss.values()];out['order_reliability'][method]={'n_answers':len(rr),'judgments_per_answer':4,'mean_range':statistics.mean(rr),'max_range':max(rr),'range_over5':sum(x>5 for x in rr)}
    out['native_versions']={}
    for version in ['v1','v2','v3','v4','v5']:
        summary=load(ROOT/'results/native_pdf'/version/'summary.json')
        if not summary:continue
        rr=summary['records'];scores=[r['score']for r in rr if r.get('status')=='ok'and r.get('score')is not None]
        out['native_versions'][version]={'planned':summary['planned'],'completed':summary['complete'],'mean_score_failure_zero':sum(scores)/summary['planned'],
                                        'mean_success_only':statistics.mean(scores)if scores else None,'n_scored':len(scores),
                                        'cases':[{'id':r['id'],'status':r['status'],'score':r.get('score')}for r in rr]}
    external=load(ROOT/'results/external_human/v3/summary.json',{});out['external_human']=external
    external_rows=[load(p)for p in (ROOT/'results/external_human/v3/records').glob('*.json')]
    disagreement=[];calibration={}
    for split in ['development','new_response_validation']:
        for method in ['holistic_v2','operational_v3']:
            rr=[r for r in external_rows if r['split']==split and r['method']==method];groups=collections.defaultdict(list)
            for r in rr:groups[r['company']].append(int(r.get('prediction')==r['human_label']))
            if not rr:continue
            calibration[split+'/'+method]={'accuracy_cluster95':cluster_interval(groups),'n':len(rr),
                'mean_self_confidence':statistics.mean(r.get('confidence',0)or 0 for r in rr),
                'mean_binary_confidence_brier':statistics.mean(((r.get('confidence',0)or 0)-int(r.get('prediction')==r['human_label']))**2 for r in rr),
                'note':'Post-hoc diagnostic of confidence in predicted class, not multiclass Brier or a calibrated probability.'}
            for r in rr:
                if r.get('prediction')!=r['human_label']:
                    disagreement.append({k:r.get(k)for k in ['id','uid','split','company','method','human_label','prediction','candidate_sha256','reference_conflict']}|{'reason':r.get('judgment',{}).get('reason')})
    out['external_confidence_diagnostics']=calibration
    write(ROOT/'results/external_human/v3/disagreements.json',disagreement)
    out['semantic_stress']=load(ROOT/'results/semantic_stress/v1/summary.json',{})
    traces={};fallback=set()
    def walk(x):
        if isinstance(x,dict):
            if x.get('model')=='hy3'and isinstance(x.get('usage'),dict)and ('prompt_hash'in x or 'latency_seconds'in x):
                key=x.get('request_id_sha256')
                if not key:key=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest();fallback.add(key)
                traces.setdefault(key,x)
            for value in x.values():walk(value)
        elif isinstance(x,list):
            for value in x:walk(value)
    for name in ['brief','grounded','external_human','native_pdf','semantic_stress','native_validation']:
        for p in (ROOT/'results'/name).rglob('*.json'):
            if p.name!='protocol.json':walk(load(p))
    for name in ['live_pdf_result.json','live_custom_result.json']:walk(load(ROOT/'audit'/name,{}))
    for p in (ROOT/'audit/live_history').rglob('*_result.json'):walk(load(p,{}))
    inputs=sum(t['usage'].get('prompt_tokens',0)for t in traces.values());outputs=sum(t['usage'].get('completion_tokens',0)for t in traces.values())
    out['usage_lower_bound']={'unique_successful_request_traces':len(traces),'fallback_trace_digest_count':len(fallback),'input_tokens':inputs,'output_tokens':outputs,
        'total_tokens':sum(t['usage'].get('total_tokens',0)for t in traces.values()),'uncached_list_price_estimate_cny':(inputs+4*outputs)/1_000_000,
        'price_assumption':'Hy3 listed 2026-09-08 input CNY1/million and output CNY4/million; ignores cached-input discounts, free credits and unlogged failures.',
        'price_source':'https://cloud.tencent.com/document/product/1823/130055',
        'scope':'New brief/grounded/external/native/stress experiments and saved live browser calls; request hashes deduplicate reused drafts and repeated copies. Not an exact account bill.'}
    write(ROOT/'results/extended_analysis.json',out)
    print(json.dumps({k:v for k,v in out.items()if k not in ['external_human','external_confidence_diagnostics']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
