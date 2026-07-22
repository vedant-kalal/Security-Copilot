"""
Dashboard aggregation service.

Builds the "Home page" summary described in the architecture document
(section 9): devices protected, security score, today's incidents,
recent threats, severity breakdown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import IncidentStatus
from app.repositories.device_repository import DeviceRepository
from app.repositories.incident_repository import IncidentRepository
from app.schemas.dashboard import DashboardSummary, SeverityBreakdown
from app.schemas.incident import IncidentRead

_SEVERITY_WEIGHTS = {"low": 2, "medium": 5, "high": 12, "critical": 25}


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.devices = DeviceRepository(session)
        self.incidents = IncidentRepository(session)

    async def get_summary(self, user_id: UUID) -> DashboardSummary:
        devices_protected = await self.devices.count_for_user(user_id)

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        incidents_today = await self.incidents.count_since(user_id, today_start)
        open_incidents = await self.incidents.count_for_user(user_id, status=IncidentStatus.OPEN)
        investigating = await self.incidents.count_for_user(user_id, status=IncidentStatus.INVESTIGATING)

        breakdown_raw = await self.incidents.severity_breakdown(user_id)
        breakdown = SeverityBreakdown(**{k: breakdown_raw.get(k, 0) for k in ("low", "medium", "high", "critical")})

        recent = await self.incidents.list_for_user(user_id, limit=5)

        security_score = self._compute_security_score(breakdown)

        return DashboardSummary(
            devices_protected=devices_protected,
            security_score=security_score,
            incidents_today=incidents_today,
            open_incidents=open_incidents + investigating,
            severity_breakdown=breakdown,
            recent_incidents=[IncidentRead.model_validate(i) for i in recent],
        )

    @staticmethod
    def _compute_security_score(breakdown: SeverityBreakdown) -> int:
        """100 = no unresolved risk. Each unresolved incident deducts points
        weighted by severity, floored at 0."""
        penalty = (
            breakdown.low * _SEVERITY_WEIGHTS["low"]
            + breakdown.medium * _SEVERITY_WEIGHTS["medium"]
            + breakdown.high * _SEVERITY_WEIGHTS["high"]
            + breakdown.critical * _SEVERITY_WEIGHTS["critical"]
        )
        return max(0, 100 - penalty)
