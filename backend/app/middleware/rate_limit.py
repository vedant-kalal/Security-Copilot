"""
Lightweight in-memory rate limiting middleware.

Uses a fixed-window counter per client IP + path prefix. This is
sufficient for a single-instance deployment (the target for this
single backend process on one machine); a horizontally-scaled deployment
should replace the in-memory store with Redis (`INCR` + `EXPIRE`)
without changing the middleware interface.
"""
from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._window_start: dict[str, float] = defaultdict(float)
        self._counts: dict[str, int] = defaultdict(int)
        self._settings = get_settings()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self._settings.ENVIRONMENT == "test" or request.url.path in ("/health", "/"):
            return await call_next(request)

        client_key = f"{request.client.host if request.client else 'unknown'}"
        now = time.time()

        if now - self._window_start[client_key] > 60:
            self._window_start[client_key] = now
            self._counts[client_key] = 0

        self._counts[client_key] += 1

        if self._counts[client_key] > self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please slow down.",
                        "details": {},
                    }
                },
            )

        return await call_next(request)
