#!/usr/bin/env python3
"""Verify the historical post-freeze challenge and run the current regression.

This runner makes no HTTP requests and calls no model.  The frozen JSON is a
small AI-curated conformance set, not human annotation or a statistical
held-out benchmark.  The original v1 evaluator/result chain is retained as a
historical attestation.  Because the current evaluator was hardened after the
set became known, re-running it is explicitly labelled a regression test.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.evaluator import ChronoFinEvaluator
from chronofin.models import (
    AnalysisAnswer,
    Answerability,
    Calculation,
    Chunk,
    Claim,
    ClaimType,
    Evidence,
    Query,
)
from chronofin.projection import (
    canonical_caveats,
    canonical_derived_claim_text,
    canonical_unknown_claim_text,
)
from chronofin.retrieval import detect_financial_slots
from chronofin.summary import canonical_executive_summary


DATASET_PATH = ROOT / "data" / "challenge" / "challenge_v1.json"
FREEZE_PATH = ROOT / "data" / "challenge" / "FROZEN.sha256"
EVALUATOR_FREEZE_PATH = ROOT / "data" / "challenge" / "EVALUATOR_FROZEN.sha256"
HISTORICAL_RESULTS_PATH = ROOT / "data" / "challenge" / "HISTORICAL_V1_RESULTS.sha256"
CURRENT_EVALUATOR_PATH = ROOT / "data" / "challenge" / "EVALUATOR_CURRENT_V2.sha256"
CURRENT_ADAPTER_PATH = ROOT / "data" / "challenge" / "ADAPTER_CURRENT_V2.sha256"
HISTORICAL_INITIAL_RESULT = ROOT / "results" / "postfreeze_challenge_v1.json"
HISTORICAL_FINAL_RESULT = ROOT / "results" / "postfreeze_challenge_v1_after_adapter_fix.json"
CURRENT_FIRST_RESULT = ROOT / "results" / "postfreeze_challenge_v1_current_regression.json"
CURRENT_FIRST_RESULT_SHA256 = "bcc6ec66642ed254da5fd1e558bc2ece0ee6faae4d2b0c3737a5405e9d0ffd8f"
DEFAULT_OUTPUT = ROOT / "results" / "postfreeze_challenge_v1_current_regression_after_slot_fix.json"

HISTORICAL_EVALUATOR_PATHS = frozenset({
    "src/chronofin/evaluator/__init__.py",
    "src/chronofin/evaluator/ablation.py",
    "src/chronofin/evaluator/benchmark.py",
    "src/chronofin/evaluator/citation.py",
    "src/chronofin/evaluator/core.py",
    "src/chronofin/evaluator/mutations.py",
    "src/chronofin/evaluator/numeric.py",
    "src/chronofin/evaluator/proof_graph.py",
    "src/chronofin/evaluator/semantic.py",
    "src/chronofin/evaluator/temporal.py",
})
CURRENT_EVALUATOR_PATHS = HISTORICAL_EVALUATOR_PATHS | frozenset({
    "src/chronofin/__init__.py",
    "src/chronofin/llm.py",
    "src/chronofin/models.py",
    "src/chronofin/ontology.py",
    "src/chronofin/projection.py",
    "src/chronofin/prompts.py",
    "src/chronofin/retrieval.py",
    "src/chronofin/summary.py",
})
CURRENT_ADAPTER_PATHS = frozenset({"scripts/run_postfreeze_challenge.py"})
HISTORICAL_RESULT_PATHS = frozenset({
    "results/postfreeze_challenge_v1.json",
    "results/postfreeze_challenge_v1_after_adapter_fix.json",
})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_checksum_ledger(
    ledger: Path,
    root: Path,
    *,
    verify_files: bool,
    expected_paths: frozenset[str] | None = None,
) -> dict[str, str]:
    if not ledger.exists():
        raise RuntimeError(f"checksum ledger is missing: {ledger}")
    checked: dict[str, str] = {}
    for line_number, raw in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            expected, relative = line.split(None, 1)
        except ValueError as exc:
            raise RuntimeError(f"invalid checksum ledger line {line_number}") from exc
        relative = relative.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError(f"invalid SHA-256 at ledger line {line_number}")
        if relative in checked:
            raise RuntimeError(f"duplicate checksum path: {relative}")
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise RuntimeError(f"checksum path escapes repository: {relative}")
        if verify_files:
            if not path.is_file():
                raise RuntimeError(f"checksummed file is missing: {relative}")
            actual = _sha256(path)
            if actual != expected:
                raise RuntimeError(
                    f"file digest mismatch: {relative}; expected={expected}, actual={actual}"
                )
        checked[relative] = expected
    if expected_paths is not None and set(checked) != set(expected_paths):
        missing = sorted(set(expected_paths) - set(checked))
        unexpected = sorted(set(checked) - set(expected_paths))
        raise RuntimeError(f"checksum ledger path mismatch: missing={missing}, unexpected={unexpected}")
    return checked


def verify_frozen_files(root: Path = ROOT) -> dict[str, str]:
    """Verify the immutable dataset and source-excerpt ledger."""

    return _read_checksum_ledger(
        root / FREEZE_PATH.relative_to(ROOT),
        root,
        verify_files=True,
        expected_paths=frozenset({
            "data/challenge/challenge_v1.json",
            "data/challenge/source_excerpts/apple_sec_xbrl_fy2024.md",
            "data/challenge/source_excerpts/microsoft_ir_html_fy2025.md",
            "data/challenge/source_excerpts/nvidia_cfo_pdf_fy2025.md",
        }),
    )


def verify_historical_attestation(root: Path = ROOT) -> dict[str, Any]:
    """Verify retained v1 results without pretending current source is v1 source."""

    data_hashes = verify_frozen_files(root)
    evaluator_hashes = _read_checksum_ledger(
        root / EVALUATOR_FREEZE_PATH.relative_to(ROOT),
        root,
        verify_files=False,
        expected_paths=HISTORICAL_EVALUATOR_PATHS,
    )
    result_hashes = _read_checksum_ledger(
        root / HISTORICAL_RESULTS_PATH.relative_to(ROOT),
        root,
        verify_files=True,
        expected_paths=HISTORICAL_RESULT_PATHS,
    )
    initial = json.loads((root / HISTORICAL_INITIAL_RESULT.relative_to(ROOT)).read_text(encoding="utf-8"))
    final = json.loads((root / HISTORICAL_FINAL_RESULT.relative_to(ROOT)).read_text(encoding="utf-8"))
    embedded = final.get("code_reference", {}).get("evaluator_source_hashes_at_run")
    if embedded != evaluator_hashes:
        raise RuntimeError("historical result evaluator hashes do not match the v1 ledger")
    if final.get("frozen_hashes") != data_hashes or initial.get("frozen_hashes") != data_hashes:
        raise RuntimeError("historical result data hashes do not match the frozen dataset ledger")
    runner_hash = final.get("code_reference", {}).get("runner_sha256_at_run")
    if not isinstance(runner_hash, str) or re.fullmatch(r"[0-9a-f]{64}", runner_hash) is None:
        raise RuntimeError("historical runner hash is missing or malformed")
    if initial.get("summary", {}).get("all_passed") is not False:
        raise RuntimeError("retained historical first run must remain a failure")
    if final.get("summary", {}).get("all_passed") is not True:
        raise RuntimeError("retained historical repaired run must remain a pass")
    current_v1_path_hashes = {
        relative: _sha256(root / relative)
        for relative in evaluator_hashes
    }
    changed_paths = sorted(
        relative
        for relative, historical_hash in evaluator_hashes.items()
        if current_v1_path_hashes[relative] != historical_hash
    )
    return {
        "attestation_kind": "repository_local_historical_record",
        "integrity_checks_passed": True,
        "dataset_bytes_match_v1_ledger": True,
        "historical_results_match_result_ledger": True,
        "final_result_evaluator_manifest_matches_v1_ledger": True,
        "historical_runner_hash_recorded": True,
        "historical_runner_source_available": False,
        "first_run_evaluator_identity_verified": False,
        "externally_timestamped": False,
        "current_tree_compared_to_v1": True,
        "current_tree_matches_v1": not changed_paths,
        "changed_evaluator_paths": changed_paths,
        "data_hashes": data_hashes,
        "historical_evaluator_hashes": evaluator_hashes,
        "historical_result_hashes": result_hashes,
        "historical_runner_sha256": runner_hash,
        "interpretation": (
            "The historical final result embeds hashes matching the v1 evaluator ledger. "
            "This repository-local record is not an external trusted timestamp and does not "
            "verify the complete code identity of the first failed run."
        ),
    }


def verify_current_evaluator(root: Path = ROOT) -> dict[str, str]:
    """Verify the current red-team-hardened evaluator/materialization code."""

    return _read_checksum_ledger(
        root / CURRENT_EVALUATOR_PATH.relative_to(ROOT),
        root,
        verify_files=True,
        expected_paths=CURRENT_EVALUATOR_PATHS,
    )


def verify_current_adapter(root: Path = ROOT) -> dict[str, str]:
    """Verify the runner/materializer separately from evaluator dependencies."""

    return _read_checksum_ledger(
        root / CURRENT_ADAPTER_PATH.relative_to(ROOT),
        root,
        verify_files=True,
        expected_paths=CURRENT_ADAPTER_PATHS,
    )


def verify_current_predecessor(root: Path = ROOT) -> dict[str, Any]:
    path = root / CURRENT_FIRST_RESULT.relative_to(ROOT)
    actual = _sha256(path)
    if actual != CURRENT_FIRST_RESULT_SHA256:
        raise RuntimeError(
            "retained current-v2 first-run result digest mismatch: "
            f"expected={CURRENT_FIRST_RESULT_SHA256}, actual={actual}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    if summary.get("all_passed") is not False or summary.get("base_passed") != 0:
        raise RuntimeError("retained current-v2 first run must remain the 0/6 failure")
    return {
        "path": CURRENT_FIRST_RESULT.relative_to(ROOT).as_posix(),
        "sha256": actual,
        "all_passed": False,
        "base_passed": 0,
        "base_total": 6,
    }


def load_dataset(root: Path = ROOT) -> dict[str, Any]:
    verify_frozen_files(root)
    return json.loads((root / DATASET_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))


def _source_index(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["document_id"]: item for item in dataset["sources"]}


def build_chunk_index(dataset: dict[str, Any], root: Path = ROOT) -> dict[str, Chunk]:
    chunks: dict[str, Chunk] = {}
    for source in dataset["sources"]:
        snapshot = (root / source["snapshot_path"]).resolve()
        text = snapshot.read_text(encoding="utf-8")
        chunk = Chunk(
            id=source["chunk_id"],
            document_id=source["document_id"],
            text=text,
            page=int(source["page"]),
            section=source["section"],
            entity=source["entity"],
            period=source["period"],
            published_at=source["published_at"],
            source_url=source["source_url"],
            currency=source["currency"],
            unit=source["unit"],
        )
        chunks[chunk.id] = chunk
    return chunks


def materialize_gold_answer(case: dict[str, Any], source: dict[str, Any]) -> AnalysisAnswer:
    """Project frozen facts through the current public-output contract."""

    query = Query(**case["query"])
    gold = case["gold"]
    if gold["answerability"] == "unanswerable":
        requested_slots = set(detect_financial_slots(query.question)) - {"full_year"}
        unknown = Claim(
            id=f"{case['id']}:UNKNOWN1",
            text="pending deterministic projection",
            claim_type=ClaimType.UNKNOWN,
            entity=source["entity"],
            period=source["period"],
            unit="",
            known_at="",
            value=None,
            evidence_ids=(),
            calculation_id="",
            confidence=0.2,
            semantic_key="",
        )
        unknown = replace(
            unknown,
            text=canonical_unknown_claim_text(unknown, query.as_of_date, requested_slots),
        )
        claims = [unknown]
        return AnalysisAnswer(
            query=query,
            answerability=Answerability.UNANSWERABLE,
            executive_summary=canonical_executive_summary(claims),
            claims=claims,
            evidence=[],
            calculations=[],
            caveats=canonical_caveats(),
            excluded_documents=[{
                "document_id": source["document_id"],
                "title": source["title"],
                "published_at": source["published_at"],
                "reason": f"published after cutoff {query.as_of_date}",
            }],
            provenance={
                "fixture": "postfreeze-ai-curated-known-data-regression-v2",
                "materialization_spec": "chronofin-deterministic-visible-projection-v2",
                "model_called": False,
                "network_used": False,
            },
        )

    facts = source["facts"]
    if len(facts) != 2:
        raise RuntimeError(f"answer materializer requires two source facts: {case['id']}")
    evidence: list[Evidence] = []
    claims: list[Claim] = []
    for index, fact in enumerate(facts, 1):
        evidence_id = f"{case['id']}:E{index}"
        evidence.append(Evidence.from_dict({
                "id": evidence_id,
                "chunk_id": source["chunk_id"],
                "document_id": source["document_id"],
                "quote": fact["quote"],
                "page": source["page"],
                "published_at": source["published_at"],
                "source_url": source["source_url"],
            }))
        claims.append(Claim.from_dict({
                "id": f"{case['id']}:C{index}",
                "text": fact["quote"],
                "claim_type": "FACT",
                "entity": source["entity"],
                "period": source["period"],
                "unit": source["unit"],
                "known_at": source["published_at"],
                "value": fact["value"],
                "evidence_ids": [evidence_id],
                "calculation_id": "",
                "confidence": 0.99,
                "semantic_key": fact["semantic_key"],
            }))

    calculation_id = f"{case['id']}:CALC1"
    derived = source["derived"]
    calculation = Calculation.from_dict({
        "id": calculation_id,
        "expression": derived["formula"],
        "result": derived["value"],
        "unit": "%",
        "operands": [
            {
                "name": "net_income",
                "value": facts[1]["value"],
                "unit": source["unit"],
                "evidence_ids": [evidence[1].id],
            },
            {
                "name": "revenue",
                "value": facts[0]["value"],
                "unit": source["unit"],
                "evidence_ids": [evidence[0].id],
            },
        ],
    })
    derived_claim = Claim.from_dict({
            "id": f"{case['id']}:C3",
            "text": "pending deterministic projection",
            "claim_type": "DERIVED",
            "entity": source["entity"],
            "period": source["period"],
            "unit": "%",
            "known_at": source["published_at"],
            "value": derived["value"],
            "evidence_ids": [item.id for item in evidence],
            "calculation_id": calculation_id,
            "confidence": 0.99,
            "semantic_key": derived["semantic_key"],
        })
    claims.append(replace(
        derived_claim,
        text=canonical_derived_claim_text(derived_claim, calculation),
    ))
    return AnalysisAnswer(
        query=query,
        answerability=Answerability.ANSWERABLE,
        executive_summary=canonical_executive_summary(claims),
        claims=claims,
        evidence=evidence,
        calculations=[calculation],
        caveats=canonical_caveats(),
        excluded_documents=[],
        provenance={
            "fixture": "postfreeze-ai-curated-known-data-regression-v2",
            "materialization_spec": "chronofin-deterministic-visible-projection-v2",
            "model_called": False,
            "network_used": False,
        },
    )


def _gold_oracle(case: dict[str, Any], answer: AnalysisAnswer, score: Any) -> dict[str, Any]:
    gold = case["gold"]
    observed_values = {
        claim.semantic_key: claim.value
        for claim in answer.claims
        if claim.semantic_key and claim.value is not None
    }
    value_checks = {
        key: key in observed_values
        and math.isclose(float(observed_values[key]), float(value), rel_tol=1e-12, abs_tol=1e-9)
        for key, value in gold["expected_values"].items()
    }
    checks = {
        "answerability": answer.answerability.value == gold["answerability"],
        "all_expected_values": all(value_checks.values()),
        "no_unexpected_values": set(observed_values) == set(gold["expected_values"]),
        "refusal_has_no_evidence": (
            not answer.evidence
            and not answer.calculations
            and bool(answer.claims)
            and all(claim.claim_type.value == "UNKNOWN" for claim in answer.claims)
            if gold["must_have_no_evidence"]
            else bool(answer.evidence and answer.claims)
        ),
        "evaluator_minimum": score.final_score >= float(gold["minimum_evaluator_score"]),
        "no_hard_gate": not score.hard_gate_reasons,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "value_checks": value_checks,
    }


def evaluate_challenge(root: Path = ROOT) -> dict[str, Any]:
    hashes = verify_frozen_files(root)
    historical_attestation = verify_historical_attestation(root)
    current_evaluator_hashes = verify_current_evaluator(root)
    current_adapter_hashes = verify_current_adapter(root)
    predecessor = verify_current_predecessor(root)
    dataset = json.loads((root / DATASET_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    source_index = _source_index(dataset)
    chunk_index = build_chunk_index(dataset, root)
    evaluator = ChronoFinEvaluator()
    case_index = {item["id"]: item for item in dataset["cases"]}
    answers: dict[str, AnalysisAnswer] = {}
    base_results = []

    for case in dataset["cases"]:
        source = source_index[case["source_document_id"]]
        answer = materialize_gold_answer(case, source)
        answers[case["id"]] = answer
        expected_keys = set(case["gold"]["semantic_keys"]) or None
        score = evaluator.evaluate(
            answer,
            chunk_index,
            expected_semantic_keys=expected_keys,
            expected_answerability=case["gold"]["answerability"],
        )
        oracle = _gold_oracle(case, answer, score)
        base_results.append(
            {
                "case_id": case["id"],
                "entity": case["query"]["entity"],
                "as_of_date": case["query"]["as_of_date"],
                "expected_answerability": case["gold"]["answerability"],
                "observed_answerability": answer.answerability.value,
                "evaluator_score": score.final_score,
                "evaluator_verdict": score.verdict,
                "hard_gate_reasons": score.hard_gate_reasons,
                "oracle": oracle,
                "scorecard": score.to_dict(),
            }
        )

    adversarial_results = []
    for spec in dataset["adversarial_specs"]:
        after_answer = deepcopy(answers[spec["candidate_answer_case_id"]])
        before_case = case_index[spec["query_case_id"]]
        after_answer.query = Query(**before_case["query"])
        candidate_case = case_index[spec["candidate_answer_case_id"]]
        expected_keys = set(candidate_case["gold"]["semantic_keys"])
        score = evaluator.evaluate(
            after_answer,
            chunk_index,
            expected_semantic_keys=expected_keys,
            expected_answerability=before_case["gold"]["answerability"],
        )
        checks = {
            "score_at_or_below_cap": score.final_score <= float(spec["expected_max_evaluator_score"]),
            "required_hard_gate_present": spec["required_hard_gate"] in score.hard_gate_reasons,
            "future_evidence_count_positive": next(
                item.metrics.get("future_count", 0.0)
                for item in score.dimensions
                if item.name == "temporal_integrity"
            ) > 0.0,
        }
        adversarial_results.append(
            {
                "case_id": spec["id"],
                "transformation": spec["transformation"],
                "evaluator_score": score.final_score,
                "evaluator_verdict": score.verdict,
                "hard_gate_reasons": score.hard_gate_reasons,
                "passed": all(checks.values()),
                "checks": checks,
                "scorecard": score.to_dict(),
            }
        )

    base_passed = sum(bool(item["oracle"]["passed"]) for item in base_results)
    adversarial_passed = sum(bool(item["passed"]) for item in adversarial_results)
    all_passed = base_passed == len(base_results) and adversarial_passed == len(adversarial_results)
    source_registry = [
        {
            "document_id": source["document_id"],
            "entity": source["entity"],
            "published_at": source["published_at"],
            "source_format": source["source_format"],
            "source_url": source["source_url"],
            "publication_url": source["publication_url"],
            "snapshot_path": source["snapshot_path"],
            "snapshot_sha256": hashes[source["snapshot_path"]],
        }
        for source in dataset["sources"]
    ]
    return {
        "schema_version": "chronofin-postfreeze-known-data-regression-v2",
        "dataset_id": dataset["metadata"]["dataset_id"],
        "dataset_version": dataset["metadata"]["version"],
        "evaluation_mode": "known_data_regression_current_evaluator_v2",
        "evaluation_role": "seen_regression_fixture",
        "dataset_was_visible_during_current_hardening": True,
        "postfreeze_relative_to_current_evaluator": False,
        "heldout_claimed": False,
        "historical_v1_comparability": "same frozen cases; changed evaluator and visible-projection protocol",
        "frozen_hashes_verified": True,
        "frozen_hashes": hashes,
        "historical_attestation": historical_attestation,
        "code_reference": {
            "current_evaluator_hashes_verified": True,
            "current_evaluator_source_hashes_at_run": current_evaluator_hashes,
            "current_adapter_hashes_verified": True,
            "current_adapter_source_hashes_at_run": current_adapter_hashes,
            "predecessor_result": predecessor,
        },
        "source_registry": source_registry,
        "execution": {
            "network_used": False,
            "model_called": False,
            "human_annotation_claimed": False,
            "statistical_heldout_claimed": False,
            "current_run_is_regression": True,
            "current_evaluator_postdates_challenge": True,
            "challenge_was_known_during_current_hardening": True,
            "historical_v1_result": "results/postfreeze_challenge_v1_after_adapter_fix.json",
            "current_regression_first_run_result": "results/postfreeze_challenge_v1_current_regression.json",
            "challenge_data_modified_for_current_fix": False,
            "current_adapter_fix": (
                "The first current-v2 run exposed that generic metric-slot aliases recognized "
                "human wording but not underscored net_income/net_income_margin semantic keys. "
                "The general alias registry and its unit test were extended; frozen challenge "
                "questions, sources, dates, values, quotes, and gold were not changed."
            ),
            "interpretation": (
                "Regression evidence only: it checks that broad red-team hardening did not break "
                "the frozen real-company cases; it is not fresh held-out evidence."
            ),
        },
        "coverage": {
            "companies": len(dataset["sources"]),
            "source_formats": sorted({item["source_format"] for item in dataset["sources"]}),
            "base_cases": len(base_results),
            "prepublication_refusals": sum(
                item["expected_answerability"] == "unanswerable" for item in base_results
            ),
            "postpublication_answers": sum(
                item["expected_answerability"] == "answerable" for item in base_results
            ),
            "future_leak_negatives": len(adversarial_results),
        },
        "summary": {
            "all_passed": all_passed,
            "base_passed": base_passed,
            "base_total": len(base_results),
            "adversarial_passed": adversarial_passed,
            "adversarial_total": len(adversarial_results),
            "mean_valid_gold_score": round(
                sum(item["evaluator_score"] for item in base_results) / max(1, len(base_results)), 3
            ),
            "mean_future_leak_score": round(
                sum(item["evaluator_score"] for item in adversarial_results)
                / max(1, len(adversarial_results)),
                3,
            ),
        },
        "limitations": [
            "AI-curated; no human expert adjudication or inter-annotator agreement.",
            "The current evaluator was developed after these cases were visible; this run is regression-only, not held-out validation.",
            "Three companies and nine runs are a conformance regression, not a population estimate.",
            "Gold answers are deterministic materializations of frozen facts, not outputs from Hy3.",
            "Offline excerpts preserve exact cited spans and URLs but are not full copyrighted reports.",
            "Without a semantic judge, factual credit is restricted to exact evidence spans and canonical calculation projections.",
        ],
        "base_results": base_results,
        "adversarial_results": adversarial_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(json.dumps(
            {
                "data": verify_frozen_files(),
                "historical_v1": verify_historical_attestation(),
                "current_v2": verify_current_evaluator(),
                "adapter_v2": verify_current_adapter(),
                "current_v2_first_run": verify_current_predecessor(),
            },
            ensure_ascii=False,
            indent=2,
        ))
        return
    result = evaluate_challenge()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if not result["summary"]["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
