"""
POST /quick-check-url — fast pre-check for the extension's automatic
per-navigation scan.

Deliberately does NOT run the full LangGraph agent (headless browser, an
LLM call) — that takes 10-30s and a real API call, fine for a deliberate
"check this" click but not for every page navigated to. Answers using,
cheapest first:
  1. The router's 24h verdict cache (cache/sqlite_cache.py) — a full
     investigation already ran for this exact URL, reuse it instantly.
  2. The static blocklist (cache/blocklist.py) — known-bad domains.
  3. content_classifier's URL-only ONNX model, called directly — the same
     model the full agent uses, skipping the agent/LLM loop.
  4. If the model didn't already say "dangerous," corroborate with
     VirusTotal (skipped only if VT_API_KEY is unset, or already resolved
     from this endpoint's own short-lived cache below).

Step 4 exists because the ONNX model alone misses real, currently-active
phishing sites VirusTotal already has plenty of signal on (verified
2026-08: a live phishing storefront scored 0.10 — "safe" — from the URL
string alone, while VT already had 15 reputable vendors, including
Kaspersky/ESET/Fortinet/Sophos, calling it phishing). The escalation rule
uses VT's raw *malicious vendor count*, not its ratio-based
reputation_score: that score divides by every engine VT queried, most of
which simply never evaluated the domain rather than actively vouching for
it, so a handful of reputable vendors actively agreeing gets diluted into
looking unremarkable. A few vendors actively calling something phishing is
meaningful on its own, regardless of how many others stayed silent.

VirusTotal's free tier is rate-limited (roughly 4 req/min, 500/day), and
without caching, a user revisiting their own regularly-used sites would
burn through that in minutes — so this endpoint keeps its own short-lived,
domain-keyed, in-memory cache of VT results, separate from the router's
per-URL verdict cache (different key granularity, different purpose: this
one exists purely to protect VT's quota under repeat navigations).
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter

from api.schemas import QuickCheckRequest
from cache.blocklist import is_blocklisted
from cache.sqlite_cache import get_cached_verdict
from config import get_settings
from logger import get_logger
from tools.content_classifier import score_url
from tools.domain_reputation import _lookup_virustotal
from utils.validators import extract_domain

router = APIRouter()
logger = get_logger(__name__)

# Same cut-offs the web UI's phishing-probability bar uses (report.py /
# ui/index.html) — kept in sync so a score reads the same label everywhere.
_DANGEROUS_THRESHOLD = 0.7
_SUSPICIOUS_THRESHOLD = 0.4

# Absolute VirusTotal vendor-count thresholds for escalation — see module
# docstring for why this is a count, not VT's own ratio-based score.
_VT_DANGEROUS_MALICIOUS_COUNT = 3
_VT_SUSPICIOUS_MALICIOUS_COUNT = 1

_VT_CACHE_TTL_SECONDS = 6 * 3600
_vt_cache: dict[str, tuple[float, dict]] = {}


def _label_for_score(score: float) -> str:
    if score >= _DANGEROUS_THRESHOLD:
        return "dangerous"
    if score >= _SUSPICIOUS_THRESHOLD:
        return "suspicious"
    return "safe"


async def _vt_lookup_cached(domain: str) -> dict:
    """`_lookup_virustotal`, but memoized per-domain for `_VT_CACHE_TTL_SECONDS`
    so repeat navigations to the same sites don't re-spend VT's quota."""
    now = time.time()
    hit = _vt_cache.get(domain)
    if hit is not None and (now - hit[0]) < _VT_CACHE_TTL_SECONDS:
        return hit[1]

    result = await _lookup_virustotal(domain)
    if result.get("available"):
        _vt_cache[domain] = (now, result)
    return result


def _label_for_vt(vt_result: dict) -> tuple[str, float]:
    malicious = vt_result.get("malicious_count", 0)
    if malicious >= _VT_DANGEROUS_MALICIOUS_COUNT:
        return "dangerous", max(0.85, vt_result.get("reputation_score", 0.0))
    if malicious >= _VT_SUSPICIOUS_MALICIOUS_COUNT:
        return "suspicious", max(0.5, vt_result.get("reputation_score", 0.0))
    return "safe", vt_result.get("reputation_score", 0.0)


_LABEL_RANK = {"safe": 0, "unknown": 0, "suspicious": 1, "dangerous": 2}


@router.post("/quick-check-url", tags=["Links"])
async def quick_check_url(payload: QuickCheckRequest) -> dict:
    cached = get_cached_verdict(payload.url)
    if cached is not None:
        return {
            "label": cached.get("label", "safe"),
            "confidence": cached.get("confidence", 0.0),
            "source": "cache",
        }

    if is_blocklisted(payload.url):
        return {"label": "dangerous", "confidence": 1.0, "source": "blocklist"}

    ml_result = await asyncio.to_thread(score_url, payload.url)
    if "error" in ml_result:
        # A model-loading hiccup degrades to "unknown," never a false "safe."
        return {"label": "unknown", "confidence": 0.0, "source": "error", "detail": ml_result["error"]}

    ml_score = ml_result.get("phishing_score", 0.0)
    ml_label = _label_for_score(ml_score)

    if ml_label == "dangerous" or not get_settings().VT_API_KEY:
        return {"label": ml_label, "confidence": ml_score, "source": "ml_model"}

    # The URL string alone didn't ring a strong bell — corroborate with
    # VirusTotal before settling on "safe". Fast (no headless browser, no
    # LLM) and cached per-domain, so this doesn't slow the common case down
    # by more than a fraction of a second after the first visit.
    domain = extract_domain(payload.url)
    vt_result = await _vt_lookup_cached(domain)
    if not vt_result.get("available"):
        return {"label": ml_label, "confidence": ml_score, "source": "ml_model"}

    vt_label, vt_confidence = _label_for_vt(vt_result)
    if _LABEL_RANK[vt_label] > _LABEL_RANK[ml_label]:
        logger.info(
            "quick-check escalated %s: ML said %s (%.2f), VT found %d malicious vendors",
            domain, ml_label, ml_score, vt_result.get("malicious_count", 0),
        )
        return {"label": vt_label, "confidence": vt_confidence, "source": "virustotal"}

    return {"label": ml_label, "confidence": ml_score, "source": "ml_model"}
