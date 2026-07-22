"""Event repository."""
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.event import Event
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    model = Event
    pk_column = "event_id"

    async def get(self, pk: UUID) -> Event | None:
        return await self.session.get(Event, pk)

    async def list_for_device_since(self, device_id: UUID, since: datetime) -> Sequence[Event]:
        stmt = (
            select(Event)
            .where(Event.device_id == device_id, Event.timestamp >= since)
            .order_by(Event.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_for_user_since(self, device_ids: Sequence[UUID], since: datetime) -> Sequence[Event]:
        if not device_ids:
            return []
        stmt = (
            select(Event)
            .where(Event.device_id.in_(device_ids), Event.timestamp >= since)
            .order_by(Event.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
