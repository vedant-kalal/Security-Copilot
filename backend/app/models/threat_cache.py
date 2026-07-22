"""ThreatCache model — table `threat_cache(indicator, source, reputation, last_checked)`.

Caches threat-intelligence lookups (VirusTotal / AbuseIPDB / PhishTank)
keyed by indicator + source so we do not exceed third-party rate limits
and so repeated lookups of the same domain/IP/hash are fast.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ThreatIntelSource(str, enum.Enum):
    VIRUSTOTAL = "virustotal"
    ABUSEIPDB = "abuseipdb"
    PHISHTANK = "phishtank"


class ThreatCache(Base):
    """Cached reputation result for a single indicator (domain, IP, URL, hash)."""

    __tablename__ = "threat_cache"
    __table_args__ = (
        UniqueConstraint("indicator", "source", name="uq_threat_cache_indicator_source"),
        Index("ix_threat_cache_indicator", "indicator"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    indicator: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[ThreatIntelSource] = mapped_column(
        Enum(ThreatIntelSource, name="threat_intel_source_enum"), nullable=False
    )
    reputation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ThreatCache indicator={self.indicator!r} source={self.source} reputation={self.reputation}>"
