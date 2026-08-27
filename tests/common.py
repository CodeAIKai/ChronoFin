from __future__ import annotations

from pathlib import Path

from chronofin.ingest import ingest_manifest
from chronofin.render import load_answer


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "demo" / "manifest.json"
GOOD = ROOT / "data" / "demo" / "fixtures" / "good.json"


def good_answer():
    return load_answer(GOOD)


def corpus():
    documents, chunks = ingest_manifest(MANIFEST)
    return documents, {chunk.id: chunk for chunk in chunks}

