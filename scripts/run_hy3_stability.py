#!/usr/bin/env python3
"""Repeat a fixed Hy3 task and report agreement without claiming human validity."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import Hy3Config, RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import load_answer, write_json


QUERY = Query(
    "截至2025-12-31，云舟科技FY2024收入、净利润及净利率是多少？并说明主要驱动与风险。",
    "2025-12-31", "云舟科技", "FY2024"
)


def value_map(answer):
    calculations = answer.calculation_index()
    return {
        claim.semantic_key: claim.value if claim.value is not None else (
            calculations[claim.calculation_id].result if claim.calculation_id in calculations else None
        )
        for claim in answer.claims if claim.semantic_key
    }


def main() -> None:
    causal_baseline = ROOT / "results" / "live_causal_baseline.json"
    baseline_path = causal_baseline if causal_baseline.exists() else ROOT / "results" / "live_fy2024_analysis.json"
    answers = [load_answer(baseline_path)] if baseline_path.exists() else []
    pipeline = ChronoFinPipeline(
        ROOT / "data" / "demo" / "manifest.json",
        ChatCompletionsClient(Hy3Config.from_env()),
        RetrievalConfig(top_k=12),
    )
    while len(answers) < 3:
        answers.append(pipeline.run(QUERY))
    evaluator = ChronoFinEvaluator()
    scores = [evaluator.evaluate(answer, pipeline.chunk_index).final_score for answer in answers]
    key_sets = [set(value_map(answer)) for answer in answers]
    shared_keys = set.intersection(*key_sets)
    numeric_agreement = {}
    for key in shared_keys:
        values = [value_map(answer)[key] for answer in answers]
        if all(isinstance(value, (int, float)) for value in values):
            numeric_agreement[key] = {"values": values, "range": max(values) - min(values)}
    pairwise_jaccard = []
    for i in range(len(key_sets)):
        for j in range(i + 1, len(key_sets)):
            pairwise_jaccard.append(len(key_sets[i] & key_sets[j]) / max(1, len(key_sets[i] | key_sets[j])))
    result = {
        "runs": 3,
        "model": "hy3",
        "temperature": Hy3Config.from_env().temperature,
        "answerability": [answer.answerability.value for answer in answers],
        "answerability_exact_agreement": len({answer.answerability.value for answer in answers}) == 1,
        "scores": scores,
        "score_mean": statistics.mean(scores),
        "score_population_std": statistics.pstdev(scores),
        "semantic_key_pairwise_jaccard_mean": statistics.mean(pairwise_jaccard),
        "numeric_agreement": numeric_agreement,
        "future_leak_runs": sum(
            any("source published after" in reason for reason in evaluator.evaluate(answer, pipeline.chunk_index).hard_gate_reasons)
            for answer in answers
        ),
        "limitation": "Repeat stability is not human-expert agreement or correctness proof.",
        "traces": [answer.provenance.get("llm", {}) for answer in answers],
    }
    for index, answer in enumerate(answers, start=1):
        write_json(answer, ROOT / "results" / f"live_stability_run_{index}.json")
    write_json(result, ROOT / "results" / "live_stability.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
