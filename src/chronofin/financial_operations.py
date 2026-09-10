"""Compile a small financial-operation vocabulary with explicit unit scales.

Checks arithmetic and compatible units; does not prove economic interpretation.
"""
from decimal import Decimal
from .evaluator.numeric import safe_evaluate

UNITS={
 'USD':('USD',1),'USD million':('USD',1000000),'USD billion':('USD',1000000000),
 'million USD':('USD',1000000),'billion USD':('USD',1000000000),
 '美元':('USD',1),'百万美元':('USD',1000000),'亿美元':('USD',100000000),'十亿美元':('USD',1000000000),
 '人民币元':('CNY',1),'人民币百万元':('CNY',1000000),'人民币亿元':('CNY',100000000),
 '百万元':('CNY',1000000),'亿元':('CNY',100000000),'CNY million':('CNY',1000000),'CNY billion':('CNY',1000000000),
 'HKD million':('HKD',1000000),'亿港元':('HKD',100000000),
 'TWD billion':('TWD',1000000000),'TWD million':('TWD',1000000),
 'thousands shares':('shares',1000),'shares thousand':('shares',1000),'千股':('shares',1000),'股':('shares',1),'亿股':('shares',100000000),
 '%':('proportion',Decimal('.01')),'percentage points':('pp',1),'个百分点':('pp',1),
}

def compile_requests(requests,cards):
    registry={c['id']:c for c in cards if c.get('value')is not None};values={k:c['value']for k,c in registry.items()}
    output=[];errors=[];seen=set()
    for i,r in enumerate(requests[:12],1):
        try:
            ident=r['id'];op=r['op'];ids=r['inputs']
            if not isinstance(ident,str) or not ident.startswith('K') or ident in seen:raise ValueError('invalid/duplicate calculation ID')
            seen.add(ident)
            if not isinstance(ids,list)or len(ids)!=(1 if op=='convert'else 2):raise ValueError('invalid number of operands')
            a=registry[ids[0]];da,sa=UNITS[a['unit']]
            if op=='convert':
                unit=r['target_unit'];db,sb=UNITS[unit]
                if da!=db:raise ValueError('cannot convert currency/dimension')
                expression=f"{ids[0]}*({sa}/{sb})"
            else:
                b=registry[ids[1]];db,sb=UNITS[b['unit']]
                if da!=db:raise ValueError('incompatible currency/dimension')
                if op=='ratio_percent':expression=f"({ids[0]}*{sa})/({ids[1]}*{sb})*100";unit='%'
                elif op=='growth_percent':expression=f"(({ids[0]}*{sa})/({ids[1]}*{sb})-1)*100";unit='%'
                elif op=='difference':expression=f"{ids[0]}-{ids[1]}*({sb}/{sa})";unit=a['unit']
                else:raise ValueError('operation not supported')
            value=safe_evaluate(expression,values)
            output.append({'id':ident,'expression':expression,'value':round(value,3),'unit':unit,'evidence_ids':ids})
        except (KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError)as e:errors.append({'request_index':i,'request':r,'error':str(e)})
    return output,errors
