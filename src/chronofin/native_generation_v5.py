"""Counterbrief with typed financial operations and bounded proof repair."""
import copy
import json
from . import brief
from .financial_operations import compile_requests

RULES='''
资料为PDF抽取：quote是原文，text是转述；核对两者，不能把抽取没找到说成整份报告未披露。
numeric_registry是numbers绑定的唯一清单。同一Fid只对应一个值，quote里的其他年份数字不能复用该ID登记。可以原文叙述，但未经登记不做精确计算。
第一稿的calculations请留[]，需要计算时另加calculation_requests:[{"id":"K1","op":"ratio_percent|growth_percent|difference|convert","inputs":["F1","F2"],"target_unit":"亿美元"}]。ratio_percent=第一个金额占第二个百分比；growth_percent=本期比上期增长百分比；difference=本期减上期；convert仅1个输入。target_unit仅convert需要。程序自动统一单位和执行，不要自行添加10/1000等换算因子。
第二稿及修复稿只能使用compiled_calculations原样列出的公式和值；未编译成功的计算不能在正文中写成已验证精确结果。表格列或指标缺少可靠登记时说明具体边界。
完全无资料也须给一条kind=unknown的拒答原因，claims不能空；source_notice仅说明文件日期/隔离原因，不包含未来正文。
写给财务读者，不要把JSON字段、脚本名或内部错误写进产品简报。把会计口径和经营推断区分，百分比份额不是市场份额。
'''

def generate(client,cards,case,strategy='counterbrief'):
    selected,excluded=brief.retrieve(cards,case,strategy);registry={c['id']:{'value':c['value'],'unit':c['unit']}for c in selected if c.get('value')is not None}
    system=brief.GENERATOR+brief.COUNTER_INSTRUCTIONS+RULES
    prompt={'query':brief.public_case(case),'evidence':selected,'numeric_registry':registry,'source_notice':case.get('source_notice',{})}
    raw,t=client.complete_json(system,json.dumps(prompt,ensure_ascii=False))
    r={'version':'native-generation-5.0','strategy':'counterbrief','query':brief.public_case(case),'evidence':selected,'excluded_ids':excluded,
       'initial':copy.deepcopy(raw),'answer':copy.deepcopy(raw),'traces':[t.to_dict()],'input_sha256':brief.digest(prompt),'numeric_registry':registry}
    try:brief.validate_answer(raw)
    except ValueError as e:
        raw,t=client.complete_json(system,json.dumps({**prompt,'invalid_draft':raw,'schema_error':str(e),'instruction':'只修复结构，拒答也要unknown结论。'},ensure_ascii=False))
        r['traces'].append(t.to_dict());r['schema_repaired']=copy.deepcopy(raw);r['answer']=copy.deepcopy(raw)
        try:brief.validate_answer(raw)
        except ValueError as e:raise brief.BriefGenerationError(str(e),r)from e
    compiled,errors=compile_requests(raw.get('calculation_requests',[]),selected)
    r.update(compiled_calculations=compiled,operation_errors=errors)
    def issues(answer):
        generic={**case,'required':[],'counter':[],'limitations':[],'expected_answerability':answer['answerability']}
        local=brief.evaluate({**r,'answer':answer},generic,selected)
        approved={c['id']:c for c in compiled};out=list(local['issues'])
        for c in answer['calculations']:
            if c!=approved.get(c['id']):out.append('calculation must match compiled result: '+str(c['id']))
        return out
    feedback=issues(raw)
    review={**prompt,'draft':raw,'binding_issues':feedback,'compiled_calculations':compiled,'operation_errors':errors,
            'review_task':'修订数值绑定和计算；把重要反证、不同期间口径及具体未知边界写清。只使用编译成功的计算。输出完整JSON。'}
    revised,t=client.complete_json(system,json.dumps(review,ensure_ascii=False));r['traces'].append(t.to_dict());r['revision_raw']=copy.deepcopy(revised)
    try:brief.validate_answer(revised)
    except ValueError as e:raise brief.BriefGenerationError(str(e),r)from e
    final_issues=issues(revised);r['pre_repair_proof_issues']=final_issues
    if final_issues:
        fixed,t=client.complete_json(system,json.dumps({**prompt,'draft':revised,'binding_issues':final_issues,'compiled_calculations':compiled,
            'repair_task':'最后一次修复可执行证据错误。numbers仅复制登记项，不能把同一ID绑定另一年度值；计算逐项复制compiled_calculations或省略未验证计算，并同步修正文内相关数值。保留原文支持的重要事实。'},ensure_ascii=False))
        r['traces'].append(t.to_dict());r['proof_repair_raw']=copy.deepcopy(fixed)
        try:brief.validate_answer(fixed)
        except ValueError as e:raise brief.BriefGenerationError(str(e),r)from e
        revised=fixed;final_issues=issues(revised)
    r.update(answer=revised,answer_sha256=brief.digest(revised),final_proof_issues=final_issues)
    return r
