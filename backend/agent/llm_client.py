"""
Groq chat model factory (spec sections 12/13, rescoped by the
security-copilot-poc-scope memory: Groq instead of Claude for this POC).

A single Groq key rate-limits fast — the agent makes several LLM calls
per case (one per tool-call round trip). This module rotates across all
configured keys (`settings.groq_api_keys`) round-robin, so load spreads
proactively, and advances to the next key on any HTTP 429 so a single
throttled key doesn't fail the whole case. If every key is rate-limited
for one request it raises `AllKeysRateLimitedError` (a specific exception,
not a generic one) so the graph can fall back to a clear verdict.

Kept as its own file so swapping the LLM provider later means editing
only this one file — nothing else in agent/ imports langchain_groq
directly.
"""
from __future__ import annotations

import itertools
import threading
from functools import lru_cache
from typing import Any, Optional, Sequence

from config import get_settings
from exceptions import AllKeysRateLimitedError
from logger import get_logger

logger = get_logger(__name__)

# Round-robin cursor shared across all threads. An itertools.cycle guarded by
# a lock hands out successive start indices so consecutive calls begin on
# different keys — balancing load proactively rather than only reacting to 429s.
_index_lock = threading.Lock()
_key_cycle: Optional["itertools.cycle[int]"] = None
_cycle_len: int = 0


def _next_start_index(num_keys: int) -> int:
    """Return the next key index to start a request on (thread-safe, round-robin)."""
    global _key_cycle, _cycle_len
    with _index_lock:
        if _key_cycle is None or _cycle_len != num_keys:
            _key_cycle = itertools.cycle(range(num_keys))
            _cycle_len = num_keys
        return next(_key_cycle)


def _is_rate_limit(exc: BaseException) -> bool:
    """Best-effort detection of a Groq HTTP 429 across SDK/langchain wrappings."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status == 429:
        return True
    if type(exc).__name__ == "RateLimitError":
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "rate_limit" in text


@lru_cache(maxsize=None)
def _client_for_key(api_key: str, model: str, temperature: float):
    """One ChatGroq client per key, cached so we don't rebuild on every call."""
    from langchain_groq import ChatGroq

    return ChatGroq(model=model, api_key=api_key, temperature=temperature)


class _RotatingGroqLLM:
    """Drop-in stand-in for a ChatGroq instance that rotates keys on 429.

    Exposes just the surface agent_node.py uses — `bind_tools()` and
    `invoke()` — delegating to a real ChatGroq client under the hood while
    handling key selection and rate-limit retry.
    """

    def __init__(self, tools: Optional[Sequence[Any]] = None) -> None:
        self._tools = tools

    def bind_tools(self, tools: Sequence[Any]) -> "_RotatingGroqLLM":
        return _RotatingGroqLLM(tools=tools)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        settings = get_settings()
        keys = settings.groq_api_keys
        if not keys:
            raise RuntimeError(
                "No Groq API keys configured. Set GROQ_API_KEYS (comma-separated) — or the "
                "legacy GROQ_API_KEY — in backend/.env. Free keys: https://console.groq.com/keys"
            )

        num_keys = len(keys)
        start = _next_start_index(num_keys)
        last_exc: Optional[BaseException] = None

        # Try each key once, starting at the round-robin cursor and advancing
        # on every 429, up to len(keys) attempts total.
        for attempt in range(num_keys):
            idx = (start + attempt) % num_keys
            client = _client_for_key(keys[idx], settings.GROQ_MODEL, 0.0)
            if self._tools:
                client = client.bind_tools(self._tools)
            try:
                logger.debug("Groq call using key index %d (attempt %d/%d)", idx, attempt + 1, num_keys)
                return client.invoke(messages, **kwargs)
            except Exception as exc:  # noqa: BLE001 — re-raised below if not a 429
                if _is_rate_limit(exc):
                    logger.warning("Groq key index %d hit a 429; rotating to the next key", idx)
                    last_exc = exc
                    continue
                raise

        raise AllKeysRateLimitedError(
            f"All {num_keys} configured Groq API key(s) are rate-limited. Try again shortly."
        ) from last_exc


@lru_cache
def get_llm() -> _RotatingGroqLLM:
    """Return a process-wide singleton rotating chat model, not yet bound to any tools."""
    return _RotatingGroqLLM()
