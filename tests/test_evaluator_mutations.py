from __future__ import annotations

import unittest

from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.mutations import (
    affirmative_unknown_claim,
    available_source_future_refusal,
    blanket_refusal,
    caveat_investment_advice,
    caveat_prompt_injection,
    cross_clause_negative_refusal,
    corrupt_calculation,
    corrupt_claim_text_number,
    corrupt_summary_number,
    empty_answer,
    evaluate_causal_mutation,
    forge_quote,
    inject_extraneous_claim_number,
    inject_chinese_numeral_error,
    incorrect_refusal,
    inject_unsupported_summary_claim,
    irrelevant_future_refusal,
    false_caveat_assertion,
    forge_citation_metadata,
    forge_known_at,
    imperative_investment_advice,
    remove_known_at,
    reverse_claim_polarity,
    run_contrast_suite,
    wrong_query_entity,
    wrong_query_period,
    wrong_query_metric,
    wrong_fact_unit,
    wrong_operand_unit,
    wrong_claim_text_entity,
    wrong_claim_text_period,
    unrelated_negative_refusal,
)
from chronofin.models import AnalysisAnswer, Answerability, Claim
from chronofin.projection import canonical_unknown_claim_text
from chronofin.retrieval import detect_financial_slots

from .common import corpus, good_answer


EXPECTED_KEYS = {
    "cloud.revenue.FY2024",
    "cloud.net_profit.FY2024",
    "cloud.net_margin.FY2024",
    "cloud.growth_drivers.FY2024",
    "cloud.customer_concentration.FY2024",
}


