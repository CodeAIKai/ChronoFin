#!/usr/bin/env python3
"""Run the two-question Hy3 killer demo and save all reproducibility traces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import Hy3Config, RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import write_html, write_json


def run_case(pipeline: ChronoFinPipeline, query: Query, stem: str) -> dict[str, object]:
    answer = pipeline.run(query)
    score = ChronoFinEvaluator().evaluate(answer, pipeline.chunk_index)
    write_json(answer, ROOT / "results" / f"live_{stem}.json")
    write_json(score, ROOT / "results" / f"live_{stem}_score.json")
    write_html(answer, ROOT / "results" / f"live_{stem}.html", score)
    return {
        "answerability": answer.answerability.value,
        "summary": answer.executive_summary,
        "score": score.final_score,
        "hard_gates": score.hard_gate_reasons,
        "excluded_documents": answer.excluded_documents,
        "usage": answer.provenance.get("llm", {}).get("usage", {}),
    }


def main() -> None:
    (ROOT / "results").mkdir(exist_ok=True)
    pipeline = ChronoFinPipeline(
        ROOT / "data" / "demo" / "manifest.json",
        ChatCompletionsClient(Hy3Config.from_env()),
        RetrievalConfig(top_k=12, temporal_filter=True),
    )
    cases = {
        "fy2024_analysis": Query(
            "截至2025-12-31，云舟科技FY2024收入、净利润及净利率是多少？并说明主要驱动与风险。",
            "2025-12-31", "云舟科技", "FY2024"
        ),
        "fy2025_before_disclosure": Query(
            "截至2025-12-31，云舟科技FY2025全年收入、净利润和净利率是多少？",
            "2025-12-31", "云舟科技", "FY2025"
        ),
        "fy2025_after_disclosure": Query(
            "截至2026-03-21，云舟科技FY2025全年收入、净利润和净利率是多少？",
            "2026-03-21", "云舟科技", "FY2025"
        ),
    }
    summary = {name: run_case(pipeline, query, name) for name, query in cases.items()}
    write_json(summary, ROOT / "results" / "live_demo_summary.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

