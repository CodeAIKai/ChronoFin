"""Citation identity, exact-span, completeness, and alignment checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..models import AnalysisAnswer, Chunk, ClaimType
from ..retrieval import tokenize


SPACE = re.compile(r"\s+")


def normalize_space(text: str) -> str:
    return SPACE.sub(" ", text).strip()


def period_is_expressed(period: str, text: str) -> bool:
    """Conservatively check that a typed period is visible in claim text.

    Cross-period statements such as "H1 does not represent FY" are legitimate.
    They pass only when both periods are explicitly expressed, preventing this
    exception from hiding a silent adjacent-column error.
    """

    compact_period = re.sub(r"\s+", "", period).lower()
    compact_text = re.sub(r"\s+", "", text).lower()
    years = re.findall(r"(?:19|20)\d{2}", compact_period)
    if any(year not in compact_text for year in years):
        return False
    if compact_period.startswith("fy"):
        return any(marker in compact_text for marker in ("fy", "财年", "年度", "全年"))
    if compact_period.startswith("h1"):
        return any(marker in compact_text for marker in ("h1", "上半年", "六个月"))
    if compact_period.startswith("h2"):
        return any(marker in compact_text for marker in ("h2", "下半年", "后六个月"))
    quarter = re.search(r"q([1-4])", compact_period)
    if quarter:
        aliases = {
            "1": ("q1", "第一季度", "一季度"),
            "2": ("q2", "第二季度", "二季度"),
            "3": ("q3", "第三季度", "三季度"),
            "4": ("q4", "第四季度", "四季度"),
        }
        return any(marker in compact_text for marker in aliases[quarter.group(1)])
    return compact_period in compact_text


@dataclass(frozen=True)
class CitationAudit:
    identity_accuracy: float
    exact_quote_accuracy: float
    claim_completeness: float
    lexical_support: float
    entity_period_alignment: float
    issues: tuple[str, ...]


def audit_citations(answer: AnalysisAnswer, chunks: Mapping[str, Chunk]) -> CitationAudit:
    issues: list[str] = []
    identity_ok = 0
    quote_ok = 0
    aligned = 0
    evidence_index = answer.evidence_index()
    valid_evidence: set[str] = set()
    for evidence in answer.evidence:
        chunk = chunks.get(evidence.chunk_id)
        if (
            chunk is None
            or chunk.document_id != evidence.document_id
            or chunk.page != evidence.page
            or chunk.published_at != evidence.published_at
            or chunk.source_url != evidence.source_url
        ):
            issues.append(f"{evidence.id}: citation identity does not match registry")
            continue
        identity_ok += 1
        if normalize_space(evidence.quote) and normalize_space(evidence.quote) in normalize_space(chunk.text):
            quote_ok += 1
            valid_evidence.add(evidence.id)
        else:
            issues.append(f"{evidence.id}: quote is not an exact source substring")

    claims_requiring_support = [
        claim for claim in answer.claims if claim.claim_type != ClaimType.UNKNOWN
    ]
    complete = 0
    lexically_supported = 0
    alignment_total = 0
    for claim in claims_requiring_support:
        usable = [evidence_index[item] for item in claim.evidence_ids if item in valid_evidence]
        if usable:
            complete += 1
        else:
            issues.append(f"{claim.id}: no valid citation")
        quote_contexts = []
        for item in usable:
            chunk = chunks[item.chunk_id]
            quote_contexts.append(
                " ".join(filter(None, [item.quote, chunk.entity, chunk.period, chunk.currency, chunk.unit]))
            )
        quote_tokens = set(tokenize(" ".join(quote_contexts)))
        claim_tokens = set(tokenize(claim.text))
        # Numeric and Latin terms carry more meaning than isolated Chinese chars;
        # the heuristic is diagnostic only, never presented as semantic entailment.
        salient = {token for token in claim_tokens if len(token) > 1 or any(char.isdigit() for char in token)}
        if claim.claim_type == ClaimType.DERIVED and claim.calculation_id:
            lexically_supported += 1
        elif not salient or len(salient & quote_tokens) / len(salient) >= 0.35:
            lexically_supported += 1
        elif usable:
            issues.append(f"{claim.id}: cited span has weak lexical overlap; semantic review required")
        for item in usable:
            alignment_total += 1
            chunk = chunks[item.chunk_id]
            same_entity = not claim.entity or not chunk.entity or claim.entity.lower() == chunk.entity.lower()
            entity_ok = same_entity or (claim.entity.lower() in claim.text.lower() and chunk.entity.lower() in claim.text.lower())
            same_period = not claim.period or not chunk.period or claim.period.lower() == chunk.period.lower()
            period_ok = same_period or (
                period_is_expressed(claim.period, claim.text)
                and period_is_expressed(chunk.period, claim.text)
            )
            if entity_ok and period_ok:
                aligned += 1
            else:
                issues.append(
                    f"{claim.id}: entity/period {claim.entity}/{claim.period} conflicts with source {chunk.entity}/{chunk.period}"
                )

    evidence_denominator = max(1, len(answer.evidence))
    claim_denominator = max(1, len(claims_requiring_support))
    identity_accuracy = identity_ok / evidence_denominator if answer.evidence else 1.0
    exact_quote_accuracy = quote_ok / evidence_denominator if answer.evidence else 1.0
    claim_completeness = complete / claim_denominator if claims_requiring_support else 1.0
    lexical_support = lexically_supported / claim_denominator if claims_requiring_support else 1.0
    entity_period_alignment = aligned / max(1, alignment_total) if alignment_total else 1.0
    return CitationAudit(
        identity_accuracy=identity_accuracy,
        exact_quote_accuracy=exact_quote_accuracy,
        claim_completeness=claim_completeness,
        lexical_support=lexical_support,
        entity_period_alignment=entity_period_alignment,
        issues=tuple(issues),
    )
