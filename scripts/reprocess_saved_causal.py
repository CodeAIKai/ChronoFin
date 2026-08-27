#!/usr/bin/env python3
"""Rebind retained Hy3 causal answers to the current deterministic contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.config import RetrievalConfig  # noqa: E402
from chronofin.evaluator import ChronoFinEvaluator  # noqa: E402
from chronofin.evaluator.mutations import evaluate_causal_mutation  # noqa: E402
from chronofin.models import Query  # noqa: E402
from chronofin.pipeline import ChronoFinPipeline  # noqa: E402
from chronofin.render import write_html, write_json  # noqa: E402


BASELINE_INPUT = ROOT / "results" / "live_causal_baseline.json"
MUTATED_INPUT = ROOT / "results" / "live_causal_mutated.json"


class UnusedClient:
    def complete_json(self, system, user):  # pragma: no cover
        raise RuntimeError("saved-answer reprocessing never calls a model")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rebind(raw: dict, pipeline: ChronoFinPipeline, query: Query, source_path: Path):
    audit = pipeline.retrieve(query)
    answer = pipeline._bind_model_output(raw, query, audit)
    deterministic = dict(answer.provenance)
    historical = dict(raw.get("provenance", {}))
    answer.provenance = {**historical, **deterministic}
    answer.provenance.update({
        "current_reprocessing_model_called": False,
        "current_reprocessing_network_used": False,
        "historical_hy3_trace_retained": bool(historical.get("llm")),
        "reprocessed_from": source_path.relative_to(ROOT).as_posix(),
    })
    return answer


def main() -> None:
    baseline_raw = json.loads(BASELINE_INPUT.read_text(encoding="utf-8"))
    mutated_raw = json.loads(MUTATED_INPUT.read_text(encoding="utf-8"))
    query = Query(**baseline_raw["query"])
    config = RetrievalConfig(top_k=12)
    baseline_pipeline = ChronoFinPipeline(
        ROOT / "data" / "demo" / "manifest.json", UnusedClient(), config,
    )
    baseline = _rebind(baseline_raw, baseline_pipeline, query, BASELINE_INPUT)

    with tempfile.TemporaryDirectory(prefix="chronofin-causal-reprocess-") as directory:
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
        mutated_pipeline = ChronoFinPipeline(dataset / "manifest.json", UnusedClient(), config)
        mutated = _rebind(mutated_raw, mutated_pipeline, query, MUTATED_INPUT)
        mutated_score = ChronoFinEvaluator().evaluate(
            mutated,
            mutated_pipeline.chunk_index,
            expected_answerability="answerable",
        )

    baseline_score = ChronoFinEvaluator().evaluate(
        baseline,
        baseline_pipeline.chunk_index,
        expected_answerability="answerable",
    )
    net_profit_key = next(
        claim.semantic_key for claim in baseline.claims if "net_profit" in claim.semantic_key
    )
    net_margin_key = next(
        claim.semantic_key for claim in baseline.claims if "net_margin" in claim.semantic_key
    )
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
        "schema_version": "chronofin-saved-hy3-causal-reprocessing-v2",
        "evaluation_mode": "current_deterministic_rebinding_of_historical_hy3_answers",
        "execution": {
            "network_used": False,
            "model_called": False,
            "historical_hy3_answers_reused": True,
        },
        "input_hashes": {
            BASELINE_INPUT.relative_to(ROOT).as_posix(): _sha256(BASELINE_INPUT),
            MUTATED_INPUT.relative_to(ROOT).as_posix(): _sha256(MUTATED_INPUT),
        },
        "mutation": {
            "document": "cloud_2024.md",
            "leaf": "FY2024 net_profit",
            "before": 144.0,
            "after": 180.0,
            "oracle_margin_before": 12.0,
            "oracle_margin_after": 15.0,
        },
        "metrics": causal,
        "baseline_score": baseline_score.to_dict(),
        "mutated_score": mutated_score.to_dict(),
        "historical_hy3_traces": {
            "baseline": baseline_raw.get("provenance", {}).get("llm", {}),
            "mutated": mutated_raw.get("provenance", {}).get("llm", {}),
        },
        "limitations": [
            "The two Hy3 generations are historical saved answers; no model call is repeated here.",
            "The source-leaf mutation is synthetic and tests causal response/locality, not real-market accuracy.",
            "Current deterministic projection may differ textually from the originally displayed answers.",
        ],
    }
    write_json(baseline, ROOT / "results" / "live_causal_baseline_current.json")
    write_json(baseline_score, ROOT / "results" / "live_causal_baseline_current_score.json")
    write_json(mutated, ROOT / "results" / "live_causal_mutated_current.json")
    write_json(output, ROOT / "results" / "live_causal_experiment_current.json")
    write_html(
        mutated,
        ROOT / "results" / "live_causal_mutated_current.html",
        mutated_score,
    )
    print(json.dumps({
        "metrics": causal,
        "baseline_score": baseline_score.final_score,
        "mutated_score": mutated_score.final_score,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