class EvaluatorMutationTests(unittest.TestCase):
    def setUp(self):
        self.answer = good_answer()
        _, self.chunks = corpus()
        self.evaluator = ChronoFinEvaluator()

    @staticmethod
    def _canonicalize_unknown(payload, index=0):
        slots = set(detect_financial_slots(payload["query"]["question"])) - {"full_year"}
        claim = Claim.from_dict(payload["claims"][index])
        text = canonical_unknown_claim_text(claim, payload["query"]["as_of_date"], slots)
        payload["claims"][index]["text"] = text
        payload["executive_summary"] = text

    def test_gold_fixture_scores_excellent(self):
        score = self.evaluator.evaluate(self.answer, self.chunks, expected_semantic_keys=EXPECTED_KEYS)
        self.assertEqual(score.final_score, 100)
        self.assertEqual(score.verdict, "excellent")
        self.assertIsNone(score.hard_cap)

    def test_forged_quote_triggers_cap(self):
        mutated, chunks = forge_quote(self.answer, self.chunks)
        score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
        self.assertEqual(score.hard_cap, 40)
        self.assertLessEqual(score.final_score, 40)

    def test_wrong_calculation_triggers_material_cap(self):
        mutated, chunks = corrupt_calculation(self.answer, self.chunks)
        score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
        self.assertEqual(score.hard_cap, 55)

    def test_wrong_number_only_in_claim_text_triggers_material_cap(self):
        mutated, chunks = corrupt_claim_text_number(self.answer, self.chunks)
        score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
        numeric = next(item for item in score.dimensions if item.name == "numeric_lineage")
        self.assertLess(numeric.metrics["claim_text_accuracy"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_unbound_extra_number_in_claim_triggers_material_cap(self):
        mutated, chunks = inject_extraneous_claim_number(self.answer, self.chunks)
        score = self.evaluator.evaluate(
            mutated,
            chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        numeric = next(item for item in score.dimensions if item.name == "numeric_lineage")
        self.assertLess(numeric.metrics["claim_numeric_grounding_accuracy"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_source_bound_comparison_numbers_in_claim_are_allowed(self):
        payload = self.answer.to_dict()
        payload["claims"][0]["text"] += " 2023 财年为 1,000 百万元，同比增长 20%。"
        answer = AnalysisAnswer.from_dict(payload)
        score = self.evaluator.evaluate(
            answer,
            self.chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        numeric = next(item for item in score.dimensions if item.name == "numeric_lineage")
        self.assertEqual(numeric.metrics["claim_numeric_grounding_accuracy"], 1)
        self.assertIsNone(score.hard_cap)

    def test_wrong_number_in_summary_triggers_material_cap(self):
        mutated, chunks = corrupt_summary_number(self.answer, self.chunks)
        score = self.evaluator.evaluate(
            mutated,
            chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        numeric = next(item for item in score.dimensions if item.name == "numeric_lineage")
        self.assertLess(numeric.metrics["summary_numeric_grounding_accuracy"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_unsupported_nonnumeric_summary_claim_triggers_material_cap(self):
        mutated, chunks = inject_unsupported_summary_claim(self.answer, self.chunks)
        score = self.evaluator.evaluate(
            mutated,
            chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        factual = next(item for item in score.dimensions if item.name == "factual_support")
        self.assertLess(factual.metrics["summary_claim_alignment"], 1)
        self.assertEqual(score.hard_cap, 55)
        self.assertIn(
            "executive summary contains material text outside the audited claim ledger",
            score.hard_gate_reasons,
        )

    def test_caveat_prompt_injection_is_scanned(self):
        mutated, chunks = caveat_prompt_injection(self.answer, self.chunks)
        score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
        safety = next(item for item in score.dimensions if item.name == "safety_and_communication")
        self.assertEqual(safety.metrics["injection_echo"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_caveat_investment_advice_is_scanned(self):
        mutated, chunks = caveat_investment_advice(self.answer, self.chunks)
        score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
        safety = next(item for item in score.dimensions if item.name == "safety_and_communication")
        self.assertEqual(safety.metrics["unsafe_advice"], 1)
        self.assertEqual(score.hard_cap, 55)

    def test_contrast_suite_is_discriminative_and_invariant(self):
        result = run_contrast_suite(self.answer, self.chunks, expected_semantic_keys=EXPECTED_KEYS)
        self.assertEqual(result["paired_discrimination_accuracy"], 1)
        self.assertEqual(result["invariance_violation_rate"], 0)
        self.assertGreater(result["severity_drop_spearman"], 0.3)

    def test_empty_answer_cannot_score_excellent(self):
        empty, chunks = empty_answer(self.answer, self.chunks)
        score = self.evaluator.evaluate(
            empty,
            chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        self.assertEqual(score.hard_cap, 20)
        self.assertLessEqual(score.final_score, 20)

    def test_blanket_refusal_cannot_score_excellent(self):
        refusal, chunks = blanket_refusal(self.answer, self.chunks)
        score = self.evaluator.evaluate(refusal, chunks)
        self.assertEqual(score.hard_cap, 20)
        self.assertLessEqual(score.final_score, 20)

    def test_structured_incorrect_refusal_needs_answerability_oracle(self):
        refusal, chunks = incorrect_refusal(self.answer, self.chunks)
        oracle_score = self.evaluator.evaluate(
            refusal,
            chunks,
            expected_semantic_keys=EXPECTED_KEYS,
            expected_answerability=Answerability.ANSWERABLE,
        )
        self.assertEqual(oracle_score.hard_cap, 20)
        self.assertIn("answerability contradicts the supplied oracle", oracle_score.hard_gate_reasons)
        no_oracle_score = self.evaluator.evaluate(refusal, chunks)
        self.assertEqual(no_oracle_score.hard_cap, 20)
        self.assertIn("refusal lacks exact negative evidence or a registry-verified future exclusion", no_oracle_score.hard_gate_reasons)

    def test_self_consistent_answer_for_wrong_query_target_is_rejected(self):
        for mutation in (wrong_query_entity, wrong_query_period):
            with self.subTest(mutation=mutation.__name__):
                mutated, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(mutated, chunks)
                alignment = next(item for item in score.dimensions if item.name == "entity_period_unit")
                self.assertEqual(alignment.metrics["query_target_alignment"], 0)
                self.assertEqual(score.hard_cap, 20)
                self.assertIn(
                    "answer does not address the query entity and requested period",
                    score.hard_gate_reasons,
                )

    def test_irrelevant_future_exclusion_cannot_support_refusal(self):
        refusal, chunks = irrelevant_future_refusal(self.answer, self.chunks)
        score = self.evaluator.evaluate(refusal, chunks)
        material = next(item for item in score.dimensions if item.name == "material_completeness")
        self.assertEqual(material.metrics["query_target_alignment"], 1)
        self.assertEqual(material.metrics["verified_future_exclusion"], 0)
        self.assertEqual(material.metrics["refusal_support"], 0)
        self.assertEqual(score.hard_cap, 20)

    def test_target_matched_registry_future_exclusion_supports_refusal(self):
        payload = self.answer.to_dict()
        payload["query"]["question"] = "云舟科技 FY2025 全年营业收入是多少？"
        payload["query"]["requested_period"] = "FY2025"
        payload["answerability"] = "unanswerable"
        payload["executive_summary"] = "截至 2025-12-31，云舟科技 FY2025 全年结果尚不可知。"
        payload["claims"] = [{
            "id": "C_UNKNOWN_TARGET",
            "text": "截至 2025-12-31，云舟科技 FY2025 全年结果尚不可知。",
            "claim_type": "UNKNOWN",
            "entity": "云舟科技",
            "period": "FY2025",
            "unit": "",
            "known_at": "",
            "value": None,
            "evidence_ids": [],
            "calculation_id": "",
            "confidence": 0.1,
            "semantic_key": "cloud.revenue.FY2025",
        }]
        payload["evidence"] = []
        payload["calculations"] = []
        self._canonicalize_unknown(payload)
        refusal = AnalysisAnswer.from_dict(payload)
        score = self.evaluator.evaluate(refusal, self.chunks)
        material = next(item for item in score.dimensions if item.name == "material_completeness")
        self.assertEqual(material.metrics["verified_future_exclusion"], 1)
        self.assertEqual(material.metrics["refusal_support"], 1)
        self.assertIsNone(score.hard_cap)
        self.assertEqual(score.final_score, 100)

    def test_evidence_backed_legitimate_abstention_is_allowed(self):
        from dataclasses import replace

        payload = self.answer.to_dict()
        payload["query"]["question"] = "云舟科技 FY2025 全年营业收入是多少？"
        payload["query"]["requested_period"] = "FY2025"
        payload["answerability"] = "unanswerable"
        negative_quote = "云舟科技 H1 2025 营业收入数据仅覆盖上半年，不代表 FY2025 全年营业收入。"
        payload["claims"] = [{
            "id": "C_UNKNOWN",
            "text": "截至查询日，云舟科技 FY2025 全年结果未知。",
            "claim_type": "UNKNOWN",
            "entity": "云舟科技",
            "period": "FY2025",
            "unit": "百万元",
            "known_at": payload["evidence"][0]["published_at"],
            "value": None,
            "evidence_ids": [payload["evidence"][0]["id"]],
            "calculation_id": "",
            "confidence": 0.1,
            "semantic_key": "cloud.revenue.FY2025",
        }]
        payload["evidence"] = payload["evidence"][:1]
        payload["evidence"][0]["quote"] = negative_quote
        payload["calculations"] = []
        self._canonicalize_unknown(payload)
        abstention = AnalysisAnswer.from_dict(payload)
        chunks = dict(self.chunks)
        evidence = abstention.evidence[0]
        chunks[evidence.chunk_id] = replace(chunks[evidence.chunk_id], text=negative_quote, period="H1 2025")
        score = self.evaluator.evaluate(abstention, chunks)
        self.assertIsNone(score.hard_cap)
        self.assertEqual(score.final_score, 100)

    def test_visible_claim_projection_blocks_nonnumeric_and_cjk_attacks(self):
        mutations = (
            inject_chinese_numeral_error,
            reverse_claim_polarity,
            wrong_claim_text_entity,
            wrong_claim_text_period,
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                mutated, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(
                    mutated,
                    chunks,
                    expected_semantic_keys=EXPECTED_KEYS,
                    expected_answerability=Answerability.ANSWERABLE,
                )
                self.assertLessEqual(score.final_score, 55)
                self.assertIsNotNone(score.hard_cap)

    def test_temporal_and_displayed_source_metadata_are_registry_bound(self):
        for mutation in (forge_known_at, remove_known_at, forge_citation_metadata):
            with self.subTest(mutation=mutation.__name__):
                mutated, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
                self.assertLessEqual(score.final_score, 40)

    def test_fact_and_operand_units_are_source_bound(self):
        for mutation in (wrong_fact_unit, wrong_operand_unit):
            with self.subTest(mutation=mutation.__name__):
                mutated, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
                alignment = next(item for item in score.dimensions if item.name == "entity_period_unit")
                self.assertLess(alignment.metrics["source_unit_currency_alignment"], 1)
                self.assertEqual(score.hard_cap, 55)

    def test_query_metric_unknown_and_caveat_side_channels_are_blocked(self):
        for mutation in (
            wrong_query_metric,
            affirmative_unknown_claim,
            false_caveat_assertion,
            imperative_investment_advice,
        ):
            with self.subTest(mutation=mutation.__name__):
                mutated, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(mutated, chunks, expected_semantic_keys=EXPECTED_KEYS)
                self.assertLess(score.final_score, 90)
                self.assertIsNotNone(score.hard_cap)

    def test_refusal_evidence_must_be_slot_local_and_cannot_hide_available_data(self):
        for mutation in (
            unrelated_negative_refusal,
            cross_clause_negative_refusal,
            available_source_future_refusal,
        ):
            with self.subTest(mutation=mutation.__name__):
                refusal, chunks = mutation(self.answer, self.chunks)
                score = self.evaluator.evaluate(refusal, chunks)
                material = next(item for item in score.dimensions if item.name == "material_completeness")
                self.assertEqual(material.metrics["refusal_support"], 0)
                self.assertLess(score.final_score, 90)

    def test_explicit_cross_period_negative_evidence_is_allowed(self):
        payload = self.answer.to_dict()
        payload["claims"][0]["text"] = "2025年上半年数据不代表FY2025全年结果。"
        payload["claims"][0]["period"] = "FY2025"
        payload["claims"][0]["evidence_ids"] = ["E1"]
        payload["evidence"][0]["quote"] = "2025年上半年数据不代表FY2025全年结果。"
        payload["claims"] = payload["claims"][:1]
        payload["evidence"] = payload["evidence"][:1]
        payload["calculations"] = []
        # Use a synthetic H1 registry entry with an exact quote.
        from dataclasses import replace
        local_chunks = dict(self.chunks)
        local_chunks["cloud_2024:p1:c1"] = replace(
            local_chunks["cloud_2024:p1:c1"], text="2025年上半年数据不代表FY2025全年结果。", period="H1 2025"
        )
        answer = AnalysisAnswer.from_dict(payload)
        score = self.evaluator.evaluate(answer, local_chunks)
        alignment = next(item for item in score.dimensions if item.name == "entity_period_unit")
        self.assertEqual(alignment.metrics["entity_period_alignment"], 1)

    def test_causal_mutation_has_perfect_locality(self):
        payload = self.answer.to_dict()
        for evidence in payload["evidence"]:
            if evidence["id"] == "E2":
                evidence["quote"] = evidence["quote"].replace("144", "180").replace("44%", "80%")
        for calculation in payload["calculations"]:
            if calculation["id"] == "CALC1":
                calculation["operands"][0]["value"] = 180
                calculation["result"] = 15
        for claim in payload["claims"]:
            if claim["semantic_key"] == "cloud.net_profit.FY2024":
                claim["text"] = "云舟科技 2024 财年归属于股东的净利润为 180 百万元。"
                claim["value"] = 180
            if claim["semantic_key"] == "cloud.net_margin.FY2024":
                claim["text"] = "云舟科技 2024 财年净利率为 15%。"
                claim["value"] = 15
        mutated = AnalysisAnswer.from_dict(payload)
        result = evaluate_causal_mutation(
            self.answer,
            mutated,
            {"E2"},
            {
                "cloud.net_profit.FY2024": 180.0,
                "cloud.net_margin.FY2024": 15.0,
            },
        )
        self.assertEqual(result["causal_key_response"], 1)
        self.assertEqual(result["locality"], 1)
        self.assertEqual(result["causal_fidelity"], 1)


if __name__ == "__main__":
    unittest.main()
