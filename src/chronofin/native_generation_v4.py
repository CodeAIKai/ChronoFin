"""Original-preserving native generation with explicit binding diagnostics."""
import copy
import json
from . import brief

RULES='''
即使完全不能回答，claims 也必须保留一条 kind=unknown 的具体拒答原因，不得返回空列表。
这是原生 PDF 抽取证据。quote 是通过连续匹配核验的原文，text 是模型转述，不能假定转述正确；核对两者，无法确定表格列归属时说明未知。
numeric_registry 是唯一可用于 numbers 和计算变量的登记数值；value=null 的资料不能自行登记一个数字。可以在正文审慎叙述其原文，但 numbers 留空且不得拿其 ID 计算。
numbers 的 source_id、value、unit 必须逐字对齐登记项；正文换算需另列可执行计算。禁止因原稿写了某数字就把它当新证据。
用财务读者能理解的语言说明数据限制；不要把脚本名称、JSON 字段或内部错误消息写入简报。
'''

def generate(client,cards,case,strategy='counterbrief'):
    selected,excluded=brief.retrieve(cards,case,strategy)
    registry={c['id']:{'value':c['value'],'unit':c['unit']}for c in selected if c.get('value') is not None}
    system=brief.GENERATOR+brief.COUNTER_INSTRUCTIONS+RULES
    prompt={'query':brief.public_case(case),'evidence':selected,'numeric_registry':registry}
    raw,t=client.complete_json(system,json.dumps(prompt,ensure_ascii=False))
    r={'version':'native-generation-4.0','strategy':'counterbrief','query':brief.public_case(case),'evidence':selected,
       'excluded_ids':excluded,'initial':copy.deepcopy(raw),'answer':copy.deepcopy(raw),'traces':[t.to_dict()],
       'input_sha256':brief.digest(prompt),'numeric_registry':registry}
    try:brief.validate_answer(raw)
    except ValueError as e:
        raw,t=client.complete_json(system,json.dumps({**prompt,'invalid_draft':raw,'schema_error':str(e),'instruction':'修复结构；完全拒答时也返回一条unknown原因，保留真实信息边界。'},ensure_ascii=False))
        r['traces'].append(t.to_dict());r['schema_repaired']=copy.deepcopy(raw);r['answer']=copy.deepcopy(raw)
        try:brief.validate_answer(raw)
        except ValueError as e:raise brief.BriefGenerationError(str(e),r) from e
    generic={**case,'required':[],'counter':[],'limitations':[],'expected_answerability':raw['answerability']}
    diagnostics=brief.evaluate(r,generic,selected)
    from .grounded import proof_feedback
    feedback=proof_feedback(r,selected)
    revision={**prompt,'draft':raw,'deterministic_binding_issues':diagnostics['issues'],'arithmetic_and_identity':feedback,
              'review_task':'先修复登记值/单位绑定与计算错误，再检查能改变结论的反证、口径和未知边界。不得删掉重要反面证据以躲避错误。只依据原文修订。输出完整 JSON。'}
    revised,t=client.complete_json(system,json.dumps(revision,ensure_ascii=False));r['traces'].append(t.to_dict())
    r.update(revision_raw=copy.deepcopy(revised),binding_feedback=diagnostics,proof_feedback=feedback)
    try:brief.validate_answer(revised)
    except ValueError as e:raise brief.BriefGenerationError(str(e),r) from e
    r.update(answer=revised,answer_sha256=brief.digest(revised))
    return r
