#!/usr/bin/env python3
"""Apply the current deterministic trust boundary to a saved model response."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import RetrievalConfig
from chronofin.evaluator import ChronoFinEvaluator
from chronofin.models import Query
from chronofin.pipeline import ChronoFinPipeline
from chronofin.render import write_html, write_json


class UnusedClient:
    def complete_json(self, system, user):  # pragma: no cover
        raise RuntimeError("reprocessing never calls a model")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--answer", required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--chunk-chars", type=int, default=2200)
    parser.add_argument("--expected-answerability", choices=("answerable", "partial", "unanswerable"), default=None)
    args = parser.parse_args()

    source = json.loads(Path(args.answer).read_text(encoding="utf-8"))
    query = Query(**source["query"])
    pipeline = ChronoFinPipeline(
        args.manifest,
        UnusedClient(),
        RetrievalConfig(top_k=args.top_k, chunk_chars=args.chunk_chars, overlap_chars=260),
    )
    audit = pipeline.retrieve(query)
    answer = pipeline._bind_model_output(source, query, audit)
    deterministic_provenance = dict(answer.provenance)
    answer.provenance = {**source.get("provenance", {}), **deterministic_provenance}
    source_path = Path(args.answer).resolve()
    try:
        reprocessed_from = source_path.relative_to(ROOT).as_posix()
    except ValueError:
        reprocessed_from = source_path.name
    answer.provenance["reprocessed_from"] = reprocessed_from
    score = ChronoFinEvaluator().evaluate(
        answer,
        pipeline.chunk_index,
        expected_answerability=args.expected_answerability,
    )
    prefix = Path(args.output_prefix)
    write_json(answer, prefix.with_suffix(".json"))
    write_json(score, prefix.with_name(prefix.name + "_score").with_suffix(".json"))
    write_html(answer, prefix.with_suffix(".html"), score)
    print(json.dumps({
        "score": score.final_score,
        "verdict": score.verdict,
        "citation_normalizations": len(answer.provenance.get("citation_normalizations", [])),
        "calculation_corrections": answer.provenance.get("calculation_corrections", []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
