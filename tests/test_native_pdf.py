import unittest
from chronofin.pdf_research import document,retrieve,validate_extraction,parse_raw_number

class NativePDFTests(unittest.TestCase):
    def chunk(self):return {'id':'P1','source_id':'doc','text':'Revenue for 2024 was $1,250 million. Revenue for 2023 was $900 million.','entity':'Example','published_at':'2025-02-01','page':1,'locator':'p1'}
    def fact(self):return {'chunk_id':'P1','quote':'Revenue for 2024 was $1,250 million.','text':'2024 revenue was USD 1250 million','value':1250,'raw_number':'1,250','unit':'USD million'}
    def test_rejects_non_pdf(self):
        with self.assertRaises(ValueError):document(b'not pdf',{})
    def test_numeric_raw_sign_and_percent(self):
        self.assertEqual(parse_raw_number('(1,250)'),-1250);self.assertEqual(parse_raw_number('35.2%'),parse_raw_number('35.2'))
    def test_quote_and_number_bind(self):
        cards,rejected=validate_extraction({'facts':[self.fact()]},[self.chunk()]);self.assertEqual(len(cards),1);self.assertFalse(rejected)
    def test_rejects_fabricated_quote(self):
        f=self.fact();f['quote']='Revenue was 9999 million.'
        with self.assertRaises(ValueError):validate_extraction({'facts':[f]},[self.chunk()])
    def test_rejects_number_from_other_year_outside_quote(self):
        f=self.fact();f.update(value=900,raw_number='900')
        with self.assertRaises(ValueError):validate_extraction({'facts':[f]},[self.chunk()])
    def test_rejects_silent_scale_conversion(self):
        f=self.fact();f.update(value=1.25,unit='USD billion')
        with self.assertRaises(ValueError):validate_extraction({'facts':[f]},[self.chunk()])
    def test_future_original_does_not_enter_selected_chunks(self):
        d={'published_at':'2025-02-01','chunks':[self.chunk()]}
        self.assertEqual(retrieve(d,'Revenue','2025-01-31'),[])
    def test_real_pdf_pages_and_metadata(self):
        try:import fitz
        except ImportError:self.skipTest('PyMuPDF optional')
        pdf=fitz.open();page=pdf.new_page();page.insert_text((30,60),'Revenue for 2024 was 1250 million USD. This public financial report has extractable text and an explicit reporting date.')
        content=pdf.tobytes();pdf.close();d=document(content,{'title':'Example annual report','entity':'Example','published_at':'2025-02-01'})
        self.assertEqual(d['pages'],1);self.assertEqual(d['metadata_identity'],'user_declared');self.assertTrue(d['chunks'])

if __name__=='__main__':unittest.main()
