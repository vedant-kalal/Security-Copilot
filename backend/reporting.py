"""
Reporting a confirmed-bad URL outward, for the "Report & Block" action
(dashboard's run page / extension popup) — the legitimate alternative to
"attack the phishing site back" (which we don't do: hacking back is
illegal even against confirmed criminal infrastructure, and looks
identical to a DoS attack regardless of intent).

Two independent, best-effort actions: (1) add the domain to our own
static blocklist (cache/blocklist.py) so this tool immediately and
permanently refuses to open it again, and (2) submit the URL to
VirusTotal and cast a "malicious" community vote, contributing to the
real, legal takedown/reputation pipeline other tools and browsers
already consult (same VT_API_KEY tools/domain_reputation.py already
uses — no new credential to configure).
"""
from __future__ import annotations

import base64

import httpx

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)


def _url_id(url: str) -> str:
    """VirusTotal identifies a URL object by the URL-safe base64 of the
    URL itself, no padding — see https://docs.virustotal.com/reference/url-info."""
    return base64.urlsafe_b64encode(url.encode()).decode("ascii").rstrip("=")


async def report_url_to_virustotal(url: str) -> dict:
    """Submits `url` for analysis, then casts a "malicious" community
    vote on it. Both steps degrade gracefully — a missing VT_API_KEY, a
    rate limit, or VT not yet having indexed the URL object (submission
    and the object it creates aren't perfectly atomic) all come back as
    `reported: False` with a human-readable `detail` rather than raising,
    the same "never fail the caller over an optional outside signal"
    convention as tools/domain_reputation.py."""
    settings = get_settings()
    if not settings.VT_API_KEY:
        return {"reported": False, "detail": "VirusTotal reporting is not configured."}

    headers = {"x-apikey": settings.VT_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=settings.THREAT_INTEL_TIMEOUT_SECONDS) as client:
            submit = await client.post(
                "https://www.virustotal.com/api/v3/urls", data={"url": url}, headers=headers
            )
            submit.raise_for_status()

            vote = await client.post(
                f"https://www.virustotal.com/api/v3/urls/{_url_id(url)}/votes",
                json={"data": {"type": "vote", "attributes": {"verdict": "malicious"}}},
                headers=headers,
            )
            if vote.status_code >= 400:
                # The URL was still submitted for analysis even though the
                # vote didn't land (e.g. VT hasn't finished creating the
                # object yet) — worth reporting as a partial success rather
                # than folding it into the same failure as a total no-op.
                logger.warning("VirusTotal vote failed for %s: HTTP %d", url, vote.status_code)
                return {"reported": True, "detail": "Submitted for analysis; the malicious vote could not be recorded yet."}

        return {"reported": True, "detail": "Submitted for analysis and flagged as malicious."}
    except httpx.HTTPStatusError as exc:
        logger.warning("VirusTotal submission failed for %s: %s", url, exc)
        return {"reported": False, "detail": f"VirusTotal submission failed: HTTP {exc.response.status_code}"}
    except httpx.RequestError as exc:
        logger.warning("VirusTotal submission unreachable for %s: %s", url, exc)
        return {"reported": False, "detail": "VirusTotal was unreachable."}
