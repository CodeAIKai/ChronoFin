import unittest
from chronofin.span_evidence import validate_span_extraction,bind_judgment,candidate_spans

class SpanEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.c={'id':'P1','text':'Revenue 2025 2024\nGreater China 64,377 66,952\nCash 100 200','page':1,'locator':'p1','source_id':'pdf_x','entity':'A','published_at':'2025-01-01'}
        self.f={'chunk_id':'P1','start_line':2,'end_line':2,'text':'大中华区全年销售下降','value':64377,'raw_number':'64,377','unit':'USD million'}
    def test_copies_original_line_without_generated_currency_signs(self):
        cards,reject=validate_span_extraction({'facts':[self.f]},[self.c]);self.assertFalse(reject)
        self.assertEqual(cards[0]['quote'],'Greater China 64,377 66,952')
    def test_rejects_numeric_from_other_line(self):
        self.f.update(value=100,raw_number='100')
        with self.assertRaises(ValueError):validate_span_extraction({'facts':[self.f]},[self.c])
    def test_rejects_out_of_range_and_boolean_line(self):
        for v in [0,4,True]:
            self.f.update(start_line=v,end_line=v)
            with self.assertRaises(ValueError):validate_span_extraction({'facts':[self.f]},[self.c])
    def test_coverage_uses_candidate_span_not_model_quote(self):
        raw={'coverage':[{'id':'R1','present':True,'candidate_span_id':'C1','quote':'fabricated source text'}],'limitations':[]}
        bound,audit=bind_judgment(raw,{'C1':'Actual candidate sentence.'})
        self.assertEqual(bound['coverage'][0]['quote'],'Actual candidate sentence.')
        self.assertEqual(raw['coverage'][0]['quote'],'fabricated source text')
        self.assertTrue(audit[0]['bound'])
    def test_unknown_candidate_span_is_unbound(self):
        bound,audit=bind_judgment({'coverage':[{'id':'R1','present':True,'candidate_span_id':'SOURCE1'}]}, {'C1':'actual'})
        self.assertFalse(audit[0]['bound']);self.assertEqual(bound['coverage'][0]['quote'],'')

if __name__=='__main__':unittest.main()
