from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_submission import (
    Check,
    check_cached_pdfs_not_tracked,
    check_demo_gif,
    check_cleanroom,
    check_current_deterministic_stability,
    check_current_live_causal,
    check_evaluator_ablation,
    check_offline_metrics,
    check_public_answerability_oracles,
    check_public_tencent_scores,
    check_raw_provider_request_ids,
    check_postfreeze_challenge,
    check_postfreeze_hash_chain,
    check_refusal_adversaries,
    check_semantic_stability,
    check_synthetic_benchmark,
    check_suspected_sk_secrets,
    load_json_artifacts,
    main,
    REQUIRED_DESTRUCTIVE_MUTATIONS,
    verify_submission,
)
from chronofin.reproducibility import (
    canonicalize_temporary_paths,
    temporary_path_leak_locations,
    tree_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]

CLEANROOM_COMMAND_LABELS = (
    "create_venv", "install_local_package", "compileall", "unit_tests",
    "reprocess_saved_causal", "offline_experiments", "synthetic_benchmark",
    "evaluator_ablation", "postfreeze_regression", "sanitize_public_artifacts",
    "cli_inspect", "git_init", "git_stage_submission", "submission_verifier",
)


def cleanroom_payload(root: Path) -> dict:
    fingerprint = tree_fingerprint(root)
    return {
        "schema_version": "chronofin-cleanroom-v2",
        "all_passed": True,
        "network_access": False,
        "api_key_environment_removed": True,
        "fresh_virtual_environment": True,
        "temporary_checkout_deleted_after_run": True,
        "cached_pdfs_in_checkout": [],
        "source_tree_sha256": fingerprint,
        "reproduced_tree_sha256": fingerprint,
        "tree_fingerprint_matches": True,
        "commands": [
            {
                "label": label,
                "exit_code": 0,
                "command": (
                    [
                        "<CLEANROOM>/venv/bin/python",
                        "scripts/verify_submission.py",
                        "--compact",
                        "--cleanroom-prerequisites",
                    ]
                    if label == "submission_verifier"
                    else [label]
                ),
                **(
                    {
                        "verification_scope":
                        "all_submission_checks_except_cleanroom_self_check"
                    }
                    if label == "submission_verifier"
                    else {}
                ),
            }
            for label in CLEANROOM_COMMAND_LABELS
        ],
    }


def offline_payload() -> dict:
    return {
        "quality_tiers": {
            "good": {"score": 100},
            "medium": {"score": 70},
            "bad": {"score": 40},
        },
        "contrast_evaluator": {
            "paired_discrimination_accuracy": 0.9,
            "invariance_violation_rate": 0.05,
        },
        "causal_system_oracle": {"causal_fidelity": 0.9},
        "point_in_time_ablation": {"strict_future_leak_count": 0},
    }


def live_causal_payload() -> dict:
    return {"metrics": {"causal_fidelity": 0.9}}


def synthetic_benchmark_payload() -> dict:
    return {
        "coverage": {
            "base_tasks": 72,
            "companies": 8,
            "total_mutation_runs": 2736,
            "destructive_runs": 2592,
            "label_preserving_runs": 144,
        },
        "metrics": {
            "paired_discrimination_accuracy": 0.9,
            "invariance_violation_rate": 0.05,
            "destructive_subtype_recall": {
                name: 0.9 for name in REQUIRED_DESTRUCTIVE_MUTATIONS
            },
        },
    }


def scorecard_with_answerability_metrics(score: float = 100) -> dict:
    return {
        "final_score": score,
        "dimensions": [{
            "name": "material_completeness",
            "metrics": {
                "answerability_oracle_supplied": 1,
                "answerability_match": 1,
                "output_structure_valid": 1,
                "refusal_support": 1,
            },
        }],
    }


