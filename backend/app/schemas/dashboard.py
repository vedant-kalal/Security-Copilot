"""Dashboard aggregate schemas (home page)."""
from typing import List

from pydantic import BaseModel

from app.schemas.incident import IncidentRead


class SeverityBreakdown(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class DashboardSummary(BaseModel):
    devices_protected: int
    security_score: int
    incidents_today: int
    open_incidents: int
    severity_breakdown: SeverityBreakdown
    recent_incidents: List[IncidentRead]
