"""Configuration loading with explicit environment-variable boundaries."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Hy3Config:
    api_key: str
    base_url: str = "https://tokenhub.tencentmaas.com/v1"
    model: str = "hy3"
    reasoning_effort: str = "high"
    timeout_seconds: int = 120
    temperature: float = 0.0
    max_tokens: int = 10000

    @classmethod
    def from_env(cls, require_key: bool = True) -> "Hy3Config":
        key = os.environ.get("HY3_API_KEY", "").strip()
        if require_key and not key:
            raise RuntimeError("HY3_API_KEY is required; copy .env.example and export it at runtime")
        effort = os.environ.get("HY3_REASONING_EFFORT", "high").strip().lower()
        if effort not in {"high", "low", "no_think"}:
            raise ValueError("HY3_REASONING_EFFORT must be high, low, or no_think")
        return cls(
            api_key=key,
            base_url=os.environ.get("HY3_BASE_URL", "https://tokenhub.tencentmaas.com/v1").rstrip("/"),
            model=os.environ.get("HY3_MODEL", "hy3"),
            reasoning_effort=effort,
            timeout_seconds=int(os.environ.get("HY3_TIMEOUT_SECONDS", "120")),
            temperature=float(os.environ.get("HY3_TEMPERATURE", "0")),
            max_tokens=int(os.environ.get("HY3_MAX_TOKENS", "10000")),
        )


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 8
    chunk_chars: int = 1800
    overlap_chars: int = 240
    temporal_filter: bool = True
    metadata_boost: float = 1.25
