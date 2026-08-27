"""Reproducible, fully offline synthetic stress benchmark.

The benchmark exercises the real :class:`ChronoFinEvaluator` with formal
oracles.  It intentionally makes no held-out, human-label, or real-world
financial-accuracy claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping

from ..models import (
    AnalysisAnswer,
    Answerability,
    Calculation,
    Chunk,
    Claim,
    ClaimType,
    Evidence,
    Operand,
    Query,
)
from .core import ChronoFinEvaluator, ScoreCard
from .mutations import DEFAULT_CONTRAST_MUTATIONS, ContrastMutation, spearman
from ..projection import canonical_derived_claim_text


BENCHMARK_VERSION = "chronofin-synthetic-multicluster-v2.0"
DEFAULT_BOOTSTRAP_ITERATIONS = 2000
DEFAULT_BOOTSTRAP_SEED = 2026
INVARIANCE_TOLERANCE = 1e-9

COMPANIES: tuple[tuple[str, str], ...] = (
    ("xinglan", "星澜科技"),
    ("yunlan", "云岚智造"),
    ("hanchuan", "瀚川零售"),
    ("qingheng", "青衡医械"),
    ("chenhai", "辰海物流"),
    ("qiyun", "栖云能源"),
    ("chengyue", "澄岳软件"),
    ("yuanqiao", "远桥材料"),
)
FISCAL_YEARS: tuple[int, ...] = (2021, 2022, 2023)
QUESTION_FAMILIES: tuple[str, ...] = (
    "profitability_margin",
    "revenue_growth",
    "liquidity_ratio",
)


@dataclass(frozen=True)
class SyntheticTask:
    task_id: str
    company_id: str
    entity: str
    fiscal_year: int
    family: str
    answer: AnalysisAnswer
    chunks: dict[str, Chunk]
    expected_semantic_keys: tuple[str, ...]
    oracle_values: dict[str, float]

    @property
    def company_cluster(self) -> str:
        return self.company_id

    @property
    def original_question_cluster(self) -> str:
        return self.task_id


@dataclass(frozen=True)
class MutationOutcome:
    task_id: str
    company_id: str
    entity: str
    fiscal_year: int
    family: str
    mutation: str
    severity: int
    label_preserving: bool
    base_score: float
    mutated_score: float
    score_drop: float
    detected: bool
    typed_detected: bool | None
    expected_signal: str
    hard_cap: float | None
    hard_gate_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["hard_gate_reasons"] = list(self.hard_gate_reasons)
        return payload


def _display_number(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=1e-9):
        return f"{int(round(value)):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _task_components(
    company_index: int,
    entity: str,
    fiscal_year: int,
    family: str,
) -> dict[str, Any]:
    """Create varied but exact arithmetic for one formal-oracle scenario."""

    year_offset = fiscal_year - FISCAL_YEARS[0]
    if family == "profitability_margin":
        revenue = float(1000 + company_index * 100 + year_offset * 200)
        margin = float(8 + company_index + year_offset)
        profit = revenue * margin / 100.0
        return {
            "question": f"{entity} FY{fiscal_year} 的营业收入、净利润和净利率是多少？",
            "facts": (
                ("revenue", "营业收入", revenue),
                ("net_profit", "归属于股东的净利润", profit),
            ),
            "operand_names": ("net_profit", "revenue"),
            "expression": "net_profit / revenue * 100",
            "derived_metric": "net_margin",
            "derived_label": "净利率",
            "result": margin,
            "result_unit": "%",
        }
    if family == "revenue_growth":
        prior_revenue = float(800 + company_index * 100 + year_offset * 200)
        growth = float(6 + company_index + 2 * year_offset)
        current_revenue = prior_revenue * (100.0 + growth) / 100.0
        return {
            "question": f"{entity} FY{fiscal_year} 的营业收入及同比增速是多少？",
            "facts": (
                ("current_revenue", "营业收入", current_revenue),
                ("prior_revenue", "收入同比计算所用的上年同期营业收入", prior_revenue),
            ),
            "operand_names": ("current_revenue", "prior_revenue"),
            "expression": "(current_revenue - prior_revenue) / prior_revenue * 100",
            "derived_metric": "revenue_growth",
            "derived_label": "营业收入同比增速",
            "result": growth,
            "result_unit": "%",
        }
    if family == "liquidity_ratio":
        liabilities = float(400 + company_index * 50 + year_offset * 50)
        ratio = float(1.5 + company_index * 0.1 + year_offset * 0.2)
        assets = liabilities * ratio
        return {
            "question": f"{entity} FY{fiscal_year} 的流动资产、流动负债和流动比率是多少？",
            "facts": (
                ("current_assets", "流动资产", assets),
                ("current_liabilities", "流动负债", liabilities),
            ),
            "operand_names": ("current_assets", "current_liabilities"),
            "expression": "current_assets / current_liabilities",
            "derived_metric": "current_ratio",
            "derived_label": "流动比率",
            "result": ratio,
            "result_unit": "倍",
        }
    raise ValueError(f"unknown question family: {family}")


def _build_task(company_index: int, company_id: str, entity: str, fiscal_year: int, family: str) -> SyntheticTask:
    period = f"FY{fiscal_year}"
    published_at = f"{fiscal_year + 1}-03-18"
    cutoff = f"{fiscal_year + 1}-12-31"
    task_id = f"{company_id}_{period.lower()}_{family}"
    document_id = f"{task_id}_formal_filing"
    components = _task_components(company_index, entity, fiscal_year, family)

    evidence: list[Evidence] = []
    chunks: dict[str, Chunk] = {}
    claims: list[Claim] = []
    oracle_values: dict[str, float] = {}
    semantic_keys: list[str] = []
    operand_by_metric: dict[str, Operand] = {}

    for index, (metric, label, value) in enumerate(components["facts"], start=1):
        evidence_id = f"E{index}"
        chunk_id = f"{document_id}:p1:c{index}"
        quote = f"{entity} {period} {label}为 {_display_number(value)} 百万元。"
        chunks[chunk_id] = Chunk(
            id=chunk_id,
            document_id=document_id,
            text=quote,
            page=1,
            section="合成财务指标",
            entity=entity,
            period=period,
            published_at=published_at,
            currency="CNY",
            unit="百万元",
        )
        evidence.append(
            Evidence(
                id=evidence_id,
                chunk_id=chunk_id,
                document_id=document_id,
                quote=quote,
                page=1,
                published_at=published_at,
            )
        )
        semantic_key = f"{company_id}.{metric}.{period}"
        semantic_keys.append(semantic_key)
        oracle_values[semantic_key] = value
        claims.append(
            Claim(
                id=f"C{index}",
                text=quote,
                claim_type=ClaimType.FACT,
                entity=entity,
                period=period,
                unit="百万元",
                known_at=published_at,
                value=value,
                evidence_ids=(evidence_id,),
                confidence=1.0,
                semantic_key=semantic_key,
            )
        )
        operand_by_metric[metric] = Operand(
            name=metric,
            value=value,
            unit="百万元",
            evidence_ids=(evidence_id,),
        )

    result = float(components["result"])
    result_unit = str(components["result_unit"])
    calculation = Calculation(
        id="CALC1",
        expression=str(components["expression"]),
        result=result,
        unit=result_unit,
        operands=tuple(operand_by_metric[name] for name in components["operand_names"]),
    )
    derived_metric = str(components["derived_metric"])
    derived_key = f"{company_id}.{derived_metric}.{period}"
    semantic_keys.append(derived_key)
    oracle_values[derived_key] = result
    derived_claim = Claim(
            id="C3",
            text="",
            claim_type=ClaimType.DERIVED,
            entity=entity,
            period=period,
            unit=result_unit,
            known_at=published_at,
            value=result,
            evidence_ids=("E1", "E2"),
            calculation_id="CALC1",
            confidence=1.0,
            semantic_key=derived_key,
        )
    claims.append(replace(derived_claim, text=canonical_derived_claim_text(derived_claim, calculation)))
    answer = AnalysisAnswer(
        query=Query(
            question=str(components["question"]),
            as_of_date=cutoff,
            entity=entity,
            requested_period=period,
        ),
        answerability=Answerability.ANSWERABLE,
        executive_summary="；".join(claim.text.rstrip("。") for claim in claims) + "。",
        claims=claims,
        evidence=evidence,
        calculations=[calculation],
        caveats=["可见结论仅来自已绑定证据与确定性计算；不构成投资建议。"],
        provenance={
            "fixture": BENCHMARK_VERSION,
            "formal_oracle": True,
            "synthetic": True,
            "model_called": False,
        },
    )
    return SyntheticTask(
        task_id=task_id,
        company_id=company_id,
        entity=entity,
        fiscal_year=fiscal_year,
        family=family,
        answer=answer,
        chunks=chunks,
        expected_semantic_keys=tuple(semantic_keys),
        oracle_values=oracle_values,
    )


def build_synthetic_tasks() -> list[SyntheticTask]:
    """Build the fixed 8 x 3 x 3 task matrix without file or network I/O."""

    return [
        _build_task(company_index, company_id, entity, fiscal_year, family)
        for company_index, (company_id, entity) in enumerate(COMPANIES)
        for fiscal_year in FISCAL_YEARS
        for family in QUESTION_FAMILIES
    ]


def _dimension(score: ScoreCard, name: str) -> Mapping[str, float]:
    return next(item.metrics for item in score.dimensions if item.name == name)


def _typed_signal(mutation_name: str, score: ScoreCard) -> tuple[bool, str]:
    """Check that the evaluator raised the mutation's intended diagnostic."""

    temporal = _dimension(score, "temporal_integrity")
    citation = _dimension(score, "citation_correctness")
    completeness = _dimension(score, "citation_completeness")
    numeric = _dimension(score, "numeric_lineage")
    alignment = _dimension(score, "entity_period_unit")
    material = _dimension(score, "material_completeness")
    factual = _dimension(score, "factual_support")
    safety = _dimension(score, "safety_and_communication")
    checks: dict[str, tuple[bool, str]] = {
        "future_leak": (temporal["future_count"] > 0.0, "temporal_integrity.future_count > 0"),
        "known_at_mismatch": (
            temporal["known_at_mismatch_count"] > 0.0,
            "temporal_integrity.known_at_mismatch_count > 0",
        ),
        "missing_known_at": (
            temporal["known_at_mismatch_count"] > 0.0,
            "temporal_integrity.known_at_mismatch_count > 0 for absent value",
        ),
        "forged_quote": (citation["exact_quote_accuracy"] < 1.0, "citation_correctness.exact_quote_accuracy < 1"),
        "citation_metadata_forgery": (
            citation["identity_accuracy"] < 1.0,
            "citation_correctness.identity_accuracy < 1 for displayed registry metadata",
        ),
        "wrong_entity": (alignment["entity_period_alignment"] < 1.0, "entity_period_unit.entity_period_alignment < 1"),
        "wrong_period": (alignment["entity_period_alignment"] < 1.0, "entity_period_unit.entity_period_alignment < 1"),
        "wrong_query_entity": (
            alignment["query_target_alignment"] < 1.0,
            "entity_period_unit.query_target_alignment < 1",
        ),
        "wrong_query_period": (
            alignment["query_target_alignment"] < 1.0,
            "entity_period_unit.query_target_alignment < 1",
        ),
        "wrong_query_metric": (
            alignment["query_metric_alignment"] < 1.0,
            "entity_period_unit.query_metric_alignment < 1",
        ),
        "wrong_unit": (alignment["claim_calculation_unit"] < 1.0, "entity_period_unit.claim_calculation_unit < 1"),
        "wrong_fact_unit": (
            alignment["source_unit_currency_alignment"] < 1.0,
            "entity_period_unit.source_unit_currency_alignment < 1 for FACT",
        ),
        "wrong_operand_unit": (
            alignment["source_unit_currency_alignment"] < 1.0,
            "entity_period_unit.source_unit_currency_alignment < 1 for operand",
        ),
        "calculation_error": (
            numeric["execution_accuracy"] < 1.0 or numeric["claim_value_accuracy"] < 1.0,
            "numeric_lineage execution/claim-value accuracy < 1",
        ),
        "claim_text_numeric_error": (
            numeric["claim_text_accuracy"] < 1.0,
            "numeric_lineage.claim_text_accuracy < 1",
        ),
        "extraneous_claim_number": (
            numeric["claim_numeric_grounding_accuracy"] < 1.0,
            "numeric_lineage.claim_numeric_grounding_accuracy < 1",
        ),
        "chinese_numeral_error": (
            numeric["claim_numeric_grounding_accuracy"] < 1.0,
            "numeric_lineage.claim_numeric_grounding_accuracy < 1 for CJK numeral",
        ),
        "summary_numeric_error": (
            numeric["summary_numeric_grounding_accuracy"] < 1.0,
            "numeric_lineage.summary_numeric_grounding_accuracy < 1",
        ),
        "summary_unsupported_claim": (
            factual["summary_claim_alignment"] < 1.0,
            "factual_support.summary_claim_alignment < 1",
        ),
        "claim_text_wrong_entity": (
            factual["deterministic_claim_grounding"] < 1.0,
            "factual_support.deterministic_claim_grounding < 1 for visible entity",
        ),
        "claim_text_wrong_period": (
            factual["deterministic_claim_grounding"] < 1.0,
            "factual_support.deterministic_claim_grounding < 1 for visible period",
        ),
        "claim_polarity_reversal": (
            factual["deterministic_claim_grounding"] < 1.0,
            "factual_support.deterministic_claim_grounding < 1 for polarity",
        ),
        "missing_citation": (completeness["claim_completeness"] < 1.0, "citation_completeness.claim_completeness < 1"),
        "prompt_injection": (safety["injection_echo"] > 0.0, "safety_and_communication.injection_echo > 0"),
        "caveat_prompt_injection": (
            safety["injection_echo"] > 0.0,
            "safety_and_communication.injection_echo > 0 for caveat text",
        ),
        "caveat_investment_advice": (
            safety["unsafe_advice"] > 0.0,
            "safety_and_communication.unsafe_advice > 0 for caveat text",
        ),
        "imperative_investment_advice": (
            safety["unsafe_advice"] > 0.0,
            "safety_and_communication.unsafe_advice > 0 for imperative advice",
        ),
        "false_caveat_assertion": (
            safety["caveat_projection_accuracy"] < 1.0,
            "safety_and_communication.caveat_projection_accuracy < 1",
        ),
        "empty_answer": (
            material["output_structure_valid"] < 1.0,
            "material_completeness.output_structure_valid < 1",
        ),
        "blanket_refusal": (
            material["output_structure_valid"] < 1.0 or material["refusal_support"] < 1.0,
            "invalid refusal structure or missing negative evidence",
        ),
        "incorrect_refusal": (
            material["answerability_match"] < 1.0,
            "material_completeness.answerability_match < 1",
        ),
        "irrelevant_future_refusal": (
            material["refusal_support"] < 1.0 and material["verified_future_exclusion"] < 1.0,
            "refusal support rejects a future exclusion for the wrong entity/period",
        ),
        "affirmative_unknown_claim": (
            material["unknown_projection_accuracy"] < 1.0,
            "material_completeness.unknown_projection_accuracy < 1",
        ),
        "unrelated_negative_refusal": (
            material["refusal_support"] < 1.0,
            "refusal support rejects negative evidence for an unrelated metric",
        ),
        "cross_clause_negative_refusal": (
            material["refusal_support"] < 1.0,
            "refusal support requires metric and negative language in one clause",
        ),
        "available_source_future_refusal": (
            material["refusal_support"] < 1.0 and material["verified_future_exclusion"] < 1.0,
            "future exclusion cannot erase already eligible target evidence",
        ),
    }
    if mutation_name not in checks:
        return False, "no destructive typed signal registered"
    return checks[mutation_name]


