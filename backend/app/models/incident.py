"""Incident model — table
`incidents(incident_id, user_id, title, severity, confidence, mitre, status, summary, created_at)`.

The Incident is the central object of the entire product (see
architecture doc, section 23: "The entire architecture is intentionally
centered around that single concept.").
"""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_response import AIResponse
    from app.models.evidence import Evidence
    from app.models.user import User


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Incident(Base, TimestampMixin):
    """A correlated security incident, built by the Threat Correlation Engine
    from one or more underlying events + threat intelligence + model scores."""

    __tablename__ = "incidents"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incident_severity_enum"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    mitre: Mapped[List[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status_enum"), nullable=False, default=IncidentStatus.OPEN, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    user: Mapped["User"] = relationship(back_populates="incidents")
    evidence_entries: Mapped[List["Evidence"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", lazy="selectin"
    )
    ai_responses: Mapped[List["AIResponse"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Incident incident_id={self.incident_id} title={self.title!r} severity={self.severity}>"
