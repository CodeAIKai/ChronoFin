import unittest
from chronofin.financial_operations import compile_requests

class FinancialOperationTests(unittest.TestCase):
    def test_mixed_money_scales_ratio(self):
        c=[{'id':'F1','value':38200,'unit':'USD million'},{'id':'F2','value':115.9,'unit':'USD billion'}]
        out,err=compile_requests([{'id':'K1','op':'ratio_percent','inputs':['F1','F2']}],c)
        self.assertFalse(err);self.assertEqual(out[0]['value'],32.959)
    def test_chinese_million_to_yi_and_thousand_shares(self):
        c=[{'id':'F1','value':63052,'unit':'百万元'},{'id':'F2','value':14863609,'unit':'thousands shares'}]
        out,err=compile_requests([{'id':'K1','op':'convert','inputs':['F1'],'target_unit':'亿元'},{'id':'K2','op':'convert','inputs':['F2'],'target_unit':'亿股'}],c)
        self.assertFalse(err);self.assertEqual(out[0]['value'],630.52);self.assertEqual(out[1]['value'],148.636)
    def test_refuses_currency_mix_and_missing_operand(self):
        c=[{'id':'F1','value':1,'unit':'USD'},{'id':'F2','value':1,'unit':'人民币元'}]
        out,err=compile_requests([{'id':'K1','op':'ratio_percent','inputs':['F1','F2']},{'id':'K2','op':'ratio_percent','inputs':['F1','F9']}],c)
        self.assertFalse(out);self.assertEqual(len(err),2)
    def test_growth_and_zero_denominator(self):
        c=[{'id':'F1','value':1.85,'unit':'USD'},{'id':'F2','value':1.64,'unit':'USD'},{'id':'F3','value':0,'unit':'USD'}]
        out,err=compile_requests([{'id':'K1','op':'growth_percent','inputs':['F1','F2']},{'id':'K2','op':'ratio_percent','inputs':['F1','F3']}],c)
        self.assertEqual(out[0]['value'],12.805);self.assertEqual(len(err),1)

if __name__=='__main__':unittest.main()
