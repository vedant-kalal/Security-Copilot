"""Evidence model — table `evidence(evidence_id, incident_id, event_id, reason, score)`.

Each row links one raw `Event` to an `Incident` and records *why* the
Threat Correlation Engine believed that event was relevant, plus a
normalized contribution score (0..1) used to compute overall confidence.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.incident import Incident


class Evidence(Base, TimestampMixin):
    """A single piece of evidence supporting an incident."""

    __tablename__ = "evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.incident_id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.event_id", ondelete="CASCADE"), index=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    incident: Mapped["Incident"] = relationship(back_populates="evidence_entries")
    event: Mapped["Event"] = relationship(back_populates="evidence_entries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Evidence evidence_id={self.evidence_id} incident_id={self.incident_id} score={self.score}>"
