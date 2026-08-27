"""Point-in-time checks that do not trust timestamps emitted by the model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..models import AnalysisAnswer, Chunk, parse_iso_date


@dataclass(frozen=True)
class TemporalAudit:
    compliant: bool
    valid_fraction: float
    future_evidence_ids: tuple[str, ...]
    known_at_mismatches: tuple[str, ...]


def audit_temporal(answer: AnalysisAnswer, chunks: Mapping[str, Chunk]) -> TemporalAudit:
    cutoff = answer.query.cutoff
    future: list[str] = []
    valid = 0
    evidence_by_id = answer.evidence_index()
    for evidence in answer.evidence:
        chunk = chunks.get(evidence.chunk_id)
        if chunk is None:
            continue
        if parse_iso_date(chunk.published_at) > cutoff:
            future.append(evidence.id)
        else:
            valid += 1
    mismatches: list[str] = []
    for claim in answer.claims:
        dates = [
            parse_iso_date(chunks[evidence_by_id[item].chunk_id].published_at)
            for item in claim.evidence_ids
            if item in evidence_by_id and evidence_by_id[item].chunk_id in chunks
        ]
        if dates and (
            not claim.known_at
            or parse_iso_date(claim.known_at) != max(dates)
        ):
            mismatches.append(claim.id)
        if claim.known_at and parse_iso_date(claim.known_at) > cutoff:
            future.append(f"claim:{claim.id}")
    denominator = max(1, len(answer.evidence))
    valid_fraction = valid / denominator if answer.evidence else 1.0
    return TemporalAudit(
        compliant=not future and not mismatches,
        valid_fraction=valid_fraction,
        future_evidence_ids=tuple(future),
        known_at_mismatches=tuple(mismatches),
    )
