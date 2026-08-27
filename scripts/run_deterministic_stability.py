#!/usr/bin/env python3
"""Repeat current deterministic Tencent evaluations and bind exact inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.evaluator import ChronoFinEvaluator  # noqa: E402
from chronofin.ingest import ingest_manifest  # noqa: E402
from chronofin.render import load_answer, write_json  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.name


def _evaluate_case(
    answer_path: Path,
    expected_answerability: str,
    chunks: dict[str, Any],
    runs: int,
) -> dict[str, Any]:
    answer = load_answer(answer_path)
    serialized_scorecards: list[str] = []
    scores: list[float] = []
    hard_gates: list[list[str]] = []
    for _ in range(runs):
        scorecard = ChronoFinEvaluator().evaluate(
            answer,
            chunks,
            expected_answerability=expected_answerability,
        )
        serialized_scorecards.append(json.dumps(
            scorecard.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ))
        scores.append(scorecard.final_score)
        hard_gates.append(list(scorecard.hard_gate_reasons))
    scorecard_hashes = [
        hashlib.sha256(item.encode("utf-8")).hexdigest()
        for item in serialized_scorecards
    ]
    return {
        "answer_path": _relative(answer_path),
        "answer_sha256": _sha256(answer_path),
        "expected_answerability": expected_answerability,
        "runs": runs,
        "final_scores": scores,
        "score_population_std": statistics.pstdev(scores),
        "scorecard_sha256s": scorecard_hashes,
        "exact_scorecard_agreement": len(set(scorecard_hashes)) == 1,
        "all_hard_gate_reasons": hard_gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/cache/tencent/manifest.json")
    parser.add_argument(
        "--before-answer", type=Path,
        default=ROOT / "results/public_tencent_before_publication_final.json",
    )
    parser.add_argument(
        "--after-answer", type=Path,
        default=ROOT / "results/public_tencent_after_publication_final.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results/public_tencent_current_deterministic_stability.json",
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--chunk-chars", type=int, default=2200)
    args = parser.parse_args()
    if args.runs < 2:
        raise SystemExit("--runs must be at least 2")

    _, chunk_list = ingest_manifest(args.manifest, args.chunk_chars, 260)
    chunks = {item.id: item for item in chunk_list}
    cases = {
        "before_publication": _evaluate_case(args.before_answer, "unanswerable", chunks, args.runs),
        "after_publication": _evaluate_case(args.after_answer, "answerable", chunks, args.runs),
    }
    result = {
        "schema_version": "chronofin-current-deterministic-stability-v1",
        "mode": "deterministic_evaluator_repeat_no_model_call",
        "network_used": False,
        "model_called": False,
        "semantic_entailment_claimed": False,
        "manifest_path": _relative(args.manifest),
        "manifest_sha256": _sha256(args.manifest),
        "cases": cases,
        "all_exact_scorecard_agreement": all(
            item["exact_scorecard_agreement"] for item in cases.values()
        ),
        "all_scores_excellent": all(
            min(item["final_scores"]) >= 90 for item in cases.values()
        ),
        "limitations": [
            "Repeated deterministic evaluation is an implementation-stability check, not model semantic agreement.",
            "The cached official PDFs are locally pinned but intentionally excluded from the public repository.",
            "The separate retained Hy3 semantic-repeat artifact is historical and not bound to these current answer bytes.",
        ],
    }
    write_json(result, args.output)
    print(json.dumps({
        "output": _relative(args.output),
        "all_exact_scorecard_agreement": result["all_exact_scorecard_agreement"],
        "scores": {name: item["final_scores"] for name, item in cases.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
