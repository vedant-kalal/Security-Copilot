"""Event model — table `events(event_id, device_id, timestamp, event_type, payload_json)`.

Events are the raw telemetry unit of the platform: a browser navigation,
a download, a CSV-uploaded network flow row, or a replayed dataset
record all become an `Event` before the pipeline runs threat
intelligence, model inference and correlation on top of it.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.evidence import Evidence


class EventType(str, enum.Enum):
    """Supported event categories, spanning all three telemetry sources
    described in the architecture document (browser extension, CSV
    upload, dataset replay)."""

    PAGE_NAVIGATION = "page_navigation"
    URL_VISIT = "url_visit"
    FILE_DOWNLOAD = "file_download"
    FORM_SUBMISSION = "form_submission"
    LOGIN_ATTEMPT = "login_attempt"
    NETWORK_FLOW = "network_flow"
    NETWORK_FLOW_REPLAY = "network_flow_replay"
    NETWORK_FLOW_UPLOAD = "network_flow_upload"


class Event(Base):
    """A single unit of telemetry captured from a device."""

    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.device_id", ondelete="CASCADE"), index=True, nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type_enum"), nullable=False, index=True)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    device: Mapped["Device"] = relationship(back_populates="events")
    evidence_entries: Mapped[List["Evidence"]] = relationship(back_populates="event")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Event event_id={self.event_id} type={self.event_type}>"
