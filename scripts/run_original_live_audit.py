"""Fresh original-project execution; logs separate from historical artifacts."""
import importlib.util
import json
import os
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=Path(os.environ.get('CHRONOFIN_ORIGINAL_ROOT',str(ROOT.parent/'Tencent/code')))
sys.path.insert(0,str(ORIGINAL/'src'))
from chronofin.config import Hy3Config,RetrievalConfig
from chronofin.pipeline import ChronoFinPipeline
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Query,Answerability
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.render import write_json,write_html

def main():
    label=os.environ.get('CHRONOFIN_AUDIT_LABEL','original_live')
    if not label.replace('_','').isalnum():raise ValueError('invalid label')
    out=ROOT/'audit'/label;out.mkdir(parents=True,exist_ok=True)
    pipe=ChronoFinPipeline(ORIGINAL/'data/cache/tencent/manifest.json',ChatCompletionsClient(Hy3Config.from_env(),max_attempts=2),RetrievalConfig(top_k=10,chunk_chars=2200,overlap_chars=260))
    summary=[]
    for name,cutoff,expected in [('before','2025-12-31',Answerability.UNANSWERABLE),('after','2026-04-10',Answerability.ANSWERABLE)]:
        q=Query('What were Tencent Holdings Limited FY2025 full-year revenues, profit attributable to equity holders, and the derived profit margin? Distinguish IFRS from non-IFRS and do not annualise interim figures.',cutoff,'Tencent Holdings Limited','FY2025')
        try:
            a=pipe.run(q);s=ChronoFinEvaluator().evaluate(a,pipe.chunk_index,expected_answerability=expected)
            write_json(a,out/(name+'.json'));write_json(s,out/(name+'_score.json'));write_html(a,out/(name+'.html'),s)
            summary.append({'case':name,'status':'ok','answerability':a.answerability.value,'score':s.final_score,'gates':s.hard_gate_reasons,'trace':a.provenance.get('llm')})
        except Exception as e:summary.append({'case':name,'status':'error','error':str(e)[:1000]})
        print(json.dumps(summary[-1],ensure_ascii=False),flush=True)
    (out/'summary.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'executed_source':str(ORIGINAL),'results':summary},ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
