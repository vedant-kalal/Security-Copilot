"""User model — table `users(id, email, password_hash, created_at)`."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.incident import Incident


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A registered SentinelAI user (browser extension + dashboard account)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    devices: Mapped[List["Device"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    incidents: Mapped[List["Incident"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<User id={self.id} email={self.email!r}>"
