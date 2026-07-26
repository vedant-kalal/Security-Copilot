"""Pydantic request/response models for the API (spec section 10)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CheckLinksRequest(BaseModel):
    urls: list[str]


class CheckLinksResponse(BaseModel):
    results: dict[str, dict]


class CheckEmailRequest(BaseModel):
    text: str


class ReportFlowRequest(BaseModel):
    """Sent by the native host when Isolation Forest/TranAD flags a flow (spec sections 9/10)."""

    destination: str
    port: Optional[int] = None
    protocol: Optional[str] = None
    process_name: Optional[str] = None
    anomaly_score: Optional[float] = None
    context: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
