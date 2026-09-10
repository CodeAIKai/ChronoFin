"""Visible review requests, independent of historical scores; never edit answers."""
def review_notes(result):
    record=result.get('record',{});answer=record.get('answer',{});notes=[]
    for c in answer.get('calculations',[]):
        ids=c.get('evidence_ids',[])
        if len(ids)>1 and len(set(ids))==1:
            notes.append(f"计算 {c.get('id','')} 重复使用同一数值，不能据此证明跨期增长或两项指标的比例；请核对输入。")
    for issue in record.get('final_proof_issues',[]):notes.append('数值复核：'+str(issue))
    for c in result.get('semantic',{}).get('judgment',{}).get('claims',[]):
        if c.get('supported') is False or c.get('verdict') in {'partial','unsupported','contradicted'} or c.get('numbers_consistent') is False:
            notes.append(f"{c.get('id','结论')} 待核查：{c.get('reason','原文支持或数字一致性未通过。')}")
    return list(dict.fromkeys(notes))
