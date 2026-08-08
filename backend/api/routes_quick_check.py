"""
POST /quick-check-url — fast, free, local-only pre-check for the
extension's automatic per-navigation scan.

Deliberately does NOT run the full LangGraph agent (headless browser,
WHOIS/VirusTotal, an LLM call) — that takes 10-30s and costs a real API
call, which is fine for a deliberate "check this" click but not for every
single page the user navigates to. This answers in milliseconds using
three free, local, already-built signals, cheapest first:
  1. The router's 24h verdict cache (cache/sqlite_cache.py) — if a full
     investigation already ran for this exact URL, reuse it instantly.
  2. The static blocklist (cache/blocklist.py) — known-bad domains.
  3. content_classifier's URL-only ONNX model, called directly — the same
     model the full agent uses, skipping the agent/LLM loop entirely.
Never calls WHOIS/VirusTotal/OpenRouter. Not recorded to history.py —
history is for full investigations, and this runs on every navigation.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from api.schemas import QuickCheckRequest
from cache.blocklist import is_blocklisted
from cache.sqlite_cache import get_cached_verdict
from tools.content_classifier import score_url

router = APIRouter()

# Same cut-offs the web UI's phishing-probability bar uses (report.py /
# ui/index.html) — kept in sync so a score reads the same label everywhere.
_DANGEROUS_THRESHOLD = 0.7
_SUSPICIOUS_THRESHOLD = 0.4


def _label_for_score(score: float) -> str:
    if score >= _DANGEROUS_THRESHOLD:
        return "dangerous"
    if score >= _SUSPICIOUS_THRESHOLD:
        return "suspicious"
    return "safe"


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

    result = await asyncio.to_thread(score_url, payload.url)
    if "error" in result:
        # A model-loading hiccup degrades to "unknown," never a false "safe."
        return {"label": "unknown", "confidence": 0.0, "source": "error", "detail": result["error"]}

    score = result.get("phishing_score", 0.0)
    return {"label": _label_for_score(score), "confidence": score, "source": "ml_model"}
