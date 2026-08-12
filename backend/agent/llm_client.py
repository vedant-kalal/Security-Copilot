"""
OpenRouter chat model factory (the agent's LLM).

OpenRouter exposes many providers behind one OpenAI-compatible endpoint, so
we talk to it with `langchain_openai.ChatOpenAI` pointed at
`settings.OPENROUTER_BASE_URL`, authenticated with `settings.OPENROUTER_API_KEY`.
A single process-wide client, no key rotation — if OpenRouter returns a 429,
`_RateLimitedLLM` (below) turns it into `LLMRateLimitedError` so `agent/graph.py`
can fail safe to a low-confidence verdict instead of a bare stack trace.

Kept as its own file so swapping the LLM provider later means editing only
this one file — nothing else in agent/ imports langchain_openai directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional, Sequence

from config import get_settings
from exceptions import LLMRateLimitedError, LLMUnavailableError
from logger import get_logger

logger = get_logger(__name__)


def _status_of(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status


def _is_rate_limit(exc: BaseException) -> bool:
    """Best-effort detection of an HTTP 429 across SDK/langchain wrappings."""
    if _status_of(exc) == 429:
        return True
    if type(exc).__name__ == "RateLimitError":
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "rate_limit" in text


def _is_account_error(exc: BaseException) -> bool:
    """402 (out of credits — the one actually seen in practice), 401/403
    (an invalid/revoked key). Distinct from a 429: these won't resolve by
    just trying again a moment later."""
    return _status_of(exc) in (401, 402, 403)


@lru_cache
def _client():
    """The real ChatOpenAI client (pointed at OpenRouter), built once."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError(
            "No OpenRouter API key configured. Set OPENROUTER_API_KEY in backend/.env. "
            "Get one at https://openrouter.ai/keys"
        )

    return ChatOpenAI(
        model=settings.OPENROUTER_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        temperature=0.0,
        # Optional OpenRouter ranking headers — harmless if ignored.
        default_headers={"X-Title": "security-copilot"},
    )


class _RateLimitedLLM:
    """Thin wrapper around the ChatOpenAI client that turns a 429 into
    `LLMRateLimitedError` instead of letting the SDK's raw exception (or a
    generic 500) reach the caller."""

    def __init__(self, tools: Optional[Sequence[Any]] = None) -> None:
        self._tools = tools

    def bind_tools(self, tools: Sequence[Any]) -> "_RateLimitedLLM":
        return _RateLimitedLLM(tools=tools)

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        client = _client()
        if self._tools:
            client = client.bind_tools(self._tools)
        try:
            return client.invoke(messages, **kwargs)
        except Exception as exc:  # noqa: BLE001 — re-raised below if neither case matches
            if _is_rate_limit(exc):
                logger.warning("OpenRouter rate-limited this request (HTTP 429)")
                raise LLMRateLimitedError("OpenRouter is rate-limiting this API key. Try again shortly.") from exc
            if _is_account_error(exc):
                logger.error("OpenRouter rejected this request at the account level (HTTP %s): %s", _status_of(exc), exc)
                raise LLMUnavailableError(
                    "The LLM provider (OpenRouter) rejected this request — the API key may be out of "
                    "credits or invalid. Check the account, not this specific request."
                ) from exc
            raise


@lru_cache
def get_llm() -> _RateLimitedLLM:
    """Return a process-wide singleton chat model, not yet bound to any tools."""
    return _RateLimitedLLM()
