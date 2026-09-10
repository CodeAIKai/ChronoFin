import copy
import unittest
from chronofin.review_notes import review_notes
class ReviewNotesTests(unittest.TestCase):
    def test_same_source_growth_is_visible_without_rewriting(self):
        r={'record':{'answer':{'calculations':[{'id':'K1','evidence_ids':['F1','F1'],'value':0}]}},'scorecard':{'score':93}}
        before=copy.deepcopy(r);self.assertTrue(review_notes(r));self.assertEqual(r,before)
    def test_distinct_sources_do_not_trigger_duplicate_warning(self):
        r={'record':{'answer':{'calculations':[{'id':'K1','evidence_ids':['F1','F2']}]}},'semantic':{'judgment':{'claims':[{'id':'C1','supported':False,'reason':'wrong period'}]}}}
        self.assertEqual(review_notes(r),['C1 待核查：wrong period'])
