"""
SentinelAI FastAPI application entrypoint.

Wires together configuration, structured logging, middleware, exception
handlers and the v1 API router. Run locally with:

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sa_text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.error_handler import register_exception_handlers
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s environment)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title="SentinelAI API",
        description=(
            "AI Security Copilot backend: phishing detection, network anomaly "
            "detection, threat correlation, incident management, MITRE mapping, "
            "and RAG-grounded, Gemini-generated guided response."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"chrome-extension://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, requests_per_minute=240 if settings.DEBUG else 120)
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["System"])
    async def health_check() -> dict:
        """Liveness/readiness probe used by process managers, load balancers, and uptime checks."""
        from app.core.database import AsyncSessionLocal

        db_status = "connected"
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(sa_text("SELECT 1"))
        except Exception:
            db_status = "disconnected"
        return {
            "status": "ok",
            "service": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "database": db_status,
        }

    @app.get("/", tags=["System"])
    async def root() -> dict:
        return {
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
