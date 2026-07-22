"""Incident repository."""
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.incident import Incident, IncidentStatus
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    model = Incident
    pk_column = "incident_id"

    async def get(self, pk: UUID) -> Optional[Incident]:
        return await self.session.get(
            Incident,
            pk,
            options=[
                selectinload(Incident.evidence_entries),
                selectinload(Incident.ai_responses),
            ],
        )

    async def list_for_user(
        self,
        user_id: UUID,
        status: Optional[IncidentStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Incident]:
        stmt = select(Incident).where(Incident.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_user(self, user_id: UUID, status: Optional[IncidentStatus] = None) -> int:
        stmt = select(func.count()).select_from(Incident).where(Incident.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Incident.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_since(self, user_id: UUID, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(Incident)
            .where(Incident.user_id == user_id, Incident.created_at >= since)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def severity_breakdown(self, user_id: UUID) -> dict[str, int]:
        stmt = (
            select(Incident.severity, func.count())
            .where(Incident.user_id == user_id, Incident.status != IncidentStatus.RESOLVED)
            .group_by(Incident.severity)
        )
        result = await self.session.execute(stmt)
        return {severity.value: count for severity, count in result.all()}

    async def find_correlation_candidates(
        self, user_id: UUID, since: datetime, statuses: Sequence[IncidentStatus]
    ) -> Sequence[Incident]:
        """Open/investigating incidents for a user within the correlation
        time window — used to decide whether a new event should be
        attached to an existing incident instead of creating a new one."""
        stmt = (
            select(Incident)
            .where(
                Incident.user_id == user_id,
                Incident.created_at >= since,
                Incident.status.in_(statuses),
            )
            .order_by(Incident.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
