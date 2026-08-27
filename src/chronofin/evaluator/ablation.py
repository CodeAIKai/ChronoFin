"""Fully offline component-ablation benchmark for the evaluator.

This module compares nested *audit capabilities* on the same synthetic formal
oracles and contrast mutations.  It is deliberately not a financial-QA model
benchmark: none of the four strategies generates an answer and none calls a
model.  Raw strategy scores have different formulas, so only within-task
paired changes and invariant violations are compared.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence

from ..models import AnalysisAnswer, Chunk
from .benchmark import BENCHMARK_VERSION, SyntheticTask, build_synthetic_tasks
from .citation import audit_citations
from .core import ChronoFinEvaluator
from .mutations import ContrastMutation
from .temporal import audit_temporal


ABLATION_SCHEMA_VERSION = "chronofin-evaluator-ablation-v1"
INVARIANCE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class AuditObservation:
    """One strategy's scalar output plus interpretable diagnostics."""

    score: float
    flags: tuple[str, ...] = ()


class AuditStrategy(Protocol):
    name: str
    description: str
    score_definition: str

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str],
    ) -> AuditObservation: ...


@dataclass(frozen=True)
class PlainOutputStrategy:
    """Negative control representing delivery without any audit."""

    name: str = "no_audit_plain_output"
    description: str = (
        "Negative control: accept every already-parsed AnalysisAnswer and do not inspect "
        "citations, dates, values, proof graph, safety, or completeness."
    )
    score_definition: str = "constant 100; a score drop is therefore impossible"

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str],
    ) -> AuditObservation:
        del answer, chunks, expected_semantic_keys
        return AuditObservation(score=100.0)


@dataclass(frozen=True)
class ExactCitationOnlyStrategy:
    """Identity and exact-substring citation audit, with no claim semantics."""

    name: str = "exact_citation_only"
    description: str = (
        "Check only that each emitted evidence pointer matches the trusted chunk registry "
        "and that its quote is a non-empty exact source substring."
    )
    score_definition: str = (
        "100 * mean(citation identity accuracy, exact quote accuracy); claim coverage, "
        "entailment, time, numbers, entity/period/unit, graph, and safety are ignored"
    )

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str],
    ) -> AuditObservation:
        del expected_semantic_keys
        audit = audit_citations(answer, chunks)
        score = 50.0 * (audit.identity_accuracy + audit.exact_quote_accuracy)
        flags: list[str] = []
        if audit.identity_accuracy < 1.0:
            flags.append("citation_identity")
        if audit.exact_quote_accuracy < 1.0:
            flags.append("non_exact_quote")
        return AuditObservation(score=round(score, 6), flags=tuple(flags))


@dataclass(frozen=True)
class PointInTimeCitationStrategy:
    """Exact-citation audit plus cutoff-date enforcement."""

    name: str = "point_in_time_exact_citation"
    description: str = (
        "Add registry-backed cutoff-date and claim known-at checks to exact citation identity "
        "and exact-substring checks."
    )
    score_definition: str = (
        "100 * mean(citation identity accuracy, exact quote accuracy, temporal compliance); "
        "temporal compliance is 1 only when no future source/claim is found"
    )

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str],
    ) -> AuditObservation:
        del expected_semantic_keys
        citation = audit_citations(answer, chunks)
        temporal = audit_temporal(answer, chunks)
        temporal_pass = float(temporal.compliant)
        score = 100.0 * (
            citation.identity_accuracy + citation.exact_quote_accuracy + temporal_pass
        ) / 3.0
        flags: list[str] = []
        if citation.identity_accuracy < 1.0:
            flags.append("citation_identity")
        if citation.exact_quote_accuracy < 1.0:
            flags.append("non_exact_quote")
        if not temporal.compliant:
            flags.append("future_information")
        return AuditObservation(score=round(score, 6), flags=tuple(flags))


