"""
FastAPI application factory (spec section 10) — CORS, middleware, and
every route module mounted here. This is the one file to touch when
adding a new route module or changing global middleware; each route
module itself only knows about its own endpoint.

Run with:
    cd backend && uvicorn api.app:app --reload --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_check_email import router as check_email_router
from api.routes_check_links import router as check_links_router
from api.routes_health import router as health_router
from api.routes_quick_check import router as quick_check_router
from api.routes_report_flow import router as report_flow_router
from api.routes_runs import router as runs_router
from config import get_settings
from logger import configure_logging, get_logger
from middleware.error_handler import register_exception_handlers
from middleware.logging_middleware import RequestLoggingMiddleware
from middleware.rate_limit import RateLimitMiddleware

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(
        title="security-copilot API",
        description="Link/email safety checks and network-anomaly reports, backed by a LangGraph agent.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"chrome-extension://.*",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, requests_per_minute=240 if settings.DEBUG else 120)
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    # Specific routes must be registered before the catch-all static mounts
    # below — Starlette matches routes in registration order, so a mount at
    # "/" registered first would shadow every API path.
    app.include_router(health_router)
    app.include_router(check_links_router)
    app.include_router(check_email_router)
    app.include_router(quick_check_router)
    app.include_router(report_flow_router)
    app.include_router(runs_router)

    # Screenshots (utils/screenshots.py) and the small history UI (ui/) are
    # both served as plain static files — neither needs its own route logic.
    Path(settings.SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
    app.mount("/screenshots", StaticFiles(directory=settings.SCREENSHOT_DIR), name="screenshots")
    app.mount("/", StaticFiles(directory="ui", html=True), name="ui")

    return app


app = create_app()
