"""GET /health (spec section 10)."""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas import HealthResponse
from config import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.APP_NAME)
