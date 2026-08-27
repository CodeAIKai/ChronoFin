"""End-to-end point-in-time analysis pipeline."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Any

from .config import RetrievalConfig
from .ingest import ingest_manifest
from .llm import ChatCompletionsClient, LLMError
from .models import (
    AnalysisAnswer,
    Answerability,
    Calculation,
    Claim,
    ClaimType,
    Document,
    Evidence,
    Query,
    ValidationError,
    parse_iso_date,
)
from .prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION, build_user_prompt
from .ontology import canonical_semantic_key
from .projection import canonical_caveats, canonical_derived_claim_text, canonical_unknown_claim_text
from .retrieval import BM25Retriever, RetrievalAudit, detect_financial_slots
from .summary import canonical_executive_summary
from .evaluator.numeric import rounded_value_appears, safe_evaluate


class ChronoFinPipeline:
    def __init__(
        self,
        manifest_path: str | Path,
        client: ChatCompletionsClient,
        retrieval_config: RetrievalConfig | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path).resolve()
        self.client = client
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.documents, self.chunks = ingest_manifest(
            self.manifest_path,
            chunk_chars=self.retrieval_config.chunk_chars,
            overlap=self.retrieval_config.overlap_chars,
        )
        self.chunk_index = {chunk.id: chunk for chunk in self.chunks}
        self.retriever = BM25Retriever(self.chunks)

    def retrieve(self, query: Query) -> RetrievalAudit:
        return self.retriever.search(
            query,
            self.documents,
            top_k=self.retrieval_config.top_k,
            temporal_filter=self.retrieval_config.temporal_filter,
            metadata_boost=self.retrieval_config.metadata_boost,
        )

    def run(self, query: Query) -> AnalysisAnswer:
        audit = self.retrieve(query)
        if not audit.hits:
            requested_slots = set(detect_financial_slots(query.question)) - {"full_year"}
            placeholder_claim = Claim(
                id="C_UNKNOWN_NO_ELIGIBLE_EVIDENCE",
                text="",
                claim_type=ClaimType.UNKNOWN,
                entity=query.entity,
                period=query.requested_period,
                unit="",
                known_at="",
                confidence=0.1,
                semantic_key="",
            )
            summary = canonical_unknown_claim_text(placeholder_claim, query.as_of_date, requested_slots)
            return AnalysisAnswer(
                query=query,
                answerability=Answerability.UNANSWERABLE,
                executive_summary=summary,
                claims=[
                    replace(placeholder_claim, text=summary)
                ],
                caveats=canonical_caveats(),
                excluded_documents=list(audit.excluded_documents),
                provenance={
                    "prompt_version": SYSTEM_PROMPT_VERSION,
                    "temporal_filter": self.retrieval_config.temporal_filter,
                    "eligible_document_ids": list(audit.eligible_document_ids),
                    "retrieved_chunk_ids": [],
                    "model_called": False,
                    "no_hit_reason": "no eligible chunk remained after point-in-time retrieval",
                },
            )
        user_prompt = build_user_prompt(query, audit.hits)
        raw, trace = self.client.complete_json(SYSTEM_PROMPT, user_prompt)
        answer = self._bind_model_output(raw, query, audit)
        answer.provenance.update(
            {
                "prompt_version": SYSTEM_PROMPT_VERSION,
                "temporal_filter": self.retrieval_config.temporal_filter,
                "eligible_document_ids": list(audit.eligible_document_ids),
                "retrieved_chunk_ids": [hit.chunk.id for hit in audit.hits],
                "evidence_slot_hits": dict(audit.slot_hits),
                "uncovered_evidence_slots": list(audit.uncovered_slots),
                "retrieval_scores": [
                    {
                        "chunk_id": hit.chunk.id,
                        "score": round(hit.score, 6),
                        "lexical_score": round(hit.lexical_score, 6),
                        "metadata_score": round(hit.metadata_score, 6),
                    }
                    for hit in audit.hits
                ],
                "llm": trace.to_dict(),
                "model_called": True,
            }
        )
        return answer

    def _bind_model_output(self, raw: dict[str, Any], query: Query, audit: RetrievalAudit) -> AnalysisAnswer:
        """Rebind untrusted citations to the exact retrieved chunk registry."""

        allowed_chunks = {hit.chunk.id: hit.chunk for hit in audit.hits}
        warnings: list[str] = []
        citation_normalizations: list[dict[str, str]] = []
        bound_evidence: list[Evidence] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(raw.get("evidence", []), start=1):
            if not isinstance(item, dict):
                warnings.append(f"evidence item {index} was not an object")
                continue
            evidence_id = str(item.get("id", f"E{index}"))
            if evidence_id in seen_ids:
                warnings.append(f"duplicate evidence id ignored: {evidence_id}")
                continue
            seen_ids.add(evidence_id)
            chunk_id = str(item.get("chunk_id", ""))
            quote = str(item.get("quote", ""))
            chunk = allowed_chunks.get(chunk_id)
            if chunk is None and quote:
                exact_matches = [candidate for candidate in allowed_chunks.values() if quote in candidate.text]
                raw_document_id = str(item.get("document_id", ""))
                raw_page = item.get("page")
                narrowed = [
                    candidate for candidate in exact_matches
                    if (not raw_document_id or candidate.document_id == raw_document_id)
                    and (not raw_page or candidate.page == int(raw_page))
                ]
                matches = narrowed or exact_matches
                if len(matches) == 1:
                    chunk = matches[0]
                    warnings.append(f"stale chunk id rebound by unique exact quote: {chunk_id} -> {chunk.id}")
                    chunk_id = chunk.id
            if chunk is None:
                # Preserve the error as a sentinel citation so the evaluator can
                # identify and hard-gate it. Never accept model-supplied metadata.
                warnings.append(f"unknown or non-retrieved chunk id: {chunk_id}")
                bound_evidence.append(
                    Evidence(
                        id=evidence_id,
                        chunk_id=chunk_id or "__missing__",
                        document_id="__unknown__",
                        quote=quote,
                        page=1,
                        published_at=query.as_of_date,
                    )
                )
            else:
                expanded_quote = _expand_exact_quote(chunk.text, quote)
                if expanded_quote != quote:
                    citation_normalizations.append({
                        "evidence_id": evidence_id,
                        "original_quote": quote,
                        "expanded_quote": expanded_quote,
                    })
                quote = expanded_quote
                bound_evidence.append(
                    Evidence(
                        id=evidence_id,
                        chunk_id=chunk.id,
                        document_id=chunk.document_id,
                        quote=quote,
                        page=chunk.page,
                        published_at=chunk.published_at,
                        source_url=chunk.source_url,
                    )
                )

        evidence_index = {item.id: item for item in bound_evidence}
        raw_calculations = raw.get("calculations", [])
        calculations: list[Calculation] = []
        calculation_corrections: list[dict[str, Any]] = []
        for item in raw_calculations if isinstance(raw_calculations, list) else []:
            try:
                calculation = Calculation.from_dict(item)
                actual = safe_evaluate(
                    calculation.expression,
                    {operand.name: operand.value for operand in calculation.operands},
                )
                if abs(actual - calculation.result) > 1e-6 * max(1.0, abs(actual)):
                    calculation_corrections.append({
                        "calculation_id": calculation.id,
                        "model_result": calculation.result,
                        "executed_result": actual,
                    })
                    calculation = replace(calculation, result=actual)
                calculations.append(calculation)
            except ValidationError as exc:
                warnings.append(str(exc))
            except (ValueError, ZeroDivisionError, OverflowError) as exc:
                warnings.append(f"calculation execution failed: {exc}")

        # Infer an explicit calculation-to-calculation edge when an operand is
        # exactly the result of an earlier step. Evidence remains on the leaf.
        enriched_calculations: list[Calculation] = []
        prior: list[Calculation] = []
        for calculation in calculations:
            operands = []
            for operand in calculation.operands:
                upstream = list(operand.calculation_ids)
                if not upstream:
                    upstream = [
                        item.id for item in prior
                        if abs(item.result - operand.value) <= 1e-6 * max(1.0, abs(item.result))
                    ]
                operands.append(replace(operand, calculation_ids=tuple(upstream)))
            calculation = replace(calculation, operands=tuple(operands))
            enriched_calculations.append(calculation)
            prior.append(calculation)
        calculations = enriched_calculations

        claims: list[Claim] = []
        claim_text_corrections: list[dict[str, Any]] = []
        raw_claims = raw.get("claims", [])
        for item in raw_claims if isinstance(raw_claims, list) else []:
            if not isinstance(item, dict):
                warnings.append("non-object claim ignored")
                continue
            normalized = dict(item)
            cited_dates = [
                parse_iso_date(evidence_index[evidence_id].published_at)
                for evidence_id in normalized.get("evidence_ids", [])
                if evidence_id in evidence_index
            ]
            # known_at is derived from registered sources, never trusted from the model.
            normalized["known_at"] = max(cited_dates).isoformat() if cited_dates else ""
            try:
                claim = Claim.from_dict(normalized)
                calculation_index = {item.id: item for item in calculations}
                if claim.claim_type.value == "DERIVED" and claim.calculation_id in calculation_index:
                    executed_value = calculation_index[claim.calculation_id].result
                    corrected_text = claim.text
                    for correction in calculation_corrections:
                        if correction["calculation_id"] == claim.calculation_id:
                            corrected_text = _replace_rendered_number(
                                corrected_text,
                                float(correction["model_result"]),
                                float(correction["executed_result"]),
                            )
                    if not rounded_value_appears(executed_value, corrected_text):
                        corrected_text = _synchronize_derived_claim_text(
                            corrected_text, executed_value, calculation_index[claim.calculation_id].unit
                        )
                    if corrected_text != claim.text:
                        claim_text_corrections.append({
                            "claim_id": claim.id,
                            "calculation_id": claim.calculation_id,
                            "original_text": claim.text,
                            "corrected_text": corrected_text,
                        })
                    claim = replace(claim, text=corrected_text, value=executed_value)
                claim = replace(claim, semantic_key=canonical_semantic_key(claim))
                projected_text = claim.text
                projection_kind = "model_text"
                if claim.claim_type == ClaimType.FACT:
                    exact_quotes = [
                        evidence_index[evidence_id].quote
                        for evidence_id in claim.evidence_ids
                        if evidence_id in evidence_index and evidence_index[evidence_id].quote.strip()
                    ]
                    if exact_quotes:
                        projected_text = "；".join(exact_quotes)
                        projection_kind = "exact_evidence_projection"
                elif claim.claim_type == ClaimType.DERIVED and claim.calculation_id in calculation_index:
                    projected_text = canonical_derived_claim_text(
                        claim,
                        calculation_index[claim.calculation_id],
                    )
                    projection_kind = "executed_calculation_projection"
                elif claim.claim_type == ClaimType.UNKNOWN:
                    requested_slots = set(detect_financial_slots(query.question)) - {"full_year"}
                    projected_text = canonical_unknown_claim_text(
                        claim,
                        query.as_of_date,
                        requested_slots,
                    )
                    projection_kind = "epistemic_unknown_projection"
                if projected_text != claim.text:
                    claim_text_corrections.append({
                        "claim_id": claim.id,
                        "calculation_id": claim.calculation_id,
                        "original_text": claim.text,
                        "corrected_text": projected_text,
                        "projection_kind": projection_kind,
                    })
                    claim = replace(claim, text=projected_text)
                claims.append(claim)
            except ValidationError as exc:
                warnings.append(str(exc))

        try:
            answerability = Answerability(str(raw.get("answerability", "unanswerable")).lower())
        except ValueError:
            warnings.append(f"invalid answerability: {raw.get('answerability')!r}")
            answerability = Answerability.PARTIAL
        model_caveats = raw.get("caveats", [])
        if not isinstance(model_caveats, list):
            model_caveats = [str(model_caveats)]
        caveats = canonical_caveats()
        model_executive_summary = str(raw.get("executive_summary", ""))
        for correction in calculation_corrections:
            old = float(correction["model_result"])
            new = float(correction["executed_result"])
            model_executive_summary = _replace_rendered_number(model_executive_summary, old, new)
        # The headline is a deterministic projection of audited claims. The
        # model-authored version is retained only as a digest so unsupported
        # prose cannot bypass the claim/evidence ledger or leak through public
        # artifacts.
        executive_summary = canonical_executive_summary(claims)
        return AnalysisAnswer(
            query=query,
            answerability=answerability,
            executive_summary=executive_summary,
            claims=claims,
            evidence=bound_evidence,
            calculations=calculations,
            caveats=list(map(str, caveats)),
            excluded_documents=list(audit.excluded_documents),
            provenance={
                "schema_warnings": warnings,
                "calculation_corrections": calculation_corrections,
                "claim_text_corrections": claim_text_corrections,
                "citation_normalizations": citation_normalizations,
                "executive_summary_mode": "deterministic_claim_projection_v1",
                "model_executive_summary_sha256": hashlib.sha256(
                    model_executive_summary.encode("utf-8")
                ).hexdigest(),
                "caveat_mode": "deterministic_policy_projection_v1",
                "model_caveats_sha256": hashlib.sha256(
                    "\n".join(map(str, model_caveats)).encode("utf-8")
                ).hexdigest(),
            },
        )


def chunk_registry(pipeline: ChronoFinPipeline) -> dict[str, Any]:
    return pipeline.chunk_index


def _replace_rendered_number(text: str, old: float, new: float) -> str:
    """Replace only explicit renderings of an audited calculation result."""

    updated = text
    for decimals in range(8, 0, -1):
        updated = updated.replace(f"{old:.{decimals}f}", f"{new:.{decimals}f}")
    if float(old).is_integer():
        updated = updated.replace(f"{old:,.0f}", f"{new:,.0f}")
    return updated


def _synchronize_derived_claim_text(text: str, value: float, unit: str) -> str:
    """Replace an unambiguous displayed result while preserving its precision.

    Only a rightmost number explicitly followed by a ratio unit, or a number in
    the final ``=`` clause, is eligible. Ambiguous prose is left untouched and
    will fail the evaluator's claim-text gate instead of being guessed.
    """

    unit_pattern = ""
    if unit in {"%", "％"}:
        unit_pattern = r"(?=\s*[%％])"
    elif unit in {"倍", "百分点"}:
        unit_pattern = rf"(?=\s*{re.escape(unit)})"
    matches = list(re.finditer(r"-?\d[\d,]*(?:\.\d+)?" + unit_pattern, text)) if unit_pattern else []
    if not matches and "=" in text:
        tail_start = text.rfind("=") + 1
        matches = list(re.finditer(r"-?\d[\d,]*(?:\.\d+)?", text[tail_start:]))
        if matches:
            match = matches[-1]
            start, end = tail_start + match.start(), tail_start + match.end()
        else:
            return text
    elif matches:
        start, end = matches[-1].span()
    else:
        return text
    token = text[start:end]
    normalized = token.replace(",", "")
    decimals = len(normalized.rsplit(".", 1)[1]) if "." in normalized else 0
    rendered = f"{value:,.{decimals}f}" if "," in token else f"{value:.{decimals}f}"
    return text[:start] + rendered + text[end:]


def _expand_exact_quote(source: str, quote: str, context_lines: int = 3) -> str:
    """Expand a bare numeric/model-fragment quote without changing its source.

    The returned text is always an exact contiguous substring. This is useful
    for PDF tables where a model cites only ``751,766`` and omits the row label.
    Non-exact quotes are left untouched so forged citations remain detectable.
    """

    if not quote.strip():
        return quote
    start = source.find(quote)
    if start < 0:
        return quote
    end = start + len(quote)
    starts_at_line_boundary = start == 0 or source[start - 1] == "\n"
    ends_at_line_boundary = end == len(source) or source[end] == "\n"
    # A long quote can still be semantically incomplete when it starts halfway
    # through a sentence, e.g. "RMB224.8 billion ... 2025" without the metric
    # name immediately before it. Only skip expansion for complete source lines.
    if (
        len(quote.strip()) >= 48
        and re.search(r"(?:19|20)\d{2}|FY\s*\d{4}", quote, re.I)
        and starts_at_line_boundary
        and ends_at_line_boundary
    ):
        return quote
    line_starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            line_starts.append(index + 1)
    line_index = max(index for index, value in enumerate(line_starts) if value <= start)
    first_line = max(0, line_index - context_lines)
    last_line = min(len(line_starts) - 1, line_index + context_lines)
    expanded_start = line_starts[first_line]
    if last_line + 1 < len(line_starts):
        expanded_end = line_starts[last_line + 1] - 1
    else:
        expanded_end = len(source)
    return source[expanded_start:expanded_end].strip("\n")
