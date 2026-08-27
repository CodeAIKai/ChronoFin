#!/usr/bin/env python3
"""Download official reports and require their pre-registered byte identity."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronofin.ingest import sha256_file


SOURCES = ROOT / "data" / "public" / "tencent_sources.json"
CACHE = ROOT / "data" / "cache" / "tencent"


def validate_snapshot(path: Path, item: dict[str, object]) -> tuple[str, int]:
    """Fail closed if a cached/downloaded file differs from the reviewed snapshot."""

    expected_hash = str(item.get("expected_sha256", "")).lower()
    try:
        expected_bytes = int(item["expected_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{item.get('id', '<unknown>')}: expected_bytes is required") from exc
    if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise RuntimeError(f"{item.get('id', '<unknown>')}: a valid expected_sha256 is required")
    actual_bytes = path.stat().st_size
    actual_hash = sha256_file(path)
    if actual_bytes != expected_bytes or actual_hash != expected_hash:
        raise RuntimeError(
            f"snapshot identity mismatch for {item.get('id', '<unknown>')}: "
            f"expected bytes={expected_bytes}, sha256={expected_hash}; "
            f"got bytes={actual_bytes}, sha256={actual_hash}. "
            "Do not silently accept an upstream replacement; verify the new filing and version the registry explicitly."
        )
    return actual_hash, actual_bytes


def download(item: dict[str, object], target: Path) -> None:
    url = str(item["source_url"])
    request = urllib.request.Request(url, headers={"User-Agent": "ChronoFin research demo / contact repository owner"})
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower():
                raise RuntimeError(f"expected a PDF from {url}, got {content_type}")
            while block := response.read(1024 * 1024):
                output.write(block)
        validate_snapshot(temporary, item)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    source_payload = json.loads(SOURCES.read_text(encoding="utf-8"))
    manifest_documents = []
    for item in source_payload["documents"]:
        target = CACHE / item["filename"]
        if not target.exists():
            print(f"downloading {item['id']} …", file=sys.stderr)
            download(item, target)
        actual_hash, actual_bytes = validate_snapshot(target, item)
        document = {
            key: value for key, value in item.items()
            if key not in {"filename", "expected_sha256", "expected_bytes"}
        }
        document["path"] = item["filename"]
        document["sha256"] = actual_hash
        document["bytes"] = actual_bytes
        manifest_documents.append(document)
    manifest = {
        "dataset": source_payload["dataset"],
        "landing_page": source_payload["landing_page"],
        "generated_from": str(SOURCES.relative_to(ROOT)),
        "documents": manifest_documents,
    }
    manifest_path = CACHE / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "documents": [{"id": item["id"], "bytes": item["bytes"], "sha256": item["sha256"]} for item in manifest_documents],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
