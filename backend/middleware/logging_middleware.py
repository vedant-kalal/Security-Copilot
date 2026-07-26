"""Structured request/response logging middleware."""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from logger import get_logger

logger = get_logger("sentinelai.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs one structured line per request, with a correlation id and latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s -> %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "ctx_request_id": request_id,
                "ctx_method": request.method,
                "ctx_path": request.url.path,
                "ctx_status_code": response.status_code,
                "ctx_duration_ms": duration_ms,
            },
        )
        return response
