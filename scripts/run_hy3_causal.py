#!/usr/bin/env python3
"""System-level causal test: mutate one source leaf, then rerun Hy3."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import Hy3Config, RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.evaluator.mutations import evaluate_causal_mutation
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import write_html, write_json


QUERY = Query(
    "截至2025-12-31，云舟科技FY2024收入、净利润及净利率是多少？并说明主要驱动与风险。",
    "2025-12-31", "云舟科技", "FY2024"
)


def main() -> None:
    client = ChatCompletionsClient(Hy3Config.from_env())
    baseline_pipeline = ChronoFinPipeline(
        ROOT / "data" / "demo" / "manifest.json",
        client,
        RetrievalConfig(top_k=12),
    )
    baseline = baseline_pipeline.run(QUERY)
    with tempfile.TemporaryDirectory(prefix="chronofin-causal-") as directory:
        dataset = Path(directory) / "demo"
        shutil.copytree(ROOT / "data" / "demo", dataset)
        source = dataset / "cloud_2024.md"
        original = source.read_text(encoding="utf-8")
        mutated_text = original.replace(
            "净利润为 144 百万元，2023 财年为 100 百万元，同比增长 44%",
            "净利润为 180 百万元，2023 财年为 100 百万元，同比增长 80%",
        )
        if mutated_text == original:
            raise RuntimeError("source mutation did not match exactly")
        source.write_text(mutated_text, encoding="utf-8")

        pipeline = ChronoFinPipeline(
            dataset / "manifest.json",
            client,
            RetrievalConfig(top_k=12),
        )
        mutated = pipeline.run(QUERY)
        score = ChronoFinEvaluator().evaluate(mutated, pipeline.chunk_index)

    net_profit_key = next(key for key in (claim.semantic_key for claim in baseline.claims) if "net_profit" in key)
    net_margin_key = next(key for key in (claim.semantic_key for claim in baseline.claims) if "net_margin" in key)
    source_evidence_id = next(
        evidence.id for evidence in baseline.evidence if evidence.chunk_id == "cloud_2024:p1:c2"
    )
    causal = evaluate_causal_mutation(
        baseline,
        mutated,
        {source_evidence_id},
        {net_profit_key: 180.0, net_margin_key: 15.0},
    )
    output = {
        "mutation": {
            "document": "cloud_2024.md",
            "leaf": "FY2024 net_profit",
            "before": 144.0,
            "after": 180.0,
            "oracle_margin_before": 12.0,
            "oracle_margin_after": 15.0,
        },
        "metrics": causal,
        "mutated_score": score.to_dict(),
        "hy3_trace": mutated.provenance.get("llm", {}),
    }
    baseline_score = ChronoFinEvaluator().evaluate(baseline, baseline_pipeline.chunk_index)
    write_json(baseline, ROOT / "results" / "live_causal_baseline.json")
    write_json(baseline_score, ROOT / "results" / "live_causal_baseline_score.json")
    write_json(mutated, ROOT / "results" / "live_causal_mutated.json")
    write_json(output, ROOT / "results" / "live_causal_experiment.json")
    write_html(mutated, ROOT / "results" / "live_causal_mutated.html", score)
    print(json.dumps({"metrics": causal, "mutated_score": score.final_score}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