def _evaluate_task(
    task: SyntheticTask,
    evaluator: ChronoFinEvaluator,
    mutations: tuple[ContrastMutation, ...],
) -> tuple[dict[str, Any], list[MutationOutcome]]:
    expected = set(task.expected_semantic_keys)
    base = evaluator.evaluate(
        task.answer,
        task.chunks,
        expected_semantic_keys=expected,
        expected_answerability=task.answer.answerability,
    )
    if base.final_score != 100.0 or base.hard_cap is not None:
        raise RuntimeError(
            f"formal oracle {task.task_id} is not clean: score={base.final_score}, cap={base.hard_cap}"
        )
    outcomes: list[MutationOutcome] = []
    for mutation in mutations:
        mutated_answer, mutated_chunks = mutation.apply(task.answer, task.chunks)
        score = evaluator.evaluate(
            mutated_answer,
            mutated_chunks,
            expected_semantic_keys=expected,
            expected_answerability=task.answer.answerability,
        )
        drop = round(base.final_score - score.final_score, 6)
        detected = abs(drop) <= INVARIANCE_TOLERANCE if mutation.label_preserving else drop > INVARIANCE_TOLERANCE
        typed_detected: bool | None = None
        expected_signal = "label-preserving: final score invariant"
        if not mutation.label_preserving:
            typed_detected, expected_signal = _typed_signal(mutation.name, score)
        outcomes.append(
            MutationOutcome(
                task_id=task.task_id,
                company_id=task.company_id,
                entity=task.entity,
                fiscal_year=task.fiscal_year,
                family=task.family,
                mutation=mutation.name,
                severity=mutation.severity,
                label_preserving=mutation.label_preserving,
                base_score=base.final_score,
                mutated_score=score.final_score,
                score_drop=drop,
                detected=detected,
                typed_detected=typed_detected,
                expected_signal=expected_signal,
                hard_cap=score.hard_cap,
                hard_gate_reasons=tuple(score.hard_gate_reasons),
            )
        )
    task_summary = {
        "task_id": task.task_id,
        "company_id": task.company_id,
        "entity": task.entity,
        "fiscal_year": task.fiscal_year,
        "family": task.family,
        "question": task.answer.query.question,
        "base_score": base.final_score,
        "oracle_values": task.oracle_values,
    }
    return task_summary, outcomes


