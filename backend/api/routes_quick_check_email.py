"""
POST /quick-check-email — fast pre-check for the extension popup's
automatic "you're looking at an email" scan.

Deliberately does NOT run the full LangGraph agent (headless browser per
link, an LLM call) — same reasoning as routes_quick_check.py's URL
fast-path, just for email body text instead of a URL: this runs on
*every* popup open on a recognized webmail tab, so it needs to answer in
well under a second, not the 10-40s+ a full multi-link investigation can
take. It's a single forward pass through content_classifier's BERT text
model (ealvaradob/bert-finetuned-phishing) — the same model the full
agent's content_classifier tool uses for email/page text, called directly
instead of through the agent/tool-calling loop.

This is intentionally text-only — it says nothing about where any links
in the email actually lead (a same-day-registered lookalike domain reads
as ordinary text to a language model that's only ever seen the sentence
around it). That's exactly what "Run full scan" escalates to: the real
agent, which investigates every extracted link with inspect_website +
domain_reputation (see routes_check_email.py's _extract_links).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from api.schemas import QuickCheckEmailRequest
from tools.content_classifier import _score_text

router = APIRouter()

_DANGEROUS_THRESHOLD = 0.7
_SUSPICIOUS_THRESHOLD = 0.4


def _label_for_score(score: float) -> str:
    if score >= _DANGEROUS_THRESHOLD:
        return "dangerous"
    if score >= _SUSPICIOUS_THRESHOLD:
        return "suspicious"
    return "safe"


@router.post("/quick-check-email", tags=["Email"])
async def quick_check_email(payload: QuickCheckEmailRequest) -> dict:
    text = payload.text.strip()
    if not text:
        return {"label": "unknown", "confidence": 0.0, "source": "error", "detail": "Empty input"}

    try:
        result = await asyncio.to_thread(_score_text, text)
    except Exception as exc:  # noqa: BLE001 - a model-loading hiccup degrades to "unknown," never a false "safe"
        return {"label": "unknown", "confidence": 0.0, "source": "error", "detail": str(exc)}

    score = result["phishing_score"]
    return {"label": _label_for_score(score), "confidence": score, "source": "ml_model"}
