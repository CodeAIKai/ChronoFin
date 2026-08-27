"""Canonical source-tree fingerprint shared by cleanroom and submission checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping


IGNORED_NAMES = frozenset({
    ".git", ".env", ".pytest_cache", ".venv", "__pycache__",
    "chronofin.egg-info", "cache", "htmlcov",
})
FINGERPRINT_EXCLUDED_PATHS = frozenset({"results/cleanroom_verification.json"})

_TEMPORARY_PATH_PATTERNS = (
    re.compile(r"[/\\]chronofin-cleanroom-[A-Za-z0-9_.-]+(?:[/\\]|$)"),
    re.compile(r"(?<![A-Za-z0-9_])(?:/private)?/tmp/[^\s\"'<>]+"),
)
_SAFE_LOCATION_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def tree_fingerprint(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if relative.as_posix() in FINGERPRINT_EXCLUDED_PATHS:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def canonicalize_temporary_paths(text: str, replacement: str = "<TEMP_PATH>") -> str:
    """Replace host-specific temporary paths in reproducibility logs.

    The replacement intentionally contains angle brackets, which terminate the
    path patterns and therefore cannot be mistaken for another leaked path.
    """
    output = text
    for pattern in _TEMPORARY_PATH_PATTERNS:
        output = pattern.sub(replacement, output)
    return output


def temporary_path_leak_locations(value: Any) -> tuple[str, ...]:
    """Return structural locations containing non-canonical temporary paths.

    Locations, rather than matching values, are returned so a failed verifier
    never copies a host-specific path into its own output.
    """
    findings: list[str] = []

    def has_leak(text: str) -> bool:
        return any(pattern.search(text) for pattern in _TEMPORARY_PATH_PATTERNS)

    def walk(current: Any, location: str) -> None:
        if isinstance(current, str):
            if has_leak(current):
                findings.append(location)
            return
        if isinstance(current, Mapping):
            for index, (key, nested) in enumerate(current.items()):
                key_text = str(key)
                if has_leak(key_text):
                    findings.append(f"{location}.<key:{index}>")
                if _SAFE_LOCATION_KEY.fullmatch(key_text) and not has_leak(key_text):
                    child_location = f"{location}.{key_text}"
                else:
                    child_location = f"{location}[{index}]"
                walk(nested, child_location)
            return
        if isinstance(current, (list, tuple)):
            for index, nested in enumerate(current):
                walk(nested, f"{location}[{index}]")

    walk(value, "$")
    return tuple(findings)