def _metric_summary(outcomes: Iterable[MutationOutcome]) -> dict[str, Any]:
    values = list(outcomes)
    destructive = [item for item in values if not item.label_preserving]
    preserving = [item for item in values if item.label_preserving]
    mutation_names = sorted({item.mutation for item in destructive})
    subtype_recall = {
        name: statistics.mean(
            float(bool(item.typed_detected)) for item in destructive if item.mutation == name
        )
        for name in mutation_names
    }
    paired_recall = {
        name: statistics.mean(float(item.detected) for item in destructive if item.mutation == name)
        for name in mutation_names
    }
    return {
        "paired_discrimination_accuracy": statistics.mean(float(item.detected) for item in destructive),
        "invariance_violation_rate": statistics.mean(float(not item.detected) for item in preserving),
        "severity_drop_spearman": spearman(
            [float(item.severity) for item in destructive],
            [item.score_drop for item in destructive],
        ),
        "destructive_subtype_recall": subtype_recall,
        "paired_score_drop_recall": paired_recall,
    }


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _ci(values: list[float]) -> list[float]:
    ordered = sorted(values)
    return [round(_quantile(ordered, 0.025), 6), round(_quantile(ordered, 0.975), 6)]


def _hierarchical_cluster_bootstrap(
    outcomes: list[MutationOutcome],
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    """Resample companies, then original questions; keep all mutants together."""

    if iterations < 1:
        raise ValueError("bootstrap iterations must be positive")
    grouped: dict[str, dict[str, list[MutationOutcome]]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome.company_id, {}).setdefault(outcome.task_id, []).append(outcome)
    mutants_per_task = max(
        (len(task_outcomes) for company in grouped.values() for task_outcomes in company.values()),
        default=0,
    )
    company_ids = sorted(grouped)
    rng = random.Random(seed)
    primary_samples: dict[str, list[float]] = {
        "paired_discrimination_accuracy": [],
        "invariance_violation_rate": [],
        "severity_drop_spearman": [],
    }
    mutation_names = sorted({item.mutation for item in outcomes if not item.label_preserving})
    subtype_samples = {name: [] for name in mutation_names}
    for _ in range(iterations):
        sample: list[MutationOutcome] = []
        for _company_draw in company_ids:
            company_id = rng.choice(company_ids)
            task_groups = grouped[company_id]
            task_ids = sorted(task_groups)
            for _task_draw in task_ids:
                task_id = rng.choice(task_ids)
                sample.extend(task_groups[task_id])
        summary = _metric_summary(sample)
        for name in primary_samples:
            primary_samples[name].append(float(summary[name]))
        for name in mutation_names:
            subtype_samples[name].append(float(summary["destructive_subtype_recall"][name]))
    return {
        "confidence_level": 0.95,
        "method": (
            "two-stage cluster bootstrap: resample companies, then original base tasks within company; "
            f"retain all {mutants_per_task} correlated mutants per base task"
        ),
        "iterations": iterations,
        "seed": seed,
        "primary_metric_ci": {name: _ci(samples) for name, samples in primary_samples.items()},
        "destructive_subtype_recall_ci": {name: _ci(samples) for name, samples in subtype_samples.items()},
    }


def _mutation_summary(outcomes: list[MutationOutcome]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted({item.mutation for item in outcomes}):
        group = [item for item in outcomes if item.mutation == name]
        result[name] = {
            "runs": len(group),
            "label_preserving": group[0].label_preserving,
            "severity": group[0].severity,
            "paired_detection_rate": round(statistics.mean(float(item.detected) for item in group), 6),
            "typed_signal_recall": (
                None
                if group[0].label_preserving
                else round(statistics.mean(float(bool(item.typed_detected)) for item in group), 6)
            ),
            "mean_score_drop": round(statistics.mean(item.score_drop for item in group), 6),
            "min_score_drop": min(item.score_drop for item in group),
            "max_score_drop": max(item.score_drop for item in group),
            "hard_cap_counts": {
                str(cap): sum(item.hard_cap == cap for item in group)
                for cap in sorted({item.hard_cap for item in group}, key=lambda value: (value is None, value or 0.0))
            },
        }
    return result


def _corpus_fingerprint(tasks: list[SyntheticTask], mutations: tuple[ContrastMutation, ...]) -> str:
    payload = {
        "version": BENCHMARK_VERSION,
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
            {"name": item.name, "severity": item.severity, "label_preserving": item.label_preserving}
            for item in mutations
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_synthetic_benchmark(
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Run all formal-oracle tasks and mutations through the real evaluator."""

    tasks = build_synthetic_tasks()
    mutations = DEFAULT_CONTRAST_MUTATIONS
    destructive_count = sum(not item.label_preserving for item in mutations)
    preserving_count = sum(item.label_preserving for item in mutations)
    if len(tasks) < 72 or destructive_count != 36 or preserving_count != 2:
        raise RuntimeError("benchmark coverage contract is not satisfied")

    evaluator = ChronoFinEvaluator()
    task_summaries: list[dict[str, Any]] = []
    outcomes: list[MutationOutcome] = []
    for task in tasks:
        task_summary, task_outcomes = _evaluate_task(task, evaluator, mutations)
        task_summaries.append(task_summary)
        outcomes.extend(task_outcomes)

    metrics = _metric_summary(outcomes)
    rounded_metrics = {
        "paired_discrimination_accuracy": round(metrics["paired_discrimination_accuracy"], 6),
        "invariance_violation_rate": round(metrics["invariance_violation_rate"], 6),
        "severity_drop_spearman": round(metrics["severity_drop_spearman"], 6),
        "destructive_subtype_recall": {
            key: round(value, 6) for key, value in metrics["destructive_subtype_recall"].items()
        },
        "paired_score_drop_recall": {
            key: round(value, 6) for key, value in metrics["paired_score_drop_recall"].items()
        },
    }
    base_scores = [item["base_score"] for item in task_summaries]
    return {
        "schema_version": "chronofin-synthetic-benchmark-result-v1",
        "benchmark_version": BENCHMARK_VERSION,
        "reproducibility": {
            "fully_offline": True,
            "model_calls": 0,
            "generator": "deterministic Cartesian task matrix",
            "corpus_sha256": _corpus_fingerprint(tasks, mutations),
            "bootstrap_seed": bootstrap_seed,
            "bootstrap_iterations": bootstrap_iterations,
            "invariance_tolerance": INVARIANCE_TOLERANCE,
        },
        "coverage": {
            "base_tasks": len(tasks),
            "companies": len({task.company_id for task in tasks}),
            "company_ids": [item[0] for item in COMPANIES],
            "fiscal_years": list(FISCAL_YEARS),
            "question_families": list(QUESTION_FAMILIES),
            "destructive_mutations_per_task": destructive_count,
            "label_preserving_mutations_per_task": preserving_count,
            "total_mutation_runs": len(outcomes),
            "destructive_runs": sum(not item.label_preserving for item in outcomes),
            "label_preserving_runs": sum(item.label_preserving for item in outcomes),
        },
        "base_oracle_quality": {
            "score_min": min(base_scores),
            "score_mean": statistics.mean(base_scores),
            "score_max": max(base_scores),
            "all_without_hard_cap": True,
            "oracle_type": "synthetic formal oracle",
        },
        "metrics": rounded_metrics,
        "cluster_bootstrap_95_ci": _hierarchical_cluster_bootstrap(
            outcomes,
            iterations=bootstrap_iterations,
            seed=bootstrap_seed,
        ),
        "mutation_summary": _mutation_summary(outcomes),
        "task_inventory": task_summaries,
        "outcomes": [item.to_dict() for item in outcomes],
        "limitations": [
            "All companies, filings, questions, values, answers, and expected mutation effects are synthetic formal oracles.",
            "This is not a held-out dataset and has no human-expert labels; task and mutation templates are visible to the benchmark code.",
            "PDA, IVR, severity correlation, subtype recall, and bootstrap intervals measure evaluator behavior on these controlled contrasts, not financial QA correctness or real-world generalization.",
            "The two-stage bootstrap represents only variation across eight fictional-company clusters and their original questions; it cannot quantify corpus-construction or human-label uncertainty.",
            "The evaluator uses deterministic citation, temporal, numeric, graph, and lexical diagnostics; without a semantic judge, factual support is not an entailment claim.",
        ],
        "claims_not_made": [
            "No claim of production investment accuracy.",
            "No claim of held-out benchmark performance.",
            "No claim of human agreement or expert validity.",
        ],
    }


def benchmark_json(result: Mapping[str, Any]) -> str:
    """Stable serialization used by the CLI and reproducibility tests."""

    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
