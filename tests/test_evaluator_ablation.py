from __future__ import annotations

import unittest

from chronofin.evaluator.ablation import (
    ABLATION_SCHEMA_VERSION,
    ablation_json,
    default_ablation_strategies,
    run_evaluator_ablation,
)
from chronofin.evaluator.benchmark import build_synthetic_tasks
from chronofin.evaluator.mutations import DEFAULT_CONTRAST_MUTATIONS


class EvaluatorAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = build_synthetic_tasks()[:3]
        cls.mutations = tuple(DEFAULT_CONTRAST_MUTATIONS)
        cls.result = run_evaluator_ablation(tasks=cls.tasks)

    def test_ordered_capability_ladder_is_explicit(self):
        self.assertEqual(
            [strategy.name for strategy in default_ablation_strategies()],
            [
                "no_audit_plain_output",
                "exact_citation_only",
                "point_in_time_exact_citation",
                "full_chronofin",
            ],
        )

    def test_runtime_registry_coverage_is_not_hard_coded(self):
        coverage = self.result["coverage"]
        destructive = sum(not item.label_preserving for item in self.mutations)
        preserving = sum(item.label_preserving for item in self.mutations)
        self.assertEqual(coverage["destructive_mutations_per_task"], destructive)
        self.assertEqual(coverage["label_preserving_mutations_per_task"], preserving)
        self.assertEqual(coverage["mutation_runs_per_strategy"], len(self.tasks) * len(self.mutations))
        self.assertEqual(
            coverage["total_strategy_mutation_runs"],
            len(self.tasks) * len(self.mutations) * len(default_ablation_strategies()),
        )

    def test_expected_component_scope_is_visible(self):
        results = self.result["strategy_results"]
        plain = results["no_audit_plain_output"]["mutation_summary"]
        exact = results["exact_citation_only"]["mutation_summary"]
        temporal = results["point_in_time_exact_citation"]["mutation_summary"]
        self.assertEqual(results["no_audit_plain_output"]["destructive_detection_rate"], 0.0)
        self.assertEqual(exact["forged_quote"]["destructive_detection_rate"], 1.0)
        self.assertEqual(exact["future_leak"]["destructive_detection_rate"], 0.0)
        self.assertEqual(temporal["forged_quote"]["destructive_detection_rate"], 1.0)
        self.assertEqual(temporal["future_leak"]["destructive_detection_rate"], 1.0)
        self.assertEqual(plain["forged_quote"]["destructive_detection_rate"], 0.0)

    def test_full_evaluator_is_invariant_and_strictly_adds_detection(self):
        results = self.result["strategy_results"]
        point = results["point_in_time_exact_citation"]
        full = results["full_chronofin"]
        self.assertEqual(full["invariance_violation_rate"], 0.0)
        self.assertGreater(full["destructive_detection_rate"], point["destructive_detection_rate"])
        self.assertTrue(
            all(
                item["destructive_detection_rate"] == 1.0
                for item in full["mutation_summary"].values()
                if not item["label_preserving"]
            )
        )

    def test_protocol_discloses_non_model_scope_and_is_deterministic(self):
        self.assertEqual(self.result["schema_version"], ABLATION_SCHEMA_VERSION)
        disclosure = " ".join(self.result["limitations"] + self.result["claims_not_made"]).lower()
        self.assertIn("not financial question-answering correctness", disclosure)
        self.assertIn("not an external model", disclosure)
        self.assertIn("no held-out", disclosure)
        self.assertEqual(self.result["reproducibility"]["model_calls"], 0)
        repeated = run_evaluator_ablation(tasks=self.tasks)
        self.assertEqual(ablation_json(self.result), ablation_json(repeated))


if __name__ == "__main__":
    unittest.main()

