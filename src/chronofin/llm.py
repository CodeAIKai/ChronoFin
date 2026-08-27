"""Minimal OpenAI-compatible client for TokenHub Hy3.

Only the standard library is used. Secrets are never serialized into traces.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import Hy3Config


JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.I | re.S)


class LLMError(RuntimeError):
    pass


def parse_json_object(text: str) -> dict[str, Any]:
    match = JSON_FENCE.match(text)
    if match:
        text = match.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("model response did not contain a JSON object")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON response: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("model response must be a JSON object")
    return value


@dataclass
class LLMTrace:
    model: str
    base_url: str
    prompt_hash: str
    latency_seconds: float
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    attempts: int = 1
    reasoning_effort: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "base_url": self.base_url,
            "prompt_hash": self.prompt_hash,
            "latency_seconds": round(self.latency_seconds, 3),
            "usage": self.usage,
            "attempts": self.attempts,
            "reasoning_effort": self.reasoning_effort,
        }
        if self.request_id:
            payload["request_id_sha256"] = hashlib.sha256(self.request_id.encode("utf-8")).hexdigest()
        return payload


class ChatCompletionsClient:
    def __init__(self, config: Hy3Config, max_attempts: int = 4) -> None:
        self.config = config
        self.max_attempts = max_attempts

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], LLMTrace]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        endpoint = f"{self.config.base_url}/chat/completions"
        prompt_hash = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                endpoint,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "ChronoFin/0.1",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    choice = body["choices"][0]
                    content = choice["message"]["content"]
                    try:
                        result = parse_json_object(content)
                    except LLMError as exc:
                        raise LLMError(
                            f"{exc}; finish_reason={choice.get('finish_reason', '')}; content_chars={len(content or '')}"
                        ) from exc
                    trace = LLMTrace(
                        model=self.config.model,
                        base_url=self.config.base_url,
                        prompt_hash=prompt_hash,
                        latency_seconds=time.monotonic() - started,
                        usage=dict(body.get("usage", {})),
                        request_id=str(body.get("id", response.headers.get("x-request-id", ""))),
                        attempts=attempt,
                        reasoning_effort=self.config.reasoning_effort,
                    )
                    return result, trace
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = LLMError(f"Hy3 HTTP {exc.code}: {body[:500]}")
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    break
            except LLMError as exc:
                # Some OpenAI-compatible gateways may occasionally return a
                # truncated JSON string even with response_format enabled.
                # Retrying is safer than attempting a lossy local repair.
                last_error = exc
            except (urllib.error.URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                delay = min(8.0, 0.75 * 2 ** (attempt - 1)) + random.random() * 0.25
                time.sleep(delay)
        raise LLMError(f"Hy3 request failed after {self.max_attempts} attempts: {last_error}")
