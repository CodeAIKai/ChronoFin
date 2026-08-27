"""Auditable BM25 retrieval with a hard publication-time boundary."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .models import Chunk, Document, Query, parse_iso_date


LATIN_OR_NUMBER = re.compile(r"[a-zA-Z]+(?:[-_][a-zA-Z]+)*|\d+(?:[.,]\d+)*%?")
CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese financial text without an external segmenter."""

    lowered = text.lower()
    tokens = LATIN_OR_NUMBER.findall(lowered)
    for run in CJK_RUN.findall(lowered):
        chars = list(run)
        tokens.extend(chars)
        tokens.extend("".join(chars[index:index + 2]) for index in range(len(chars) - 1))
    return tokens


@dataclass(frozen=True)
class RetrievalHit:
    chunk: Chunk
    score: float
    lexical_score: float
    metadata_score: float

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk.id,
            "document_id": self.chunk.document_id,
            "page": self.chunk.page,
            "section": self.chunk.section,
            "entity": self.chunk.entity,
            "period": self.chunk.period,
            "published_at": self.chunk.published_at,
            "currency": self.chunk.currency,
            "unit": self.chunk.unit,
            "text": self.chunk.text,
        }


@dataclass(frozen=True)
class RetrievalAudit:
    hits: tuple[RetrievalHit, ...]
    eligible_document_ids: tuple[str, ...]
    excluded_documents: tuple[dict[str, str], ...]
    slot_hits: tuple[tuple[str, str], ...] = ()
    uncovered_slots: tuple[str, ...] = ()


FINANCIAL_SLOT_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenues", "revenue", "net sales", "total revenue", "营业收入", "营收"),
    "profit_attributable": (
        "profit attributable to equity holders", "profit attributable",
        "profit_attributable", "归属于股东的净利润", "归母净利润",
    ),
    "net_profit": (
        "net profit", "net_profit", "net income", "net_income",
        "gaap net income", "gaap_net_income", "净利润",
    ),
    "profit_margin": (
        "profit margin", "net margin", "net_margin", "profit_margin",
        "net income margin", "net_income_margin", "gaap net income margin",
        "gaap_net_income_margin", "净利率",
    ),
    "non_ifrs": ("non-ifrs", "non ifrs", "非国际财务报告准则", "非ifrs"),
    "full_year": ("year ended 31 december", "full-year", "full year", "全年", "财年"),
    "risk": ("risk", "风险"),
    "driver": ("driver", "driven", "主要驱动", "驱动因素"),
    "revenue_growth": ("revenue growth", "revenue_growth", "同比增速", "收入增长率"),
    "current_assets": ("current assets", "current_assets", "流动资产"),
    "current_liabilities": ("current liabilities", "current_liabilities", "流动负债"),
    "current_ratio": ("current ratio", "current_ratio", "流动比率"),
}
MATERIAL_NUMBER = re.compile(r"(?:RMB|USD|CNY|HKD)?\s*\d{3,}(?:,\d{3})*(?:\.\d+)?", re.I)


def detect_financial_slots(question: str) -> dict[str, tuple[str, ...]]:
    lowered = question.lower()
    detected: dict[str, tuple[str, ...]] = {}
    for name, aliases in FINANCIAL_SLOT_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            detected[name] = aliases
    # A request for margin requires both numerator and denominator even when
    # the user does not repeat their names.
    if any(marker in lowered for marker in ("profit margin", "net margin", "净利率")):
        detected.setdefault("revenue", FINANCIAL_SLOT_ALIASES["revenue"])
        # A margin needs a numerator, but an explicitly requested attributable
        # profit is already that numerator. Requiring both attributable profit
        # and generic net profit creates a duplicate, unsatisfiable slot.
        if "profit_attributable" not in detected and "net_profit" not in detected:
            detected["net_profit"] = FINANCIAL_SLOT_ALIASES["net_profit"]
    if any(marker in lowered for marker in ("current ratio", "current_ratio", "流动比率")):
        detected.setdefault("current_assets", FINANCIAL_SLOT_ALIASES["current_assets"])
        detected.setdefault("current_liabilities", FINANCIAL_SLOT_ALIASES["current_liabilities"])
    return detected


def _slot_priority(slot: str, hit: RetrievalHit, query: Query) -> tuple[float, float, str]:
    text = hit.chunk.text.lower()
    bonus = 0.0
    if hit.chunk.period and query.requested_period and hit.chunk.period.lower() == query.requested_period.lower():
        bonus += 12.0
    if slot in {"revenue", "profit_attributable", "net_profit", "non_ifrs"}:
        bonus += 10.0 if MATERIAL_NUMBER.search(text) else -10.0
    if slot == "revenue":
        if re.search(r"(?im)^\s*revenues?\s+\(?\d", hit.chunk.text):
            bonus += 24.0
        elif re.search(r"(?i)\brevenues?\s+(?:increased|decreased|was|were|of)\b", hit.chunk.text):
            bonus += 9.0
        if "revenue streams" in text and not re.search(r"(?im)^\s*revenues?\s+\(?\d", hit.chunk.text):
            bonus -= 9.0
    if slot == "profit_attributable" and re.search(
        r"(?i)profit attributable to equity holders.{0,80}(?:RMB\s*)?\d", hit.chunk.text.replace("\n", " ")
    ):
        bonus += 12.0
    if query.requested_period.lower().startswith("fy"):
        year_match = re.search(r"(?:19|20)\d{2}", query.requested_period)
        year = year_match.group(0) if year_match else ""
        if "year ended 31 december" in text or (year and f"year ended 31 december {year}" in text):
            bonus += 8.0
        if any(marker in text for marker in ("quarter", "three months", "季度")) and "year ended" not in text:
            bonus -= 7.0
    return (hit.score + bonus, hit.score, hit.chunk.id)


