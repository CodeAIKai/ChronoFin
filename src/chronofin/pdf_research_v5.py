"""Native PDF workflow v4: source line spans and candidate span identities.

v1 parsing/extraction constraints are retained. Gold criteria enter only the
judge. Exact quote matching does not claim financial semantic correctness.
"""
import copy
import hashlib
import json
from pathlib import Path
from . import brief,grounded,pdf_research
from . import native_generation_v5 as native_generation
from .pdf_research import document,retrieve
from .span_evidence import EXTRACT as BASE_EXTRACT,indexed_chunks,validate_span_extraction as validate_extraction,candidate_spans,bind_judgment
from .reliability import numeric_witnesses

EXTRACT=BASE_EXTRACT+'''
涉及同比、利润率或现金转化时，将本期与比较期所需的明确数值分别登记为不同facts；同一ID不能同时表示多个年份/金额。单位要保留每股、千股、百万/亿元等尺度；最多24条，优先用户实际询问的指标及其反证。
'''

class NativePDFError(ValueError):
    def __init__(self,message,result):super().__init__(message);self.result=result

def judge(client,record,case,cards,previous=None):
    inputs={'query':brief.public_case(case),'sources':cards,
            'reference':{k:case[k] for k in ['required','counter','limitations','expected_answerability']},
            'limitation_checks':[{'index':i,'criterion':v}for i,v in enumerate(case['limitations'])],'point_definitions':case.get('point_definitions',{}),'reference_points':[{'id':k,'criterion':v} for k,v in case.get('point_definitions',{}).items()],'candidate':record['answer'],'candidate_spans':candidate_spans(record['answer']),
            'local_numeric_witnesses':numeric_witnesses(record['answer'],cards)}
    system=brief.JUDGE+grounded.ANCHOR_RULES+'''
本版coverage/limitations改变输出协议：每项返回 id（或index）、present、candidate_span_id，不要自己写quote。candidate_span_id只能选择candidate_spans中的SUMMARY、C1等实际ID。程序会复制候选原句，不能用sources的ID。未覆盖则present=false,candidate_span_id:null。
limitations是对limitation_checks的核查，不是枚举候选自己的limitations数组。只能返回limitation_checks指定的index，长度必须完全相同。
逐项按reference_points中对应criterion核查。point_definitions只定义要求，不是新证据；不得把问题里包含一个数字视为候选回答覆盖了该数字。复合criterion需要实质覆盖核心关系与指定口径；一个不同指标的句子不能借来顶替。
'''
    if previous:inputs['schema_repair']={'previous_judgment':previous['judgment'],'error':previous['error'],
                        'instruction':'纠正结构遗漏或重复，重新核查并返回完整 JSON；不得因为报错而提高实质评分。'}
    raw,trace=client.complete_json(system,json.dumps(inputs,ensure_ascii=False))
    value,binding=bind_judgment(raw,candidate_spans(record['answer']))
    return {'version':'native-source-audit-5.0','raw_judgment':raw,'span_binding':binding,'judgment':value,'trace':trace.to_dict(),'input_sha256':brief.digest(inputs),
            'answer_sha256':brief.digest(record['answer']),'judge_prompt_sha256':brief.digest(system)}

def run(client,content,metadata,question,as_of,root=None,reference_case=None,checkpoint=None):
    result={'status':'running','mode':'live_pdf','stage':'source','record':{},'judge_attempts':[]}
    def save():
        if checkpoint:checkpoint(copy.deepcopy(result))
    try:
        # Additional originals are separately pinned; frozen v3 sources stay intact.
        manifest=Path(root)/'data/native/sources.json' if root else None
        match=None
        if manifest and manifest.exists():
            sha=hashlib.sha256(content).hexdigest()
            match=next((s for s in json.loads(manifest.read_text()) if s['sha256']==sha),None)
        if match:metadata={**metadata,**{k:match[k] for k in ['title','entity','published_at','url']}}
        doc=document(content,metadata,root)
        if match:doc['metadata_identity']='pinned_official'
        selected=retrieve(doc,question,as_of);case={'question':question,'as_of':as_of,'source_notice':{'title':doc['title'],'published_at':doc['published_at'],'identity':doc['metadata_identity'],'excluded_for_future_date':doc['published_at']>as_of}}
        facts=[];rejected=[];extraction=None;traces=[]
        provenance={'source_document':{k:v for k,v in doc.items() if k!='chunks'},
                    'source_selection':{'total_chunks':len(doc['chunks']),'selected_ids':[c['id'] for c in selected],
                    'selected_pages':sorted({c['page'] for c in selected}),'selection_sha256':brief.digest(selected)}}
        result['record'].update(provenance);result['sources']=[provenance['source_document']];save()
        if selected:
            result['stage']='extract'
            extraction,t=client.complete_json(EXTRACT,json.dumps({'question':question,'as_of':as_of,'chunks':indexed_chunks(selected)},ensure_ascii=False))
            traces.append(t.to_dict());result['record'].update(extraction_raw=extraction,extraction_traces=traces);save()
            facts,rejected=validate_extraction(extraction,selected)
        provenance.update(pipeline='native_pdf_v5',extraction_raw=extraction,extraction_traces=traces,
            extraction_audit={'facts_proposed':len(extraction.get('facts',[])) if extraction else 0,'facts_accepted':len(facts),'rejected':rejected,
            'raw_response_sha256':brief.digest(extraction),'quote_verification':'Program-copied original line range; whitespace-normalized exact match checked again',
            'limitation':'Quote existence and raw numeric equality do not prove fiscal-column or semantic correctness.'})
        result['stage']='generate';result['record'].update(provenance);save()
        try:record=native_generation.generate(client,facts,case,'counterbrief')
        except brief.BriefGenerationError as e:
            result['record'].update(e.record);result['record'].update(provenance);raise
        record.update(provenance)
        if not selected:record['excluded_ids']=[c['id'] for c in doc['chunks']]
        result['record']=record;save()
        audit_facts=[{**f,'text':f['quote'],'status':'source_excerpt'} for f in facts]
        audit_cards=selected+audit_facts
        result['native_replay_material']={'audit_cards':audit_cards,'reference_case':reference_case}
        if reference_case:
            result['stage']='judge';previous=None
            for attempt in range(2):
                semantic=judge(client,record,reference_case,audit_cards,previous)
                result['judge_attempts'].append(semantic);save()
                try:
                    candidate_text=brief.answer_text(record['answer'])
                    bad=[x.get('id',x.get('index')) for x in semantic['judgment'].get('coverage',[])+semantic['judgment'].get('limitations',[]) if x.get('present') is True and (not x.get('quote') or x['quote'] not in candidate_text)]
                    if bad:raise ValueError('Positive quote must be a verbatim candidate span, not source text; invalid IDs: '+str(bad))
                    result['scorecard']=brief.evaluate(record,reference_case,audit_cards,semantic)
                except ValueError as e:
                    result['judge_attempts'][-1]['validation_error']=str(e)
                    previous={'judgment':semantic['judgment'],'error':str(e)};save()
                    if attempt==1:raise
                else:result['semantic']=semantic;break
        else:
            generic={**case,'required':[],'counter':[],'limitations':[],'expected_answerability':record['answer']['answerability']}
            result['scorecard']=brief.evaluate(record,generic,audit_cards)
        result.update(status='ok',stage='complete');save();return result
    except Exception as e:
        result.update(status='error',error=str(e));save();raise NativePDFError(str(e),result) from e
