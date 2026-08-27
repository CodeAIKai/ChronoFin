from __future__ import annotations

import unittest

from chronofin.evaluator.numeric import (
    UnsafeExpression,
    audit_calculations,
    rounded_value_appears,
    safe_evaluate,
)
from chronofin.evaluator.proof_graph import NodeKind, ProofGraph

from .common import corpus, good_answer


class NumericGraphTests(unittest.TestCase):
    def test_safe_arithmetic(self):
        self.assertAlmostEqual(safe_evaluate("profit / revenue * 100", {"profit": 144, "revenue": 1200}), 12)

    def test_number_after_currency_prefix_is_detected(self):
        from chronofin.evaluator.numeric import value_appears
        self.assertTrue(value_appears(224.8, "increased to RMB224.8 billion"))

    def test_formula_identifier_is_not_a_displayed_result(self):
        wrong = "星澜科技 FY2021 CALC1: current_assets / current_liabilities = 2.5倍。"
        correct = "星澜科技 FY2021 CALC1: current_assets / current_liabilities = 1.5倍。"
        self.assertFalse(rounded_value_appears(1.5, wrong))
        self.assertTrue(rounded_value_appears(1.5, correct))

    def test_function_call_rejected(self):
        with self.assertRaises(UnsafeExpression):
            safe_evaluate("__import__('os').system('id')", {})

    def test_attribute_access_rejected(self):
        with self.assertRaises(UnsafeExpression):
            safe_evaluate("x.__class__", {"x": 1})

    def test_unknown_operand_rejected(self):
        with self.assertRaises(UnsafeExpression):
            safe_evaluate("profit / revenue", {"profit": 144})

    def test_divide_by_zero_rejected_by_audit(self):
        answer = good_answer()
        payload = answer.to_dict()
        payload["calculations"][0]["operands"][1]["value"] = 0
        from chronofin.models import AnalysisAnswer
        broken = AnalysisAnswer.from_dict(payload)
        _, chunks = corpus()
        evidence_text = {item.id: chunks[item.chunk_id].text for item in broken.evidence}
        audit = audit_calculations(broken.calculations, broken.evidence_index(), evidence_text)
        self.assertEqual(audit.execution_accuracy, 0)

    def test_gold_numeric_lineage_is_complete(self):
        answer = good_answer()
        _, chunks = corpus()
        evidence_text = {item.id: chunks[item.chunk_id].text for item in answer.evidence}
        audit = audit_calculations(answer.calculations, answer.evidence_index(), evidence_text, answer.claims)
        self.assertEqual(audit.execution_accuracy, 1)
        self.assertEqual(audit.leaf_binding_accuracy, 1)
        self.assertEqual(audit.trace_coverage, 1)
        self.assertEqual(audit.claim_value_accuracy, 1)
        self.assertEqual(audit.claim_text_accuracy, 1)

    def test_wrong_number_in_claim_text_is_detected_even_when_typed_value_is_correct(self):
        answer = good_answer()
        payload = answer.to_dict()
        derived = next(item for item in payload["claims"] if item.get("calculation_id"))
        derived["text"] = derived["text"].replace("12%", "13%")
        from chronofin.evaluator import ChronoFinEvaluator
        from chronofin.models import AnalysisAnswer
        broken = AnalysisAnswer.from_dict(payload)
        _, chunks = corpus()
        score = ChronoFinEvaluator().evaluate(broken, chunks)
        numeric = next(item for item in score.dimensions if item.name == "numeric_lineage")
        self.assertLess(numeric.metrics["claim_text_accuracy"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_proof_graph_is_valid(self):
        graph = ProofGraph.from_answer(good_answer())
        self.assertEqual(graph.validate(), [])

    def test_source_descendants_are_local(self):
        graph = ProofGraph.from_answer(good_answer())
        descendants = graph.descendants({"E2"}, {NodeKind.CLAIM})
        self.assertEqual(descendants, {"C2", "C3"})


if __name__ == "__main__":
    unittest.main()