def _matches_requested_period(hit: RetrievalHit, query: Query) -> bool:
    """Return whether a slot candidate belongs to the requested period.

    Slot coverage is a sufficiency assertion, not merely a relevance hint. A
    FY2024 row or an H1 2025 warning may be useful context for an FY2025 query,
    but neither can satisfy the FY2025 full-year revenue/profit slot.
    """

    if not query.requested_period:
        return True
    normalized_target = re.sub(r"[^a-z0-9]", "", query.requested_period.lower())
    normalized_source = re.sub(r"[^a-z0-9]", "", hit.chunk.period.lower())
    return bool(normalized_source) and normalized_source == normalized_target


class BM25Retriever:
    def __init__(self, chunks: Iterable[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._tokens = [tokenize(chunk.text) for chunk in self.chunks]
        self._term_frequencies = [Counter(tokens) for tokens in self._tokens]
        self._doc_frequency: Counter[str] = Counter()
        for tokens in self._tokens:
            self._doc_frequency.update(set(tokens))
        self._average_length = sum(map(len, self._tokens)) / max(1, len(self._tokens))

    def _idf(self, term: str, population: int) -> float:
        count = self._doc_frequency.get(term, 0)
        return math.log(1.0 + (population - count + 0.5) / (count + 0.5))

    def _lexical_score(self, query_tokens: list[str], index: int) -> float:
        frequencies = self._term_frequencies[index]
        doc_length = len(self._tokens[index])
        score = 0.0
        for term in set(query_tokens):
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (
                1.0 - self.b + self.b * doc_length / max(1.0, self._average_length)
            )
            score += self._idf(term, len(self.chunks)) * frequency * (self.k1 + 1.0) / denominator
        return score

    @staticmethod
    def _metadata_score(query: Query, chunk: Chunk) -> float:
        score = 0.0
        lowered_question = query.question.lower()
        if query.entity and query.entity.lower() == chunk.entity.lower():
            score += 1.5
        elif chunk.entity and chunk.entity.lower() in lowered_question:
            score += 1.0
        if query.requested_period and query.requested_period.lower() == chunk.period.lower():
            score += 1.25
        elif chunk.period and chunk.period.lower() in lowered_question:
            score += 0.75
        return score

    def search(
        self,
        query: Query,
        documents: Iterable[Document],
        top_k: int = 8,
        temporal_filter: bool = True,
        metadata_boost: float = 1.25,
    ) -> RetrievalAudit:
        document_index = {document.id: document for document in documents}
        cutoff = query.cutoff
        eligible = {
            document.id
            for document in document_index.values()
            if not temporal_filter or document.is_known_by(cutoff)
        }
        excluded = tuple(
            {
                "document_id": document.id,
                "title": document.title,
                "published_at": document.published_at,
                "reason": f"published after cutoff {query.as_of_date}",
            }
            for document in document_index.values()
            if temporal_filter and document.id not in eligible
        )
        query_tokens = tokenize(" ".join(filter(None, [query.question, query.entity, query.requested_period])))
        candidates: list[RetrievalHit] = []
        for index, chunk in enumerate(self.chunks):
            if chunk.document_id not in eligible:
                continue
            lexical = self._lexical_score(query_tokens, index)
            metadata = self._metadata_score(query, chunk)
            candidates.append(
                RetrievalHit(
                    chunk=chunk,
                    score=lexical + metadata_boost * metadata,
                    lexical_score=lexical,
                    metadata_score=metadata,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.chunk.id))
        slots = detect_financial_slots(query.question)
        selected: list[RetrievalHit] = []
        selected_ids: set[str] = set()
        slot_hits: list[tuple[str, str]] = []
        uncovered: list[str] = []
        for slot, aliases in slots.items():
            matching = [
                hit for hit in candidates
                if any(alias in hit.chunk.text.lower() for alias in aliases)
                and _matches_requested_period(hit, query)
            ]
            if not matching:
                uncovered.append(slot)
                continue
            best = max(matching, key=lambda item: _slot_priority(slot, item, query))
            slot_hits.append((slot, best.chunk.id))
            if best.chunk.id not in selected_ids and len(selected) < top_k:
                selected.append(best)
                selected_ids.add(best.chunk.id)
        for hit in candidates:
            if len(selected) >= top_k:
                break
            if hit.chunk.id not in selected_ids:
                selected.append(hit)
                selected_ids.add(hit.chunk.id)
        return RetrievalAudit(
            hits=tuple(selected),
            eligible_document_ids=tuple(sorted(eligible)),
            excluded_documents=excluded,
            slot_hits=tuple(slot_hits),
            uncovered_slots=tuple(uncovered),
        )


def future_leak_count(hits: Iterable[RetrievalHit], cutoff: str | date) -> int:
    boundary = parse_iso_date(cutoff)
    return sum(parse_iso_date(hit.chunk.published_at) > boundary for hit in hits)
