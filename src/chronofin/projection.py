"""Canonical visible projections for typed, deterministically verified nodes."""

from __future__ import annotations

import math

from .models import Calculation, Claim


DETERMINISTIC_CAVEAT = "可见结论仅来自已绑定证据与确定性计算；不构成投资建议。"


def display_number(value: float) -> str:
    if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-12):
        return f"{int(round(value)):,}"
    return f"{value:,.12f}".rstrip("0").rstrip(".")


def canonical_derived_claim_text(claim: Claim, calculation: Calculation) -> str:
    """Render a derived claim using only typed target fields and executed math."""

    return (
        f"{claim.entity} {claim.period} {calculation.id}: "
        f"{calculation.expression} = {display_number(calculation.result)}{calculation.unit}。"
    )


def canonical_unknown_claim_text(
    claim: Claim,
    as_of_date: str,
    requested_slots: set[str] | None = None,
) -> str:
    """Render UNKNOWN as an epistemic limitation, never an affirmative claim."""

    target = claim.semantic_key or ", ".join(sorted(requested_slots or set())) or "requested metric"
    return (
        f"{claim.entity} {claim.period} {target}：截至 {as_of_date}，"
        "在已注册证据中不可确定。"
    )


def canonical_caveats() -> list[str]:
    return [DETERMINISTIC_CAVEAT]
