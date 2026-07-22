"""Phishing-check schemas (used by both the extension popup and CSV/manual checks)."""
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID


class PhishingCheckRequest(BaseModel):
    url: str = Field(min_length=1, description="Full URL the browser navigated to")
    page_title: Optional[str] = None
    page_text_snippet: Optional[str] = Field(
        default=None, max_length=4000, description="Short excerpt of visible page text, if available"
    )
    device_id: Optional[UUID] = None


class PhishingCheckResponse(BaseModel):
    url: str
    is_phishing: bool
    confidence: float = Field(ge=0.0, le=1.0)
    risk_label: str
    reasons: list[str]
    threat_intel_hit: bool
    incident_id: Optional[UUID] = None
