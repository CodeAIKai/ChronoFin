import copy
import unittest
from pathlib import Path
from chronofin.brief import digest,evaluate,public_case,read_data,retrieve,validate_answer

ROOT=Path(__file__).resolve().parents[1]

class BriefTrustTests(unittest.TestCase):
    def setUp(self):
        self.sources,self.cards,self.cases=read_data(ROOT)
        self.case={'question':'Meta FY2024 revenue','as_of':'2025-06-01','required':['M01'],'counter':[],
                   'limitations':[],'expected_answerability':'answerable'}
        self.answer={'answerability':'answerable','summary':'Meta 收入为 164501 百万美元。',
          'claims':[{'id':'C1','text':'Meta 收入为 164501 百万美元。','kind':'fact','role':'context',
                     'evidence_ids':['M01'],'numbers':[{'source_id':'M01','value':164501,'unit':'USD million'}]}],
          'calculations':[],'limitations':[],'follow_up':[]}
        self.record={'answer':self.answer,'evidence':[self.cards[0]],'excluded_ids':[]}
        self.j={'judgment':{'claims':[{'id':'C1','verdict':'supported','kind_valid':True,'scope_valid':True,'numbers_consistent':True}],
          'coverage':[{'id':'M01','present':True,'quote':self.answer['summary']}],'limitations':[],
          'summary_supported':True,'follow_up_useful':False,'direct_answer':True},'answer_sha256':digest(self.answer)}

    def test_no_semantic_means_no_overall_score(self):
        self.assertIsNone(evaluate(self.record,self.case,self.cards)['score'])

    def test_stale_judgment_rejected(self):
        self.answer['summary']='changed'
        with self.assertRaisesRegex(ValueError,'different answer'):evaluate(self.record,self.case,self.cards,self.j)

    def test_coverage_cannot_be_invented_by_judge(self):
        self.j['judgment']['coverage'][0]['quote']='not present'
        s=evaluate(self.record,self.case,self.cards,self.j)
        self.assertLessEqual(s['score'],35)
        self.assertIn('unverifiable positive judge quote',s['issues'])

    def test_every_claim_must_be_judged(self):
        self.j['judgment']['claims']=[]
        with self.assertRaises(ValueError):evaluate(self.record,self.case,self.cards,self.j)

    def test_duplicate_coverage_rejected(self):
        self.j['judgment']['coverage']*=2
        with self.assertRaises(ValueError):evaluate(self.record,self.case,self.cards,self.j)

    def test_wrong_value_cannot_pass_judge(self):
        self.answer['claims'][0]['numbers'][0]['value']=1645010
        self.j['answer_sha256']=digest(self.answer)
        self.assertLessEqual(evaluate(self.record,self.case,self.cards,self.j)['score'],55)

    def test_wrong_unit_cannot_pass_judge(self):
        self.answer['claims'][0]['numbers'][0]['unit']='TWD million'
        self.j['answer_sha256']=digest(self.answer)
        self.assertLessEqual(evaluate(self.record,self.case,self.cards,self.j)['score'],55)

    def test_forged_pointer_cannot_pass_judge(self):
        self.answer['claims'][0]['evidence_ids']=['forged']
        self.j['answer_sha256']=digest(self.answer)
        self.assertLessEqual(evaluate(self.record,self.case,self.cards,self.j)['score'],40)

    def test_future_prompt_gated_even_if_answer_omits_it(self):
        c=copy.deepcopy(self.cards[1]);c['published_at']='2030-01-01';self.record['evidence'].append(c)
        self.assertLessEqual(evaluate(self.record,self.case,self.cards,self.j)['score'],30)

    def test_date_cutoff_applies_to_all_strategies(self):
        c=next(c for c in self.cases if c['id']=='E02')
        for strategy in ['lexical','full_context','counterbrief']:
            selected,_=retrieve(self.cards,c,strategy)
            self.assertTrue(all(x['published_at']<=c['as_of'] for x in selected))

    def test_generator_input_never_exposes_oracles(self):
        for c in self.cases:self.assertEqual(set(public_case(c)),{'question','as_of'})

    def test_source_expansion_includes_meta_footnote(self):
        selected,_=retrieve(self.cards,self.cases[0])
        self.assertIn('M10',{c['id'] for c in selected})

    def test_nan_rejected(self):
        self.answer['claims'][0]['numbers'][0]['value']=float('nan')
        with self.assertRaises(ValueError):validate_answer(self.answer)

    def test_duplicate_claim_rejected(self):
        self.answer['claims']*=2
        with self.assertRaises(ValueError):validate_answer(self.answer)

    def test_expression_code_execution_rejected(self):
        self.answer['calculations']=[{'id':'K1','expression':"__import__('os').system('true')",'value':0,'unit':'','evidence_ids':[]}]
        self.j['answer_sha256']=digest(self.answer)
        self.assertLessEqual(evaluate(self.record,self.case,self.cards,self.j)['score'],55)

    def test_same_input_identical_output(self):
        self.assertEqual(digest(evaluate(self.record,self.case,self.cards,self.j)),digest(evaluate(self.record,self.case,self.cards,self.j)))

if __name__=='__main__':unittest.main()
