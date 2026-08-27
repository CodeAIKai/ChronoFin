#!/usr/bin/env python3
"""Replace raw provider request IDs in checked-in JSON with SHA-256 digests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def sanitize(value: Any) -> tuple[Any, int]:
    if isinstance(value, list):
        output = []
        changed = 0
        for item in value:
            sanitized, count = sanitize(item)
            output.append(sanitized)
            changed += count
        return output, changed
    if not isinstance(value, dict):
        return value, 0
    output: dict[str, Any] = {}
    changed = 0
    for key, item in value.items():
        if key == "request_id":
            if item:
                output["request_id_sha256"] = hashlib.sha256(str(item).encode("utf-8")).hexdigest()
            changed += 1
            continue
        sanitized, count = sanitize(item)
        output[key] = sanitized
        changed += count
    return output, changed


def main() -> None:
    files_changed = 0
    identifiers_removed = 0
    for path in sorted(RESULTS.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        sanitized, changed = sanitize(payload)
        if not changed:
            continue
        path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files_changed += 1
        identifiers_removed += changed
    print(json.dumps({
        "files_changed": files_changed,
        "raw_request_ids_removed": identifiers_removed,
        "replacement": "sha256",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