class FullChronoFinStrategy:
    """Adapter over the production deterministic-first evaluator."""

    name = "full_chronofin"
    description = (
        "Run the full weighted evaluator and hard gates: temporal, citation, claim coverage, "
        "lexical factual diagnostic, numeric lineage, entity/period/unit, proof graph, material "
        "coverage, inference boundary, and safety/communication."
    )
    score_definition = (
        "ChronoFinEvaluator.final_score with expected semantic keys; no semantic LLM judge is "
        "supplied in this offline study"
    )

    def __init__(self) -> None:
        self._evaluator = ChronoFinEvaluator()

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str],
    ) -> AuditObservation:
        card = self._evaluator.evaluate(
            answer,
            chunks,
            expected_semantic_keys=expected_semantic_keys,
        )
        return AuditObservation(
            score=card.final_score,
            flags=tuple(card.hard_gate_reasons),
        )


def default_ablation_strategies() -> tuple[AuditStrategy, ...]:
    """Return the ordered nested capability ladder used in the report."""

    return (
        PlainOutputStrategy(),
        ExactCitationOnlyStrategy(),
        PointInTimeCitationStrategy(),
        FullChronoFinStrategy(),
    )


@dataclass(frozen=True)
class AblationOutcome:
    strategy: str
    task_id: str
    company_id: str
    family: str
    mutation: str
    severity: int
    label_preserving: bool
    base_score: float
    mutated_score: float
    score_drop: float
    detected: bool
    invariant_violation: bool
    base_flags: tuple[str, ...]
    mutated_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["base_flags"] = list(self.base_flags)
        payload["mutated_flags"] = list(self.mutated_flags)
        return payload


def _strategy_definition(strategy: AuditStrategy) -> dict[str, str]:
    return {
        "name": strategy.name,
        "description": strategy.description,
        "score_definition": strategy.score_definition,
    }


def _evaluate_strategy(
    strategy: AuditStrategy,
    tasks: Sequence[SyntheticTask],
    mutations: Sequence[ContrastMutation],
    tolerance: float,
) -> tuple[list[AblationOutcome], list[float]]:
    outcomes: list[AblationOutcome] = []
    base_scores: list[float] = []
    for task in tasks:
        expected = set(task.expected_semantic_keys)
        base = strategy.evaluate(task.answer, task.chunks, expected)
        base_scores.append(base.score)
        for mutation in mutations:
            mutated_answer, mutated_chunks = mutation.apply(task.answer, task.chunks)
            mutated = strategy.evaluate(mutated_answer, mutated_chunks, expected)
            drop = round(base.score - mutated.score, 6)
            changed = abs(drop) > tolerance
            outcomes.append(
                AblationOutcome(
                    strategy=strategy.name,
                    task_id=task.task_id,
                    company_id=task.company_id,
                    family=task.family,
                    mutation=mutation.name,
                    severity=mutation.severity,
                    label_preserving=mutation.label_preserving,
                    base_score=base.score,
                    mutated_score=mutated.score,
                    score_drop=drop,
                    detected=(not mutation.label_preserving and drop > tolerance),
                    invariant_violation=(mutation.label_preserving and changed),
                    base_flags=base.flags,
                    mutated_flags=mutated.flags,
                )
            )
    return outcomes, base_scores


