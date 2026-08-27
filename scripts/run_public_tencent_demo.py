#!/usr/bin/env python3
"""Run the point-in-time unlock demo on unmodified official Tencent PDFs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import Hy3Config, RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.llm import ChatCompletionsClient
from chronofin.models import Answerability, Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import write_html, write_json


MANIFEST = ROOT / "data" / "cache" / "tencent" / "manifest.json"


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit("Run scripts/download_public_reports.py first.")
    pipeline = ChronoFinPipeline(
        MANIFEST,
        ChatCompletionsClient(Hy3Config.from_env()),
        RetrievalConfig(top_k=10, chunk_chars=2200, overlap_chars=260),
    )
    cases = {
        "before_publication": (Query(
            "As of 2025-12-31, what were Tencent Holdings Limited FY2025 full-year revenues, profit attributable to equity holders, and the derived profit margin? Do not annualise interim figures.",
            "2025-12-31", "Tencent Holdings Limited", "FY2025",
        ), Answerability.UNANSWERABLE),
        "after_publication": (Query(
            "As of 2026-04-10, what were Tencent Holdings Limited FY2025 full-year revenues, profit attributable to equity holders, and the derived profit margin? Distinguish IFRS from non-IFRS figures.",
            "2026-04-10", "Tencent Holdings Limited", "FY2025",
        ), Answerability.ANSWERABLE),
    }
    summary = {}
    for name, (query, expected_answerability) in cases.items():
        answer = pipeline.run(query)
        score = ChronoFinEvaluator().evaluate(
            answer,
            pipeline.chunk_index,
            expected_answerability=expected_answerability,
        )
        write_json(answer, ROOT / "results" / f"public_tencent_{name}.json")
        write_json(score, ROOT / "results" / f"public_tencent_{name}_score.json")
        write_html(answer, ROOT / "results" / f"public_tencent_{name}.html", score)
        summary[name] = {
            "answerability": answer.answerability.value,
            "expected_answerability": expected_answerability.value,
            "summary": answer.executive_summary,
            "score": score.final_score,
            "hard_gates": score.hard_gate_reasons,
            "excluded_documents": answer.excluded_documents,
            "trace": answer.provenance.get("llm", {}),
        }
    write_json(summary, ROOT / "results" / "public_tencent_summary.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
