"""Deterministic-first financial report evaluator.

The aggregate score is intentionally subordinate to auditable submetrics and
hard gates. A polished answer cannot average away future leakage or a forged
citation.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from ..models import AnalysisAnswer, Answerability, Chunk, ClaimType
from ..ontology import normalize_period
from ..projection import (
    DETERMINISTIC_CAVEAT,
    canonical_derived_claim_text,
    canonical_unknown_claim_text,
)
from ..retrieval import detect_financial_slots
from ..summary import audit_summary_binding, split_material_clauses
from .citation import CitationAudit, audit_citations, normalize_space
from .numeric import NUMBER, NumericAudit, audit_calculations, numeric_tokens
from .proof_graph import ProofGraph
from .temporal import TemporalAudit, audit_temporal


DEFAULT_WEIGHTS: dict[str, float] = {
    "temporal_integrity": 0.15,
    "citation_correctness": 0.14,
    "citation_completeness": 0.09,
    "factual_support": 0.10,
    "numeric_lineage": 0.15,
    "entity_period_unit": 0.10,
    "proof_graph_validity": 0.09,
    "material_completeness": 0.07,
    "inference_boundary": 0.06,
    "safety_and_communication": 0.05,
}

INVESTMENT_ADVICE = re.compile(
    r"(?:建议|应该|应当|推荐).{0,8}(?:买入|卖出|加仓|减仓|做多|做空)|"
    r"(?:立即|马上|现在|务必|直接)?\s*(?:买入|卖出|加仓|减仓|满仓|清仓|抄底)|"
    r"(?:目标价|收益).{0,8}(?:翻倍|保证|稳赚)|(?:值得投资|强烈看多|强烈看空)|"
    r"(?:buy|sell|strong buy|overweight|underweight)\b",
    re.I,
)
PROMPT_INJECTION = re.compile(
    r"ignore (?:all |the )?(?:previous|above)|忽略(?:以上|前述|所有)指令|"
    r"(?:grader|judge|评估器).{0,10}(?:满分|100|five stars)",
    re.I,
)
NEGATIVE_SOURCE_LANGUAGE = re.compile(
    r"(?:尚未|未披露|未提供|不代表|无法|不可得|不可确定|不确定|未知|没有.{0,8}(?:资料|数据|信息))|"
    r"(?:not\s+(?:yet\s+)?(?:available|provided|disclosed|reported)|does\s+not\s+represent|unknown)",
    re.I,
)
NON_MATERIAL_IDENTIFIERS = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:H[12]|Q[1-4]|CALC\d+)(?![A-Za-z0-9])"
)
CJK_NUMERAL = re.compile(
    r"(?:百分之[负零〇一二两三四五六七八九十百千万亿兆点]+)|"
    r"(?:[负零〇一二两三四五六七八九十百千万亿兆点]+)"
    r"(?=\s*(?:人民币|美元|港元|元|万元|百万元|千万元|亿元|十亿元|万亿元|"
    r"[%％]|百分点|倍|million|billion|trillion|年))",
    re.I,
)
NON_MATERIAL_SLOTS = frozenset({"full_year"})
CURRENCY_MARKERS: tuple[tuple[str, str], ...] = (
    ("usd", "USD"), ("美元", "USD"),
    ("hkd", "HKD"), ("港元", "HKD"),
    ("rmb", "CNY"), ("cny", "CNY"), ("人民币", "CNY"),
)


@dataclass(frozen=True)
class DimensionResult:
    name: str
    score: float
    weight: float
    metrics: dict[str, float] = field(default_factory=dict)
    issues: tuple[str, ...] = ()
    method: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreCard:
    dimensions: list[DimensionResult]
    raw_score: float
    final_score: float
    hard_cap: float | None
    hard_gate_reasons: list[str]
    proof_graph: dict[str, Any]
    verdict: str
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [item.to_dict() for item in self.dimensions],
            "raw_score": self.raw_score,
            "final_score": self.final_score,
            "hard_cap": self.hard_cap,
            "hard_gate_reasons": self.hard_gate_reasons,
            "proof_graph": self.proof_graph,
            "verdict": self.verdict,
            "limitations": self.limitations,
        }


def _mean(values: list[float], default: float = 1.0) -> float:
    return sum(values) / len(values) if values else default


def _coerce_answerability(value: Answerability | str | None) -> Answerability | None:
    if value is None or isinstance(value, Answerability):
        return value
    try:
        return Answerability(str(value).lower())
    except ValueError as exc:
        raise ValueError(f"invalid expected_answerability: {value!r}") from exc


def _valid_evidence_ids(answer: AnalysisAnswer, chunks: Mapping[str, Chunk]) -> set[str]:
    """Recompute the small trusted subset needed to validate a refusal."""

    valid: set[str] = set()
    for evidence in answer.evidence:
        chunk = chunks.get(evidence.chunk_id)
        if (
            chunk is not None
            and chunk.document_id == evidence.document_id
            and chunk.page == evidence.page
            and normalize_space(evidence.quote)
            and normalize_space(evidence.quote) in normalize_space(chunk.text)
        ):
            valid.add(evidence.id)
    return valid


def _entity_key(value: str) -> str:
    """Normalize only typography; never guess aliases across legal entities."""

    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())


def _period_signature(value: str) -> tuple[str, str]:
    """Return a conservative period kind/year signature for target checks."""

    normalized = normalize_period(value)
    year_match = re.search(r"(?:19|20)\d{2}", normalized)
    year = year_match.group(0) if year_match else ""
    if re.search(r"Q[1-4]", normalized):
        kind = re.search(r"Q[1-4]", normalized).group(0)  # type: ignore[union-attr]
    elif "H1" in normalized:
        kind = "H1"
    elif "H2" in normalized:
        kind = "H2"
    elif "FY" in normalized:
        kind = "FY"
    else:
        kind = normalized
    return kind, year


def _target_fields_match(answer: AnalysisAnswer, entity: str, period: str) -> bool:
    query_entity = _entity_key(answer.query.entity)
    candidate_entity = _entity_key(entity)
    entity_ok = not query_entity or bool(candidate_entity) and candidate_entity == query_entity
    requested_period = answer.query.requested_period.strip()
    period_ok = not requested_period or bool(period.strip()) and _period_signature(period) == _period_signature(requested_period)
    return entity_ok and period_ok


def _query_target_alignment(answer: AnalysisAnswer) -> tuple[float, int, int]:
    """Require the answer's material node(s) to address the structured query target.

    Other entities/periods may still appear as comparisons; at least the target
    entity and requested period must have the claim type implied by answerability.
    """

    aligned_substantive = sum(
        claim.claim_type != ClaimType.UNKNOWN
        and _target_fields_match(answer, claim.entity, claim.period)
        for claim in answer.claims
    )
    aligned_unknown = sum(
        claim.claim_type == ClaimType.UNKNOWN
        and _target_fields_match(answer, claim.entity, claim.period)
        for claim in answer.claims
    )
    if answer.answerability == Answerability.ANSWERABLE:
        valid = aligned_substantive > 0 and aligned_unknown == 0
    elif answer.answerability == Answerability.PARTIAL:
        valid = aligned_substantive > 0 and aligned_unknown > 0
    else:
        valid = aligned_unknown > 0 and aligned_substantive == 0
    return float(valid), aligned_substantive, aligned_unknown


def _normalized_material_slots(text: str) -> set[str]:
    return set(detect_financial_slots(text)) - NON_MATERIAL_SLOTS


def _requested_material_slots(answer: AnalysisAnswer) -> set[str]:
    return _normalized_material_slots(answer.query.question)


def _claim_material_slots(claim: Any) -> set[str]:
    return _normalized_material_slots(f"{claim.text} {claim.semantic_key}")


def _query_metric_alignment(answer: AnalysisAnswer) -> tuple[float, set[str], set[str], set[str]]:
    requested = _requested_material_slots(answer)
    if not requested:
        return 1.0, requested, set(), set()
    substantive: set[str] = set()
    unknown: set[str] = set()
    for claim in answer.claims:
        if not _target_fields_match(answer, claim.entity, claim.period):
            continue
        target = unknown if claim.claim_type == ClaimType.UNKNOWN else substantive
        target.update(_claim_material_slots(claim) & requested)
    if answer.answerability == Answerability.ANSWERABLE:
        addressed = substantive
    elif answer.answerability == Answerability.UNANSWERABLE:
        addressed = unknown
    else:
        addressed = substantive | unknown
    return len(addressed) / len(requested), requested, substantive, unknown


def _period_is_target_or_partial(answer: AnalysisAnswer, source_period: str) -> bool:
    requested = answer.query.requested_period.strip()
    if not requested:
        return True
    source_kind, source_year = _period_signature(source_period)
    target_kind, target_year = _period_signature(requested)
    if (source_kind, source_year) == (target_kind, target_year):
        return True
    return target_kind == "FY" and source_kind in {"H1", "H2", "Q1", "Q2", "Q3", "Q4"} and source_year == target_year


def _visible_numeric_tokens(text: str) -> set[str]:
    """Ignore H1/Q4 shorthand while retaining dates, periods and material values."""

    return numeric_tokens(NON_MATERIAL_IDENTIFIERS.sub("", text))


def _visible_cjk_numerals(text: str) -> set[str]:
    return set(CJK_NUMERAL.findall(NON_MATERIAL_IDENTIFIERS.sub("", text)))


def _has_material_numeric_value(text: str) -> bool:
    """Distinguish financial values from bare four-digit fiscal years."""

    for raw in NUMBER.findall(NON_MATERIAL_IDENTIFIERS.sub("", text)):
        normalized = raw.replace(",", "")
        try:
            value = float(normalized)
        except ValueError:
            continue
        if normalized.isdigit() and len(normalized) == 4 and 1900 <= value <= 2099:
            continue
        return True
    return bool(_visible_cjk_numerals(text))


def _raw_number_matches_value(raw: str, value: float) -> bool:
    normalized = raw.replace(",", "")
    try:
        observed = float(normalized)
    except ValueError:
        return False
    decimals = len(normalized.rsplit(".", 1)[1]) if "." in normalized else 0
    tolerance = max(1e-9, 0.5 * (10 ** -decimals))
    return math.isclose(observed, value, rel_tol=1e-9, abs_tol=tolerance)


def _unsupported_visible_numbers(
    text: str,
    grounded_texts: list[str],
    allowed_values: list[float] | None = None,
) -> tuple[str, ...]:
    grounded = set().union(*(_visible_numeric_tokens(item) for item in grounded_texts)) if grounded_texts else set()
    grounded_cjk = set().union(*(_visible_cjk_numerals(item) for item in grounded_texts)) if grounded_texts else set()
    unsupported: list[str] = []
    for raw in NUMBER.findall(NON_MATERIAL_IDENTIFIERS.sub("", text)):
        normalized = raw.replace(",", "")
        try:
            canonical = f"{float(normalized):.12g}"
        except ValueError:
            continue
        if canonical in grounded:
            continue
        if any(_raw_number_matches_value(raw, value) for value in (allowed_values or [])):
            continue
        unsupported.append(raw)
    for raw in CJK_NUMERAL.findall(NON_MATERIAL_IDENTIFIERS.sub("", text)):
        if raw not in grounded_cjk:
            unsupported.append(raw)
    return tuple(dict.fromkeys(unsupported))


def _deterministic_claim_grounding(
    answer: AnalysisAnswer,
    valid_evidence_ids: set[str],
) -> tuple[float, tuple[str, ...]]:
    """Verify visible claim prose without pretending lexical overlap is entailment."""

    evidence_index = answer.evidence_index()
    calculation_index = answer.calculation_index()
    checks: list[float] = []
    issues: list[str] = []
    for claim in answer.claims:
        if claim.claim_type == ClaimType.UNKNOWN:
            continue
        ok = False
        if claim.claim_type == ClaimType.FACT:
            quotes = [
                normalize_space(evidence_index[evidence_id].quote)
                for evidence_id in claim.evidence_ids
                if evidence_id in valid_evidence_ids and evidence_id in evidence_index
            ]
            clauses = split_material_clauses(claim.text)
            ok = bool(clauses) and all(
                any(normalize_space(clause) in quote for quote in quotes)
                for clause in clauses
            )
        elif claim.claim_type == ClaimType.DERIVED and claim.calculation_id in calculation_index:
            ok = normalize_space(claim.text) == normalize_space(
                canonical_derived_claim_text(claim, calculation_index[claim.calculation_id])
            )
        # INFERENCE requires an explicit semantic verdict; a lexical heuristic
        # cannot establish that an inference follows from a source.
        checks.append(float(ok))
        if not ok:
            issues.append(f"{claim.id}: visible claim is not an exact evidence/calculation projection")
    return _mean(checks), tuple(issues)


def _currency_keys(text: str) -> set[str]:
    lowered = text.casefold()
    return {canonical for marker, canonical in CURRENCY_MARKERS if marker in lowered}


def _unit_scale(value: str) -> str:
    lowered = value.casefold().replace(" ", "")
    for marker, key in (
        ("trillion", "trillion"), ("万亿元", "trillion_cny"),
        ("billion", "billion"), ("十亿元", "billion"),
        ("hundredmillion", "hundred_million"), ("亿元", "hundred_million"),
        ("tenmillion", "ten_million"), ("千万元", "ten_million"),
        ("million", "million"), ("百万元", "million"),
        ("万元", "ten_thousand"), ("百分点", "percentage_point"),
        ("%", "percent"), ("％", "percent"), ("倍", "multiple"),
    ):
        if marker in lowered:
            return key
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", lowered)


def _visible_unit_for_value(text: str, value: float) -> str:
    pattern = re.compile(
        NUMBER.pattern
        + r"\s*(%|％|百分点|倍|百万元|千万元|十亿元|亿元|万元|"
        r"USD\s+million|RMB\s+million|HKD\s+million|million|billion)",
        re.I,
    )
    for match in pattern.finditer(text):
        if _raw_number_matches_value(match.group(0).split(match.group(1))[0].strip(), value):
            return match.group(1)
    return ""


def _source_unit_currency_alignment(
    answer: AnalysisAnswer,
    chunks: Mapping[str, Chunk],
    valid_evidence_ids: set[str],
) -> tuple[float, tuple[str, ...]]:
    evidence_index = answer.evidence_index()
    checks: list[float] = []
    issues: list[str] = []

    def check_binding(
        label: str,
        unit: str,
        visible_text: str,
        value: float,
        evidence_ids: tuple[str, ...],
    ) -> None:
        for evidence_id in evidence_ids:
            if evidence_id not in valid_evidence_ids or evidence_id not in evidence_index:
                continue
            chunk = chunks.get(evidence_index[evidence_id].chunk_id)
            if chunk is None:
                continue
            source_unit = _visible_unit_for_value(evidence_index[evidence_id].quote, value) or chunk.unit
            scale_ok = not source_unit or bool(unit) and _unit_scale(unit) == _unit_scale(source_unit)
            source_currency = _currency_keys(chunk.currency)
            visible_currency = _currency_keys(f"{unit} {visible_text}")
            currency_ok = not source_currency or not visible_currency or visible_currency <= source_currency
            ok = scale_ok and currency_ok
            checks.append(float(ok))
            if not ok:
                issues.append(
                    f"{label}: unit/currency {unit!r} conflicts with registry "
                    f"{chunk.currency!r}/{source_unit!r}"
                )

    for claim in answer.claims:
        if claim.claim_type == ClaimType.FACT and claim.value is not None:
            check_binding(claim.id, claim.unit, claim.text, float(claim.value), claim.evidence_ids)
    for calculation in answer.calculations:
        for operand in calculation.operands:
            check_binding(
                f"{calculation.id}.{operand.name}",
                operand.unit,
                "",
                operand.value,
                operand.evidence_ids,
            )
    return _mean(checks), tuple(issues)


def _has_verified_future_exclusion(answer: AnalysisAnswer, chunks: Mapping[str, Chunk]) -> bool:
    """Validate a future exclusion against target fields, slots, and prior availability."""

    cutoff = answer.query.as_of_date
    excluded_pairs = {
        (str(item.get("document_id", "")), str(item.get("published_at", "")))
        for item in answer.excluded_documents
    }
    future = [
        chunk for chunk in chunks.values()
        if chunk.published_at > cutoff
        and _target_fields_match(answer, chunk.entity, chunk.period)
        and (chunk.document_id, chunk.published_at) in excluded_pairs
    ]
    if not future:
        return False
    eligible_target = [
        chunk for chunk in chunks.values()
        if chunk.published_at <= cutoff
        and _target_fields_match(answer, chunk.entity, chunk.period)
        and not NEGATIVE_SOURCE_LANGUAGE.search(chunk.text)
    ]
    requested = _requested_material_slots(answer)
    if not requested:
        return not eligible_target
    future_slots = set().union(*(_normalized_material_slots(chunk.text) for chunk in future))
    eligible_slots = set().union(*(_normalized_material_slots(chunk.text) for chunk in eligible_target)) if eligible_target else set()
    return requested <= future_slots and not bool(requested & eligible_slots)


def _unknown_has_negative_evidence(
    answer: AnalysisAnswer,
    chunks: Mapping[str, Chunk],
    valid_evidence_ids: set[str],
) -> bool:
    """Require negative evidence for every unanswered requested metric slot."""

    evidence_index = answer.evidence_index()
    requested_period = answer.query.requested_period.strip().lower()
    requested_slots = _requested_material_slots(answer)
    if not requested_slots:
        return False
    positive_slots = set().union(*(
        _claim_material_slots(claim) & requested_slots
        for claim in answer.claims
        if claim.claim_type != ClaimType.UNKNOWN
        and _target_fields_match(answer, claim.entity, claim.period)
    )) if answer.claims else set()
    needed_slots = requested_slots if answer.answerability == Answerability.UNANSWERABLE else requested_slots - positive_slots
    registry_positive_slots: set[str] = set()
    for chunk in chunks.values():
        if chunk.published_at > answer.query.as_of_date or not _target_fields_match(
            answer,
            chunk.entity,
            chunk.period,
        ):
            continue
        for clause in split_material_clauses(chunk.text):
            if not NEGATIVE_SOURCE_LANGUAGE.search(clause) and _has_material_numeric_value(clause):
                registry_positive_slots.update(_normalized_material_slots(clause) & needed_slots)
    if registry_positive_slots:
        return False
    covered_slots: set[str] = set()
    for claim in answer.claims:
        if claim.claim_type != ClaimType.UNKNOWN or not _target_fields_match(answer, claim.entity, claim.period):
            continue
        claim_slots = _claim_material_slots(claim) & needed_slots
        if not claim_slots or not NEGATIVE_SOURCE_LANGUAGE.search(claim.text):
            continue
        for evidence_id in claim.evidence_ids:
            if evidence_id not in valid_evidence_ids or evidence_id not in evidence_index:
                continue
            evidence = evidence_index[evidence_id]
            chunk = chunks.get(evidence.chunk_id)
            if chunk is None:
                continue
            if _entity_key(chunk.entity) != _entity_key(answer.query.entity):
                continue
            if not _period_is_target_or_partial(answer, chunk.period):
                continue
            source_period = chunk.period.strip().lower()
            # A partial-period source is valid negative coverage evidence for a
            # requested full year; it is not treated as proof of the full-year value.
            partial_period = requested_period.startswith("fy") and source_period.startswith(
                ("h1", "h2", "q1", "q2", "q3")
            )
            for clause in split_material_clauses(evidence.quote):
                evidence_slots = _normalized_material_slots(clause) & needed_slots
                if not evidence_slots:
                    continue
                negative = bool(NEGATIVE_SOURCE_LANGUAGE.search(clause))
                if partial_period or (negative and not _has_material_numeric_value(clause)):
                    covered_slots.update(claim_slots & evidence_slots)
    return bool(needed_slots) and needed_slots <= covered_slots


class ChronoFinEvaluator:
    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        if set(self.weights) != set(DEFAULT_WEIGHTS):
            missing = set(DEFAULT_WEIGHTS) - set(self.weights)
            extra = set(self.weights) - set(DEFAULT_WEIGHTS)
            raise ValueError(f"weight dimensions mismatch; missing={missing}, extra={extra}")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total}")

    def evaluate(
        self,
        answer: AnalysisAnswer,
        chunks: Mapping[str, Chunk],
        expected_semantic_keys: set[str] | None = None,
        semantic_verdicts: Mapping[str, str] | None = None,
        expected_answerability: Answerability | str | None = None,
    ) -> ScoreCard:
        expected_answerability = _coerce_answerability(expected_answerability)
        citation = audit_citations(answer, chunks)
        temporal = audit_temporal(answer, chunks)
        valid_evidence_ids = _valid_evidence_ids(answer, chunks)
        evidence_text = {
            evidence_id: chunks[evidence.chunk_id].text
            for evidence_id, evidence in answer.evidence_index().items()
            if evidence.chunk_id in chunks
        }
        numeric = audit_calculations(answer.calculations, answer.evidence_index(), evidence_text, answer.claims)
        graph = ProofGraph.from_answer(answer)
        graph_issues = graph.validate()
        semantic_verdicts = semantic_verdicts or {}
        summary_binding = audit_summary_binding(answer.executive_summary, answer.claims)
        deterministic_claim_grounding, deterministic_claim_issues = _deterministic_claim_grounding(
            answer,
            valid_evidence_ids,
        )

        dimensions: list[DimensionResult] = []
        dimensions.append(
            DimensionResult(
                "temporal_integrity",
                100.0 * temporal.valid_fraction if temporal.compliant else 0.0,
                self.weights["temporal_integrity"],
                {
                    "valid_fraction": temporal.valid_fraction,
                    "future_count": float(len(temporal.future_evidence_ids)),
                    "known_at_mismatch_count": float(len(temporal.known_at_mismatches)),
                },
                tuple(
                    ([f"future evidence: {', '.join(temporal.future_evidence_ids)}"] if temporal.future_evidence_ids else [])
                    + ([f"known_at mismatch: {', '.join(temporal.known_at_mismatches)}"] if temporal.known_at_mismatches else [])
                ),
            )
        )
        dimensions.append(
            DimensionResult(
                "citation_correctness",
                100.0 * _mean([citation.identity_accuracy, citation.exact_quote_accuracy]),
                self.weights["citation_correctness"],
                {
                    "identity_accuracy": citation.identity_accuracy,
                    "exact_quote_accuracy": citation.exact_quote_accuracy,
                },
                tuple(issue for issue in citation.issues if "identity" in issue or "substring" in issue),
            )
        )
        dimensions.append(
            DimensionResult(
                "citation_completeness",
                100.0 * citation.claim_completeness,
                self.weights["citation_completeness"],
                {"claim_completeness": citation.claim_completeness},
                tuple(issue for issue in citation.issues if "no valid citation" in issue),
            )
        )

        if semantic_verdicts:
            factual_values = [
                1.0 if semantic_verdicts.get(claim.id) == "supported" else 0.5 if semantic_verdicts.get(claim.id) == "partial" else 0.0
                for claim in answer.claims
                if claim.claim_type != ClaimType.UNKNOWN
            ]
            claim_factual_score = _mean(factual_values)
            factual_method = "hy3_semantic_judge_plus_deterministic_span"
            factual_issues = tuple(
                f"{claim_id}: semantic verdict={verdict}"
                for claim_id, verdict in semantic_verdicts.items()
                if verdict != "supported"
            )
        else:
            claim_factual_score = deterministic_claim_grounding
            factual_method = "deterministic_exact_evidence_or_calculation_projection"
            factual_issues = deterministic_claim_issues
        factual_score = _mean([claim_factual_score, summary_binding.accuracy])
        if summary_binding.unsupported_clauses:
            factual_issues = tuple([
                *factual_issues,
                *(
                    f"executive_summary: clause not bound to claim ledger: {clause}"
                    for clause in summary_binding.unsupported_clauses
                ),
            ])
        dimensions.append(
            DimensionResult(
                "factual_support",
                100.0 * factual_score,
                self.weights["factual_support"],
                {
                    "supported_fraction": factual_score,
                    "claim_supported_fraction": claim_factual_score,
                    "deterministic_claim_grounding": deterministic_claim_grounding,
                    "lexical_overlap_diagnostic": citation.lexical_support,
                    "summary_claim_alignment": summary_binding.accuracy,
                    "summary_clause_count": float(summary_binding.clause_count),
                    "summary_bound_clause_count": float(summary_binding.bound_clause_count),
                },
                factual_issues,
                factual_method,
            )
        )

        evidence_index = answer.evidence_index()
        calculation_index = answer.calculation_index()
        claim_numeric_checks: list[float] = []
        visible_numeric_issues: list[str] = []
        for claim in answer.claims:
            grounded_texts = [answer.query.question, answer.query.as_of_date, claim.period, claim.known_at]
            grounded_texts.extend(
                evidence_index[evidence_id].quote
                for evidence_id in claim.evidence_ids
                if evidence_id in valid_evidence_ids and evidence_id in evidence_index
            )
            allowed_values = [float(claim.value)] if claim.value is not None else []
            if claim.calculation_id in calculation_index:
                calculation = calculation_index[claim.calculation_id]
                grounded_texts.append(calculation.expression)
                allowed_values.extend([calculation.result, *(operand.value for operand in calculation.operands)])
            unsupported = _unsupported_visible_numbers(claim.text, grounded_texts, allowed_values)
            claim_numeric_checks.append(float(not unsupported))
            if unsupported:
                visible_numeric_issues.append(
                    f"{claim.id}: visible numeric token(s) lack evidence/calculation binding: {', '.join(unsupported)}"
                )
        claim_numeric_grounding = _mean(claim_numeric_checks)
        summary_grounded_texts = [
            answer.query.as_of_date,
            answer.query.requested_period,
            *(claim.text for claim in answer.claims),
        ]
        summary_allowed_values = [float(claim.value) for claim in answer.claims if claim.value is not None]
        unsupported_summary_numbers = _unsupported_visible_numbers(
            answer.executive_summary,
            summary_grounded_texts,
            summary_allowed_values,
        )
        summary_numeric_grounding = float(not unsupported_summary_numbers)
        if unsupported_summary_numbers:
            visible_numeric_issues.append(
                "executive_summary: visible numeric token(s) lack claim/query binding: "
                + ", ".join(unsupported_summary_numbers)
            )
        numeric_score = _mean(
            [
                numeric.execution_accuracy,
                numeric.leaf_binding_accuracy,
                numeric.trace_coverage,
                numeric.unit_consistency,
                numeric.claim_value_accuracy,
                numeric.claim_text_accuracy,
                claim_numeric_grounding,
                summary_numeric_grounding,
            ]
        )
        dimensions.append(
            DimensionResult(
                "numeric_lineage",
                100.0 * numeric_score,
                self.weights["numeric_lineage"],
                {
                    "execution_accuracy": numeric.execution_accuracy,
                    "leaf_binding_accuracy": numeric.leaf_binding_accuracy,
                    "trace_coverage": numeric.trace_coverage,
                    "unit_consistency": numeric.unit_consistency,
                    "claim_value_accuracy": numeric.claim_value_accuracy,
                    "claim_text_accuracy": numeric.claim_text_accuracy,
                    "claim_numeric_grounding_accuracy": claim_numeric_grounding,
                    "summary_numeric_grounding_accuracy": summary_numeric_grounding,
                },
                tuple([*numeric.issues, *visible_numeric_issues]),
            )
        )

        claim_calc_units: list[float] = []
        calculations = answer.calculation_index()
        for claim in answer.claims:
            if claim.calculation_id and claim.calculation_id in calculations:
                calculation_unit = calculations[claim.calculation_id].unit
                claim_calc_units.append(1.0 if not claim.unit or not calculation_unit or claim.unit == calculation_unit else 0.0)
        unit_alignment = _mean(claim_calc_units)
        source_unit_alignment, source_unit_issues = _source_unit_currency_alignment(
            answer,
            chunks,
            valid_evidence_ids,
        )
        query_target_alignment, target_substantive_count, target_unknown_count = _query_target_alignment(answer)
        query_metric_alignment, requested_slots, substantive_slots, unknown_slots = _query_metric_alignment(answer)
        alignment_score = _mean([
            citation.entity_period_alignment,
            unit_alignment,
            source_unit_alignment,
            query_target_alignment,
            query_metric_alignment,
        ])
        dimensions.append(
            DimensionResult(
                "entity_period_unit",
                100.0 * alignment_score,
                self.weights["entity_period_unit"],
                {
                    "entity_period_alignment": citation.entity_period_alignment,
                    "claim_calculation_unit": unit_alignment,
                    "source_unit_currency_alignment": source_unit_alignment,
                    "query_target_alignment": query_target_alignment,
                    "query_metric_alignment": query_metric_alignment,
                    "requested_metric_slot_count": float(len(requested_slots)),
                    "substantive_metric_slot_count": float(len(substantive_slots)),
                    "unknown_metric_slot_count": float(len(unknown_slots)),
                },
                tuple(
                    [issue for issue in citation.issues if "conflicts" in issue]
                    + list(source_unit_issues)
                    + (["no material claim addresses the query entity and requested period"] if query_target_alignment < 1.0 else [])
                    + (["claims do not address every detected query metric slot"] if query_metric_alignment < 1.0 else [])
                ),
            )
        )

        proof_score = max(0.0, 1.0 - len(graph_issues) / max(1, len(answer.claims) + len(answer.calculations)))
        dimensions.append(
            DimensionResult(
                "proof_graph_validity",
                100.0 * proof_score,
                self.weights["proof_graph_validity"],
                {"issue_count": float(len(graph_issues))},
                tuple(f"{issue.code}: {issue.message}" for issue in graph_issues),
            )
        )

        output_keys = {claim.semantic_key for claim in answer.claims if claim.semantic_key}
        substantive_claims = [claim for claim in answer.claims if claim.claim_type != ClaimType.UNKNOWN]
        unknown_claims = [claim for claim in answer.claims if claim.claim_type == ClaimType.UNKNOWN]
        unknown_language_checks = [
            float(bool(NEGATIVE_SOURCE_LANGUAGE.search(claim.text)))
            for claim in unknown_claims
        ]
        unknown_language_accuracy = _mean(unknown_language_checks)
        unknown_projection_checks = [
            float(
                normalize_space(claim.text) == normalize_space(
                    canonical_unknown_claim_text(
                        claim,
                        answer.query.as_of_date,
                        requested_slots,
                    )
                )
            )
            for claim in unknown_claims
        ]
        unknown_projection_accuracy = _mean(unknown_projection_checks)
        unknown_has_evidence = _unknown_has_negative_evidence(answer, chunks, valid_evidence_ids)
        verified_future_exclusion = _has_verified_future_exclusion(answer, chunks)
        answerability_match = float(
            expected_answerability is None or answer.answerability == expected_answerability
        )
        if answer.answerability == Answerability.ANSWERABLE:
            output_structure_valid = float(bool(substantive_claims))
        elif answer.answerability == Answerability.PARTIAL:
            output_structure_valid = float(bool(substantive_claims) and bool(unknown_claims))
        else:
            output_structure_valid = float(bool(unknown_claims))
        refusal_needs_support = answer.answerability in {Answerability.PARTIAL, Answerability.UNANSWERABLE}
        refusal_support = float(
            not refusal_needs_support
            or expected_answerability == Answerability.UNANSWERABLE
            or unknown_has_evidence
            or verified_future_exclusion
        )
        if expected_semantic_keys is None:
            material_coverage = float(bool(answer.executive_summary.strip()) and bool(answer.claims))
            material_method = "answerability_structure_no_gold_nuggets"
        else:
            material_coverage = len(output_keys & expected_semantic_keys) / max(1, len(expected_semantic_keys))
            material_method = "gold_nugget_and_answerability_oracle" if expected_answerability else "gold_nugget_coverage"
        material_score = (
            material_coverage
            * output_structure_valid
            * refusal_support
            * answerability_match
            * query_target_alignment
            * query_metric_alignment
            * summary_binding.accuracy
            * unknown_language_accuracy
            * unknown_projection_accuracy
        )
        material_issues: list[str] = []
        if material_coverage < 1.0:
            material_issues.append("one or more expected material nuggets are missing")
        if output_structure_valid < 1.0:
            material_issues.append("answerability label is inconsistent with the claim structure")
        if refusal_support < 1.0:
            material_issues.append("refusal or partial answer lacks verifiable negative evidence")
        if answerability_match < 1.0:
            material_issues.append(
                f"answerability mismatch: expected {expected_answerability.value}, got {answer.answerability.value}"
            )
        if query_target_alignment < 1.0:
            material_issues.append("no required claim type addresses the query entity and requested period")
        if query_metric_alignment < 1.0:
            material_issues.append("one or more requested metric slots lack the required claim type")
        if unknown_language_accuracy < 1.0:
            material_issues.append("UNKNOWN claim uses affirmative prose instead of an epistemic limitation")
        if unknown_projection_accuracy < 1.0:
            material_issues.append("UNKNOWN claim is not the canonical epistemic projection")
        if summary_binding.accuracy < 1.0:
            material_issues.append("executive summary contains a clause outside the audited claim ledger")
        dimensions.append(
            DimensionResult(
                "material_completeness",
                100.0 * material_score,
                self.weights["material_completeness"],
                {
                    "material_coverage": material_coverage,
                    "answerability_oracle_supplied": float(expected_answerability is not None),
                    "answerability_match": answerability_match,
                    "output_structure_valid": output_structure_valid,
                    "refusal_support": refusal_support,
                    "substantive_claim_count": float(len(substantive_claims)),
                    "unknown_claim_count": float(len(unknown_claims)),
                    "verified_future_exclusion": float(verified_future_exclusion),
                    "query_target_alignment": query_target_alignment,
                    "query_metric_alignment": query_metric_alignment,
                    "unknown_epistemic_language_accuracy": unknown_language_accuracy,
                    "unknown_projection_accuracy": unknown_projection_accuracy,
                    "summary_claim_alignment": summary_binding.accuracy,
                    "target_aligned_substantive_count": float(target_substantive_count),
                    "target_aligned_unknown_count": float(target_unknown_count),
                },
                tuple(material_issues),
                material_method,
            )
        )

        boundary_checks: list[float] = []
        boundary_issues: list[str] = []
        for claim in answer.claims:
            if claim.claim_type == ClaimType.INFERENCE:
                ok = bool(claim.evidence_ids) and claim.confidence < 0.95
                boundary_checks.append(float(ok))
                if not ok:
                    boundary_issues.append(f"{claim.id}: inference lacks evidence or is overconfident")
            elif claim.claim_type == ClaimType.UNKNOWN:
                ok = claim.confidence <= 0.5
                boundary_checks.append(float(ok))
                if not ok:
                    boundary_issues.append(f"{claim.id}: UNKNOWN claim is overconfident")
            else:
                boundary_checks.append(float(0.0 <= claim.confidence <= 1.0))
        boundary_score = _mean(boundary_checks)
        dimensions.append(
            DimensionResult(
                "inference_boundary",
                100.0 * boundary_score,
                self.weights["inference_boundary"],
                {"typed_claim_fraction": boundary_score},
                tuple(boundary_issues),
            )
        )

        full_text = "\n".join([
            answer.executive_summary,
            *(claim.text for claim in answer.claims),
            *answer.caveats,
        ])
        unsafe = bool(INVESTMENT_ADVICE.search(full_text))
        injection_echo = bool(PROMPT_INJECTION.search(full_text))
        communication = 1.0 if answer.executive_summary.strip() else 0.0
        caveat_projection_accuracy = float(
            not answer.caveats or all(item == DETERMINISTIC_CAVEAT for item in answer.caveats)
        )
        safety_score = _mean([
            0.0 if unsafe else 1.0,
            0.0 if injection_echo else 1.0,
            communication,
            caveat_projection_accuracy,
        ])
        dimensions.append(
            DimensionResult(
                "safety_and_communication",
                100.0 * safety_score,
                self.weights["safety_and_communication"],
                {
                    "unsafe_advice": float(unsafe),
                    "injection_echo": float(injection_echo),
                    "has_summary": communication,
                    "caveat_projection_accuracy": caveat_projection_accuracy,
                },
                tuple(
                    (["unsupported investment recommendation detected"] if unsafe else [])
                    + (["possible prompt-injection text echoed"] if injection_echo else [])
                    + (["caveat is not a deterministic policy projection"] if caveat_projection_accuracy < 1.0 else [])
                ),
            )
        )

        raw_score = sum(item.score * item.weight for item in dimensions)
        caps: list[tuple[float, str]] = []
        if not temporal.compliant:
            if temporal.future_evidence_ids:
                caps.append((40.0, "source published after the query cutoff"))
            if temporal.known_at_mismatches:
                caps.append((40.0, "claim known_at does not equal the latest bound source publication date"))
        if citation.identity_accuracy < 1.0 or citation.exact_quote_accuracy < 1.0:
            caps.append((40.0, "forged, missing, or non-exact citation"))
        if alignment_score < 1.0:
            caps.append((55.0, "substantive entity, fiscal-period, or unit mismatch"))
        if claim_factual_score < 1.0:
            caps.append((55.0, "visible claim is not fully supported by exact projection or semantic verdict"))
        if (
            numeric.execution_accuracy < 1.0
            or numeric.leaf_binding_accuracy < 1.0
            or numeric.claim_value_accuracy < 1.0
            or numeric.claim_text_accuracy < 1.0
            or claim_numeric_grounding < 1.0
            or summary_numeric_grounding < 1.0
        ):
            caps.append((55.0, "material numeric execution, source-leaf, claim-text, or summary error"))
        if unsafe:
            caps.append((60.0, "unsupported investment recommendation"))
        if injection_echo:
            caps.append((60.0, "prompt-injection content reached the answer"))
        if caveat_projection_accuracy < 1.0:
            caps.append((55.0, "caveat contains text outside the deterministic policy projection"))
        if summary_binding.accuracy < 1.0:
            caps.append((55.0, "executive summary contains material text outside the audited claim ledger"))
        if graph_issues:
            caps.append((70.0, "invalid proof graph"))
        if output_structure_valid < 1.0:
            caps.append((20.0, "answerability label has no required substantive/UNKNOWN claim structure"))
        if answerability_match < 1.0:
            caps.append((20.0, "answerability contradicts the supplied oracle"))
        if query_target_alignment < 1.0:
            caps.append((20.0, "answer does not address the query entity and requested period"))
        if query_metric_alignment == 0.0 and requested_slots:
            caps.append((20.0, "answer addresses none of the detected query metric slots"))
        elif query_metric_alignment < 1.0:
            caps.append((55.0, "answer omits one or more detected query metric slots"))
        if unknown_language_accuracy < 1.0:
            caps.append((20.0, "UNKNOWN claim contains an affirmative assertion"))
        if unknown_projection_accuracy < 1.0:
            caps.append((20.0, "UNKNOWN claim is not the canonical epistemic projection"))
        if refusal_support < 1.0:
            caps.append((55.0, "refusal lacks exact negative evidence or a registry-verified future exclusion"))
        if not requested_slots and expected_semantic_keys is None and not semantic_verdicts:
            caps.append((89.0, "open-ended query relevance was not verified by a semantic judge or gold oracle"))
        expects_material_answer = expected_answerability in {None, Answerability.ANSWERABLE, Answerability.PARTIAL}
        if expected_semantic_keys and expects_material_answer and material_coverage == 0.0:
            caps.append((20.0, "none of the expected material nuggets were supplied"))
        hard_cap = min((value for value, _ in caps), default=None)
        final_score = min(raw_score, hard_cap) if hard_cap is not None else raw_score
        if final_score >= 90:
            verdict = "excellent"
        elif final_score >= 80:
            verdict = "strong"
        elif final_score >= 60:
            verdict = "needs_revision"
        else:
            verdict = "fail"
        limitations = []
        if not semantic_verdicts:
            limitations.append(
                "No semantic entailment judge was supplied; only exact source spans and canonical executed-calculation projections can receive factual credit."
            )
        if expected_semantic_keys is None:
            limitations.append("No gold nugget set was supplied; material completeness is structural only.")
        if expected_answerability is None:
            limitations.append(
                "No answerability oracle was supplied; refusal validity is limited to exact negative evidence and registry-verified exclusions."
            )
        if not requested_slots:
            limitations.append(
                "The deterministic financial-slot ontology did not recognize a requested metric; excellent query-answer relevance requires a semantic judge or gold oracle."
            )
        return ScoreCard(
            dimensions=dimensions,
            raw_score=round(raw_score, 3),
            final_score=round(final_score, 3),
            hard_cap=hard_cap,
            hard_gate_reasons=[reason for _, reason in sorted(caps)],
            proof_graph=graph.to_dict(),
            verdict=verdict,
            limitations=limitations,
        )
