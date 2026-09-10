import unittest
from chronofin.reliability import money_equal,numeric_witnesses

class NumericWitnessTests(unittest.TestCase):
    def test_billion_to_yi_real_judge_failure(self):
        self.assertTrue(money_equal(1.55,'USD billion',15.5,'亿美元'))
        self.assertFalse(money_equal(1.55,'USD billion',1.55,'亿美元'))
    def test_currency_never_silently_converted(self):
        self.assertFalse(money_equal(1,'USD billion',1,'TWD billion'))
    def test_decimal_exact_conversion(self):
        self.assertTrue(money_equal(62360,'USD million',623.6,'亿美元'))
    def test_ambiguous_claim_not_force_matched(self):
        a={'claims':[{'id':'C1','text':'15.5 亿美元及 29 亿美元','evidence_ids':['M10']}]} 
        cards=[{'id':'M10','value':1.55,'unit':'USD billion'}]
        self.assertEqual(numeric_witnesses(a,cards),[])
    def test_observed_false_accusation_has_witness(self):
        a={'claims':[{'id':'C5','text':'Q4 因 15.5 亿美元法律拨备转回压低费用率','evidence_ids':['M10']}]} 
        cards=[{'id':'M10','value':1.55,'unit':'USD billion'}]
        self.assertTrue(numeric_witnesses(a,cards)[0]['numerically_equivalent'])

if __name__=='__main__':unittest.main()
