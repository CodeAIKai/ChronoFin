"""Typed domain objects and strict, dependency-free validation.

The LLM is never the authority for source time, entity, page, or publication
metadata. Those fields are rebound from the local document registry after
generation. This is a small but important trust-boundary decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ValidationError(ValueError):
    """Raised when an external or model-produced object violates the schema."""


class ClaimType(str, Enum):
    FACT = "FACT"
    DERIVED = "DERIVED"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class Answerability(str, Enum):
    ANSWERABLE = "answerable"
    PARTIAL = "partial"
    UNANSWERABLE = "unanswerable"


def parse_iso_date(value: str | date, field_name: str = "date") -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be ISO YYYY-MM-DD: {value!r}") from exc


@dataclass(frozen=True)
class Query:
    question: str
    as_of_date: str
    entity: str = ""
    requested_period: str = ""
    language: str = "zh-CN"

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValidationError("question cannot be empty")
        parse_iso_date(self.as_of_date, "as_of_date")
        if not self.entity.strip():
            raise ValidationError("entity is required for an auditable financial query")
        if not self.requested_period.strip():
            raise ValidationError("requested_period is required for an auditable financial query")

    @property
    def cutoff(self) -> date:
        return parse_iso_date(self.as_of_date)


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    entity: str
    published_at: str
    period: str
    path: str
    source_url: str = ""
    source_type: str = "official_filing"
    sha256: str = ""
    currency: str = ""
    unit: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.path:
            raise ValidationError("document id and path are required")
        parse_iso_date(self.published_at, "published_at")

    @property
    def publication_date(self) -> date:
        return parse_iso_date(self.published_at)

    def is_known_by(self, cutoff: date | str) -> bool:
        return self.publication_date <= parse_iso_date(cutoff)

    def resolved_path(self, base_dir: Path) -> Path:
        candidate = Path(self.path)
        return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Document":
        known = {
            "id", "title", "entity", "published_at", "period", "path",
            "source_url", "source_type", "sha256", "currency", "unit",
        }
        data = {key: value.get(key, "") for key in known}
        data["metadata"] = {key: val for key, val in value.items() if key not in known}
        return cls(**data)


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    text: str
    page: int
    section: str
    entity: str
    period: str
    published_at: str
    source_url: str = ""
    currency: str = ""
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.document_id or not self.text.strip():
            raise ValidationError("chunk id, document_id and text are required")
        if self.page < 1:
            raise ValidationError("page must be >= 1")
        parse_iso_date(self.published_at, "chunk.published_at")


@dataclass(frozen=True)
class Evidence:
    id: str
    chunk_id: str
    document_id: str
    quote: str
    page: int
    published_at: str
    source_url: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Evidence":
        try:
            return cls(
                id=str(value["id"]),
                chunk_id=str(value["chunk_id"]),
                document_id=str(value["document_id"]),
                quote=str(value["quote"]),
                page=int(value["page"]),
                published_at=str(value["published_at"]),
                source_url=str(value.get("source_url", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"invalid evidence: {value!r}") from exc


@dataclass(frozen=True)
class Operand:
    name: str
    value: float
    unit: str
    evidence_ids: tuple[str, ...]
    calculation_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Operand":
        try:
            evidence_ids = tuple(str(item) for item in value.get("evidence_ids", []))
            return cls(
                name=str(value["name"]),
                value=float(value["value"]),
                unit=str(value.get("unit", "")),
                evidence_ids=evidence_ids,
                calculation_ids=tuple(str(item) for item in value.get("calculation_ids", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"invalid operand: {value!r}") from exc


@dataclass(frozen=True)
class Calculation:
    id: str
    expression: str
    result: float
    unit: str
    operands: tuple[Operand, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Calculation":
        try:
            return cls(
                id=str(value["id"]),
                expression=str(value["expression"]),
                result=float(value["result"]),
                unit=str(value.get("unit", "")),
                operands=tuple(Operand.from_dict(item) for item in value.get("operands", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"invalid calculation: {value!r}") from exc


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    claim_type: ClaimType
    entity: str
    period: str
    unit: str
    known_at: str
    value: float | None = None
    evidence_ids: tuple[str, ...] = ()
    calculation_id: str = ""
    confidence: float = 0.0
    semantic_key: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Claim":
        try:
            claim_type = ClaimType(str(value.get("claim_type", value.get("type", "UNKNOWN"))).upper())
            confidence = float(value.get("confidence", 0.0))
            if not 0.0 <= confidence <= 1.0:
                raise ValidationError("claim confidence must be between 0 and 1")
            known_at = str(value.get("known_at", ""))
            if known_at:
                parse_iso_date(known_at, "claim.known_at")
            return cls(
                id=str(value["id"]),
                text=str(value["text"]),
                claim_type=claim_type,
                entity=str(value.get("entity", "")),
                period=str(value.get("period", "")),
                unit=str(value.get("unit", "")),
                known_at=known_at,
                value=float(value["value"]) if value.get("value") is not None else None,
                evidence_ids=tuple(str(item) for item in value.get("evidence_ids", [])),
                calculation_id=str(value.get("calculation_id", "")),
                confidence=confidence,
                semantic_key=str(value.get("semantic_key", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"invalid claim: {value!r}") from exc


@dataclass
class AnalysisAnswer:
    query: Query
    answerability: Answerability
    executive_summary: str
    claims: list[Claim] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    calculations: list[Calculation] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    excluded_documents: list[dict[str, str]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any], query: Query | None = None) -> "AnalysisAnswer":
        if query is None:
            query = Query(**value["query"])
        try:
            return cls(
                query=query,
                answerability=Answerability(str(value.get("answerability", "unanswerable")).lower()),
                executive_summary=str(value.get("executive_summary", "")),
                claims=[Claim.from_dict(item) for item in value.get("claims", [])],
                evidence=[Evidence.from_dict(item) for item in value.get("evidence", [])],
                calculations=[Calculation.from_dict(item) for item in value.get("calculations", [])],
                caveats=[str(item) for item in value.get("caveats", [])],
                excluded_documents=list(value.get("excluded_documents", [])),
                provenance=dict(value.get("provenance", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"invalid analysis answer: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        def normalize(value: Any) -> Any:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, tuple):
                return [normalize(item) for item in value]
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            return value

        return normalize(asdict(self))

    def evidence_index(self) -> dict[str, Evidence]:
        return {item.id: item for item in self.evidence}

    def calculation_index(self) -> dict[str, Calculation]:
        return {item.id: item for item in self.calculations}


def ensure_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValidationError(f"duplicate {label}: {sorted(duplicates)}")
