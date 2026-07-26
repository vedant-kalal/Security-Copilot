"""
Centralized exception handling.

Domain services raise typed `SentinelAIError` subclasses (see
`app.core.exceptions`); this module is the single place that translates
them (and any unexpected exception) into a consistent JSON error
response, so routers never need their own try/except blocks.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from exceptions import SentinelAIError
from logger import get_logger

logger = get_logger(__name__)


def _error_body(error_code: str, message: str, details: dict | None, request_id: str) -> dict:
    return {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to the FastAPI app."""

    @app.exception_handler(SentinelAIError)
    async def handle_domain_error(request: Request, exc: SentinelAIError) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.warning(
            "Domain error on %s %s: %s",
            request.method,
            request.url.path,
            exc.message,
            extra={"ctx_request_id": request_id, "ctx_error_code": exc.error_code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.error_code, exc.message, exc.details, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = str(uuid.uuid4())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_error", "Request validation failed", {"errors": exc.errors()}, request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = str(uuid.uuid4())
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", str(exc.detail), None, request_id),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.error(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
            extra={"ctx_request_id": request_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "An unexpected error occurred", None, request_id),
        )
