"""
Threat Intelligence service.

Integrates VirusTotal, AbuseIPDB and PhishTank behind a single
interface, with a database-backed cache (`threat_cache` table) so
repeated lookups of the same indicator do not exceed third-party rate
limits (architecture doc: "Implement caching").

Each provider client degrades gracefully: if an API key is not
configured, or the provider call fails/times out, the service returns
a neutral (zero-reputation, `queried=False`) result rather than raising,
so the rest of the pipeline (phishing detection, correlation) can still
proceed using its other signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.threat_cache import ThreatIntelSource
from app.repositories.threat_cache_repository import ThreatCacheRepository
from app.utils.validators import extract_domain, is_ip_address

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReputationResult:
    indicator: str
    source: ThreatIntelSource
    reputation: float  # 0.0 (clean) .. 1.0 (malicious)
    queried: bool  # False if the provider was skipped (no key / error / cache miss & failure)
    from_cache: bool
    detail: str


class ThreatIntelService:
    """Aggregates reputation lookups across all configured threat-intel providers."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cache = ThreatCacheRepository(session)
        self.settings = get_settings()

    async def check_url(self, url: str) -> list[ReputationResult]:
        """Run VirusTotal + PhishTank lookups for a URL/domain."""
        domain = extract_domain(url)
        results = []
        results.append(await self._check_virustotal(domain, is_ip=False))
        results.append(await self._check_phishtank(url))
        return results

    async def check_ip(self, ip_address: str) -> list[ReputationResult]:
        """Run AbuseIPDB + VirusTotal lookups for an IP address."""
        results = []
        results.append(await self._check_abuseipdb(ip_address))
        if is_ip_address(ip_address):
            results.append(await self._check_virustotal(ip_address, is_ip=True))
        return results

    # ------------------------------------------------------------------
    # VirusTotal
    # ------------------------------------------------------------------
    async def _check_virustotal(self, indicator: str, is_ip: bool) -> ReputationResult:
        source = ThreatIntelSource.VIRUSTOTAL
        cached = await self.cache.get_fresh(indicator, source, self.settings.THREAT_INTEL_CACHE_TTL_SECONDS)
        if cached:
            return ReputationResult(indicator, source, cached.reputation, True, True, "Served from cache")

        if not self.settings.VIRUSTOTAL_API_KEY:
            return ReputationResult(indicator, source, 0.0, False, False, "VirusTotal API key not configured")

        endpoint = (
            f"https://www.virustotal.com/api/v3/ip_addresses/{indicator}"
            if is_ip
            else f"https://www.virustotal.com/api/v3/domains/{indicator}"
        )
        headers = {"x-apikey": self.settings.VIRUSTOTAL_API_KEY}

        try:
            async with httpx.AsyncClient(timeout=self.settings.THREAT_INTEL_TIMEOUT_SECONDS) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
                data = response.json()

            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            total = sum(stats.values()) or 1
            reputation = min(1.0, (malicious + 0.5 * suspicious) / total)

            await self.cache.upsert(indicator, source, reputation, data)
            await self.cache.commit()
            return ReputationResult(
                indicator, source, reputation, True, False, f"{malicious} vendors flagged as malicious"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                await self.cache.upsert(indicator, source, 0.0, {"status": "not_found"})
                await self.cache.commit()
                return ReputationResult(indicator, source, 0.0, True, False, "Indicator not found in VirusTotal")
            logger.warning("VirusTotal lookup failed for %s: %s", indicator, exc)
            return ReputationResult(indicator, source, 0.0, False, False, f"VirusTotal error: {exc}")
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("VirusTotal lookup error for %s: %s", indicator, exc)
            return ReputationResult(indicator, source, 0.0, False, False, f"VirusTotal unreachable: {exc}")

    # ------------------------------------------------------------------
    # AbuseIPDB
    # ------------------------------------------------------------------
    async def _check_abuseipdb(self, ip_address: str) -> ReputationResult:
        source = ThreatIntelSource.ABUSEIPDB
        cached = await self.cache.get_fresh(ip_address, source, self.settings.THREAT_INTEL_CACHE_TTL_SECONDS)
        if cached:
            return ReputationResult(ip_address, source, cached.reputation, True, True, "Served from cache")

        if not self.settings.ABUSEIPDB_API_KEY:
            return ReputationResult(ip_address, source, 0.0, False, False, "AbuseIPDB API key not configured")

        try:
            async with httpx.AsyncClient(timeout=self.settings.THREAT_INTEL_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://api.abuseipdb.com/api/v2/check",
                    headers={"Key": self.settings.ABUSEIPDB_API_KEY, "Accept": "application/json"},
                    params={"ipAddress": ip_address, "maxAgeInDays": 90},
                )
                response.raise_for_status()
                data = response.json()

            score = data.get("data", {}).get("abuseConfidenceScore", 0) / 100.0
            await self.cache.upsert(ip_address, source, score, data)
            await self.cache.commit()
            return ReputationResult(
                ip_address, source, score, True, False, f"AbuseIPDB confidence score: {score:.0%}"
            )
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            logger.warning("AbuseIPDB lookup failed for %s: %s", ip_address, exc)
            return ReputationResult(ip_address, source, 0.0, False, False, f"AbuseIPDB error: {exc}")

    # ------------------------------------------------------------------
    # PhishTank
    # ------------------------------------------------------------------
    async def _check_phishtank(self, url: str) -> ReputationResult:
        source = ThreatIntelSource.PHISHTANK
        cached = await self.cache.get_fresh(url, source, self.settings.THREAT_INTEL_CACHE_TTL_SECONDS)
        if cached:
            return ReputationResult(url, source, cached.reputation, True, True, "Served from cache")

        try:
            async with httpx.AsyncClient(timeout=self.settings.THREAT_INTEL_TIMEOUT_SECONDS) as client:
                payload = {"url": url, "format": "json"}
                if self.settings.PHISHTANK_API_KEY:
                    payload["app_key"] = self.settings.PHISHTANK_API_KEY
                response = await client.post("https://checkurl.phishtank.com/checkurl/", data=payload)
                response.raise_for_status()
                data = response.json()

            results = data.get("results", {})
            in_database = bool(results.get("in_database"))
            verified = bool(results.get("verified"))
            reputation = 1.0 if (in_database and verified) else (0.6 if in_database else 0.0)

            await self.cache.upsert(url, source, reputation, data)
            await self.cache.commit()
            detail = "Verified phishing URL in PhishTank database" if in_database else "Not found in PhishTank"
            return ReputationResult(url, source, reputation, True, False, detail)
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            logger.warning("PhishTank lookup failed for %s: %s", url, exc)
            return ReputationResult(url, source, 0.0, False, False, f"PhishTank error: {exc}")