def _mutation_summary(outcomes: Sequence[AblationOutcome]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for mutation_name in sorted({item.mutation for item in outcomes}):
        group = [item for item in outcomes if item.mutation == mutation_name]
        preserving = group[0].label_preserving
        summary[mutation_name] = {
            "runs": len(group),
            "label_preserving": preserving,
            "severity": group[0].severity,
            "destructive_detection_rate": (
                None
                if preserving
                else round(statistics.mean(float(item.detected) for item in group), 6)
            ),
            "invariance_violation_rate": (
                round(statistics.mean(float(item.invariant_violation) for item in group), 6)
                if preserving
                else None
            ),
            "mean_within_task_score_drop": round(
                statistics.mean(item.score_drop for item in group), 6
            ),
            "min_within_task_score_drop": min(item.score_drop for item in group),
            "max_within_task_score_drop": max(item.score_drop for item in group),
        }
    return summary


def _strategy_summary(
    outcomes: Sequence[AblationOutcome],
    base_scores: Sequence[float],
) -> dict[str, Any]:
    destructive = [item for item in outcomes if not item.label_preserving]
    preserving = [item for item in outcomes if item.label_preserving]
    return {
        "base_score_min": min(base_scores),
        "base_score_mean": round(statistics.mean(base_scores), 6),
        "base_score_max": max(base_scores),
        "destructive_runs": len(destructive),
        "label_preserving_runs": len(preserving),
        "destructive_detection_rate": round(
            statistics.mean(float(item.detected) for item in destructive), 6
        ) if destructive else None,
        "invariance_violation_rate": round(
            statistics.mean(float(item.invariant_violation) for item in preserving), 6
        ) if preserving else None,
        "mutation_summary": _mutation_summary(outcomes),
    }


def _paired_component_gains(
    outcomes_by_strategy: Mapping[str, Sequence[AblationOutcome]],
    ordered_names: Sequence[str],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for previous, current in zip(ordered_names, ordered_names[1:]):
        previous_items = {
            (item.task_id, item.mutation): item
            for item in outcomes_by_strategy[previous]
            if not item.label_preserving
        }
        current_items = {
            (item.task_id, item.mutation): item
            for item in outcomes_by_strategy[current]
            if not item.label_preserving
        }
        keys = sorted(set(previous_items) & set(current_items))
        newly_detected = [
            key for key in keys
            if not previous_items[key].detected and current_items[key].detected
        ]
        lost = [
            key for key in keys
            if previous_items[key].detected and not current_items[key].detected
        ]
        previous_rate = statistics.mean(float(previous_items[key].detected) for key in keys)
        current_rate = statistics.mean(float(current_items[key].detected) for key in keys)
        comparisons.append({
            "from": previous,
            "to": current,
            "paired_destructive_runs": len(keys),
            "newly_detected_runs": len(newly_detected),
            "lost_detected_runs": len(lost),
            "detection_rate_gain": round(current_rate - previous_rate, 6),
            "mutation_types_with_new_detections": sorted({name for _, name in newly_detected}),
            "mutation_types_with_lost_detections": sorted({name for _, name in lost}),
            "interpretation": "descriptive paired component gain; no statistical significance claim",
        })
    return comparisons


def _corpus_fingerprint(
    tasks: Sequence[SyntheticTask],
    mutations: Sequence[ContrastMutation],
    strategies: Sequence[AuditStrategy],
) -> str:
    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "tasks": [
            {
                "task_id": task.task_id,
                "answer": task.answer.to_dict(),
                "chunks": [asdict(task.chunks[key]) for key in sorted(task.chunks)],
                "expected_semantic_keys": list(task.expected_semantic_keys),
            }
            for task in tasks
        ],
        "mutations": [
            {
                "name": mutation.name,
                "severity": mutation.severity,
                "label_preserving": mutation.label_preserving,
            }
            for mutation in mutations
        ],
        "strategies": [_strategy_definition(strategy) for strategy in strategies],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_evaluator_ablation(
    *,
    tasks: Sequence[SyntheticTask] | None = None,
    mutations: Sequence[ContrastMutation] | None = None,
    strategies: Sequence[AuditStrategy] | None = None,
    tolerance: float = INVARIANCE_TOLERANCE,
) -> dict[str, Any]:
    """Run a paired evaluator-component ablation without model or network calls.

    ``mutations=None`` resolves ``DEFAULT_CONTRAST_MUTATIONS`` at call time so
    the experiment automatically includes newly registered mutations.
    """

    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    task_list = list(tasks) if tasks is not None else build_synthetic_tasks()
    if mutations is None:
        # Resolve at run time instead of freezing the registry in this module.
        from . import mutations as mutation_registry

        mutation_list = list(mutation_registry.DEFAULT_CONTRAST_MUTATIONS)
    else:
        mutation_list = list(mutations)
    strategy_list = list(strategies) if strategies is not None else list(default_ablation_strategies())
    if not task_list:
        raise ValueError("at least one synthetic task is required")
    if not mutation_list:
        raise ValueError("at least one contrast mutation is required")
    if not strategy_list:
        raise ValueError("at least one audit strategy is required")
    names = [strategy.name for strategy in strategy_list]
    if len(set(names)) != len(names):
        raise ValueError("audit strategy names must be unique")

    outcomes_by_strategy: dict[str, list[AblationOutcome]] = {}
    summaries: dict[str, Any] = {}
    all_outcomes: list[AblationOutcome] = []
    for strategy in strategy_list:
        outcomes, base_scores = _evaluate_strategy(
            strategy,
            task_list,
            mutation_list,
            tolerance,
        )
        outcomes_by_strategy[strategy.name] = outcomes
        summaries[strategy.name] = _strategy_summary(outcomes, base_scores)
        all_outcomes.extend(outcomes)

    destructive_mutations = [item for item in mutation_list if not item.label_preserving]
    preserving_mutations = [item for item in mutation_list if item.label_preserving]
    return {
        "schema_version": ABLATION_SCHEMA_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "study_type": "offline deterministic evaluator-component ablation",
        "reproducibility": {
            "fully_offline": True,
            "model_calls": 0,
            "network_calls": 0,
            "mutation_registry_resolution": "runtime DEFAULT_CONTRAST_MUTATIONS",
            "invariance_tolerance": tolerance,
            "corpus_and_protocol_sha256": _corpus_fingerprint(
                task_list, mutation_list, strategy_list
            ),
        },
        "coverage": {
            "base_tasks": len(task_list),
            "companies": len({task.company_id for task in task_list}),
            "question_families": len({task.family for task in task_list}),
            "strategies": len(strategy_list),
            "destructive_mutations_per_task": len(destructive_mutations),
            "label_preserving_mutations_per_task": len(preserving_mutations),
            "mutation_runs_per_strategy": len(task_list) * len(mutation_list),
            "total_strategy_mutation_runs": len(all_outcomes),
            "mutation_names": [item.name for item in mutation_list],
        },
        "paired_protocol": {
            "destructive_detection": "mutated score is lower than the same strategy's clean-task score by more than tolerance",
            "invariance_violation": "label-preserving mutation changes the same strategy's clean-task score by more than tolerance",
            "comparison_unit": "same base task x same mutation; raw scores are never compared across strategies",
            "clean_answers": "synthetic formal oracles built by build_synthetic_tasks()",
        },
        "strategy_definitions": [_strategy_definition(strategy) for strategy in strategy_list],
        "strategy_results": summaries,
        "paired_component_gains": _paired_component_gains(outcomes_by_strategy, names),
        "outcomes": [item.to_dict() for item in all_outcomes],
        "limitations": [
            "This study evaluates detector response to controlled mutations, not financial question-answering correctness.",
            "The plain-output arm is an intentional no-audit negative control, not an external model or competitive system.",
            "Exact-citation baselines are component ablations built from ChronoFin primitives, not independently developed strong baselines.",
            "All tasks, companies, filings, values, answers, and mutation oracles are synthetic and template-generated; there are no held-out or human-expert labels.",
            "A non-detection may mean the strategy lacks that audit capability; a detection does not establish semantic financial correctness.",
            "Raw score magnitude and score-drop magnitude are not comparable across strategies because their score formulas differ.",
            "Rates are descriptive over this fixed formal-oracle matrix; no p-value, population-generalization, or causal effect-size claim is made.",
        ],
        "claims_not_made": [
            "No Hy3 or other model QA-accuracy comparison.",
            "No external strong-model baseline comparison.",
            "No held-out benchmark, human agreement, or production reliability claim.",
        ],
    }


def ablation_json(result: Mapping[str, Any]) -> str:
    """Return deterministic pretty JSON for result artifacts and tests."""

    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

