#!/usr/bin/env python3
"""Reproduce the deterministic evaluator and metamorphic experiments."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.mutations import (
    delete_claim_citation,
    evaluate_causal_mutation,
    forge_quote,
    run_contrast_suite,
)
from chronofin.ingest import ingest_manifest
from chronofin.models import AnalysisAnswer, Query
from chronofin.render import load_answer, write_html, write_json
from chronofin.retrieval import BM25Retriever, future_leak_count


MANIFEST = ROOT / "data" / "demo" / "manifest.json"
GOOD_PATH = ROOT / "data" / "demo" / "fixtures" / "good.json"
EXPECTED_KEYS = {
    "cloud.revenue.FY2024",
    "cloud.net_profit.FY2024",
    "cloud.net_margin.FY2024",
    "cloud.growth_drivers.FY2024",
    "cloud.customer_concentration.FY2024",
}


def causal_fixture(answer: AnalysisAnswer) -> tuple[AnalysisAnswer, dict[str, object]]:
    payload = answer.to_dict()
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
        elif claim["semantic_key"] == "cloud.net_margin.FY2024":
            claim["text"] = "云舟科技 2024 财年净利率为 15%。"
            claim["value"] = 15
    mutated = AnalysisAnswer.from_dict(payload)
    metrics = evaluate_causal_mutation(
        answer,
        mutated,
        {"E2"},
        {
            "cloud.net_profit.FY2024": 180.0,
            "cloud.net_margin.FY2024": 15.0,
        },
    )
    return mutated, metrics


def main() -> None:
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    documents, chunks_list = ingest_manifest(MANIFEST)
    chunks = {item.id: item for item in chunks_list}
    evaluator = ChronoFinEvaluator()
    good = load_answer(GOOD_PATH)
    medium, _ = delete_claim_citation(good, chunks)
    bad, _ = forge_quote(good, chunks)
    tiers = {}
    for name, answer in (("good", good), ("medium", medium), ("bad", bad)):
        score = evaluator.evaluate(answer, chunks, expected_semantic_keys=EXPECTED_KEYS)
        tiers[name] = score.to_dict()
        write_json(answer, results_dir / f"tier_{name}.json")
        write_json(score, results_dir / f"tier_{name}_score.json")
        write_html(answer, results_dir / f"tier_{name}.html", score)

    contrast = run_contrast_suite(good, chunks, evaluator, expected_semantic_keys=EXPECTED_KEYS)
    _, causal = causal_fixture(good)

    pit_query = Query("云舟科技 FY2025 全年净利润是多少？", "2025-12-31", "云舟科技", "FY2025")
    retriever = BM25Retriever(chunks.values())
    strict = retriever.search(pit_query, documents, top_k=30, temporal_filter=True)
    naive = retriever.search(pit_query, documents, top_k=30, temporal_filter=False)
    point_in_time = {
        "query": pit_query.__dict__,
        "strict_future_leak_count": future_leak_count(strict.hits, pit_query.as_of_date),
        "naive_future_leak_count": future_leak_count(naive.hits, pit_query.as_of_date),
        "strict_excluded_documents": list(strict.excluded_documents),
        "naive_retrieved_future_chunk_ids": [
            hit.chunk.id for hit in naive.hits if hit.chunk.published_at > pit_query.as_of_date
        ],
    }

    repeated_scores = [
        evaluator.evaluate(good, chunks, expected_semantic_keys=EXPECTED_KEYS).final_score
        for _ in range(20)
    ]
    consistency = {
        "runs": len(repeated_scores),
        "scores": repeated_scores,
        "range": max(repeated_scores) - min(repeated_scores),
        "exact_agreement": len(set(repeated_scores)) == 1,
        "scope": "deterministic evaluation layer only",
    }

    report = {
        "experiment_version": "offline-v1",
        "data": "CC0 synthetic financial reports; no human labels claimed",
        "quality_tiers": {name: {"score": value["final_score"], "verdict": value["verdict"], "hard_cap": value["hard_cap"]} for name, value in tiers.items()},
        "contrast_evaluator": contrast,
        "causal_system_oracle": causal,
        "point_in_time_ablation": point_in_time,
        "repeat_consistency": consistency,
        "claims_not_made": [
            "The lexical diagnostic is not semantic entailment.",
            "Deterministic repeat agreement is not human-human agreement.",
            "Synthetic-case performance is not evidence of production investment accuracy."
        ],
    }
    write_json(report, results_dir / "offline_experiment.json")
    print(json.dumps({
        "quality_tiers": report["quality_tiers"],
        "PDA": contrast["paired_discrimination_accuracy"],
        "IVR": contrast["invariance_violation_rate"],
        "causal_fidelity": causal["causal_fidelity"],
        "strict_future_leaks": point_in_time["strict_future_leak_count"],
        "naive_future_leaks": point_in_time["naive_future_leak_count"],
        "output": str(results_dir / "offline_experiment.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
