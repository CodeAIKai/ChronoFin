from __future__ import annotations

import unittest

from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.benchmark import (
    BENCHMARK_VERSION,
    benchmark_json,
    build_synthetic_tasks,
    run_synthetic_benchmark,
)


class SyntheticBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = build_synthetic_tasks()
        cls.result = run_synthetic_benchmark(bootstrap_iterations=64, bootstrap_seed=2026)

    def test_task_matrix_meets_multicluster_contract(self):
        self.assertEqual(len(self.tasks), 72)
        self.assertEqual(len({item.company_id for item in self.tasks}), 8)
        self.assertEqual(len({item.fiscal_year for item in self.tasks}), 3)
        self.assertEqual(len({item.family for item in self.tasks}), 3)
        self.assertEqual(len({item.task_id for item in self.tasks}), 72)

    def test_every_formal_oracle_uses_real_evaluator_and_scores_cleanly(self):
        evaluator = ChronoFinEvaluator()
        for task in self.tasks:
            with self.subTest(task=task.task_id):
                score = evaluator.evaluate(
                    task.answer,
                    task.chunks,
                    expected_semantic_keys=set(task.expected_semantic_keys),
                )
                self.assertEqual(score.final_score, 100.0)
                self.assertIsNone(score.hard_cap)

    def test_all_mutations_are_run_and_reported(self):
        coverage = self.result["coverage"]
        self.assertEqual(coverage["destructive_mutations_per_task"], 36)
        self.assertEqual(coverage["label_preserving_mutations_per_task"], 2)
        self.assertEqual(coverage["total_mutation_runs"], 2736)
        self.assertEqual(coverage["destructive_runs"], 2592)
        self.assertEqual(coverage["label_preserving_runs"], 144)
        self.assertEqual(len(self.result["outcomes"]), 2736)

    def test_primary_metrics_and_subtype_recall_are_complete(self):
        metrics = self.result["metrics"]
        self.assertEqual(metrics["paired_discrimination_accuracy"], 1.0)
        self.assertEqual(metrics["invariance_violation_rate"], 0.0)
        self.assertGreater(metrics["severity_drop_spearman"], 0.0)
        self.assertLessEqual(abs(metrics["severity_drop_spearman"]), 1.0)
        expected = {
            "future_leak",
            "citation_metadata_forgery",
            "known_at_mismatch",
            "missing_known_at",
            "forged_quote",
            "wrong_entity",
            "wrong_period",
            "claim_text_wrong_entity",
            "claim_text_wrong_period",
            "claim_polarity_reversal",
            "wrong_query_entity",
            "wrong_query_period",
            "wrong_query_metric",
            "wrong_unit",
            "wrong_fact_unit",
            "wrong_operand_unit",
            "calculation_error",
            "claim_text_numeric_error",
            "extraneous_claim_number",
            "chinese_numeral_error",
            "summary_numeric_error",
            "summary_unsupported_claim",
            "missing_citation",
            "prompt_injection",
            "caveat_prompt_injection",
            "caveat_investment_advice",
            "imperative_investment_advice",
            "false_caveat_assertion",
            "empty_answer",
            "affirmative_unknown_claim",
            "blanket_refusal",
            "incorrect_refusal",
            "irrelevant_future_refusal",
            "unrelated_negative_refusal",
            "cross_clause_negative_refusal",
            "available_source_future_refusal",
        }
        self.assertEqual(set(metrics["destructive_subtype_recall"]), expected)
        self.assertTrue(all(value == 1.0 for value in metrics["destructive_subtype_recall"].values()))

    def test_bootstrap_is_hierarchical_and_reproducible(self):
        bootstrap = self.result["cluster_bootstrap_95_ci"]
        self.assertIn("resample companies", bootstrap["method"])
        self.assertIn("original base tasks", bootstrap["method"])
        self.assertEqual(bootstrap["iterations"], 64)
        repeated = run_synthetic_benchmark(bootstrap_iterations=64, bootstrap_seed=2026)
        self.assertEqual(benchmark_json(self.result), benchmark_json(repeated))

    def test_result_discloses_formal_oracle_limits(self):
        self.assertEqual(self.result["benchmark_version"], BENCHMARK_VERSION)
        disclosure = " ".join(self.result["limitations"] + self.result["claims_not_made"]).lower()
        self.assertIn("synthetic formal oracles", disclosure)
        self.assertIn("not a held-out dataset", disclosure)
        self.assertIn("no human-expert labels", disclosure)
        self.assertEqual(self.result["reproducibility"]["model_calls"], 0)
        self.assertTrue(self.result["reproducibility"]["fully_offline"])


if __name__ == "__main__":
    unittest.main()
