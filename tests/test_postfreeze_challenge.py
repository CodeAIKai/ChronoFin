from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_postfreeze_challenge.py"
SPEC = importlib.util.spec_from_file_location("postfreeze_challenge_runner", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _copy_integrity_fixture(destination: Path) -> None:
    relative_paths = {
        MODULE.FREEZE_PATH.relative_to(ROOT).as_posix(),
        MODULE.EVALUATOR_FREEZE_PATH.relative_to(ROOT).as_posix(),
        MODULE.HISTORICAL_RESULTS_PATH.relative_to(ROOT).as_posix(),
        MODULE.CURRENT_EVALUATOR_PATH.relative_to(ROOT).as_posix(),
        MODULE.CURRENT_ADAPTER_PATH.relative_to(ROOT).as_posix(),
        MODULE.HISTORICAL_INITIAL_RESULT.relative_to(ROOT).as_posix(),
        MODULE.HISTORICAL_FINAL_RESULT.relative_to(ROOT).as_posix(),
        MODULE.CURRENT_FIRST_RESULT.relative_to(ROOT).as_posix(),
        *MODULE.HISTORICAL_EVALUATOR_PATHS,
        *MODULE.CURRENT_EVALUATOR_PATHS,
        *MODULE.CURRENT_ADAPTER_PATHS,
    }
    relative_paths.update(MODULE.verify_frozen_files(ROOT))
    for relative in relative_paths:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class PostfreezeChallengeTests(unittest.TestCase):
    def test_all_hash_ledgers_and_retained_failures_are_intact(self) -> None:
        checked = MODULE.verify_frozen_files(ROOT)
        self.assertEqual(len(checked), 4)
        historical = MODULE.verify_historical_attestation(ROOT)
        self.assertTrue(historical["integrity_checks_passed"])
        self.assertFalse(historical["first_run_evaluator_identity_verified"])
        self.assertFalse(historical["externally_timestamped"])
        self.assertFalse(historical["current_tree_matches_v1"])
        self.assertTrue(historical["changed_evaluator_paths"])
        self.assertEqual(len(MODULE.verify_current_evaluator(ROOT)), len(MODULE.CURRENT_EVALUATOR_PATHS))
        self.assertEqual(MODULE.verify_current_adapter(ROOT), {
            "scripts/run_postfreeze_challenge.py": MODULE._sha256(SCRIPT),
        })
        predecessor = MODULE.verify_current_predecessor(ROOT)
        self.assertEqual(predecessor["base_passed"], 0)
        self.assertEqual(predecessor["base_total"], 6)

    def test_scope_is_explicitly_non_human_non_heldout_and_seen(self) -> None:
        dataset = json.loads(
            (ROOT / "data" / "challenge" / "challenge_v1.json").read_text(encoding="utf-8")
        )
        metadata = dataset["metadata"]
        self.assertEqual(metadata["company_count"], 3)
        self.assertEqual(metadata["base_case_count"], 6)
        self.assertEqual(metadata["adversarial_case_count"], 3)
        self.assertTrue(metadata["curation_type"].startswith("AI-curated"))
        self.assertIn("not human-expert annotated", metadata["non_claims"])
        self.assertIn("not a statistical held-out estimate", metadata["non_claims"])
        self.assertEqual(len({source["source_format"] for source in dataset["sources"]}), 3)

        result = MODULE.evaluate_challenge(ROOT)
        self.assertEqual(result["evaluation_role"], "seen_regression_fixture")
        self.assertTrue(result["dataset_was_visible_during_current_hardening"])
        self.assertFalse(result["postfreeze_relative_to_current_evaluator"])
        self.assertFalse(result["heldout_claimed"])
        self.assertTrue(result["execution"]["current_run_is_regression"])

    def test_current_regression_all_oracles_pass_offline(self) -> None:
        result = MODULE.evaluate_challenge(ROOT)
        self.assertFalse(result["execution"]["network_used"])
        self.assertFalse(result["execution"]["model_called"])
        self.assertTrue(result["code_reference"]["current_evaluator_hashes_verified"])
        self.assertTrue(result["code_reference"]["current_adapter_hashes_verified"])
        self.assertTrue(result["summary"]["all_passed"])
        self.assertEqual(result["summary"]["base_passed"], 6)
        self.assertEqual(result["summary"]["adversarial_passed"], 3)
        self.assertTrue(all(item["evaluator_score"] >= 90 for item in result["base_results"]))
        self.assertTrue(all(item["evaluator_score"] <= 20 for item in result["adversarial_results"]))

    def test_current_regression_is_byte_deterministic(self) -> None:
        first = json.dumps(MODULE.evaluate_challenge(ROOT), ensure_ascii=False, sort_keys=True)
        second = json.dumps(MODULE.evaluate_challenge(ROOT), ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)

    def test_current_dependency_mutation_does_not_rewrite_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_integrity_fixture(root)
            retrieval = root / "src" / "chronofin" / "retrieval.py"
            retrieval.write_text(retrieval.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                MODULE.verify_current_evaluator(root)
            self.assertTrue(MODULE.verify_historical_attestation(root)["integrity_checks_passed"])

    def test_historical_result_and_adapter_mutations_fail_their_own_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_integrity_fixture(root)
            historical = root / "results" / "postfreeze_challenge_v1.json"
            historical.write_text(historical.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                MODULE.verify_historical_attestation(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_integrity_fixture(root)
            adapter = root / "scripts" / "run_postfreeze_challenge.py"
            adapter.write_text(adapter.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                MODULE.verify_current_adapter(root)
            self.assertEqual(
                len(MODULE.verify_current_evaluator(root)),
                len(MODULE.CURRENT_EVALUATOR_PATHS),
            )


if __name__ == "__main__":
    unittest.main()