class SubmissionVerifierUnitTests(unittest.TestCase):
    def test_offline_metrics_accept_inclusive_thresholds(self):
        checks = check_offline_metrics(offline_payload(), live_causal_payload())
        self.assertEqual(len(checks), 5)
        self.assertTrue(all(item.status == "pass" for item in checks))

    def test_quality_order_must_be_strict(self):
        payload = offline_payload()
        payload["quality_tiers"]["medium"]["score"] = 100
        checks = {item.id: item for item in check_offline_metrics(payload, live_causal_payload())}
        self.assertEqual(checks["offline_quality_order"].status, "fail")

    def test_each_offline_threshold_can_fail(self):
        mutations = {
            "paired_discrimination_accuracy": ("contrast_evaluator", "paired_discrimination_accuracy", 0.899),
            "invariance_violation_rate": ("contrast_evaluator", "invariance_violation_rate", 0.051),
            "strict_future_leak_count": ("point_in_time_ablation", "strict_future_leak_count", 1),
        }
        for check_id, (section, key, value) in mutations.items():
            with self.subTest(check_id=check_id):
                payload = offline_payload()
                payload[section][key] = value
                checks = {item.id: item for item in check_offline_metrics(payload, live_causal_payload())}
                self.assertEqual(checks[check_id].status, "fail")

        live = live_causal_payload()
        live["metrics"]["causal_fidelity"] = 0.899
        checks = {item.id: item for item in check_offline_metrics(offline_payload(), live)}
        self.assertEqual(checks["causal_fidelity"].status, "fail")

    def test_missing_or_non_numeric_metric_fails_without_crashing(self):
        payload = offline_payload()
        payload["contrast_evaluator"]["paired_discrimination_accuracy"] = "0.95"
        checks = {item.id: item for item in check_offline_metrics(payload, live_causal_payload())}
        self.assertEqual(checks["paired_discrimination_accuracy"].status, "fail")
        self.assertIn("not numeric", checks["paired_discrimination_accuracy"].details["error"])

    def test_semantic_stability_requires_all_three_thresholds(self):
        passing = {
            "claim_exact_agreement_rate": 0.9,
            "supported_verdict_rate": 0.9,
            "score_population_std": 2.0,
            "evaluation_scope": "historical_answer_projection",
            "current_answer_projection_claimed": False,
        }
        self.assertEqual(check_semantic_stability(passing).status, "pass")
        for key, value in (
            ("claim_exact_agreement_rate", 0.899),
            ("supported_verdict_rate", 0.899),
            ("score_population_std", 2.001),
        ):
            with self.subTest(key=key):
                payload = deepcopy(passing)
                payload[key] = value
                self.assertEqual(check_semantic_stability(payload).status, "fail")

        wrong_scope = deepcopy(passing)
        wrong_scope["current_answer_projection_claimed"] = True
        self.assertEqual(check_semantic_stability(wrong_scope).status, "fail")

    def test_current_deterministic_stability_binds_current_answer_bytes(self):
        original = json.loads(
            (ROOT / "results" / "public_tencent_current_deterministic_stability.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(check_current_deterministic_stability(original, ROOT).status, "pass")
        payload = deepcopy(original)
        payload["cases"]["after_publication"]["answer_sha256"] = "0" * 64
        self.assertEqual(check_current_deterministic_stability(payload, ROOT).status, "fail")

        payload = deepcopy(original)
        payload["cases"]["before_publication"]["scorecard_sha256s"] = [
            "not-a-digest"
        ] * 5
        self.assertEqual(check_current_deterministic_stability(payload, ROOT).status, "fail")

        payload = deepcopy(original)
        payload["cases"]["before_publication"]["scorecard_sha256s"] = ["0" * 64] * 5
        self.assertEqual(check_current_deterministic_stability(payload, ROOT).status, "fail")

        payload = deepcopy(original)
        payload["cases"]["before_publication"]["runs"] = 6
        self.assertEqual(check_current_deterministic_stability(payload, ROOT).status, "fail")

        payload = deepcopy(original)
        payload["cases"]["before_publication"]["final_scores"][0] = 99
        self.assertEqual(check_current_deterministic_stability(payload, ROOT).status, "fail")

    def test_current_live_causal_binds_historical_hy3_inputs(self):
        payload = json.loads(
            (ROOT / "results" / "live_causal_experiment_current.json").read_text(encoding="utf-8")
        )
        self.assertEqual(check_current_live_causal(payload, ROOT).status, "pass")
        payload["input_hashes"]["results/live_causal_mutated.json"] = "0" * 64
        self.assertEqual(check_current_live_causal(payload, ROOT).status, "fail")

    def test_public_tencent_scores_require_both_cases_at_90(self):
        self.assertEqual(
            check_public_tencent_scores({"final_score": 90}, {"final_score": 90}).status,
            "pass",
        )

    def test_public_answerability_oracles_require_all_four_metrics(self):
        passing = scorecard_with_answerability_metrics()
        self.assertEqual(check_public_answerability_oracles(passing, passing).status, "pass")
        failing = deepcopy(passing)
        failing["dimensions"][0]["metrics"]["answerability_match"] = 0
        self.assertEqual(check_public_answerability_oracles(failing, passing).status, "fail")

    def test_refusal_adversaries_require_all_capped_detected_attacks(self):
        payload = offline_payload()
        payload["contrast_evaluator"]["results"] = [
            {"name": name, "mutated_score": 20, "detected": True}
            for name in (
                "empty_answer", "affirmative_unknown_claim", "blanket_refusal",
                "incorrect_refusal", "irrelevant_future_refusal", "unrelated_negative_refusal",
                "cross_clause_negative_refusal", "available_source_future_refusal",
            )
        ]
        self.assertEqual(check_refusal_adversaries(payload).status, "pass")
        payload["contrast_evaluator"]["results"][0]["mutated_score"] = 93
        self.assertEqual(check_refusal_adversaries(payload).status, "fail")

    def test_evaluator_ablation_requires_ordered_component_gain(self):
        passing = {
            "coverage": {"strategies": 4, "total_strategy_mutation_runs": 10944},
            "strategy_results": {
                "no_audit_plain_output": {"destructive_detection_rate": 0},
                "exact_citation_only": {"destructive_detection_rate": 0.08},
                "point_in_time_exact_citation": {"destructive_detection_rate": 0.16},
                "full_chronofin": {"destructive_detection_rate": 1, "invariance_violation_rate": 0},
            },
        }
        self.assertEqual(check_evaluator_ablation(passing).status, "pass")
        passing["strategy_results"]["full_chronofin"]["destructive_detection_rate"] = 0.1
        self.assertEqual(check_evaluator_ablation(passing).status, "fail")

    def test_demo_gif_checks_dimensions_frames_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "assets" / "chronofin_demo.gif"
            target.parent.mkdir()
            header = b"GIF89a" + (1280).to_bytes(2, "little") + (720).to_bytes(2, "little")
            control = b"\x21\xf9\x04\x00" + (700).to_bytes(2, "little") + b"\x00\x00"
            target.write_bytes(header + control * 8 + b"\x3b")
            self.assertEqual(check_demo_gif(root).status, "pass")
            target.write_bytes(header + control * 20 + b"\x3b")
            self.assertEqual(check_demo_gif(root).status, "fail")

    def test_postfreeze_challenge_requires_frozen_failure_repair_chain(self):
        historical_initial = {"summary": {"all_passed": False, "base_passed": 3, "base_total": 6}}
        historical_final = {
            "frozen_hashes_verified": True,
            "execution": {
                "network_used": False,
                "model_called": False,
                "human_annotation_claimed": False,
                "statistical_heldout_claimed": False,
                "core_evaluator_modified_for_challenge": False,
            },
            "summary": {"all_passed": True, "base_passed": 6, "base_total": 6},
        }
        current_initial = {
            "summary": {"all_passed": False, "base_passed": 0, "base_total": 6},
        }
        current_final = {
            "frozen_hashes_verified": True,
            "evaluation_role": "seen_regression_fixture",
            "postfreeze_relative_to_current_evaluator": False,
            "heldout_claimed": False,
            "historical_attestation": {
                "integrity_checks_passed": True,
                "first_run_evaluator_identity_verified": False,
                "externally_timestamped": False,
            },
            "code_reference": {
                "current_evaluator_hashes_verified": True,
                "current_adapter_hashes_verified": True,
            },
            "execution": {
                "network_used": False,
                "model_called": False,
                "statistical_heldout_claimed": False,
                "current_run_is_regression": True,
                "current_evaluator_postdates_challenge": True,
            },
            "coverage": {"companies": 3, "source_formats": ["a", "b", "c"]},
            "summary": {
                "all_passed": True,
                "base_passed": 6,
                "base_total": 6,
                "adversarial_passed": 3,
                "adversarial_total": 3,
                "mean_valid_gold_score": 100,
                "mean_future_leak_score": 20,
            },
        }
        self.assertEqual(check_postfreeze_challenge(
            historical_initial, historical_final, current_initial, current_final,
        ).status, "pass")
        current_final["heldout_claimed"] = True
        self.assertEqual(check_postfreeze_challenge(
            historical_initial, historical_final, current_initial, current_final,
        ).status, "fail")

    def test_current_postfreeze_hash_chain_is_independently_verified(self):
        self.assertEqual(check_postfreeze_hash_chain(ROOT).status, "pass")

    def test_cleanroom_requires_each_core_command_and_no_cached_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "covered.txt").write_text("stable", encoding="utf-8")
            passing = cleanroom_payload(root)
            self.assertEqual(check_cleanroom(passing, root).status, "pass")
            passing["cached_pdfs_in_checkout"] = ["data/cache/report.pdf"]
            self.assertEqual(check_cleanroom(passing, root).status, "fail")

            for label in CLEANROOM_COMMAND_LABELS:
                with self.subTest(missing_label=label):
                    payload = cleanroom_payload(root)
                    payload["commands"] = [
                        item for item in payload["commands"] if item["label"] != label
                    ]
                    self.assertEqual(check_cleanroom(payload, root).status, "fail")

            payload = cleanroom_payload(root)
            payload["commands"][3]["exit_code"] = 1
            self.assertEqual(check_cleanroom(payload, root).status, "fail")

            payload = cleanroom_payload(root)
            payload["commands"][0], payload["commands"][1] = (
                payload["commands"][1], payload["commands"][0]
            )
            self.assertEqual(check_cleanroom(payload, root).status, "fail")

            payload = cleanroom_payload(root)
            payload["commands"][-1]["command"] = [
                "python", "scripts/verify_submission.py", "--compact"
            ]
            self.assertEqual(check_cleanroom(payload, root).status, "fail")

            payload = cleanroom_payload(root)
            payload["commands"][-1]["command"][0] = "/bin/true"
            self.assertEqual(check_cleanroom(payload, root).status, "fail")

            payload = cleanroom_payload(root)
            payload["commands"][-1].pop("verification_scope")
            self.assertEqual(check_cleanroom(payload, root).status, "fail")
        self.assertEqual(
            check_public_tencent_scores({"final_score": 89.999}, {"final_score": 100}).status,
            "fail",
        )

    def test_cleanroom_fails_after_any_fingerprinted_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            covered = root / "src" / "chronofin" / "models.py"
            covered.parent.mkdir(parents=True)
            covered.write_text("VERSION = 1\n", encoding="utf-8")
            evidence = cleanroom_payload(root)
            self.assertEqual(check_cleanroom(evidence, root).status, "pass")

            covered.write_text("VERSION = 2\n", encoding="utf-8")
            check = check_cleanroom(evidence, root)
            self.assertEqual(check.status, "fail")
            self.assertFalse(check.observed["source_tree_sha256_matches"])
            self.assertNotEqual(
                check.observed["source_tree_sha256"],
                check.observed["current_tree_sha256"],
            )

    def test_cleanroom_rejects_temporary_paths_without_echoing_them(self):
        leaked_paths = (
            "/var/folders/x/chronofin-cleanroom-a1b2c3/checkout",
            "/tmp/pip-ephem-wheel-cache-z9y8x7/wheels",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "covered.txt").write_text("stable", encoding="utf-8")
            for leaked_path in leaked_paths:
                with self.subTest(leaked_path=leaked_path):
                    evidence = cleanroom_payload(root)
                    evidence["commands"][0]["stdout"] = f"created {leaked_path}"
                    check = check_cleanroom(evidence, root)
                    self.assertEqual(check.status, "fail")
                    self.assertGreater(check.observed["temporary_path_leaks"], 0)
                    self.assertNotIn(leaked_path, json.dumps(check.to_dict()))

    def test_temporary_path_canonicalization_removes_pip_cache_path(self):
        leaked_path = "/tmp/pip-ephem-wheel-cache-a1b2/wheels/aa/bb"
        cleaned = canonicalize_temporary_paths(f"Stored in {leaked_path}\n")
        self.assertNotIn(leaked_path, cleaned)
        self.assertIn("<TEMP_PATH>", cleaned)
        self.assertEqual(temporary_path_leak_locations(cleaned), ())

    def test_synthetic_benchmark_checks_coverage_and_typed_recall(self):
        self.assertEqual(check_synthetic_benchmark(synthetic_benchmark_payload()).status, "pass")
        payload = synthetic_benchmark_payload()
        payload["coverage"]["base_tasks"] = 71
        self.assertEqual(check_synthetic_benchmark(payload).status, "fail")
        payload = synthetic_benchmark_payload()
        payload["metrics"]["destructive_subtype_recall"]["type_0"] = 0.899
        self.assertEqual(check_synthetic_benchmark(payload).status, "fail")

    def test_json_loader_rejects_malformed_and_nonstandard_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.json").write_text("{broken", encoding="utf-8")
            (root / "nan.json").write_text('{"score": NaN}', encoding="utf-8")
            payloads, check = load_json_artifacts(root, ("broken.json", "nan.json"))
        self.assertEqual(payloads, {})
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.observed["parse_errors"], 2)

    def test_secret_scan_finds_token_without_echoing_it(self):
        suspected = "sk-" + ("A" * 32)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.txt").write_text("TOKEN=" + suspected, encoding="utf-8")
            check = check_suspected_sk_secrets(root)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.observed["suspected_keys"], 1)
        self.assertNotIn(suspected, json.dumps(check.to_dict()))
        self.assertEqual(check.details["findings"][0]["path"], "config.txt")

    def test_secret_scan_handles_chunk_boundary(self):
        suspected = b"sk-" + (b"B" * 32)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # The default scanner reads 1 MiB chunks; split the token there.
            # Keep a non-token delimiter before ``sk-`` while splitting ``sk``
            # from ``-...`` across the chunk boundary.
            (root / "boundary.bin").write_bytes(
                (b"x" * (1024 * 1024 - 3)) + b" " + suspected
            )
            check = check_suspected_sk_secrets(root)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.observed["suspected_keys"], 1)

    def test_raw_provider_request_id_is_rejected_without_echoing_value(self):
        raw_id = "12345678-1234-1234-1234-123456789abc"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results").mkdir()
            (root / "results" / "trace.json").write_text(
                json.dumps({"trace": {"request_id": raw_id}}), encoding="utf-8"
            )
            check = check_raw_provider_request_ids(root)
        self.assertEqual(check.status, "fail")
        self.assertNotIn(raw_id, json.dumps(check.to_dict()))

    def test_non_git_directory_is_not_checkable(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=128, stdout=b"", stderr=b"not a git repository"
        )

        def fake_runner(*args, **kwargs):
            return completed

        with tempfile.TemporaryDirectory() as directory:
            check = check_cached_pdfs_not_tracked(Path(directory), runner=fake_runner)
        self.assertEqual(check.status, "not_checkable")
        self.assertNotEqual(check.status, "pass")

    def test_tracked_cached_pdf_fails(self):
        responses = iter((
            subprocess.CompletedProcess(args=[], returncode=0, stdout=b"/repo\n", stderr=b""),
            subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=b"data/cache/tencent/report.pdf\0data/cache/tencent/manifest.json\0",
                stderr=b"",
            ),
        ))

        def fake_runner(*args, **kwargs):
            return next(responses)

        check = check_cached_pdfs_not_tracked(ROOT, runner=fake_runner)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.observed["tracked_cached_pdfs"], 1)

    def test_check_objects_are_machine_serializable(self):
        item = Check("id", "category", "pass", "description", observed={"value": 1})
        self.assertEqual(json.loads(json.dumps(item.to_dict()))["status"], "pass")


