"""Command-line interface for analysis and deterministic auditing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Hy3Config, RetrievalConfig
from .evaluator import ChronoFinEvaluator
from .ingest import ingest_manifest
from .llm import ChatCompletionsClient
from .models import Query
from .pipeline import ChronoFinPipeline
from .render import load_answer, write_html, write_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronofin", description="Point-in-time, causally auditable Hy3 financial research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask = subparsers.add_parser("ask", help="run Hy3 against an as-of filtered document manifest")
    ask.add_argument("--manifest", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--as-of", required=True, dest="as_of")
    ask.add_argument("--entity", required=True)
    ask.add_argument("--period", required=True)
    ask.add_argument("--top-k", type=int, default=8)
    ask.add_argument("--output", default="results/live_answer.json")
    ask.add_argument("--html", default="")
    ask.add_argument("--evaluate", action="store_true")
    ask.add_argument("--expected-answerability", choices=("answerable", "partial", "unanswerable"), default=None)
    ask.add_argument("--unsafe-disable-time-filter", action="store_true")

    evaluate = subparsers.add_parser("evaluate", help="audit a saved answer with deterministic checks")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--answer", required=True)
    evaluate.add_argument("--output", default="results/scorecard.json")
    evaluate.add_argument("--html", default="")
    evaluate.add_argument("--expected-key", action="append", default=[])
    evaluate.add_argument("--expected-answerability", choices=("answerable", "partial", "unanswerable"), default=None)

    inspect = subparsers.add_parser("inspect", help="show which evidence is eligible at a cutoff")
    inspect.add_argument("--manifest", required=True)
    inspect.add_argument("--question", required=True)
    inspect.add_argument("--as-of", required=True, dest="as_of")
    inspect.add_argument("--entity", required=True)
    inspect.add_argument("--period", required=True)
    inspect.add_argument("--top-k", type=int, default=8)
    return parser


def command_ask(args: argparse.Namespace) -> int:
    config = RetrievalConfig(top_k=args.top_k, temporal_filter=not args.unsafe_disable_time_filter)
    if args.unsafe_disable_time_filter:
        print("WARNING: temporal filter disabled for baseline/ablation only", file=sys.stderr)
    pipeline = ChronoFinPipeline(args.manifest, ChatCompletionsClient(Hy3Config.from_env()), config)
    query = Query(args.question, args.as_of, args.entity, args.period)
    answer = pipeline.run(query)
    scorecard = (
        ChronoFinEvaluator().evaluate(
            answer,
            pipeline.chunk_index,
            expected_answerability=args.expected_answerability,
        )
        if args.evaluate
        else None
    )
    write_json(answer, args.output)
    if scorecard:
        score_path = str(Path(args.output).with_suffix(".score.json"))
        write_json(scorecard, score_path)
    if args.html:
        write_html(answer, args.html, scorecard)
    print(json.dumps({"answer": args.output, "score": scorecard.final_score if scorecard else None}, ensure_ascii=False))
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    answer = load_answer(args.answer)
    _, chunks = ingest_manifest(args.manifest)
    scorecard = ChronoFinEvaluator().evaluate(
        answer,
        {chunk.id: chunk for chunk in chunks},
        expected_semantic_keys=set(args.expected_key) if args.expected_key else None,
        expected_answerability=args.expected_answerability,
    )
    write_json(scorecard, args.output)
    if args.html:
        write_html(answer, args.html, scorecard)
    print(json.dumps({"score": scorecard.final_score, "verdict": scorecard.verdict, "hard_cap": scorecard.hard_cap}, ensure_ascii=False))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    config = RetrievalConfig(top_k=args.top_k)
    pipeline = ChronoFinPipeline.__new__(ChronoFinPipeline)
    pipeline.manifest_path = Path(args.manifest).resolve()
    pipeline.retrieval_config = config
    pipeline.documents, pipeline.chunks = ingest_manifest(args.manifest, config.chunk_chars, config.overlap_chars)
    pipeline.chunk_index = {chunk.id: chunk for chunk in pipeline.chunks}
    from .retrieval import BM25Retriever
    pipeline.retriever = BM25Retriever(pipeline.chunks)
    query = Query(args.question, args.as_of, args.entity, args.period)
    audit = pipeline.retrieve(query)
    print(json.dumps({
        "eligible_document_ids": audit.eligible_document_ids,
        "excluded_documents": audit.excluded_documents,
        "evidence_slot_hits": dict(audit.slot_hits),
        "uncovered_evidence_slots": audit.uncovered_slots,
        "hits": [hit.to_prompt_dict() | {"score": hit.score} for hit in audit.hits],
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    handlers = {"ask": command_ask, "evaluate": command_evaluate, "inspect": command_inspect}
    raise SystemExit(handlers[args.command](args))
