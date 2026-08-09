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
     model the full agent uses, skipping the agent/LLM loop. Scored against
     the bare domain ("https://{domain}/"), not the full URL — phishing is
     a property of who controls the domain, not which page on it, and
     scoring the full URL made the result path-sensitive noise (see below).
  4. Corroborate with VirusTotal in both directions (skipped only if
     VT_API_KEY is unset, or already resolved from this endpoint's own
     short-lived cache below) — escalate a too-lenient ML verdict, or
     de-escalate a too-harsh one.
  5. If the content script found a password field inside a form that
     posts to a different site than the page itself, escalate — a strong,
     independent signal a URL/VT-only check can't see at all (see
     `_apply_page_signal`). Never applied after step 4 has already
     de-escalated to "safe": once VirusTotal's vendor consensus vouches
     for a domain, a single page-shape heuristic must not override that
     back into a false alarm.

Step 4 exists because the ONNX model is URL-string-only (no domain age,
no reputation, nothing about who actually operates the site), and gets
both kinds of call wrong on real sites even scored domain-only:
  - Verified 2026-08: a live phishing storefront scored 0.10 — "safe" —
    from the URL string alone, while VT already had 15 reputable vendors,
    including Kaspersky/ESET/Fortinet/Sophos, calling it phishing.
  - Verified 2026-08: `https://login.microsoftonline.com/` scores 0.97 —
    "dangerous" — even with no path at all, because the model treats a
    "login." subdomain itself as characteristic of phishing kit naming
    (which, divorced from who actually owns the domain, it often is),
    while VT shows ~59 vendors actively calling the domain harmless.

Both corrections use VT's raw vendor *counts*, not its ratio-based
reputation_score: that score divides by every engine VT queried, most of
which simply never evaluated the domain rather than actively vouching for
it either way, so a handful of vendors actively agreeing (in either
direction) gets diluted into looking unremarkable. A few vendors actively
calling something phishing — or a large number actively calling it
harmless — is meaningful on its own, regardless of how many others stayed
silent. That's also why the de-escalation rule requires a real count of
harmless votes rather than just "malicious_count == 0": VT simply not
having evaluated a domain yet (a brand-new phishing domain, say) must not
read the same as VT having looked and vouched for it.

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
from utils.validators import extract_domain, same_registrable_domain

router = APIRouter()
logger = get_logger(__name__)

# Same cut-offs the web UI's phishing-probability bar uses (report.py /
# ui/index.html) — kept in sync so a score reads the same label everywhere.
_DANGEROUS_THRESHOLD = 0.7
_SUSPICIOUS_THRESHOLD = 0.4

# Absolute VirusTotal vendor-count thresholds for escalation/de-escalation —
# see module docstring for why these are counts, not VT's own ratio-based
# score.
_VT_DANGEROUS_MALICIOUS_COUNT = 3
_VT_SUSPICIOUS_MALICIOUS_COUNT = 1
# De-escalation is the riskier direction to get wrong (clearing a verdict
# that was actually correct costs a lot more than leaving a false alarm up
# a little longer), so the bar is deliberately high: a real, substantial
# number of vendors must have actively vouched for the domain. A single
# stray malicious/suspicious vote is tolerated rather than blocking the
# override outright — verified 2026-08 that heavily-impersonated real
# domains (login.microsoftonline.com, web.whatsapp.com) each carry exactly
# one low-quality vendor's false positive alongside ~58 harmless votes;
# requiring a hard zero would leave those permanently misflagged.
_VT_HARMLESS_OVERRIDE_COUNT = 20
_VT_HARMLESS_OVERRIDE_MAX_BAD = 1

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


