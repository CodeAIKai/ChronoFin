"""Expose judge disagreement and auditable bilingual monetary conversions.

This layer does not overwrite historical semantic decisions or raise scores.
It requests review when exact arithmetic and an LLM accusation disagree.
"""
from __future__ import annotations
from decimal import Decimal,InvalidOperation
import re

UNIT_SCALE={
    'USD million':('USD',Decimal('1000000')),'USD billion':('USD',Decimal('1000000000')),
    'TWD billion':('TWD',Decimal('1000000000')),
    '百万美元':('USD',Decimal('1000000')),'亿美元':('USD',Decimal('100000000')),
    '十亿美元':('USD',Decimal('1000000000')),'万美元':('USD',Decimal('10000')),
    '万亿美元':('USD',Decimal('1000000000000')),
    'billion USD':('USD',Decimal('1000000000')),'million USD':('USD',Decimal('1000000')),
    'billion TWD':('TWD',Decimal('1000000000')),
}
AMOUNT=re.compile(r'(-?\d[\d,]*(?:\.\d+)?)\s*('+ '|'.join(re.escape(u) for u in sorted(UNIT_SCALE,key=len,reverse=True))+r')')

def money_equal(value,unit,other_value,other_unit):
    if unit not in UNIT_SCALE or other_unit not in UNIT_SCALE:return None
    c,s=UNIT_SCALE[unit];c2,s2=UNIT_SCALE[other_unit]
    if c!=c2:return False
    try:return Decimal(str(value))*s==Decimal(str(other_value))*s2
    except InvalidOperation:return False

def numeric_witnesses(answer,cards):
    index={c['id']:c for c in cards};out=[]
    for claim in answer['claims']:
        refs=[index[x] for x in claim['evidence_ids'] if x in index and index[x].get('value') is not None and index[x].get('unit') in UNIT_SCALE]
        mentions=AMOUNT.findall(claim['text'])
        # Restrict automatic correspondence to unambiguous one-to-one claims.
        if len(refs)!=1 or len(mentions)!=1:continue
        src=refs[0];number,unit=mentions[0];number=number.replace(',','')
        source_value=src['value']
        if source_value<0 and re.search(r'亏损|loss',claim['text'],re.I):source_value=abs(source_value)
        equivalent=money_equal(source_value,src['unit'],number,unit)
        out.append({'claim_id':claim['id'],'source_id':src['id'],'source_value':src['value'],'source_unit':src['unit'],
                    'text_value':number,'text_unit':unit,'numerically_equivalent':equivalent,
                    'scope':'Exact scale/currency equality only; does not prove period/metric/causality'})
    return out

def reliability_envelope(base,repeats,cards,tolerance=5):
    """All included judgments must refer to the same exact answer hash."""
    sha=base['scorecard']['answer_sha256'];accepted=[]
    for r in repeats:
        if r.get('status')=='ok' and r.get('scorecard',{}).get('answer_sha256')==sha:accepted.append(r)
    pool=[base]+accepted
    scores=[r['scorecard']['score'] for r in pool]
    witnesses=numeric_witnesses(base['record']['answer'],cards)
    conflicts=[]
    for r in pool:
        js={c['id']:c for c in r.get('semantic',{}).get('judgment',{}).get('claims',[])}
        for w in witnesses:
            c=js.get(w['claim_id'],{})
            if w['numerically_equivalent'] and c.get('numbers_consistent') is False:
                conflicts.append({'claim_id':w['claim_id'],'judgment':r.get('mutation','original'),
                                 'reason':c.get('reason',''),'witness':w})
    spread=max(scores)-min(scores)
    return {'answer_sha256':sha,'n_judgments':len(pool),'observed_score_interval':[min(scores),max(scores)],
            'range':round(spread,3),'status':'review_required' if spread>tolerance or conflicts else ('sampled_stable' if accepted else 'not_repeated'),
            'numeric_witnesses':witnesses,'arithmetic_judge_conflicts':conflicts,
            'human_validated':False,'interpretation':'Observed interval, not a confidence interval. Historical scores are preserved.'}
