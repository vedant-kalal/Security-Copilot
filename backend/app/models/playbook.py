"""Playbook model — supports the RAG pipeline.

Not part of the original 8-table spec in the architecture document, but
required to make "RAG retrieves playbooks" (core workflow step 11)
concrete: each row is a guided-response playbook (MITRE technique,
title, markdown body) plus a pgvector embedding of its content so it can
be semantically retrieved for a given incident.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Float, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.database import Base
from app.models.mixins import TimestampMixin

_settings = get_settings()


class Playbook(Base, TimestampMixin):
    """A guided incident-response playbook, retrievable via vector similarity search."""

    __tablename__ = "playbooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    mitre_techniques: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Playbook id={self.id} title={self.title!r}>"
