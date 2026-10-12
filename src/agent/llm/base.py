"""Common interface for LLM providers (Gemini, Groq, ...) so the agent does not depend on a single one.

Neutral message format (each provider translates it to its own):
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [ToolCall], "raw": <provider-native object or None>}
    {"role": "tool", "results": [{"call": ToolCall, "output": dict}]}
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("agent")

MAX_USEFUL_WAIT_S = 120  # if the provider asks to wait longer (daily quota), retrying is pointless


class QuotaExhausted(RuntimeError):
    """Free-plan quota exhausted; retrying will not help until it is released."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments object


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # native content to send back unchanged (Gemini requires keeping its 'thought signatures')
    usage: dict[str, int] = field(default_factory=dict)  # prompt / output / thoughts


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        """One generation round. Must raise QuotaExhausted if the daily quota is exhausted."""


def call_with_retries(fn: Callable[[], Any], classify: Callable[[Exception], tuple[bool, float]],
                      max_retries: int, who: str) -> Any:
    """Runs fn() with retries.

    classify(exc) -> (retryable, suggested_wait_s). A suggested wait above MAX_USEFUL_WAIT_S is interpreted
    as an exhausted quota and stops immediately with QuotaExhausted.
    """
    delay = 5.0
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except QuotaExhausted:
            raise
        except Exception as e:
            retryable, hint = classify(e)
            if hint > MAX_USEFUL_WAIT_S:
                raise QuotaExhausted(f"{who} quota exhausted. It resets in ~{hint / 60:.0f} min. "
                                     "Try another model/provider (.env) or wait.") from e
            if not retryable or attempt == max_retries:
                raise
            wait = max(hint, delay)
            log.warning("%s: %s; retry %d/%d in %.0fs", who, _brief(e), attempt, max_retries, wait)
            time.sleep(wait)
            delay = min(delay * 2, 60)
    raise RuntimeError("unreachable")


def _brief(e: Exception) -> str:
    return f"{type(e).__name__} {getattr(e, 'code', getattr(e, 'status_code', ''))}".strip()
