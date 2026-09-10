"""Reference-free live auditing: evidence support without a made-up total."""
from . import brief

def partial_scorecard(record,cards,semantic):
    case={**record['query'],'required':[],'counter':[],'limitations':[],
          'expected_answerability':record['answer']['answerability']}
    score=brief.evaluate(record,case,cards,semantic)
    for d in score['dimensions']:
        if d['id'] in {'materiality','counterevidence','uncertainty'}:
            d.update(value=None,status='not_measured')
    score.update(score=None,uncapped_score=None,reference_available=False,
                 definition='Live evidence-support audit only. Coverage, counterevidence completeness and unknown-boundary calibration require an independent reference; no aggregate score is reported.')
    return score

def judge_partial(client,record,cards):
    """Use candidate-span binding and one bounded format repair for custom work."""
    from .pdf_research_v5 import judge
    generic={**record['query'],'required':[],'counter':[],'limitations':[],
             'expected_answerability':record['answer']['answerability']}
    attempts=[];previous=None
    for attempt in range(2):
        semantic=judge(client,record,generic,cards,previous)
        attempts.append(semantic)
        try:score=partial_scorecard(record,cards,semantic)
        except ValueError as e:
            semantic['validation_error']=str(e)
            previous={'judgment':semantic['judgment'],'error':str(e)}
            if attempt==1:raise
        else:return semantic,score,attempts
