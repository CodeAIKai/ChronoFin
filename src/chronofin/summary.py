"""Deterministic executive-summary projection and binding audit.

The executive summary is the most prominent text in the UI, so it must not be
an unaudited side channel around the typed claim ledger. The pipeline renders
it from claim text, while the evaluator independently checks that every visible
summary clause is an exact normalized span of at least one audited claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .models import Claim


SUMMARY_BOUNDARY = re.compile(r"[。！？!?；;]+")
TRAILING_BOUNDARY = re.compile(r"[\s。！？!?；;]+$")


def _normalize(value: str) -> str:
    return " ".join(value.split()).strip()


def split_material_clauses(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for part in SUMMARY_BOUNDARY.split(value)
        if (normalized := _normalize(part))
    )


def canonical_executive_summary(claims: Sequence[Claim]) -> str:
    """Project the visible summary directly from the typed claim ledger."""

    parts = [
        TRAILING_BOUNDARY.sub("", claim.text.strip())
        for claim in claims
        if claim.text.strip()
    ]
    parts = [part for part in parts if part]
    return "；".join(parts) + ("。" if parts else "")


@dataclass(frozen=True)
class SummaryBindingAudit:
    clause_count: int
    bound_clause_count: int
    accuracy: float
    unsupported_clauses: tuple[str, ...]


def audit_summary_binding(summary: str, claims: Sequence[Claim]) -> SummaryBindingAudit:
    """Require every summary clause to be copied from an audited claim span.

    A claim may be longer than its summary projection, but the summary may not
    introduce any novel material clause. This conservative rule is deliberate:
    fluent model-authored paraphrases remain available only as a hashed trace,
    never as an unverified headline presented to the user.
    """

    clauses = split_material_clauses(summary)
    claim_texts = tuple(_normalize(claim.text) for claim in claims if _normalize(claim.text))
    unsupported = tuple(
        clause
        for clause in clauses
        if not any(clause in claim_text for claim_text in claim_texts)
    )
    bound = len(clauses) - len(unsupported)
    accuracy = bound / len(clauses) if clauses else 0.0
    return SummaryBindingAudit(
        clause_count=len(clauses),
        bound_clause_count=bound,
        accuracy=accuracy,
        unsupported_clauses=unsupported,
    )