def _apply_page_signal(payload: QuickCheckRequest, label: str, confidence: float, source: str) -> dict:
    """The one page-content signal this endpoint uses: a password field
    inside a form whose action posts to a different site than the page
    itself. Deliberately narrow — a password *field* alone is on countless
    ordinary login pages and proves nothing; it's the combination with a
    cross-site submit target that's the actual tell, and it's rare enough
    on genuine sites (same_registrable_domain already forgives ordinary
    subdomain-to-subdomain logins) that it's safe to escalate on directly.

    Never pushes past "suspicious" unless the URL/VT signal already agreed
    something was off — a single heuristic shouldn't be able to single-
    handedly brand an otherwise-clean site "dangerous"."""
    if not payload.cross_domain_password_form or not payload.action_domain:
        return {"label": label, "confidence": confidence, "source": source}

    page_domain = extract_domain(payload.url)
    if same_registrable_domain(page_domain, payload.action_domain):
        return {"label": label, "confidence": confidence, "source": source}

    escalated_label = "dangerous" if label in ("suspicious", "dangerous") else "suspicious"
    if _LABEL_RANK[escalated_label] > _LABEL_RANK[label]:
        escalated_confidence = 0.8 if escalated_label == "dangerous" else 0.55
        logger.info(
            "quick-check page-signal escalated %s: password form submits to %s (was %s)",
            page_domain, payload.action_domain, label,
        )
        return {"label": escalated_label, "confidence": max(confidence, escalated_confidence), "source": "page_signal"}

    return {"label": label, "confidence": confidence, "source": source}


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

    # Score the domain, not the full URL — phishing/legitimacy is a property
    # of who controls the domain, not which page on it. Scoring the full URL
    # made the model sensitive to path noise that has nothing to do with
    # that: verified 2026-08 that the exact same legitimate domain
    # (docs.python.org) scored "safe" (0.07) on one path and "dangerous"
    # (0.79-0.98) on another, purely because that path happened to contain
    # the word "login" — something almost every real site with a login page
    # also does. Scoring "https://{domain}/" instead makes the result
    # consistent for every page on a given site, and it's still fine for the
    # one scenario this loses: a legitimate domain that's been compromised
    # (or a subdomain host that's been handed to a phisher) and now serves a
    # bad page at some specific path — that's exactly what the page-signal
    # check below is for, and it looks at what the page actually does
    # instead of guessing from URL text.
    domain = extract_domain(payload.url)
    ml_result = await asyncio.to_thread(score_url, f"https://{domain}/")
    if "error" in ml_result:
        # A model-loading hiccup degrades to "unknown," never a false "safe."
        return {"label": "unknown", "confidence": 0.0, "source": "error", "detail": ml_result["error"]}

    ml_score = ml_result.get("phishing_score", 0.0)
    ml_label = _label_for_score(ml_score)

    if not get_settings().VT_API_KEY:
        return _apply_page_signal(payload, ml_label, ml_score, "ml_model")

    # Corroborate with VirusTotal either way — the domain-only model still
    # has no reputation or history, so it can be too lenient (misses a live
    # phishing site) just as easily as too harsh (flags a legitimate but
    # unusually-shaped domain, e.g. a SaaS app's subdomain). Fast (no
    # headless browser, no LLM) and cached per-domain, so this doesn't slow
    # the common case down by more than a fraction of a second after the
    # first visit.
    vt_result = await _vt_lookup_cached(domain)
    if not vt_result.get("available"):
        return _apply_page_signal(payload, ml_label, ml_score, "ml_model")

    vt_label, vt_confidence = _label_for_vt(vt_result)
    if _LABEL_RANK[vt_label] > _LABEL_RANK[ml_label]:
        logger.info(
            "quick-check escalated %s: ML said %s (%.2f), VT found %d malicious vendors",
            domain, ml_label, ml_score, vt_result.get("malicious_count", 0),
        )
        return _apply_page_signal(payload, vt_label, vt_confidence, "virustotal")

    vt_bad_count = vt_result.get("malicious_count", 0) + vt_result.get("suspicious_count", 0)
    if (
        ml_label != "safe"
        and vt_bad_count <= _VT_HARMLESS_OVERRIDE_MAX_BAD
        and vt_result.get("harmless_count", 0) >= _VT_HARMLESS_OVERRIDE_COUNT
    ):
        logger.info(
            "quick-check de-escalated %s: ML said %s (%.2f), VT found %d vendors actively vouching it's harmless (vs %d flagging it)",
            domain, ml_label, ml_score, vt_result.get("harmless_count", 0), vt_bad_count,
        )
        # Hard stop, deliberately not routed through _apply_page_signal —
        # see module docstring: strong VT consensus is the floor a single
        # page-shape heuristic isn't allowed to override.
        return {"label": "safe", "confidence": vt_result.get("reputation_score", 0.0), "source": "virustotal"}

    return _apply_page_signal(payload, ml_label, ml_score, "ml_model")
