"""Device model — table `devices(device_id, user_id, browser, os, last_seen)`."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.session import Session
    from app.models.user import User


class Device(Base):
    """A browser/device instance running the SentinelAI extension."""

    __tablename__ = "devices"

    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    browser: Mapped[str] = mapped_column(String(100), nullable=False)
    os: Mapped[str] = mapped_column(String(100), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="devices")
    sessions: Mapped[List["Session"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    events: Mapped[List["Event"]] = relationship(back_populates="device", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device device_id={self.device_id} browser={self.browser} os={self.os}>"
