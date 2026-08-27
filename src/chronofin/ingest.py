"""Document ingestion with publication-time metadata preserved end to end."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .models import Chunk, Document, ValidationError, ensure_unique


PAGE_MARKER = re.compile(r"^\s*<!--\s*page\s*:\s*(\d+)\s*-->\s*$", re.I | re.M)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
TABLE_HEADER = re.compile(
    r"(?:year|years|three months|six months) ended|as at|截至|年度|年止",
    re.I,
)
TABLE_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?%?\)?")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: str | Path, verify_hashes: bool = True) -> list[Document]:
    manifest_path = Path(path).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_documents = payload.get("documents", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_documents, list):
        raise ValidationError("manifest must be a list or an object with a documents list")
    documents = [Document.from_dict(item) for item in raw_documents]
    ensure_unique((item.id for item in documents), "document ids")
    for document in documents:
        source = document.resolved_path(manifest_path.parent)
        if not source.exists():
            raise FileNotFoundError(f"document not found: {source}")
        if verify_hashes and document.sha256:
            actual = sha256_file(source)
            if actual.lower() != document.sha256.lower():
                raise ValidationError(
                    f"sha256 mismatch for {document.id}: expected {document.sha256}, got {actual}"
                )
    return documents


def extract_pages(path: str | Path) -> list[str]:
    """Extract pages from PDF, Markdown, or UTF-8 text.

    For PDFs, PyMuPDF is preferred when installed. The widely available
    ``pdftotext`` binary is the dependency-free fallback. Page boundaries are
    retained because citations without a location are not auditable.
    """

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # type: ignore

            with fitz.open(source) as pdf:
                return [page.get_text("text") for page in pdf]
        except ImportError:
            executable = shutil.which("pdftotext")
            if not executable:
                raise RuntimeError("PDF input requires PyMuPDF or the pdftotext executable")
            completed = subprocess.run(
                [executable, "-layout", str(source), "-"],
                check=True,
                capture_output=True,
            )
            text = completed.stdout.decode("utf-8", errors="replace")
            pages = text.split("\f")
            if pages and not pages[-1].strip():
                pages.pop()
            return pages or [text]

    text = source.read_text(encoding="utf-8")
    if PAGE_MARKER.search(text):
        pages: list[str] = []
        matches = list(PAGE_MARKER.finditer(text))
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            explicit_page = int(match.group(1))
            while len(pages) < explicit_page - 1:
                pages.append("")
            pages.append(text[start:end].strip())
        return pages
    return text.split("\f")


def _paragraph_blocks(page_text: str) -> list[tuple[str, str]]:
    """Return ``(section, paragraph)`` blocks while carrying headings forward."""

    blocks: list[tuple[str, str]] = []
    section = ""
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            value = "\n".join(buffer).strip()
            if value:
                blocks.append((section, value))
            buffer.clear()

    for line in page_text.splitlines():
        heading = HEADING.match(line)
        if heading:
            flush()
            section = heading.group(1).strip()
        elif not line.strip():
            flush()
        else:
            buffer.append(line.rstrip())
    flush()
    return blocks


def _attach_table_context(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Attach a nearby table header to numeric rows split by PDF whitespace."""

    enriched: list[tuple[str, str]] = []
    table_context = ""
    for section, block in blocks:
        years = re.findall(r"(?:19|20)\d{2}", block)
        if TABLE_HEADER.search(block) and years:
            table_context = block
            enriched.append((section, block))
            continue
        numeric_count = len(TABLE_NUMBER.findall(block))
        looks_like_row = numeric_count >= 2 and len(block) <= 1800
        if table_context and looks_like_row:
            enriched.append((section, f"{table_context}\n{block}"))
        else:
            enriched.append((section, block))
            if table_context and len(block) > 240 and numeric_count < 2:
                table_context = ""
    return enriched


def _split_long_text(text: str, limit: int, overlap: int) -> Iterable[str]:
    if len(text) <= limit:
        yield text
        return
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            candidates = [text.rfind(mark, start + limit // 2, end) for mark in ("。", "；", "\n", ". ")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        yield text[start:end].strip()
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def chunk_document(document: Document, manifest_dir: Path, chunk_chars: int = 1800, overlap: int = 240) -> list[Chunk]:
    pages = extract_pages(document.resolved_path(manifest_dir))
    chunks: list[Chunk] = []
    sequence = 0
    for page_number, page in enumerate(pages, start=1):
        for section, block in _attach_table_context(_paragraph_blocks(page)):
            for piece in _split_long_text(block, chunk_chars, overlap):
                if not piece:
                    continue
                sequence += 1
                chunks.append(
                    Chunk(
                        id=f"{document.id}:p{page_number}:c{sequence}",
                        document_id=document.id,
                        text=piece,
                        page=page_number,
                        section=section,
                        entity=document.entity,
                        period=document.period,
                        published_at=document.published_at,
                        source_url=document.source_url,
                        currency=document.currency,
                        unit=document.unit,
                    )
                )
    if not chunks:
        raise ValidationError(f"no text chunks extracted from {document.id}")
    return chunks


def ingest_manifest(path: str | Path, chunk_chars: int = 1800, overlap: int = 240) -> tuple[list[Document], list[Chunk]]:
    manifest_path = Path(path).resolve()
    documents = load_manifest(manifest_path)
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, manifest_path.parent, chunk_chars, overlap))
    ensure_unique((item.id for item in chunks), "chunk ids")
    return documents, chunks
