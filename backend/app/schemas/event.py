"""Event ingestion schemas."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.event import EventType
from app.schemas.common import ORMBaseModel


class EventCreateRequest(BaseModel):
    """A single telemetry event submitted by the extension, CSV upload, or replay engine."""

    device_id: UUID
    event_type: EventType
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class EventBatchCreateRequest(BaseModel):
    events: list[EventCreateRequest]


class EventRead(ORMBaseModel):
    event_id: UUID
    device_id: UUID
    timestamp: datetime
    event_type: EventType
    payload_json: Dict[str, Any]


class EventIngestResponse(BaseModel):
    """Result of ingesting one or more events, including any incident that was created."""

    accepted: int
    incident_id: Optional[UUID] = None
    incident_created: bool = False
