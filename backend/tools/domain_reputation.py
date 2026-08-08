"""
`domain_reputation` tool (spec section 4.2).

Looks up outside signals about a domain: how old it is (WHOIS) and
whether VirusTotal already flags it as malicious. Both lookups degrade
independently and gracefully — a WHOIS rate-limit or a missing
VT_API_KEY never fails the whole tool, they just make that half of the
result `available: False` so the agent knows to weigh it less.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from langchain_core.tools import tool

from config import get_settings
from logger import get_logger
from utils.validators import extract_domain, is_ip_address

logger = get_logger(__name__)


def _first_date(value: Any) -> datetime | None:
    """python-whois sometimes returns a list of dates (registrars disagree) instead of one — take the earliest.
    Some registrars mix naive and tz-aware datetimes within that same list, which makes them
    uncomparable, so every date is normalized to UTC-aware before `min()` ever sees them."""
    if isinstance(value, list):
        dates = [v for v in value if isinstance(v, datetime)]
    elif isinstance(value, datetime):
        dates = [value]
    else:
        return None

    if not dates:
        return None

    normalized = [d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc) for d in dates]
    return min(normalized)


async def _lookup_whois(domain: str) -> dict:
    try:
        import whois  # python-whois

        record = await asyncio.to_thread(whois.whois, domain)
        creation = _first_date(record.creation_date)  # always UTC-aware, or None
        if creation is None:
            return {"available": False, "creation_date": None, "age_days": None, "detail": "No creation date returned"}

        age_days = (datetime.now(timezone.utc) - creation).days

        # A WHOIS server resolves a query up to whatever is actually
        # registered — for a subdomain of a shared platform (tunneling
        # services like loca.lt/ngrok, free hosting, dynamic DNS), that's
        # the platform itself, not the attacker-controlled subdomain.
        # `record.domain_name` shows what was actually matched; if it's
        # shorter than what was queried, this "age" describes the
        # platform, not this specific subdomain — which could have been
        # created seconds ago. That distinction matters enormously for a
        # phishing verdict (confirmed on a real case: a fake
        # "wmw-google-com.loca.lt" page read as "an established
        # 2688-day-old domain" when that age is loca.lt's, not its own),
        # so it's surfaced explicitly instead of silently misreported.
        matched = record.domain_name
        matched = matched[0] if isinstance(matched, list) else matched
        matched = (matched or "").lower().strip()
        is_parent_match = bool(matched) and matched != domain.lower()

        if is_parent_match:
            detail = (
                f"WHOIS only has a record for the parent domain '{matched}' (registered {age_days} days ago) — "
                f"'{domain}' is an unregistered subdomain of it, not independently registered, and could have "
                f"been created at any time. Do not treat this age as evidence about '{domain}' itself."
            )
        else:
            detail = f"Registered {age_days} days ago"

        return {
            "available": True,
            "creation_date": creation.isoformat(),
            "age_days": age_days,
            "is_parent_domain_match": is_parent_match,
            "matched_domain": matched or domain,
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 - WHOIS failures/rate-limits are "unknown", never a negative signal
        logger.warning("WHOIS lookup failed for %s: %s", domain, exc)
        return {"available": False, "creation_date": None, "age_days": None, "detail": f"WHOIS unavailable: {exc}"}


async def _lookup_virustotal(target: str) -> dict:
    """Queries VirusTotal. VT doesn't scan anything itself — it aggregates
    ~70-90 third-party security vendors (antivirus companies, URL/domain
    reputation feeds, blacklist services), each of which independently
    classifies the target with its own engine (blacklist matching,
    heuristics, sandboxing, ML) and reports a category
    (malicious/suspicious/harmless/undetected/timeout) plus that engine's own
    result label. `last_analysis_stats` is just the aggregate counts across
    those; `last_analysis_results` is the actual per-vendor verdicts, and
    `categories` is separate threat-type labeling (phishing, malware, spam,
    etc.) from web-categorization vendors when they have an opinion — both
    are pulled here so the agent (and the report/UI) can say *what kind* of
    threat was flagged, not just how many vendors flagged it.

    VT has two different endpoints for this depending on what `target` is —
    a domain name or a raw IP (network_flow cases report a bare destination
    IP, never a hostname). Calling the domains endpoint with an IP gets a
    guaranteed 400 from VT, which is exactly what happened here before this
    branch existed: every network-anomaly investigation silently lost its VT
    signal. Response shape is otherwise identical between the two endpoints,
    so nothing below needs to know which kind of target it got."""
    settings = get_settings()
    if not settings.VT_API_KEY:
        return {"available": False, "detail": "VT_API_KEY not configured"}

    endpoint = "ip_addresses" if is_ip_address(target) else "domains"
    noun = "IP" if endpoint == "ip_addresses" else "domain"

    try:
        async with httpx.AsyncClient(timeout=settings.THREAT_INTEL_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"https://www.virustotal.com/api/v3/{endpoint}/{target}",
                headers={"x-apikey": settings.VT_API_KEY},
            )
            response.raise_for_status()
            data = response.json()

        attributes = data.get("data", {}).get("attributes", {})
        stats = attributes.get("last_analysis_stats", {})
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless = stats.get("harmless", 0)
        total = sum(stats.values()) or 1
        reputation_score = min(1.0, (malicious + 0.5 * suspicious) / total)

        # Which specific vendors flagged it, and what they called it — the
        # "what type" detail that the raw counts above don't carry. Capped so
        # a widely-flagged target doesn't blow up the LLM's context.
        flagged_by = [
            {"vendor": vendor, "category": r.get("category"), "result": r.get("result")}
            for vendor, r in (attributes.get("last_analysis_results") or {}).items()
            if r.get("category") in ("malicious", "suspicious")
        ][:15]

        # Separate from the security-vendor verdicts above: dedicated
        # web-categorization services' own labels for the target (e.g.
        # "phishing and other frauds", "spam") — usually the most direct
        # answer to "what kind of bad site is this," when populated.
        categories = attributes.get("categories") or {}

        detail = f"{malicious} vendors flagged this {noun} as malicious"
        if flagged_by:
            named = ", ".join(f"{f['vendor']} ({f['result']})" for f in flagged_by[:3])
            detail += f" — including {named}"

        return {
            "available": True,
            "malicious_count": malicious,
            "suspicious_count": suspicious,
            "harmless_count": harmless,
            "reputation_score": round(reputation_score, 4),
            "detail": detail,
            "flagged_by": flagged_by,
            "categories": categories,
            "community_reputation": attributes.get("reputation"),
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {
                "available": True,
                "malicious_count": 0,
                "suspicious_count": 0,
                "harmless_count": 0,
                "reputation_score": 0.0,
                "detail": f"{noun} not found in VirusTotal",
                "flagged_by": [],
                "categories": {},
                "community_reputation": None,
            }
        logger.warning("VirusTotal lookup failed for %s: %s", target, exc)
        return {"available": False, "detail": f"VirusTotal error: {exc}"}
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("VirusTotal lookup error for %s: %s", target, exc)
        return {"available": False, "detail": f"VirusTotal unreachable: {exc}"}


@tool
async def domain_reputation(url: str) -> dict:
    """Looks up outside signals about a domain — how old it is, and whether VirusTotal already flags it as malicious. Use this to corroborate or double-check what the sandbox showed you."""
    domain = extract_domain(url)
    whois_result, vt_result = await asyncio.gather(_lookup_whois(domain), _lookup_virustotal(domain))
    return {"domain": domain, "whois": whois_result, "virustotal": vt_result}
