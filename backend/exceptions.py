"""
Application-wide exception hierarchy.

Using typed domain exceptions (instead of raising `HTTPException` deep
inside services) keeps business logic decoupled from the web framework
and lets a single middleware translate exceptions into HTTP responses.
"""
from typing import Any, Dict, Optional


class SentinelAIError(Exception):
    """Base class for all domain-level errors raised by SentinelAI services."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(SentinelAIError):
    status_code = 404
    error_code = "not_found"


class AlreadyExistsError(SentinelAIError):
    status_code = 409
    error_code = "already_exists"


class InvalidCredentialsError(SentinelAIError):
    status_code = 401
    error_code = "invalid_credentials"


class UnauthorizedError(SentinelAIError):
    status_code = 401
    error_code = "unauthorized"


class ForbiddenError(SentinelAIError):
    status_code = 403
    error_code = "forbidden"


class ValidationError(SentinelAIError):
    status_code = 422
    error_code = "validation_error"


class ExternalServiceError(SentinelAIError):
    """Raised when a downstream dependency (threat intel API, Gemini, etc.) fails."""

    status_code = 502
    error_code = "external_service_error"


class RateLimitedError(SentinelAIError):
    status_code = 429
    error_code = "rate_limited"


class LLMRateLimitedError(RateLimitedError):
    """OpenRouter returned HTTP 429 for one request.

    Raised by agent/llm_client.py so callers (agent/graph.py / the API's error
    handler) can surface a specific "temporarily rate-limited" fallback verdict
    instead of a bare stack trace.
    """

    error_code = "llm_rate_limited"


class LLMUnavailableError(ExternalServiceError):
    """OpenRouter returned a terminal account-level error for this request —
    HTTP 402 (out of credits) being the one actually seen in practice, but
    this also covers 401/403 (a revoked/invalid key). None of these are
    "try again in a second" like a 429 — the account needs attention — but
    they deserve exactly the same treatment agent/graph.py already gives a
    rate limit: a low-confidence "unresolved" verdict, not a bare 500."""

    error_code = "llm_unavailable"
