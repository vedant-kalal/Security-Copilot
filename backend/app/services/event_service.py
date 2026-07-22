"""Event ingestion service: persists raw telemetry events."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventType
from app.repositories.event_repository import EventRepository


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventRepository(session)

    async def record_event(
        self, device_id: UUID, event_type: EventType, payload: dict, timestamp: datetime | None = None
    ) -> Event:
        event = Event(
            device_id=device_id,
            event_type=event_type,
            payload_json=payload,
            timestamp=timestamp or datetime.now(timezone.utc),
        )
        await self.events.add(event)
        await self.events.commit()
        return event

    async def record_events(self, device_id: UUID, events: Sequence[tuple[EventType, dict, datetime | None]]) -> list[Event]:
        created: list[Event] = []
        for event_type, payload, timestamp in events:
            event = Event(
                device_id=device_id,
                event_type=event_type,
                payload_json=payload,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            created.append(await self.events.add(event))
        await self.events.commit()
        return created
