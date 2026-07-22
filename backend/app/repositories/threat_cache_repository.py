"""Threat-intel cache repository."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from app.models.threat_cache import ThreatCache, ThreatIntelSource
from app.repositories.base import BaseRepository


class ThreatCacheRepository(BaseRepository[ThreatCache]):
    model = ThreatCache

    async def get_fresh(
        self, indicator: str, source: ThreatIntelSource, ttl_seconds: int
    ) -> Optional[ThreatCache]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        stmt = select(ThreatCache).where(
            ThreatCache.indicator == indicator,
            ThreatCache.source == source,
            ThreatCache.last_checked >= cutoff,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any(self, indicator: str, source: ThreatIntelSource) -> Optional[ThreatCache]:
        stmt = select(ThreatCache).where(ThreatCache.indicator == indicator, ThreatCache.source == source)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self, indicator: str, source: ThreatIntelSource, reputation: float, raw_response: dict
    ) -> ThreatCache:
        existing = await self.get_any(indicator, source)
        if existing:
            existing.reputation = reputation
            existing.raw_response = raw_response
            existing.last_checked = datetime.now(timezone.utc)
            await self.session.flush()
            return existing

        entry = ThreatCache(indicator=indicator, source=source, reputation=reputation, raw_response=raw_response)
        return await self.add(entry)