class SubmissionVerifierReportTests(unittest.TestCase):
    def test_current_submission_always_emits_serializable_report(self):
        report = verify_submission(ROOT)
        json.loads(json.dumps(report, ensure_ascii=False))
        self.assertIn(report["status"], {"pass", "fail"})
        git_check = next(
            item for item in report["checks"]
            if item["id"] == "cached_pdfs_git_tracking"
        )
        self.assertIn(git_check["status"], {"pass", "not_checkable"})

    def test_cleanroom_prerequisite_scope_is_explicit_and_non_circular(self):
        report = verify_submission(ROOT, include_cleanroom=False)
        self.assertEqual(
            report["scope"],
            "all_submission_checks_except_cleanroom_self_check",
        )
        self.assertFalse(report["policy"]["cleanroom_self_check_included"])
        self.assertNotIn(
            "cleanroom_reproduction",
            {item["id"] for item in report["checks"]},
        )

    def test_cli_returns_nonzero_and_json_for_failed_report(self):
        failed_report = {
            "status": "fail",
            "summary": {"total": 1, "pass": 0, "fail": 1, "not_checkable": 0},
            "checks": [],
        }
        output = io.StringIO()
        with patch("scripts.verify_submission.verify_submission", return_value=failed_report):
            with patch("sys.stdout", output):
                exit_code = main(["--compact"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "fail")


if __name__ == "__main__":
    unittest.main()
