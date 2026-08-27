#!/usr/bin/env python3
"""Repeat the optional batch semantic judge and report its exact stability."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import Hy3Config
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.semantic import judge_claims_batch
from chronofin.ingest import ingest_manifest
from chronofin.llm import ChatCompletionsClient
from chronofin.render import load_answer, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--output", default="results/semantic_stability.json")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--chunk-chars", type=int, default=2200)
    parser.add_argument("--expected-answerability", choices=("answerable", "partial", "unanswerable"), default=None)
    args = parser.parse_args()

    answer = load_answer(args.answer)
    _, chunks_list = ingest_manifest(args.manifest, args.chunk_chars, 260)
    chunks = {chunk.id: chunk for chunk in chunks_list}
    client = ChatCompletionsClient(Hy3Config.from_env())
    verdict_runs, traces, scores = [], [], []
    evaluator = ChronoFinEvaluator()
    for _ in range(args.runs):
        verdicts, trace = judge_claims_batch(answer, client, chunks)
        verdict_runs.append(verdicts)
        traces.append(trace)
        scores.append(evaluator.evaluate(
            answer,
            chunks,
            semantic_verdicts=verdicts,
            expected_answerability=args.expected_answerability,
        ).final_score)
    claim_ids = sorted(set().union(*(set(run) for run in verdict_runs)))
    per_claim = {
        claim_id: {
            "verdicts": [run.get(claim_id, "omitted") for run in verdict_runs],
            "exact_agreement": len({run.get(claim_id, "omitted") for run in verdict_runs}) == 1,
        }
        for claim_id in claim_ids
    }
    result = {
        "runs": args.runs,
        "model": "hy3",
        "expected_answerability": args.expected_answerability,
        "per_claim": per_claim,
        "claim_exact_agreement_rate": sum(item["exact_agreement"] for item in per_claim.values()) / max(1, len(per_claim)),
        "supported_verdict_rate": sum(verdict == "supported" for run in verdict_runs for verdict in run.values()) / max(1, sum(len(run) for run in verdict_runs)),
        "semantic_augmented_scores": scores,
        "score_population_std": statistics.pstdev(scores),
        "traces": traces,
        "limitations": [
            "The judge model family is the same as the answer model, so self-preference may remain.",
            "Repeat agreement is not human-expert agreement.",
            "Semantic judgments cannot override deterministic time, identity, or arithmetic gates."
        ],
    }
    write_json(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
