#!/usr/bin/env python3
"""Offline, read-only acceptance checks for the ChronoFin submission.

The verifier deliberately does not regenerate experiments or access the
network.  It validates the checked-in submission artifacts and emits one JSON
document to stdout.  Failed checks produce exit status 1.  A check that cannot
be performed (currently only Git tracking outside a work tree) is reported as
``not_checkable`` and is never silently counted as a pass.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronofin.reproducibility import (  # noqa: E402
    temporary_path_leak_locations,
    tree_fingerprint,
)

REQUIRED_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "source": (
        "README.md",
        ".env.example",
        "LICENSE",
        "app.py",
        "pyproject.toml",
        "src/chronofin/__init__.py",
        "src/chronofin/models.py",
        "src/chronofin/pipeline.py",
        "src/chronofin/projection.py",
        "src/chronofin/retrieval.py",
        "src/chronofin/summary.py",
        "src/chronofin/evaluator/core.py",
        "src/chronofin/evaluator/benchmark.py",
        "src/chronofin/evaluator/mutations.py",
        "src/chronofin/evaluator/proof_graph.py",
        "scripts/run_offline_experiments.py",
        "scripts/run_synthetic_benchmark.py",
        "scripts/run_evaluator_ablation.py",
        "scripts/run_deterministic_stability.py",
        "scripts/reprocess_saved_causal.py",
        "scripts/build_demo_gif.py",
        "scripts/run_postfreeze_challenge.py",
        "scripts/run_cleanroom_check.py",
        "scripts/sanitize_public_artifacts.py",
        "scripts/run_public_tencent_demo.py",
        "scripts/run_semantic_stability.py",
        "scripts/verify_submission.py",
        "tests/test_submission_verifier.py",
    ),
    "docs": (
        "docs/data_card.md",
        "docs/demo_script.md",
        "docs/evaluation_method.md",
        "docs/experiment_report.md",
        "docs/human_annotation_protocol.md",
        "docs/innovation_review.md",
        "docs/research_landscape.md",
        "docs/evaluator_ablation.md",
        "docs/postfreeze_challenge_report.md",
        "assets/chronofin_demo.gif",
        "data/challenge/challenge_v1.json",
        "data/challenge/FROZEN.sha256",
        "data/challenge/EVALUATOR_FROZEN.sha256",
        "data/challenge/HISTORICAL_V1_RESULTS.sha256",
        "data/challenge/EVALUATOR_CURRENT_V2.sha256",
        "data/challenge/ADAPTER_CURRENT_V2.sha256",
        "data/challenge/CURRENT_V2_ADAPTER_FIX.json",
        "data/challenge/CURRENT_V2_REGRESSION_CHAIN.sha256",
    ),
    "results": (
        "results/offline_experiment.json",
        "results/synthetic_benchmark.json",
        "results/evaluator_ablation.json",
        "results/postfreeze_challenge_v1.json",
        "results/postfreeze_challenge_v1_after_adapter_fix.json",
        "results/postfreeze_challenge_v1_current_regression.json",
        "results/postfreeze_challenge_v1_current_regression_after_slot_fix.json",
        "results/cleanroom_verification.json",
        "results/live_causal_experiment.json",
        "results/live_causal_baseline_current.json",
        "results/live_causal_baseline_current_score.json",
        "results/live_causal_mutated_current.json",
        "results/live_causal_experiment_current.json",
        "results/public_tencent_before_publication_final_score.json",
        "results/public_tencent_after_publication_final_score.json",
        "results/public_tencent_semantic_stability_final.json",
        "results/public_tencent_current_deterministic_stability.json",
    ),
}

REQUIRED_JSON_FILES: tuple[str, ...] = (
    *REQUIRED_ARTIFACTS["results"],
    "data/challenge/CURRENT_V2_ADAPTER_FIX.json",
)

OFFLINE_RESULT = "results/offline_experiment.json"
LIVE_CAUSAL_RESULT = "results/live_causal_experiment_current.json"
SYNTHETIC_BENCHMARK_RESULT = "results/synthetic_benchmark.json"
TENCENT_BEFORE_SCORE = "results/public_tencent_before_publication_final_score.json"
TENCENT_AFTER_SCORE = "results/public_tencent_after_publication_final_score.json"
SEMANTIC_STABILITY_RESULT = "results/public_tencent_semantic_stability_final.json"
CURRENT_DETERMINISTIC_STABILITY_RESULT = "results/public_tencent_current_deterministic_stability.json"
EVALUATOR_ABLATION_RESULT = "results/evaluator_ablation.json"
POSTFREEZE_INITIAL_RESULT = "results/postfreeze_challenge_v1.json"
POSTFREEZE_FINAL_RESULT = "results/postfreeze_challenge_v1_after_adapter_fix.json"
POSTFREEZE_CURRENT_INITIAL_RESULT = "results/postfreeze_challenge_v1_current_regression.json"
POSTFREEZE_CURRENT_FINAL_RESULT = "results/postfreeze_challenge_v1_current_regression_after_slot_fix.json"
POSTFREEZE_FIX_MANIFEST = "data/challenge/CURRENT_V2_ADAPTER_FIX.json"
CLEANROOM_RESULT = "results/cleanroom_verification.json"
DEMO_GIF = "assets/chronofin_demo.gif"

REQUIRED_DESTRUCTIVE_MUTATIONS = frozenset({
    "forged_quote", "citation_metadata_forgery", "future_leak",
    "known_at_mismatch", "missing_known_at", "wrong_entity", "wrong_period",
    "claim_text_wrong_entity", "claim_text_wrong_period", "claim_polarity_reversal",
    "wrong_query_entity", "wrong_query_period", "wrong_query_metric", "wrong_unit",
    "wrong_fact_unit", "wrong_operand_unit", "calculation_error",
    "claim_text_numeric_error", "extraneous_claim_number", "chinese_numeral_error",
    "summary_numeric_error", "summary_unsupported_claim", "missing_citation",
    "prompt_injection", "caveat_prompt_injection", "caveat_investment_advice",
    "imperative_investment_advice", "false_caveat_assertion", "empty_answer",
    "affirmative_unknown_claim", "blanket_refusal", "incorrect_refusal",
    "irrelevant_future_refusal", "unrelated_negative_refusal",
    "cross_clause_negative_refusal", "available_source_future_refusal",
})

SECRET_PATTERN = re.compile(
    rb"(?<![A-Za-z0-9])sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}"
)
SCAN_EXCLUDED_PARTS = frozenset({
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".venv", "__pycache__", "node_modules", "venv",
})


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    status: str
    description: str
    expected: Any = None
    observed: Any = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResultShapeError(ValueError):
    """Raised when a required result field is absent or non-numeric."""


def _pass_fail(
    check_id: str,
    category: str,
    passed: bool,
    description: str,
    *,
    expected: Any = None,
    observed: Any = None,
    details: Mapping[str, Any] | None = None,
) -> Check:
    return Check(
        id=check_id,
        category=category,
        status="pass" if passed else "fail",
        description=description,
        expected=expected,
        observed=observed,
        details=dict(details or {}),
    )


def _required_number(payload: Mapping[str, Any], path: str) -> float:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ResultShapeError(f"missing numeric field: {path}")
        current = current[part]
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise ResultShapeError(f"field is not numeric: {path}")
    value = float(current)
    if not math.isfinite(value):
        raise ResultShapeError(f"field is not finite: {path}")
    return value


def check_required_artifacts(
    root: Path,
    artifacts: Mapping[str, Sequence[str]] = REQUIRED_ARTIFACTS,
) -> Check:
    missing: dict[str, list[str]] = {}
    empty: dict[str, list[str]] = {}
    required_count = 0
    for category, paths in artifacts.items():
        for relative in paths:
            required_count += 1
            target = root / relative
            if not target.is_file():
                missing.setdefault(category, []).append(relative)
            elif target.stat().st_size == 0:
                empty.setdefault(category, []).append(relative)
    return _pass_fail(
        "required_artifacts",
        "artifacts",
        not missing and not empty,
        "Required source, documentation, and result artifacts exist and are non-empty.",
        expected={"missing": 0, "empty": 0, "readme_enforced": True},
        observed={
            "required_count": required_count,
            "missing_count": sum(map(len, missing.values())),
            "empty_count": sum(map(len, empty.values())),
        },
        details={"missing": missing, "empty": empty},
    )


def _reject_nonstandard_json(token: str) -> None:
    raise ValueError(f"non-standard JSON constant: {token}")


def load_json_artifacts(
    root: Path,
    relative_paths: Sequence[str] = REQUIRED_JSON_FILES,
) -> tuple[dict[str, Mapping[str, Any]], Check]:
    payloads: dict[str, Mapping[str, Any]] = {}
    errors: dict[str, str] = {}
    for relative in relative_paths:
        target = root / relative
        try:
            raw = target.read_text(encoding="utf-8")
            payload = json.loads(raw, parse_constant=_reject_nonstandard_json)
            if not isinstance(payload, Mapping):
                raise ValueError("top-level JSON value must be an object")
            payloads[relative] = payload
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors[relative] = f"{type(exc).__name__}: {exc}"
    check = _pass_fail(
        "result_json_parse",
        "results",
        not errors,
        "Every required result is a UTF-8, standards-compliant JSON object.",
        expected={"parse_errors": 0},
        observed={"parsed": len(payloads), "parse_errors": len(errors)},
        details={"errors": errors},
    )
    return payloads, check


def _shape_failure(check_id: str, description: str, exc: Exception) -> Check:
    return _pass_fail(
        check_id,
        "metrics",
        False,
        description,
        observed=None,
        details={"error": str(exc)},
    )


def check_offline_metrics(
    offline: Mapping[str, Any] | None,
    live_causal: Mapping[str, Any] | None,
) -> list[Check]:
    checks: list[Check] = []
    description = "Offline quality tiers are strictly ordered good > medium > bad."
    try:
        if offline is None:
            raise ResultShapeError(f"unavailable result: {OFFLINE_RESULT}")
        good = _required_number(offline, "quality_tiers.good.score")
        medium = _required_number(offline, "quality_tiers.medium.score")
        bad = _required_number(offline, "quality_tiers.bad.score")
        checks.append(_pass_fail(
            "offline_quality_order",
            "metrics",
            good > medium > bad,
            description,
            expected="good > medium > bad",
            observed={"good": good, "medium": medium, "bad": bad},
        ))
    except ResultShapeError as exc:
        checks.append(_shape_failure("offline_quality_order", description, exc))

    threshold_specs = (
        (
            "paired_discrimination_accuracy",
            "contrast_evaluator.paired_discrimination_accuracy",
            ">= 0.9",
            lambda value: value >= 0.9,
            "Paired discrimination accuracy (PDA) meets the submission threshold.",
        ),
        (
            "invariance_violation_rate",
            "contrast_evaluator.invariance_violation_rate",
            "<= 0.05",
            lambda value: value <= 0.05,
            "Invariance violation rate (IVR) meets the submission threshold.",
        ),
        (
            "strict_future_leak_count",
            "point_in_time_ablation.strict_future_leak_count",
            "== 0",
            lambda value: value == 0.0,
            "Strict point-in-time retrieval contains no future evidence.",
        ),
    )
    for check_id, field_path, expected, predicate, metric_description in threshold_specs:
        try:
            if offline is None:
                raise ResultShapeError(f"unavailable result: {OFFLINE_RESULT}")
            value = _required_number(offline, field_path)
            checks.append(_pass_fail(
                check_id,
                "metrics",
                predicate(value),
                metric_description,
                expected=expected,
                observed=value,
            ))
        except ResultShapeError as exc:
            checks.append(_shape_failure(check_id, metric_description, exc))

    causal_description = "Offline and live Hy3 causal fidelity both meet the threshold."
    try:
        if offline is None:
            raise ResultShapeError(f"unavailable result: {OFFLINE_RESULT}")
        if live_causal is None:
            raise ResultShapeError(f"unavailable result: {LIVE_CAUSAL_RESULT}")
        offline_fidelity = _required_number(offline, "causal_system_oracle.causal_fidelity")
        live_fidelity = _required_number(live_causal, "metrics.causal_fidelity")
        checks.append(_pass_fail(
            "causal_fidelity",
            "metrics",
            min(offline_fidelity, live_fidelity) >= 0.9,
            causal_description,
            expected={"offline": ">= 0.9", "live_hy3": ">= 0.9"},
            observed={"offline": offline_fidelity, "live_hy3": live_fidelity},
        ))
    except ResultShapeError as exc:
        checks.append(_shape_failure("causal_fidelity", causal_description, exc))
    return checks


def check_public_tencent_scores(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> Check:
    description = "Final public Tencent before/after score cards both reach 90."
    try:
        if before is None:
            raise ResultShapeError(f"unavailable result: {TENCENT_BEFORE_SCORE}")
        if after is None:
            raise ResultShapeError(f"unavailable result: {TENCENT_AFTER_SCORE}")
        values = {
            "before_publication": _required_number(before, "final_score"),
            "after_publication": _required_number(after, "final_score"),
        }
        return _pass_fail(
            "public_tencent_final_scores",
            "metrics",
            all(value >= 90.0 for value in values.values()),
            description,
            expected={"before_publication": ">= 90", "after_publication": ">= 90"},
            observed=values,
        )
    except ResultShapeError as exc:
        return _shape_failure("public_tencent_final_scores", description, exc)


def check_current_live_causal(
    causal: Mapping[str, Any] | None,
    root: Path = ROOT,
) -> Check:
    description = "Current deterministic rebinding of retained Hy3 causal answers is input-bound, local, responsive, and excellent."
    expected_inputs = {
        "results/live_causal_baseline.json",
        "results/live_causal_mutated.json",
    }
    try:
        if causal is None:
            raise ResultShapeError(f"unavailable result: {LIVE_CAUSAL_RESULT}")
        inputs = causal.get("input_hashes")
        traces = causal.get("historical_hy3_traces")
        execution = causal.get("execution")
        if not isinstance(inputs, Mapping) or set(inputs) != expected_inputs:
            raise ResultShapeError("causal input_hashes must bind both retained Hy3 answers")
        if not isinstance(traces, Mapping) or set(traces) != {"baseline", "mutated"}:
            raise ResultShapeError("causal result must retain both historical Hy3 trace summaries")
        input_matches = all(
            isinstance(inputs[path], str)
            and inputs[path] == _sha256_path(root / path)
            for path in expected_inputs
        )
        trace_shape_ok = all(
            isinstance(trace, Mapping)
            and trace.get("model") == "hy3"
            and re.fullmatch(r"[0-9a-f]{64}", str(trace.get("prompt_hash", ""))) is not None
            and re.fullmatch(r"[0-9a-f]{64}", str(trace.get("request_id_sha256", ""))) is not None
            and "request_id" not in trace
            for trace in traces.values()
        )
        values = {
            "causal_key_response": _required_number(causal, "metrics.causal_key_response"),
            "locality": _required_number(causal, "metrics.locality"),
            "causal_fidelity": _required_number(causal, "metrics.causal_fidelity"),
            "baseline_score": _required_number(causal, "baseline_score.final_score"),
            "mutated_score": _required_number(causal, "mutated_score.final_score"),
        }
        declarations_ok = (
            isinstance(execution, Mapping)
            and execution.get("network_used") is False
            and execution.get("model_called") is False
            and execution.get("historical_hy3_answers_reused") is True
            and causal.get("evaluation_mode")
            == "current_deterministic_rebinding_of_historical_hy3_answers"
        )
        passed = (
            input_matches
            and trace_shape_ok
            and declarations_ok
            and min(values["causal_key_response"], values["locality"], values["causal_fidelity"]) >= 0.9
            and min(values["baseline_score"], values["mutated_score"]) >= 90.0
        )
        return _pass_fail(
            "current_live_causal_reprocessing", "metrics", passed, description,
            expected={"CKR/locality/fidelity": ">= 0.9", "scores": ">= 90", "input_hashes_match": True},
            observed={**values, "input_hashes_match": input_matches, "trace_shape_ok": trace_shape_ok},
            details={"scope_declarations_ok": declarations_ok},
        )
    except (OSError, ResultShapeError, TypeError, ValueError) as exc:
        return _shape_failure("current_live_causal_reprocessing", description, exc)


def check_public_answerability_oracles(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> Check:
    description = "Tencent before/after score cards use matching pre-registered answerability oracles."
    try:
        if before is None or after is None:
            raise ResultShapeError("one or both Tencent score cards are unavailable")

        def material(payload: Mapping[str, Any]) -> Mapping[str, Any]:
            dimensions = payload.get("dimensions")
            if not isinstance(dimensions, list):
                raise ResultShapeError("dimensions must be an array")
            match = next(
                (item for item in dimensions if isinstance(item, Mapping) and item.get("name") == "material_completeness"),
                None,
            )
            if not isinstance(match, Mapping) or not isinstance(match.get("metrics"), Mapping):
                raise ResultShapeError("material_completeness metrics are unavailable")
            return match["metrics"]

        observed: dict[str, float] = {}
        for prefix, payload in (("before", before), ("after", after)):
            metrics = material(payload)
            for name in ("answerability_oracle_supplied", "answerability_match", "output_structure_valid", "refusal_support"):
                observed[f"{prefix}.{name}"] = _required_number(metrics, name)
        return _pass_fail(
            "public_answerability_oracles",
            "metrics",
            all(value == 1.0 for value in observed.values()),
            description,
            expected="all oracle/structure/refusal-support metrics == 1",
            observed=observed,
        )
    except ResultShapeError as exc:
        return _shape_failure("public_answerability_oracles", description, exc)


def check_refusal_adversaries(offline: Mapping[str, Any] | None) -> Check:
    description = "All empty/UNKNOWN/refusal evidence-bypass attacks are detected and capped at 20."
    required = {
        "empty_answer", "affirmative_unknown_claim", "blanket_refusal",
        "incorrect_refusal", "irrelevant_future_refusal", "unrelated_negative_refusal",
        "cross_clause_negative_refusal", "available_source_future_refusal",
    }
    try:
        if offline is None:
            raise ResultShapeError(f"unavailable result: {OFFLINE_RESULT}")
        contrast = offline.get("contrast_evaluator")
        if not isinstance(contrast, Mapping) or not isinstance(contrast.get("results"), list):
            raise ResultShapeError("contrast_evaluator.results must be an array")
        observed: dict[str, float] = {}
        detected: dict[str, bool] = {}
        for item in contrast["results"]:
            if not isinstance(item, Mapping) or item.get("name") not in required:
                continue
            name = str(item["name"])
            observed[name] = _required_number(item, "mutated_score")
            detected[name] = bool(item.get("detected"))
        missing = sorted(required - set(observed))
        passed = not missing and all(value <= 20.0 for value in observed.values()) and all(detected.values())
        return _pass_fail(
            "refusal_adversarial_gates",
            "metrics",
            passed,
            description,
            expected={name: "mutated_score <= 20 and detected" for name in sorted(required)},
            observed=observed,
            details={"missing": missing, "detected": detected},
        )
    except ResultShapeError as exc:
        return _shape_failure("refusal_adversarial_gates", description, exc)


def check_synthetic_benchmark(benchmark: Mapping[str, Any] | None) -> Check:
    description = "Multi-cluster formal benchmark meets coverage, discrimination, invariance, and typed-recall gates."
    try:
        if benchmark is None:
            raise ResultShapeError(f"unavailable result: {SYNTHETIC_BENCHMARK_RESULT}")
        values = {
            "base_tasks": _required_number(benchmark, "coverage.base_tasks"),
            "companies": _required_number(benchmark, "coverage.companies"),
            "total_mutation_runs": _required_number(benchmark, "coverage.total_mutation_runs"),
            "destructive_runs": _required_number(benchmark, "coverage.destructive_runs"),
            "invariant_runs": _required_number(benchmark, "coverage.label_preserving_runs"),
            "PDA": _required_number(benchmark, "metrics.paired_discrimination_accuracy"),
            "IVR": _required_number(benchmark, "metrics.invariance_violation_rate"),
        }
        subtype_payload = benchmark.get("metrics", {}).get("destructive_subtype_recall", {})
        if not isinstance(subtype_payload, Mapping) or set(subtype_payload) != REQUIRED_DESTRUCTIVE_MUTATIONS:
            raise ResultShapeError("metrics.destructive_subtype_recall must contain exactly the 36 registered destructive types")
        subtype_values = {
            str(name): float(value)
            for name, value in subtype_payload.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        }
        if len(subtype_values) != len(subtype_payload):
            raise ResultShapeError("destructive subtype recall contains a non-numeric value")
        passed = (
            values["base_tasks"] >= 72
            and values["companies"] >= 8
            and values["total_mutation_runs"] >= 2736
            and values["destructive_runs"] >= 2592
            and values["invariant_runs"] >= 144
            and values["PDA"] >= 0.9
            and values["IVR"] <= 0.05
            and min(subtype_values.values()) >= 0.9
        )
        return _pass_fail(
            "synthetic_multicluster_benchmark", "metrics", passed, description,
            expected={
                "base_tasks": ">= 72", "companies": ">= 8", "mutation_runs": ">= 2736",
                "destructive_runs": ">= 2592", "invariant_runs": ">= 144",
                "PDA": ">= 0.9", "IVR": "<= 0.05", "min_typed_recall": ">= 0.9",
            },
            observed={**values, "min_typed_recall": min(subtype_values.values())},
            details={"destructive_subtype_recall": subtype_values},
        )
    except (ResultShapeError, ValueError) as exc:
        return _shape_failure("synthetic_multicluster_benchmark", description, exc)


def check_semantic_stability(stability: Mapping[str, Any] | None) -> Check:
    description = "Retained historical Hy3 judge repeats meet thresholds and explicitly disclaim binding to the current projection."
    try:
        if stability is None:
            raise ResultShapeError(f"unavailable result: {SEMANTIC_STABILITY_RESULT}")
        values = {
            "claim_exact_agreement_rate": _required_number(stability, "claim_exact_agreement_rate"),
            "supported_verdict_rate": _required_number(stability, "supported_verdict_rate"),
            "score_population_std": _required_number(stability, "score_population_std"),
        }
        passed = (
            values["claim_exact_agreement_rate"] >= 0.9
            and values["supported_verdict_rate"] >= 0.9
            and values["score_population_std"] <= 2.0
            and stability.get("evaluation_scope") == "historical_answer_projection"
            and stability.get("current_answer_projection_claimed") is False
        )
        return _pass_fail(
            "semantic_stability",
            "metrics",
            passed,
            description,
            expected={
                "claim_exact_agreement_rate": ">= 0.9",
                "supported_verdict_rate": ">= 0.9",
                "score_population_std": "<= 2",
                "evaluation_scope": "historical_answer_projection",
                "current_answer_projection_claimed": False,
            },
            observed={
                **values,
                "evaluation_scope": stability.get("evaluation_scope"),
                "current_answer_projection_claimed": stability.get("current_answer_projection_claimed"),
            },
        )
    except ResultShapeError as exc:
        return _shape_failure("semantic_stability", description, exc)


def check_current_deterministic_stability(
    stability: Mapping[str, Any] | None,
    root: Path = ROOT,
) -> Check:
    description = (
        "Current Tencent before/after answer bytes each declare at least five identical "
        "excellent runs bound to the checked-in canonical scorecard."
    )
    expected_cases = {
        "before_publication": {
            "answer_path": "results/public_tencent_before_publication_final.json",
            "score_path": "results/public_tencent_before_publication_final_score.json",
            "expected_answerability": "unanswerable",
        },
        "after_publication": {
            "answer_path": "results/public_tencent_after_publication_final.json",
            "score_path": "results/public_tencent_after_publication_final_score.json",
            "expected_answerability": "answerable",
        },
    }
    try:
        if stability is None:
            raise ResultShapeError(f"unavailable result: {CURRENT_DETERMINISTIC_STABILITY_RESULT}")
        cases = stability.get("cases")
        if not isinstance(cases, Mapping) or set(cases) != set(expected_cases):
            raise ResultShapeError("deterministic stability must contain exactly before/after cases")
        observed: dict[str, Any] = {}
        cases_ok = True
        for name, expected in expected_cases.items():
            case = cases.get(name)
            if not isinstance(case, Mapping):
                raise ResultShapeError(f"invalid stability case: {name}")
            scores = case.get("final_scores")
            hashes = case.get("scorecard_sha256s")
            hard_gates = case.get("all_hard_gate_reasons")
            if not isinstance(scores, list) or not isinstance(hashes, list) or not isinstance(hard_gates, list):
                raise ResultShapeError(f"invalid repeated arrays: {name}")
            declared_runs = case.get("runs")
            if isinstance(declared_runs, bool) or not isinstance(declared_runs, int):
                raise ResultShapeError(f"runs must be an integer: {name}")
            expected_path = expected["answer_path"]
            answer_path = str(case.get("answer_path", ""))
            actual_answer_hash = _sha256_path(root / expected_path)
            canonical_score_hash, canonical_scorecard = _canonical_json_sha256(
                root / expected["score_path"]
            )
            canonical_final_score = _required_number(canonical_scorecard, "final_score")
            canonical_hard_gates = canonical_scorecard.get("hard_gate_reasons")
            if not isinstance(canonical_hard_gates, list):
                raise ResultShapeError(f"canonical hard_gate_reasons must be an array: {name}")
            scores_valid = all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) == canonical_final_score
                for value in scores
            )
            hashes_valid = all(
                isinstance(value, str)
                and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                and value == canonical_score_hash
                for value in hashes
            )
            gates_valid = all(
                isinstance(item, list) and item == canonical_hard_gates
                for item in hard_gates
            )
            observed[name] = {
                "declared_runs": declared_runs,
                "runs": len(scores),
                "min_score": min(map(float, scores)) if scores else None,
                "distinct_scorecards": len(set(map(str, hashes))),
                "answer_sha256_matches": case.get("answer_sha256") == actual_answer_hash,
                "canonical_scorecard_sha256_matches": hashes_valid,
            }
            cases_ok = cases_ok and (
                answer_path == expected_path
                and case.get("expected_answerability") == expected["expected_answerability"]
                and declared_runs == len(scores) >= 5
                and len(hashes) == declared_runs
                and len(hard_gates) == declared_runs
                and scores_valid
                and canonical_final_score >= 90.0
                and hashes_valid
                and len(set(hashes)) == 1
                and gates_valid
                and not canonical_hard_gates
                and case.get("exact_scorecard_agreement") is True
                and _required_number(case, "score_population_std") == 0.0
                and case.get("answer_sha256") == actual_answer_hash
            )
        declarations_ok = (
            stability.get("schema_version") == "chronofin-current-deterministic-stability-v1"
            and stability.get("mode") == "deterministic_evaluator_repeat_no_model_call"
            and stability.get("network_used") is False
            and stability.get("model_called") is False
            and stability.get("semantic_entailment_claimed") is False
            and stability.get("manifest_path") == "data/cache/tencent/manifest.json"
            and isinstance(stability.get("manifest_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", str(stability.get("manifest_sha256"))) is not None
            and stability.get("all_exact_scorecard_agreement") is True
            and stability.get("all_scores_excellent") is True
        )
        return _pass_fail(
            "current_deterministic_stability", "reproducibility",
            cases_ok and declarations_ok, description,
            expected={"cases": 2, "runs_per_case": ">= 5", "min_score": ">= 90", "distinct_scorecards": 1},
            observed=observed,
            details={"scope_declarations_ok": declarations_ok},
        )
    except (OSError, ResultShapeError, TypeError, ValueError) as exc:
        return _shape_failure("current_deterministic_stability", description, exc)


def check_evaluator_ablation(ablation: Mapping[str, Any] | None) -> Check:
    description = "Four-strategy evaluator ablation is complete and the full system detects all controlled attacks."
    try:
        if ablation is None:
            raise ResultShapeError(f"unavailable result: {EVALUATOR_ABLATION_RESULT}")
        values = {
            "strategies": _required_number(ablation, "coverage.strategies"),
            "outcomes": _required_number(ablation, "coverage.total_strategy_mutation_runs"),
            "plain": _required_number(ablation, "strategy_results.no_audit_plain_output.destructive_detection_rate"),
            "citation": _required_number(ablation, "strategy_results.exact_citation_only.destructive_detection_rate"),
            "pit_citation": _required_number(ablation, "strategy_results.point_in_time_exact_citation.destructive_detection_rate"),
            "full": _required_number(ablation, "strategy_results.full_chronofin.destructive_detection_rate"),
            "full_ivr": _required_number(ablation, "strategy_results.full_chronofin.invariance_violation_rate"),
        }
        passed = (
            values["strategies"] >= 4
            and values["outcomes"] >= 10944
            and values["plain"] < values["citation"] < values["pit_citation"] < values["full"]
            and values["full"] >= 0.9
            and values["full_ivr"] <= 0.05
        )
        return _pass_fail(
            "evaluator_component_ablation", "metrics", passed, description,
            expected="plain < citation < PIT+citation < full; full >= .9; IVR <= .05",
            observed=values,
        )
    except ResultShapeError as exc:
        return _shape_failure("evaluator_component_ablation", description, exc)


def check_postfreeze_challenge(
    historical_initial: Mapping[str, Any] | None,
    historical_final: Mapping[str, Any] | None,
    current_initial: Mapping[str, Any] | None,
    current_final: Mapping[str, Any] | None,
) -> Check:
    description = "Historical v1 and seen-data v2 preserve both failures and pass their separately scoped final protocols."
    try:
        if any(item is None for item in (historical_initial, historical_final, current_initial, current_final)):
            raise ResultShapeError("one or more historical/current challenge results are unavailable")
        assert historical_initial is not None and historical_final is not None
        assert current_initial is not None and current_final is not None
        observed = {
            "companies": _required_number(current_final, "coverage.companies"),
            "source_formats": float(len(current_final.get("coverage", {}).get("source_formats", []))),
            "historical_initial_base_passed": _required_number(historical_initial, "summary.base_passed"),
            "historical_final_base_passed": _required_number(historical_final, "summary.base_passed"),
            "current_initial_base_passed": _required_number(current_initial, "summary.base_passed"),
            "current_final_base_passed": _required_number(current_final, "summary.base_passed"),
            "current_base_total": _required_number(current_final, "summary.base_total"),
            "current_adversarial_passed": _required_number(current_final, "summary.adversarial_passed"),
            "current_adversarial_total": _required_number(current_final, "summary.adversarial_total"),
            "current_mean_valid_score": _required_number(current_final, "summary.mean_valid_gold_score"),
            "current_mean_future_leak_score": _required_number(current_final, "summary.mean_future_leak_score"),
        }
        historical_execution = historical_final.get("execution", {})
        current_execution = current_final.get("execution", {})
        code_reference = current_final.get("code_reference", {})
        historical_attestation = current_final.get("historical_attestation", {})
        declarations_ok = (
            isinstance(historical_execution, Mapping)
            and historical_execution.get("network_used") is False
            and historical_execution.get("model_called") is False
            and historical_execution.get("statistical_heldout_claimed") is False
            and historical_execution.get("core_evaluator_modified_for_challenge") is False
            and isinstance(current_execution, Mapping)
            and current_execution.get("network_used") is False
            and current_execution.get("model_called") is False
            and current_execution.get("statistical_heldout_claimed") is False
            and current_execution.get("current_run_is_regression") is True
            and current_execution.get("current_evaluator_postdates_challenge") is True
            and current_final.get("evaluation_role") == "seen_regression_fixture"
            and current_final.get("postfreeze_relative_to_current_evaluator") is False
            and current_final.get("heldout_claimed") is False
            and current_final.get("frozen_hashes_verified") is True
            and isinstance(code_reference, Mapping)
            and code_reference.get("current_evaluator_hashes_verified") is True
            and code_reference.get("current_adapter_hashes_verified") is True
            and isinstance(historical_attestation, Mapping)
            and historical_attestation.get("integrity_checks_passed") is True
            and historical_attestation.get("first_run_evaluator_identity_verified") is False
            and historical_attestation.get("externally_timestamped") is False
        )
        passed = (
            historical_initial.get("summary", {}).get("all_passed") is False
            and historical_final.get("summary", {}).get("all_passed") is True
            and current_initial.get("summary", {}).get("all_passed") is False
            and current_final.get("summary", {}).get("all_passed") is True
            and observed["companies"] >= 3
            and observed["source_formats"] >= 3
            and observed["historical_initial_base_passed"] == 3
            and observed["historical_final_base_passed"] == 6
            and observed["current_initial_base_passed"] == 0
            and observed["current_final_base_passed"] == observed["current_base_total"] >= 6
            and observed["current_adversarial_passed"] == observed["current_adversarial_total"] >= 3
            and observed["current_mean_valid_score"] >= 90
            and observed["current_mean_future_leak_score"] <= 20
            and declarations_ok
        )
        return _pass_fail(
            "postfreeze_real_company_challenge", "metrics", passed, description,
            expected="historical 3/6→6/6; seen-regression 0/6→6/6; 3/3 negatives; no held-out claim",
            observed=observed,
            details={"scope_declarations_ok": declarations_ok},
        )
    except (ResultShapeError, TypeError) as exc:
        return _shape_failure("postfreeze_real_company_challenge", description, exc)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_sha256(path: Path) -> tuple[str, Mapping[str, Any]]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonstandard_json,
    )
    if not isinstance(payload, Mapping):
        raise ResultShapeError(f"canonical scorecard must be a JSON object: {path.name}")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest(), payload


def _read_checksum_ledger(
    root: Path,
    relative: str,
    *,
    verify_files: bool,
    expected_paths: set[str],
) -> dict[str, str]:
    ledger = root / relative
    values: dict[str, str] = {}
    for line_number, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            expected, item = line.split(None, 1)
        except ValueError as exc:
            raise ResultShapeError(f"invalid checksum ledger line: {relative}:{line_number}") from exc
        item = item.strip()
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None or item in values:
            raise ResultShapeError(f"invalid or duplicate checksum entry: {relative}:{line_number}")
        target = (root / item).resolve()
        if root.resolve() not in target.parents:
            raise ResultShapeError(f"checksum path escapes repository: {item}")
        if verify_files and _sha256_path(target) != expected:
            raise ResultShapeError(f"checksum mismatch: {item}")
        values[item] = expected
    if set(values) != expected_paths:
        raise ResultShapeError(f"unexpected checksum path set: {relative}")
    return values


def check_postfreeze_hash_chain(root: Path) -> Check:
    description = "Dataset, historical results, current evaluator/adapter, and v2 repair chain pass independent SHA-256 verification."
    data_paths = {
        "data/challenge/challenge_v1.json",
        "data/challenge/source_excerpts/apple_sec_xbrl_fy2024.md",
        "data/challenge/source_excerpts/microsoft_ir_html_fy2025.md",
        "data/challenge/source_excerpts/nvidia_cfo_pdf_fy2025.md",
    }
    historical_evaluator_paths = {
        f"src/chronofin/evaluator/{name}.py"
        for name in (
            "__init__", "ablation", "benchmark", "citation", "core", "mutations",
            "numeric", "proof_graph", "semantic", "temporal",
        )
    }
    current_evaluator_paths = historical_evaluator_paths | {
        "src/chronofin/__init__.py", "src/chronofin/llm.py", "src/chronofin/models.py",
        "src/chronofin/ontology.py", "src/chronofin/projection.py", "src/chronofin/prompts.py",
        "src/chronofin/retrieval.py", "src/chronofin/summary.py",
    }
    historical_result_paths = {
        POSTFREEZE_INITIAL_RESULT, POSTFREEZE_FINAL_RESULT,
    }
    chain_paths = {
        POSTFREEZE_CURRENT_INITIAL_RESULT, POSTFREEZE_CURRENT_FINAL_RESULT, POSTFREEZE_FIX_MANIFEST,
    }
    try:
        data_hashes = _read_checksum_ledger(
            root, "data/challenge/FROZEN.sha256", verify_files=True, expected_paths=data_paths,
        )
        historical_evaluator = _read_checksum_ledger(
            root, "data/challenge/EVALUATOR_FROZEN.sha256", verify_files=False,
            expected_paths=historical_evaluator_paths,
        )
        historical_results = _read_checksum_ledger(
            root, "data/challenge/HISTORICAL_V1_RESULTS.sha256", verify_files=True,
            expected_paths=historical_result_paths,
        )
        current_evaluator = _read_checksum_ledger(
            root, "data/challenge/EVALUATOR_CURRENT_V2.sha256", verify_files=True,
            expected_paths=current_evaluator_paths,
        )
        current_adapter = _read_checksum_ledger(
            root, "data/challenge/ADAPTER_CURRENT_V2.sha256", verify_files=True,
            expected_paths={"scripts/run_postfreeze_challenge.py"},
        )
        current_chain = _read_checksum_ledger(
            root, "data/challenge/CURRENT_V2_REGRESSION_CHAIN.sha256", verify_files=True,
            expected_paths=chain_paths,
        )
        historical_initial = json.loads((root / POSTFREEZE_INITIAL_RESULT).read_text(encoding="utf-8"))
        historical_final = json.loads((root / POSTFREEZE_FINAL_RESULT).read_text(encoding="utf-8"))
        current_final = json.loads((root / POSTFREEZE_CURRENT_FINAL_RESULT).read_text(encoding="utf-8"))
        manifest = json.loads((root / POSTFREEZE_FIX_MANIFEST).read_text(encoding="utf-8"))
        embedded_ok = (
            historical_initial.get("frozen_hashes") == data_hashes
            and historical_final.get("frozen_hashes") == data_hashes
            and historical_final.get("code_reference", {}).get("evaluator_source_hashes_at_run") == historical_evaluator
            and current_final.get("frozen_hashes") == data_hashes
            and current_final.get("code_reference", {}).get("current_evaluator_source_hashes_at_run") == current_evaluator
            and current_final.get("code_reference", {}).get("current_adapter_source_hashes_at_run") == current_adapter
            and manifest.get("first_run", {}).get("sha256") == current_chain[POSTFREEZE_CURRENT_INITIAL_RESULT]
            and manifest.get("final_run", {}).get("sha256") == current_chain[POSTFREEZE_CURRENT_FINAL_RESULT]
            and manifest.get("frozen_data_ledger_sha256") == _sha256_path(root / "data/challenge/FROZEN.sha256")
            and manifest.get("final_run", {}).get("current_evaluator_ledger_sha256") == _sha256_path(root / "data/challenge/EVALUATOR_CURRENT_V2.sha256")
            and manifest.get("final_run", {}).get("current_adapter_ledger_sha256") == _sha256_path(root / "data/challenge/ADAPTER_CURRENT_V2.sha256")
            and manifest.get("evaluation_role") == "seen_regression_fixture"
            and manifest.get("postfreeze_relative_to_current_evaluator") is False
            and manifest.get("heldout_claimed") is False
            and manifest.get("challenge_data_modified") is False
        )
        return _pass_fail(
            "postfreeze_hash_chain", "integrity", embedded_ok, description,
            expected={"verified_ledgers": 6, "embedded_manifests_match": True},
            observed={
                "verified_ledgers": 6,
                "verified_files": sum(map(len, (
                    data_hashes, historical_results, current_evaluator, current_adapter, current_chain,
                ))),
                "embedded_manifests_match": embedded_ok,
            },
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ResultShapeError) as exc:
        return _pass_fail(
            "postfreeze_hash_chain", "integrity", False, description,
            observed=None, details={"error": str(exc)},
        )


def check_cleanroom(cleanroom: Mapping[str, Any] | None, root: Path = ROOT) -> Check:
    description = "Sanitized temporary checkout passes local install, tests, experiments, CLI, Git staging, and byte-identical regeneration."
    try:
        if cleanroom is None:
            raise ResultShapeError(f"unavailable result: {CLEANROOM_RESULT}")
        commands = cleanroom.get("commands")
        if not isinstance(commands, list):
            raise ResultShapeError("commands must be an array")
        expected_labels = (
            "create_venv",
            "install_local_package",
            "compileall",
            "unit_tests",
            "reprocess_saved_causal",
            "offline_experiments",
            "synthetic_benchmark",
            "evaluator_ablation",
            "postfreeze_regression",
            "sanitize_public_artifacts",
            "cli_inspect",
            "git_init",
            "git_stage_submission",
            "submission_verifier",
        )
        command_shape_ok = all(
            isinstance(item, Mapping)
            and isinstance(item.get("exit_code"), int)
            and not isinstance(item.get("exit_code"), bool)
            for item in commands
        )
        actual_labels = tuple(
            str(item.get("label")) if isinstance(item, Mapping) else "<invalid>"
            for item in commands
        )
        all_commands_succeeded = command_shape_ok and all(
            item.get("exit_code") == 0 for item in commands if isinstance(item, Mapping)
        )
        command_protocol_matches = actual_labels == expected_labels
        prerequisite_verifier_ok = False
        if command_protocol_matches and isinstance(commands[-1], Mapping):
            verifier_command = commands[-1].get("command")
            prerequisite_verifier_ok = (
                isinstance(verifier_command, list)
                and verifier_command == [
                    "<CLEANROOM>/venv/bin/python",
                    "scripts/verify_submission.py",
                    "--compact",
                    "--cleanroom-prerequisites",
                ]
                and commands[-1].get("verification_scope")
                == "all_submission_checks_except_cleanroom_self_check"
            )
        cached = cleanroom.get("cached_pdfs_in_checkout")
        source_fingerprint = cleanroom.get("source_tree_sha256")
        if (
            not isinstance(source_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_fingerprint) is None
        ):
            raise ResultShapeError("source_tree_sha256 must be a lowercase SHA-256 digest")
        current_fingerprint = tree_fingerprint(root)
        fingerprint_matches = source_fingerprint == current_fingerprint
        reproduced_fingerprint = cleanroom.get("reproduced_tree_sha256")
        if (
            not isinstance(reproduced_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", reproduced_fingerprint) is None
        ):
            raise ResultShapeError("reproduced_tree_sha256 must be a lowercase SHA-256 digest")
        reproduction_matches = (
            reproduced_fingerprint == source_fingerprint
            and cleanroom.get("tree_fingerprint_matches") is True
        )
        temporary_path_locations = temporary_path_leak_locations(cleanroom)
        passed = (
            cleanroom.get("all_passed") is True
            and cleanroom.get("network_access") is False
            and cleanroom.get("api_key_environment_removed") is True
            and cleanroom.get("fresh_virtual_environment") is True
            and cleanroom.get("temporary_checkout_deleted_after_run") is True
            and isinstance(cached, list) and not cached
            and command_protocol_matches
            and all_commands_succeeded
            and prerequisite_verifier_ok
            and fingerprint_matches
            and reproduction_matches
            and not temporary_path_locations
        )
        return _pass_fail(
            "cleanroom_reproduction", "reproducibility", passed, description,
            expected={
                "all_passed": True,
                "cached_pdfs": 0,
                "required_commands_in_order": list(expected_labels),
                "source_tree_sha256": current_fingerprint,
                "reproduced_tree_sha256": current_fingerprint,
                "temporary_path_leaks": 0,
            },
            observed={
                "all_passed": cleanroom.get("all_passed"),
                "commands": len(commands),
                "command_protocol_matches": command_protocol_matches,
                "all_commands_succeeded": all_commands_succeeded,
                "prerequisite_verifier_scope_matches": prerequisite_verifier_ok,
                "cached_pdfs": len(cached) if isinstance(cached, list) else None,
                "source_tree_sha256": source_fingerprint,
                "current_tree_sha256": current_fingerprint,
                "source_tree_sha256_matches": fingerprint_matches,
                "reproduced_tree_sha256": reproduced_fingerprint,
                "reproduction_matches": reproduction_matches,
                "temporary_path_leaks": len(temporary_path_locations),
            },
            details={
                "actual_command_labels": list(actual_labels),
                "temporary_path_leak_locations": list(temporary_path_locations),
            },
        )
    except (OSError, ResultShapeError) as exc:
        return _shape_failure("cleanroom_reproduction", description, exc)


def check_demo_gif(root: Path) -> Check:
    description = "A non-empty 16:9 demo GIF exists and its encoded duration is below two minutes."
    path = root / DEMO_GIF
    try:
        data = path.read_bytes()
        if len(data) < 14 or data[:6] not in {b"GIF87a", b"GIF89a"}:
            raise ValueError("missing GIF87a/GIF89a header")
        width = int.from_bytes(data[6:8], "little")
        height = int.from_bytes(data[8:10], "little")
        delays: list[int] = []
        cursor = 0
        marker = b"\x21\xf9\x04"
        while True:
            index = data.find(marker, cursor)
            if index < 0:
                break
            if index + 8 > len(data):
                raise ValueError("truncated graphic control extension")
            delays.append(int.from_bytes(data[index + 4:index + 6], "little"))
            cursor = index + 3
        duration_seconds = sum(delays) / 100.0
        observed = {
            "width": width,
            "height": height,
            "frames_with_delay": len(delays),
            "duration_seconds": duration_seconds,
            "bytes": len(data),
        }
        passed = (
            data.endswith(b"\x3b")
            and width >= 960
            and height >= 540
            and len(delays) >= 2
            and 0 < duration_seconds <= 120
        )
        return _pass_fail(
            "demo_gif", "artifacts", passed, description,
            expected={"min_dimensions": [960, 540], "frames": ">= 2", "duration_seconds": "0 < d <= 120"},
            observed=observed,
        )
    except (OSError, ValueError) as exc:
        return _pass_fail(
            "demo_gif", "artifacts", False, description,
            observed=None, details={"error": f"{type(exc).__name__}: {exc}"},
        )


def _scan_file_for_sk_tokens(path: Path, chunk_size: int = 1024 * 1024) -> list[dict[str, Any]]:
    """Return non-secret metadata for suspicious tokens, including boundary matches."""

    findings: list[dict[str, Any]] = []
    seen_offsets: set[int] = set()
    carry = b""
    consumed = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            combined = carry + chunk
            combined_start = consumed - len(carry)
            for match in SECRET_PATTERN.finditer(combined):
                absolute_offset = combined_start + match.start()
                if absolute_offset in seen_offsets:
                    continue
                seen_offsets.add(absolute_offset)
                findings.append({
                    "byte_offset": absolute_offset,
                    "fingerprint": hashlib.sha256(match.group(0)).hexdigest()[:12],
                })
            consumed += len(chunk)
            carry = combined[-256:]
    return findings


def check_suspected_sk_secrets(root: Path) -> Check:
    findings: list[dict[str, Any]] = []
    read_errors: dict[str, str] = {}
    if root.is_dir():
        candidates = sorted(
            (
                path for path in root.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and not any(part in SCAN_EXCLUDED_PARTS for part in path.relative_to(root).parts)
            ),
            key=lambda item: item.as_posix(),
        )
    else:
        candidates = []
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        try:
            for finding in _scan_file_for_sk_tokens(path):
                findings.append({"path": relative, **finding})
        except OSError as exc:
            read_errors[relative] = f"{type(exc).__name__}: {exc}"
    return _pass_fail(
        "suspected_sk_secrets",
        "security",
        not findings and not read_errors,
        "Working tree contains no token resembling a live sk-* API key.",
        expected={"suspected_keys": 0, "read_errors": 0},
        observed={
            "files_scanned": len(candidates),
            "suspected_keys": len(findings),
            "read_errors": len(read_errors),
        },
        # Never echo the matching token itself.
        details={"findings": findings, "read_errors": read_errors},
    )


def check_raw_provider_request_ids(root: Path) -> Check:
    """Raw provider telemetry IDs are unnecessary in a public submission."""

    findings: list[dict[str, Any]] = []

    def visit(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_location = f"{location}.{key}" if location else key
                if key == "request_id" and item:
                    findings.append({"location": next_location})
                else:
                    visit(item, next_location)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{location}[{index}]")

    for path in sorted((root / "results").glob("*.json")) if (root / "results").is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        before = len(findings)
        visit(payload, "")
        for finding in findings[before:]:
            finding["path"] = path.relative_to(root).as_posix()
    return _pass_fail(
        "raw_provider_request_ids",
        "privacy",
        not findings,
        "Checked-in result JSON contains no raw provider request ID; SHA-256 digests are allowed.",
        expected={"raw_request_ids": 0},
        observed={"raw_request_ids": len(findings)},
        details={"findings": findings},
    )


def check_cached_pdfs_not_tracked(
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> Check:
    """Check Git's index only; no work-tree mutation or network access occurs."""

    runner = runner or subprocess.run
    description = "PDF files under data/cache are not tracked by Git."
    try:
        probe = runner(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        return Check(
            "cached_pdfs_git_tracking",
            "git",
            "not_checkable",
            description,
            expected={"tracked_cached_pdfs": 0},
            observed=None,
            details={"reason": f"git unavailable: {type(exc).__name__}: {exc}"},
        )
    if probe.returncode != 0:
        reason = probe.stderr.decode("utf-8", errors="replace").strip()
        return Check(
            "cached_pdfs_git_tracking",
            "git",
            "not_checkable",
            description,
            expected={"tracked_cached_pdfs": 0},
            observed=None,
            details={"reason": reason or "root is not inside a Git work tree"},
        )
    indexed = runner(
        ["git", "-C", str(root), "ls-files", "-z", "--", "data/cache"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if indexed.returncode != 0:
        reason = indexed.stderr.decode("utf-8", errors="replace").strip()
        return _pass_fail(
            "cached_pdfs_git_tracking",
            "git",
            False,
            description,
            expected={"tracked_cached_pdfs": 0},
            details={"error": reason or "git ls-files failed"},
        )
    tracked = [
        raw.decode("utf-8", errors="replace")
        for raw in indexed.stdout.split(b"\0")
        if raw and raw.lower().endswith(b".pdf")
    ]
    return _pass_fail(
        "cached_pdfs_git_tracking",
        "git",
        not tracked,
        description,
        expected={"tracked_cached_pdfs": 0},
        observed={"tracked_cached_pdfs": len(tracked)},
        details={"tracked": sorted(tracked)},
    )


def verify_submission(root: Path, *, include_cleanroom: bool = True) -> dict[str, Any]:
    root = root.resolve()
    checks: list[Check] = [check_required_artifacts(root)]
    payloads, parse_check = load_json_artifacts(root)
    checks.append(parse_check)
    checks.extend(check_offline_metrics(
        payloads.get(OFFLINE_RESULT),
        payloads.get(LIVE_CAUSAL_RESULT),
    ))
    checks.append(check_current_live_causal(payloads.get(LIVE_CAUSAL_RESULT), root))
    checks.append(check_refusal_adversaries(payloads.get(OFFLINE_RESULT)))
    checks.append(check_synthetic_benchmark(payloads.get(SYNTHETIC_BENCHMARK_RESULT)))
    checks.append(check_public_tencent_scores(
        payloads.get(TENCENT_BEFORE_SCORE),
        payloads.get(TENCENT_AFTER_SCORE),
    ))
    checks.append(check_public_answerability_oracles(
        payloads.get(TENCENT_BEFORE_SCORE),
        payloads.get(TENCENT_AFTER_SCORE),
    ))
    checks.append(check_semantic_stability(payloads.get(SEMANTIC_STABILITY_RESULT)))
    checks.append(check_current_deterministic_stability(
        payloads.get(CURRENT_DETERMINISTIC_STABILITY_RESULT), root,
    ))
    checks.append(check_evaluator_ablation(payloads.get(EVALUATOR_ABLATION_RESULT)))
    checks.append(check_postfreeze_challenge(
        payloads.get(POSTFREEZE_INITIAL_RESULT),
        payloads.get(POSTFREEZE_FINAL_RESULT),
        payloads.get(POSTFREEZE_CURRENT_INITIAL_RESULT),
        payloads.get(POSTFREEZE_CURRENT_FINAL_RESULT),
    ))
    checks.append(check_postfreeze_hash_chain(root))
    if include_cleanroom:
        checks.append(check_cleanroom(payloads.get(CLEANROOM_RESULT), root))
    checks.append(check_demo_gif(root))
    checks.append(check_suspected_sk_secrets(root))
    checks.append(check_raw_provider_request_ids(root))
    checks.append(check_cached_pdfs_not_tracked(root))

    counts = {
        status: sum(item.status == status for item in checks)
        for status in ("pass", "fail", "not_checkable")
    }
    status = "fail" if counts["fail"] else "pass"
    return {
        "schema_version": "chronofin-submission-verifier-v1",
        "scope": (
            "full_submission"
            if include_cleanroom
            else "all_submission_checks_except_cleanroom_self_check"
        ),
        "status": status,
        "root": str(root),
        "read_only": True,
        "network_access": False,
        "policy": {
            "readme_required": True,
            "not_checkable_is_not_pass": True,
            "not_checkable_causes_failure": False,
            "cleanroom_self_check_included": include_cleanroom,
        },
        "summary": {"total": len(checks), **counts},
        "checks": [item.to_dict() for item in checks],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=f"submission root (default: {ROOT})",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact rather than indented JSON",
    )
    parser.add_argument(
        "--cleanroom-prerequisites",
        action="store_true",
        help=(
            "inside the cleanroom only: verify every submission gate except the "
            "cleanroom report that this process is still constructing"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_submission(
        args.root,
        include_cleanroom=not args.cleanroom_prerequisites,
    )
    print(json.dumps(
        report,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=args.compact,
    ))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
