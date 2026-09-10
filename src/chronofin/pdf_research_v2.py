"""Native PDF workflow v2: independent rubric IDs and lossless failure records.

v1 parsing/extraction constraints are retained. Gold criteria enter only the
judge. Exact quote matching does not claim financial semantic correctness.
"""
import copy
import hashlib
import json
from pathlib import Path
from . import brief,grounded,pdf_research
from .pdf_research import document,retrieve,validate_extraction,EXTRACT
from .reliability import numeric_witnesses

class NativePDFError(ValueError):
    def __init__(self,message,result):super().__init__(message);self.result=result

def judge(client,record,case,cards,previous=None):
    inputs={'query':brief.public_case(case),'sources':cards,
            'reference':{k:case[k] for k in ['required','counter','limitations','expected_answerability']},
            'point_definitions':case.get('point_definitions',{}),'candidate':record['answer'],
            'local_numeric_witnesses':numeric_witnesses(record['answer'],cards)}
    system=brief.JUDGE+grounded.ANCHOR_RULES+'''
point_definitions 是评测清单 ID 到核查要求的映射，不是新证据，不得用它替代原文支持。coverage 逐项返回 reference.required/counter 中的短 ID（例如 R1），不要把文字说明当作 ID。最终回答的证据引用仍应只指向 sources。
'''
    if previous:inputs['schema_repair']={'previous_judgment':previous['judgment'],'error':previous['error'],
                        'instruction':'纠正结构遗漏或重复，重新核查并返回完整 JSON；不得因为报错而提高实质评分。'}
    value,trace=client.complete_json(system,json.dumps(inputs,ensure_ascii=False))
    return {'version':'native-source-audit-2.0','judgment':value,'trace':trace.to_dict(),'input_sha256':brief.digest(inputs),
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
        selected=retrieve(doc,question,as_of);case={'question':question,'as_of':as_of}
        facts=[];rejected=[];extraction=None;traces=[]
        provenance={'source_document':{k:v for k,v in doc.items() if k!='chunks'},
                    'source_selection':{'total_chunks':len(doc['chunks']),'selected_ids':[c['id'] for c in selected],
                    'selected_pages':sorted({c['page'] for c in selected}),'selection_sha256':brief.digest(selected)}}
        result['record'].update(provenance);result['sources']=[provenance['source_document']];save()
        if selected:
            result['stage']='extract'
            extraction,t=client.complete_json(EXTRACT,json.dumps({'question':question,'as_of':as_of,'chunks':selected},ensure_ascii=False))
            traces.append(t.to_dict());result['record'].update(extraction_raw=extraction,extraction_traces=traces);save()
            facts,rejected=validate_extraction(extraction,selected)
        provenance.update(pipeline='native_pdf_v2',extraction_raw=extraction,extraction_traces=traces,
            extraction_audit={'facts_proposed':len(extraction.get('facts',[])) if extraction else 0,'facts_accepted':len(facts),'rejected':rejected,
            'raw_response_sha256':brief.digest(extraction),'quote_verification':'whitespace-normalized exact contiguous source match',
            'limitation':'Quote existence and raw numeric equality do not prove fiscal-column or semantic correctness.'})
        result['stage']='generate';result['record'].update(provenance);save()
        try:record=brief.generate(client,facts,case,'counterbrief')
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
                try:result['scorecard']=brief.evaluate(record,reference_case,audit_cards,semantic)
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
