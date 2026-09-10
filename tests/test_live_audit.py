import unittest
from chronofin import brief
from chronofin.live_audit import partial_scorecard

class LiveAuditTests(unittest.TestCase):
    def test_missing_reference_never_yields_aggregate_or_coverage_credit(self):
        card={'id':'S1','text':'公司收入100百万美元','source_id':'s','entity':'甲','published_at':'2025-01-01','value':100,'unit':'USD million'}
        answer={'answerability':'answerable','summary':card['text'],'claims':[{'id':'C1','text':card['text'],'kind':'fact','role':'context','evidence_ids':['S1'],'numbers':[]}],
                'calculations':[],'limitations':[],'follow_up':[{'action':'查下季度收入','reason':'检查变化','evidence_ids':['S1']}]}
        r={'answer':answer,'evidence':[card],'excluded_ids':[],'query':{'question':'收入多少','as_of':'2025-02-01'}}
        sem={'answer_sha256':brief.digest(answer),'judgment':{'claims':[{'id':'C1','verdict':'supported','kind_valid':True,'scope_valid':True,'numbers_consistent':True}],
             'coverage':[],'limitations':[],'summary_supported':True,'follow_up_useful':True,'direct_answer':True}}
        score=partial_scorecard(r,[card],sem)
        self.assertIsNone(score['score']);self.assertIsNone(score['uncapped_score'])
        self.assertTrue(score['semantic_verified'])
        for d in score['dimensions']:
            if d['id'] in {'materiality','counterevidence','uncertainty'}:self.assertIsNone(d['value']);self.assertEqual(d['status'],'not_measured')
        sem['answer_sha256']='unrelated'
        with self.assertRaisesRegex(ValueError,'different answer'):partial_scorecard(r,[card],sem)

if __name__=='__main__':unittest.main()
