"""Evidence-anchored judging and equal-call revision controls.

Extends the frozen v3 module without changing its historical source or scores.
"""
import copy
import json
from . import brief
from .evaluator.numeric import safe_evaluate
from .reliability import numeric_witnesses

VERSION='grounded-audit-1.0'
ANCHOR_RULES='''
额外审计规约：
先核对候选命题与其引用的原资料，再看参考覆盖清单，防止把参考清单当作完整答案。
local_numeric_witnesses 由 Decimal 做精确金额/币种比例换算。true 只证明数字金额等价，不能证明期间、主体或指标口径正确；false 是需要解释的金额冲突。
1 billion=10亿；1 million=100万=0.01亿；1.55 billion USD=15.5亿美元；这些单位常识用于所有公司，示例不是题目答案。
不能因为等价换算、source 顺序或同义改写就判为 contradicted。亏损的正向金额表示与带负号的损益值需区别。
numeric_witnesses 未覆盖的命题必须自行逐数核对；不能把未检测当作通过。
数字相等不代表推断正确：预测写成事实、单季写成年份总量、GAAP 与调整口径混用仍应否定。
对争议命题在 reason 指明候选具体文字、来源 ID 和冲突点；不得笼统说“有误”。
'''

def judge(client,record,case,cards,reverse=False):
    sources=[c for c in cards if c['published_at']<=case['as_of']]
    if reverse:sources=list(reversed(sources))
    inputs={'query':brief.public_case(case),'sources':sources,
            'reference':{k:case[k] for k in ['required','counter','limitations','expected_answerability']},
            'candidate':record['answer'],'local_numeric_witnesses':numeric_witnesses(record['answer'],cards)}
    system=brief.JUDGE+ANCHOR_RULES
    result,trace=client.complete_json(system,json.dumps(inputs,ensure_ascii=False))
    return {'version':VERSION,'judgment':result,'trace':trace.to_dict(),'input_sha256':brief.digest(inputs),
            'answer_sha256':brief.digest(record['answer']),'judge_prompt_sha256':brief.digest(system)}

def neutral_revision(client,record,case,cards):
    """One generic revision after a saved full-context draft: two calls total.

No gold/reference points or counterbrief-specific instructions are exposed.
"""
    result=copy.deepcopy(record)
    prompt={'query':brief.public_case(case),'evidence':result['evidence'],'draft':result['answer'],
            'review_task':'请检查原稿的正确性、清晰度和完整性。仅依据给定材料，在有充分依据时修订。输出完整 JSON。'}
    answer,trace=client.complete_json(brief.GENERATOR,json.dumps(prompt,ensure_ascii=False))
    result['traces'].append(trace.to_dict());result['revision_raw']=copy.deepcopy(answer)
    try:brief.validate_answer(answer)
    except ValueError as e:raise brief.BriefGenerationError(str(e),result) from e
    result.update(version=VERSION,strategy='full_context_revision',answer=answer,answer_sha256=brief.digest(answer))
    return result

def proof_feedback(record,cards):
    """Deterministic evidence for diagnostics; not an oracle or a score override."""
    index={c['id']:c for c in cards}
    numbers={c['id']:c['value'] for c in record['evidence'] if c.get('value') is not None}
    arithmetic=[]
    for c in record['answer'].get('calculations',[]):
        try:
            value=safe_evaluate(c['expression'],numbers)
            arithmetic.append({'id':c['id'],'executed_value':value,'claimed_value':c['value'],'unit':c.get('unit')})
        except (ValueError,KeyError,TypeError,ZeroDivisionError,OverflowError) as e:
            arithmetic.append({'id':c.get('id'),'error':type(e).__name__})
    return {'money':numeric_witnesses(record['answer'],cards),'calculations':arithmetic,
            'citation_identity':[{ 'claim_id':c['id'],'unknown_ids':[x for x in c['evidence_ids'] if x not in index]} for c in record['answer']['claims']]}
