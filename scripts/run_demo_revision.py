"""Create a new source-reviewed Hy3 demonstration record; retain original experiment."""
import argparse,copy,datetime,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=None
sys.path.insert(0,str(ROOT/'src'))
from chronofin import brief,pdf_research_v5 as native,pdf_research
from chronofin.native_generation_v5 import RULES
from chronofin.config import Hy3Config
from chronofin.runtime import RateLimitedClient,safe_error

def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
    global WORK
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.execute:parser.error('--execute is required for billable Hy3 calls')
    WORK=args.output.resolve()
    if WORK.exists() and any(WORK.iterdir()):parser.error('Output must be a new or empty directory')
    WORK.mkdir(parents=True,exist_ok=True)
    cfg=Hy3Config.from_env();assert cfg.model=='hy3' and cfg.base_url=='https://tokenhub.tencentmaas.com/v1'
    client=RateLimitedClient(cfg,max_attempts=3)
    origin=ROOT/'results/native_pdf/v5/TC01.json';original=json.loads(origin.read_text());record=copy.deepcopy(original['record'])
    case=next(j['case'] for j in json.loads((ROOT/'data/native/cases.json').read_text()) if j['id']=='TC01')
    pdf=args.pdf.read_bytes()
    assert hashlib.sha256(pdf).hexdigest()==record['source_document']['sha256']
    doc=pdf_research.document(pdf,record['source_document'],ROOT)
    selected=pdf_research.retrieve(doc,case['question'],case['as_of'])
    assert brief.digest(selected)==record['source_selection']['selection_sha256']
    for fact in record['evidence']:
        assert any(''.join(fact['quote'].split()) in ''.join(c['text'].split()) for c in selected),fact['id']
    system=brief.GENERATOR+brief.COUNTER_INSTRUCTIONS+RULES
    prompt={'query':brief.public_case(case),'evidence':record['evidence'],'numeric_registry':record['numeric_registry'],'draft':record['answer'],'compiled_calculations':record['compiled_calculations'],
        'review_task':'基于财报原文核查并修订完整研究简报。保留已有claim ID、引用ID及数字绑定关系，必要时纠正措辞，不新增无原文支持的内容。F12原文的555亿元和10%属于金融科技及企业服务业务合计，不能归为企业服务子项；金融科技增长与企业服务AI需求各有不同因素。AI与业务改善的关联要归因于公司披露，不能把定性关联说成已测算的AI收益贡献。资本开支是总体口径，未单列AI投资回报。所有正文、摘要和数字注释口径一致。summary控制在160个汉字以内，先述收入及两种经营盈利，再述现金流与投入约束，保留AI投资回报未知边界。完整输出原JSON结构，产品简报中不出现修订、更正、原稿或内部指令。'}
    write(WORK/'revision_protocol.json',{'origin':'results/native_pdf/v5/TC01.json','origin_sha256':hashlib.sha256(origin.read_bytes()).hexdigest(),'system':system,'prompt':prompt,'model':'hy3','scope':'Separate demonstration revision and fresh judgment; excluded from original 12-case regression and all comparative aggregates.'})
    started=time.monotonic();out={'status':'running','mode':'replay_pdf','id':'TC01_demo','record':record,'sources':original['sources'],'judge_attempts':[]}
    try:
        answer,trace=client.complete_json(system,json.dumps(prompt,ensure_ascii=False))
        write(WORK/'revision_response.json',{'answer':answer,'trace':trace.to_dict()})
        brief.validate_answer(answer)
        record['answer']=answer;record['answer_sha256']=brief.digest(answer);record['traces'].append(trace.to_dict())
        record['demo_revision']={'parent_record':'results/native_pdf/v5/TC01.json','parent_record_sha256':hashlib.sha256(origin.read_bytes()).hexdigest(),'parent_answer_sha256':brief.digest(original['record']['answer']),'input_sha256':brief.digest(prompt),'system_sha256':brief.digest(system),'response':answer,'trace':trace.to_dict()}
        facts=[{**f,'text':f['quote'],'status':'source_excerpt'} for f in record['evidence']]
        audit_cards=selected+facts
        previous=None
        for attempt in range(2):
            sem=native.judge(client,record,case,audit_cards,previous);out['judge_attempts'].append(sem)
            write(WORK/'judge_attempts.json',out['judge_attempts'])
            try:score=brief.evaluate(record,case,audit_cards,sem)
            except ValueError as e:
                previous={'judgment':sem['judgment'],'error':str(e)};out['judge_attempts'][-1]['validation_error']=str(e)
                if attempt==1:raise
            else:break
        out.update(status='ok',stage='complete',semantic=sem,scorecard=score,
            replay_material={'audit_cards':facts,'reference_case':case},
            protocol_sha256=hashlib.sha256((WORK/'revision_protocol.json').read_bytes()).hexdigest(),
            source_audit_sha256=brief.digest(audit_cards),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_seconds=round(time.monotonic()-started,3),
            scope='Source-reviewed demonstration revision with a new Hy3 judgment; not an additional independent benchmark question and not included in frozen comparative results.')
        assert brief.digest(brief.evaluate(record,case,facts,sem))==brief.digest(score)
        write(WORK/'TC01_demo.json',out)
        print(json.dumps({'status':'ok','score':score['score'],'summary':answer['summary'],'claims':[(c['id'],c['text']) for c in answer['claims']],'wall_seconds':out['wall_seconds']},ensure_ascii=False),flush=True)
    except Exception as e:
        out.update(status='error',error=safe_error(str(e),cfg.api_key));write(WORK/'revision_failed.json',out);raise
if __name__=='__main__':main()
